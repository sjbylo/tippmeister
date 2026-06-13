from datetime import timedelta, datetime
import pytz
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, make_response, jsonify
from flask_babel import gettext as _
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db, get_now
from app.models import Match, Prediction, User

main_bp = Blueprint('main', __name__)


@main_bp.route('/app-version')
def app_version():
	"""Lightweight endpoint for client-side version check."""
	from flask import current_app
	return jsonify(v=current_app.jinja_env.globals.get('cache_bust', 0))

KNOCKOUT_ROUNDS = (
	'Round of 32', 'Round of 16', 'Quarter-final',
	'Semi-final', 'Match for third place', 'Final'
)

def translate_round(round_name):
	"""Translate a knockout round name stored in the DB."""
	mapping = {
		'Round of 32': _('Round of 32'),
		'Round of 16': _('Round of 16'),
		'Quarter-final': _('Quarter-final'),
		'Semi-final': _('Semi-final'),
		'Match for third place': _('Match for third place'),
		'Final': _('Final'),
	}
	return mapping.get(round_name, round_name)


def _user_today_utc_bounds(now):
	"""Return (start, end) of the user's local 'today' as naive UTC datetimes."""
	tz_name = getattr(current_user, 'timezone', None) or 'UTC'
	try:
		tz = pytz.timezone(tz_name)
	except pytz.UnknownTimeZoneError:
		tz = pytz.UTC
	# Convert naive UTC 'now' to the user's local time to find their calendar date
	utc_now = pytz.utc.localize(now)
	local_now = utc_now.astimezone(tz)
	local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
	local_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
	# Convert back to naive UTC for DB queries
	return local_start.astimezone(pytz.utc).replace(tzinfo=None), \
		   local_end.astimezone(pytz.utc).replace(tzinfo=None)


def _filter_matches(filter_type, now):
	"""Apply match filter and return (match_list, resolved_filter_type)."""
	if filter_type == 'today':
		today_start, today_end = _user_today_utc_bounds(now)
		match_list = Match.query.filter(
			Match.kickoff_utc >= today_start,
			Match.kickoff_utc <= today_end
		).order_by(Match.kickoff_utc).all()
		if match_list:
			return match_list, 'today'
		# Smart fallback: try 3d, 7d, then all upcoming
		for fallback, days in [('3d', 3), ('7d', 7)]:
			cutoff = now + timedelta(days=days)
			match_list = Match.query.filter(
				Match.kickoff_utc > now, Match.kickoff_utc <= cutoff
			).order_by(Match.kickoff_utc).all()
			if match_list:
				return match_list, fallback
		match_list = Match.query.filter(
			Match.kickoff_utc > now
		).order_by(Match.kickoff_utc).limit(12).all()
		if match_list:
			return match_list, 'next'
		return [], 'today'
	elif filter_type == '3d':
		cutoff = now + timedelta(days=3)
		match_list = Match.query.filter(
			Match.kickoff_utc > now, Match.kickoff_utc <= cutoff
		).order_by(Match.kickoff_utc).all()
	elif filter_type == '7d':
		cutoff = now + timedelta(days=7)
		match_list = Match.query.filter(
			Match.kickoff_utc > now, Match.kickoff_utc <= cutoff
		).order_by(Match.kickoff_utc).all()
	elif filter_type == 'past':
		match_list = Match.query.filter(
			Match.kickoff_utc <= now
		).order_by(Match.kickoff_utc.desc()).all()
	elif filter_type == 'missing':
		predicted_ids = db.session.query(Prediction.match_id).filter(
			Prediction.user_id == current_user.id,
			Prediction.team1_score.isnot(None),
		).subquery()
		match_list = Match.query.filter(
			Match.kickoff_utc > now,
			Match.id.notin_(predicted_ids),
		).order_by(Match.kickoff_utc).all()
		match_list = [m for m in match_list if m.has_known_teams]
	elif filter_type == 'all':
		match_list = Match.query.order_by(Match.kickoff_utc).all()
	elif filter_type.startswith('Group'):
		match_list = Match.query.filter_by(group_name=filter_type).order_by(Match.kickoff_utc).all()
	elif filter_type in KNOCKOUT_ROUNDS:
		match_list = Match.query.filter_by(round=filter_type).order_by(Match.kickoff_utc).all()
	else:
		match_list = Match.query.order_by(Match.kickoff_utc).all()
	return match_list, filter_type


def _get_filter(page_name):
	"""Get filter from query param, falling back to cookie."""
	f = request.args.get('filter')
	if f:
		return f
	return request.cookies.get(f'filter_{page_name}', 'today')


def _set_filter_cookie(response, page_name, filter_type):
	"""Save the user's filter choice in a cookie."""
	response.set_cookie(f'filter_{page_name}', filter_type, max_age=60*60*24*90)
	return response


def load_predictions_map(match_list):
	"""Load all predictions for given matches into a {match_id: {user_id: pred}} dict."""
	if not match_list:
		return {}
	match_ids = [m.id for m in match_list]
	all_preds = Prediction.query.filter(Prediction.match_id.in_(match_ids)).all()
	pmap = {}
	for p in all_preds:
		pmap.setdefault(p.match_id, {})[p.user_id] = p
	return pmap


def _get_untipped_count(now):
	"""Count upcoming matches with known teams that the user hasn't tipped."""
	upcoming = Match.query.filter(Match.kickoff_utc > now).all()
	upcoming_known = [m for m in upcoming if m.has_known_teams]
	if not upcoming_known:
		return 0
	match_ids = [m.id for m in upcoming_known]
	tipped_ids = set(
		p.match_id for p in Prediction.query.filter(
			Prediction.user_id == current_user.id,
			Prediction.match_id.in_(match_ids),
			Prediction.team1_score.isnot(None),
		).all()
	)
	return len(match_ids) - len(tipped_ids)


def get_filter_options():
	"""Build the list of available filter tabs."""
	groups = db.session.query(Match.group_name).filter(
		Match.group_name != '', Match.group_name.isnot(None)
	).distinct().order_by(Match.group_name).all()
	group_names = [g[0] for g in groups]

	rounds = db.session.query(Match.round).filter(
		Match.round.in_(KNOCKOUT_ROUNDS)
	).distinct().all()
	knockout_rounds = [r[0] for r in rounds if r[0] in KNOCKOUT_ROUNDS]
	knockout_rounds.sort(key=lambda r: KNOCKOUT_ROUNDS.index(r))

	return group_names, knockout_rounds


@main_bp.route('/')
def index():
	if current_user.is_authenticated:
		return redirect(url_for('main.matches'))
	return redirect(url_for('auth.login'))


@main_bp.route('/rules')
@login_required
def rules():
	return render_template('rules.html')


@main_bp.route('/matches')
@login_required
def matches():
	now = get_now()
	filter_type = _get_filter('matches')
	group_names, knockout_rounds = get_filter_options()

	match_list, filter_type = _filter_matches(filter_type, now)

	users = User.query.order_by(User.display_name).all()
	predictions_map = load_predictions_map(match_list)

	untipped_count = _get_untipped_count(now)

	resp = make_response(render_template('matches.html',
		matches=match_list,
		users=users,
		predictions_map=predictions_map,
		now=now,
		filter_type=filter_type,
		group_names=group_names,
		knockout_rounds=knockout_rounds,
		untipped_count=untipped_count,
	))
	return _set_filter_cookie(resp, 'matches', filter_type)


@main_bp.route('/grid')
@login_required
def grid():
	now = get_now()
	filter_type = _get_filter('grid')
	group_names, knockout_rounds = get_filter_options()

	match_list, filter_type = _filter_matches(filter_type, now)

	other_users = User.query.filter(User.id != current_user.id).order_by(User.display_name).all()
	users = [current_user] + other_users
	predictions_map = load_predictions_map(match_list)

	resp = make_response(render_template('grid.html',
		matches=match_list,
		users=users,
		predictions_map=predictions_map,
		now=now,
		filter_type=filter_type,
		group_names=group_names,
		knockout_rounds=knockout_rounds,
	))
	return _set_filter_cookie(resp, 'grid', filter_type)


@main_bp.route('/predict/<int:match_id>', methods=['POST'])
@login_required
def predict_single(match_id):
	"""AJAX endpoint: save a single prediction, return JSON."""
	now = get_now()

	match = db.session.get(Match, match_id)
	if not match:
		return jsonify(success=False, error=_("Match not found.")), 404
	if match.kickoff_utc and match.kickoff_utc <= now:
		return jsonify(success=False, error=_("Match has already started.")), 400
	if not match.has_known_teams:
		return jsonify(success=False, error=_("Teams not yet determined.")), 400

	data = request.get_json(silent=True) or {}
	t1_val = data.get('team1_score')
	t2_val = data.get('team2_score')
	pen_val = data.get('penalty_winner', '')

	if t1_val is None or t2_val is None:
		return jsonify(success=False, error=_("Please enter valid scores.")), 400

	try:
		t1 = int(t1_val)
		t2 = int(t2_val)
	except (ValueError, TypeError):
		return jsonify(success=False, error=_("Please enter valid scores.")), 400

	if t1 < 0 or t2 < 0 or t1 > 99 or t2 > 99:
		return jsonify(success=False, error=_("Scores must be between 0 and 99.")), 400

	pred = Prediction.query.filter_by(
		user_id=current_user.id, match_id=match_id
	).first()
	if not pred:
		pred = Prediction(user_id=current_user.id, match_id=match_id)
		db.session.add(pred)

	pred.team1_score = t1
	pred.team2_score = t2

	if match.is_knockout and t1 == t2:
		if pen_val in (match.team1, match.team2):
			pred.penalty_winner = pen_val
		else:
			return jsonify(success=False, error=_("Draw in knockout requires a penalty winner.")), 400
	else:
		pred.penalty_winner = None

	db.session.commit()
	return jsonify(success=True, score_display=pred.score_display)


@main_bp.route('/predictions', methods=['GET', 'POST'])
@login_required
def predictions():
	now = get_now()

	if request.method == 'POST':
		saved = 0
		for key, val in request.form.items():
			if not key.startswith('t1_'):
				continue
			match_id_str = key.replace('t1_', '')
			try:
				match_id = int(match_id_str)
			except ValueError:
				continue

			t1_val = request.form.get(f't1_{match_id}', '').strip()
			t2_val = request.form.get(f't2_{match_id}', '').strip()
			pen_val = request.form.get(f'pen_{match_id}', '').strip()

			if not t1_val and not t2_val:
				continue

			match = db.session.get(Match, match_id)
			if not match or (match.kickoff_utc and match.kickoff_utc <= now):
				continue

			try:
				t1 = int(t1_val)
				t2 = int(t2_val)
			except (ValueError, TypeError):
				continue

			if t1 < 0 or t2 < 0 or t1 > 99 or t2 > 99:
				continue

			pred = Prediction.query.filter_by(
				user_id=current_user.id, match_id=match_id
			).first()

			if not pred:
				pred = Prediction(user_id=current_user.id, match_id=match_id)
				db.session.add(pred)

			pred.team1_score = t1
			pred.team2_score = t2

			if match.is_knockout and t1 == t2:
				if pen_val in (match.team1, match.team2):
					pred.penalty_winner = pen_val
				else:
					flash(_("Match %(num)d: draw in knockout requires a penalty winner.", num=match.match_num), "error")
					continue
			else:
				pred.penalty_winner = None

			saved += 1

		db.session.commit()
		flash(_("Saved %(count)d prediction(s).", count=saved), "success")
		return redirect(url_for('main.predictions'))

	upcoming = [m for m in Match.query.filter(
		Match.kickoff_utc > now
	).order_by(Match.kickoff_utc).all() if m.has_known_teams]

	user_preds = {}
	if upcoming:
		match_ids = [m.id for m in upcoming]
		preds = Prediction.query.filter(
			Prediction.user_id == current_user.id,
			Prediction.match_id.in_(match_ids)
		).all()
		for p in preds:
			user_preds[p.match_id] = p

	unpredicted = [m for m in upcoming if m.id not in user_preds]
	predicted = [m for m in upcoming if m.id in user_preds]

	return render_template('predictions.html',
		unpredicted=unpredicted,
		predicted=predicted,
		user_preds=user_preds,
		now=now,
	)


@main_bp.route('/leaderboard')
@login_required
def leaderboard():
	scores = db.session.query(
		User.id,
		User.display_name,
		func.coalesce(func.sum(Prediction.points_awarded), 0).label('total_points'),
		func.count(Prediction.id).label('predictions_made'),
	).outerjoin(Prediction, User.id == Prediction.user_id).group_by(
		User.id
	).order_by(func.sum(Prediction.points_awarded).desc()).all()

	return render_template('leaderboard.html', scores=scores)
