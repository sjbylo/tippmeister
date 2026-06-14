"""
World Cup 2026 results poller using ESPN's public scoreboard API.

Primary source: ESPN (live scores, real-time updates, no API key).
Fallback: worldcup26.ir (final results, no API key).

Adaptive polling: only polls when matches are near, live, or recently finished.
"""

import logging
import urllib.request
import json
import ssl

log = logging.getLogger(__name__)

ESPN_URL = 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard'
FALLBACK_URL = 'https://worldcup26.ir/get/games'

ESPN_TEAM_MAP = {
	'Czechia': 'Czech Republic',
	'Bosnia-Herzegovina': 'Bosnia & Herzegovina',
	'United States': 'USA',
	'Congo DR': 'DR Congo',
	'Türkiye': 'Turkey',
}

FALLBACK_TEAM_MAP = {
	'Bosnia and Herzegovina': 'Bosnia & Herzegovina',
	'United States': 'USA',
	'Democratic Republic of the Congo': 'DR Congo',
}


def _normalize_espn(name):
	return ESPN_TEAM_MAP.get(name, name)


def _normalize_fallback(name):
	return FALLBACK_TEAM_MAP.get(name, name)


def should_poll(app, now):
	"""Decide whether to poll based on today's match schedule."""
	from app.models import Match, AppSetting
	from app import db

	with app.app_context():
		fetch_paused = db.session.get(AppSetting, 'fetch_paused')
		if fetch_paused and fetch_paused.value == 'true':
			return False

		from datetime import timedelta
		day_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=14)
		day_end = now.replace(hour=23, minute=59, second=59) + timedelta(hours=12)

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
				if -7200 < diff < 1800:
					return True
				if m.status == 'scheduled' and -10800 < diff < 0:
					return True

		unfinished = [m for m in todays_matches if m.status != 'finished']
		return len(unfinished) > 0


def _find_match(home, away, Match):
	"""Find a match by team names, trying both orderings."""
	m = Match.query.filter_by(team1=home, team2=away).first()
	if m:
		return m, False
	m = Match.query.filter_by(team1=away, team2=home).first()
	if m:
		return m, True
	return None, False


def _http_get_json(url, timeout=15):
	"""Fetch JSON from a URL."""
	ctx = ssl.create_default_context()
	req = urllib.request.Request(url)
	resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
	return json.loads(resp.read())


def fetch_and_update(app):
	"""Poll ESPN for live scores and results. Falls back to worldcup26.ir."""
	from app import db, get_now
	from app.models import Match
	from app.scoring import recalculate_match

	with app.app_context():
		now = get_now()
		if not should_poll(app, now):
			return

		updated = 0

		try:
			updated = _fetch_espn(db, Match, recalculate_match)
		except Exception as e:
			log.warning(f"ESPN fetch failed ({e}), trying fallback...")
			try:
				updated = _fetch_fallback(db, Match, recalculate_match)
			except Exception as e2:
				log.error(f"Fallback also failed: {e2}")

		if updated:
			log.info(f"Updated {updated} match(es)")


def _fetch_espn(db, Match, recalculate_match):
	"""Fetch from ESPN scoreboard API (default + today + yesterday to catch all matches)."""
	from datetime import datetime, timezone, timedelta

	all_events = []
	seen_ids = set()

	data = _http_get_json(ESPN_URL)
	for e in data.get('events', []):
		seen_ids.add(e['id'])
		all_events.append(e)

	now = datetime.now(timezone.utc)
	for day_offset in (0, -1):
		day = (now + timedelta(days=day_offset)).strftime('%Y%m%d')
		day_data = _http_get_json(f"{ESPN_URL}?dates={day}")
		for e in day_data.get('events', []):
			if e['id'] not in seen_ids:
				seen_ids.add(e['id'])
				all_events.append(e)

	log.info(f"ESPN returned {len(all_events)} events (default + today/yesterday)")

	updated = 0
	for event in all_events:
		if _process_espn_event(event, db, Match, recalculate_match):
			updated += 1

	if updated:
		db.session.commit()
	return updated


def _process_espn_event(event, db, Match, recalculate_match):
	"""Process a single ESPN event."""
	comps = event.get('competitions', [])
	if not comps:
		return False

	comp = comps[0]
	competitors = comp.get('competitors', [])
	if len(competitors) != 2:
		return False

	home_team = None
	away_team = None
	home_score = None
	away_score = None

	for c in competitors:
		team_name = _normalize_espn(c.get('team', {}).get('displayName', ''))
		score = c.get('score')
		try:
			score = int(score) if score else None
		except (ValueError, TypeError):
			score = None

		if c.get('homeAway') == 'home':
			home_team = team_name
			home_score = score
		else:
			away_team = team_name
			away_score = score

	if not home_team or not away_team:
		return False

	match, reversed_order = _find_match(home_team, away_team, Match)
	if not match:
		return False

	if match.status == 'finished' and match.result_source == 'manual':
		return False

	if home_score is None or away_score is None:
		return False

	if reversed_order:
		home_score, away_score = away_score, home_score

	status_type = event.get('status', {}).get('type', {}).get('name', '')

	LIVE_STATUSES = {
		'STATUS_IN_PROGRESS', 'STATUS_FIRST_HALF', 'STATUS_SECOND_HALF',
		'STATUS_HALFTIME', 'STATUS_EXTRA_TIME', 'STATUS_PENALTIES',
	}
	FINAL_STATUSES = {'STATUS_FINAL', 'STATUS_FULL_TIME'}

	if status_type in LIVE_STATUSES and match.status != 'finished':
		match.status = 'live'
		match.team1_score = home_score
		match.team2_score = away_score
		return True

	elif status_type in FINAL_STATUSES and match.status != 'finished':
		match.status = 'finished'
		match.result_source = 'auto'
		match.team1_score = home_score
		match.team2_score = away_score
		db.session.commit()
		recalculate_match(match.id)
		_send_match_result_notifications(match)
		log.info(
			f"Auto-imported result: Match {match.match_num} "
			f"{match.team1} {home_score}-{away_score} {match.team2}"
		)
		return True

	return False


def _fetch_fallback(db, Match, recalculate_match):
	"""Fetch from worldcup26.ir as fallback."""
	data = _http_get_json(FALLBACK_URL)
	games = data.get('games', [])
	log.info(f"worldcup26.ir returned {len(games)} games (fallback)")

	updated = 0
	for game in games:
		if _process_fallback_game(game, db, Match, recalculate_match):
			updated += 1

	if updated:
		db.session.commit()
	return updated


def _process_fallback_game(game, db, Match, recalculate_match):
	"""Process a single game from worldcup26.ir."""
	home_name = _normalize_fallback(game.get('home_team_name_en', ''))
	away_name = _normalize_fallback(game.get('away_team_name_en', ''))

	if not home_name or not away_name:
		return False

	match, reversed_order = _find_match(home_name, away_name, Match)
	if not match:
		return False

	if match.status == 'finished' and match.result_source == 'manual':
		return False

	finished = game.get('finished', '').upper() == 'TRUE'
	home_score = game.get('home_score')
	away_score = game.get('away_score')

	try:
		home_score = int(home_score) if home_score and home_score != 'null' else None
		away_score = int(away_score) if away_score and away_score != 'null' else None
	except (ValueError, TypeError):
		return False

	if home_score is None or away_score is None:
		return False

	if reversed_order:
		home_score, away_score = away_score, home_score

	if finished and match.status != 'finished':
		match.status = 'finished'
		match.result_source = 'auto'
		match.team1_score = home_score
		match.team2_score = away_score
		db.session.commit()
		recalculate_match(match.id)
		_send_match_result_notifications(match)
		log.info(
			f"Auto-imported result (fallback): Match {match.match_num} "
			f"{match.team1} {home_score}-{away_score} {match.team2}"
		)
		return True

	return False


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


def setup_scheduler(app):
	"""Configure APScheduler to poll for match results."""
	from apscheduler.schedulers.background import BackgroundScheduler

	scheduler = BackgroundScheduler()
	scheduler.add_job(
		func=fetch_and_update,
		args=[app],
		trigger='interval',
		minutes=5,
		id='worldcup_poller',
		replace_existing=True,
	)
	scheduler.start()
	log.info("World Cup results scheduler started (ESPN primary, polling every 5 min during matches)")
	return scheduler
