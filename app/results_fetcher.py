"""
Smart API-Football poller for auto-importing match results.

Adaptive polling: only polls when matches are near, live, or recently finished.
Budget: ~48 requests on a busy 4-match day (well within 100/day free tier).
"""

import logging
import requests as http_requests

log = logging.getLogger(__name__)

API_BASE = 'https://v3.football.api-sports.io'


def should_poll(app, now):
	"""Decide whether to poll based on today's match schedule."""
	from app.models import Match, AppSetting
	from app import db

	with app.app_context():
		fetch_paused = db.session.get(AppSetting, 'fetch_paused')
		if fetch_paused and fetch_paused.value == 'true':
			return False

		if not app.config.get('API_FOOTBALL_KEY'):
			return False

		day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
		day_end = now.replace(hour=23, minute=59, second=59)

		todays_matches = Match.query.filter(
			Match.kickoff_utc >= day_start,
			Match.kickoff_utc <= day_end,
		).all()

		if not todays_matches:
			return False

		for m in todays_matches:
			if m.status == 'live':
				return True
			if m.kickoff_utc:
				diff = (m.kickoff_utc - now).total_seconds()
				# 30 min before kickoff
				if -7200 < diff < 1800:
					return True
				# Up to 3 hours after kickoff (covers ET + penalties)
				if m.status == 'scheduled' and -10800 < diff < 0:
					return True

		unfinished = [m for m in todays_matches if m.status != 'finished']
		return len(unfinished) > 0


def fetch_and_update(app):
	"""Poll API-Football and update match results."""
	from app import db, get_now
	from app.models import Match
	from app.scoring import recalculate_match

	with app.app_context():
		now = get_now()
		if not should_poll(app, now):
			return

		api_key = app.config.get('API_FOOTBALL_KEY')
		if not api_key:
			return

		try:
			headers = {'x-apisports-key': api_key}
			params = {
				'league': app.config.get('API_FOOTBALL_LEAGUE_ID', 1),
				'season': app.config.get('API_FOOTBALL_SEASON', 2026),
			}

			resp = http_requests.get(
				f'{API_BASE}/fixtures', headers=headers, params=params, timeout=15
			)
			resp.raise_for_status()
			data = resp.json()

			fixtures = data.get('response', [])
			log.info(f"API-Football returned {len(fixtures)} fixtures")

			for fixture in fixtures:
				_process_fixture(fixture, db, Match, recalculate_match)

			db.session.commit()

		except http_requests.RequestException as e:
			log.error(f"API-Football request failed: {e}")
		except Exception as e:
			log.error(f"Error processing API-Football data: {e}")


def _process_fixture(fixture, db, Match, recalculate_match):
	"""Process a single API-Football fixture response."""
	fixture_info = fixture.get('fixture', {})
	teams = fixture.get('teams', {})
	goals = fixture.get('goals', {})
	score_data = fixture.get('score', {})
	fixture_id = fixture_info.get('id')
	status_short = fixture_info.get('status', {}).get('short', '')

	match = None
	if fixture_id:
		match = Match.query.filter_by(api_fixture_id=fixture_id).first()

	if not match:
		match = _find_match_by_teams_and_date(fixture, db.session)

	if not match:
		return

	if not match.api_fixture_id:
		match.api_fixture_id = fixture_id

	if status_short in ('1H', 'HT', '2H', 'ET', 'P', 'BT', 'LIVE'):
		match.status = 'live'
		home_goals = goals.get('home')
		away_goals = goals.get('away')
		if home_goals is not None and away_goals is not None:
			match.team1_score = home_goals
			match.team2_score = away_goals

	elif status_short in ('FT', 'AET', 'PEN'):
		match.status = 'finished'
		match.result_source = 'auto'

		ft = score_data.get('fulltime', {})
		match.team1_score = ft.get('home')
		match.team2_score = ft.get('away')

		et = score_data.get('extratime', {})
		if et.get('home') is not None:
			match.team1_extra = et['home']
			match.team2_extra = et.get('away')

		pen = score_data.get('penalty', {})
		if pen.get('home') is not None:
			match.team1_pen = pen['home']
			match.team2_pen = pen.get('away')
			if pen['home'] > pen.get('away', 0):
				match.penalty_winner = match.team1
			else:
				match.penalty_winner = match.team2

		db.session.commit()
		recalculate_match(match.id)
		_send_match_result_notifications(match)
		log.info(
			f"Auto-imported result: Match {match.match_num} "
			f"{match.team1} {match.score_display} {match.team2}"
		)


def _send_match_result_notifications(match):
	"""Send result notification emails to all users who predicted this match."""
	from app import db
	from app.models import User, Prediction
	from app.notifications import send_results_email

	predictions = Prediction.query.filter_by(match_id=match.id).all()
	for pred in predictions:
		user = db.session.get(User, pred.user_id)
		if user:
			try:
				send_results_email(user, match, pred.points_awarded)
			except Exception as e:
				log.warning(f"Failed to send result email to {user.email}: {e}")


def _find_match_by_teams_and_date(fixture, session):
	"""Try to match an API fixture to a DB match by team names and date."""
	from app.models import Match
	from datetime import datetime, timezone

	teams = fixture.get('teams', {})
	home_name = teams.get('home', {}).get('name', '')
	away_name = teams.get('away', {}).get('name', '')
	fixture_date = fixture.get('fixture', {}).get('date', '')

	if not home_name or not away_name:
		return None

	candidates = Match.query.filter(
		Match.team1.ilike(f'%{home_name[:10]}%'),
		Match.team2.ilike(f'%{away_name[:10]}%'),
	).all()

	if len(candidates) == 1:
		return candidates[0]

	if fixture_date:
		try:
			from dateutil import parser
			api_dt = parser.isoparse(fixture_date).replace(tzinfo=timezone.utc)
			for c in candidates:
				if c.kickoff_utc and abs((c.kickoff_utc - api_dt).total_seconds()) < 7200:
					return c
		except Exception:
			pass

	return None


def setup_scheduler(app):
	"""Configure APScheduler to poll API-Football on an interval."""
	if not app.config.get('API_FOOTBALL_KEY'):
		log.info("No API_FOOTBALL_KEY set -- auto-fetch disabled")
		return None

	from apscheduler.schedulers.background import BackgroundScheduler

	scheduler = BackgroundScheduler()
	scheduler.add_job(
		func=fetch_and_update,
		args=[app],
		trigger='interval',
		minutes=10,
		id='api_football_poller',
		replace_existing=True,
	)
	scheduler.start()
	log.info("API-Football scheduler started (polling every 10 minutes)")
	return scheduler
