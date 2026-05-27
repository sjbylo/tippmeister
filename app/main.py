from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_babel import gettext as _
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db, get_now
from app.models import Match, Prediction, User

main_bp = Blueprint('main', __name__)

KNOCKOUT_ROUNDS = (
	'Round of 32', 'Round of 16', 'Quarter-final',
	'Semi-final', 'Match for third place', 'Final'
)


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
	filter_type = request.args.get('filter', 'today')

	group_names, knockout_rounds = get_filter_options()

	if filter_type == 'today':
		today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
		today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
		match_list = Match.query.filter(
			Match.kickoff_utc >= today_start,
			Match.kickoff_utc <= today_end
		).order_by(Match.kickoff_utc).all()
		if not match_list:
			match_list = Match.query.filter(
				Match.kickoff_utc > now
			).order_by(Match.kickoff_utc).limit(12).all()
			if match_list:
				filter_type = 'next'
	elif filter_type == 'all':
		match_list = Match.query.order_by(Match.kickoff_utc).all()
	elif filter_type.startswith('Group'):
		match_list = Match.query.filter_by(group_name=filter_type).order_by(Match.kickoff_utc).all()
	elif filter_type in KNOCKOUT_ROUNDS:
		match_list = Match.query.filter_by(round=filter_type).order_by(Match.kickoff_utc).all()
	else:
		match_list = Match.query.order_by(Match.kickoff_utc).limit(12).all()

	users = User.query.order_by(User.display_name).all()

	predictions_map = {}
	if match_list:
		match_ids = [m.id for m in match_list]
		all_preds = Prediction.query.filter(Prediction.match_id.in_(match_ids)).all()
		for p in all_preds:
			predictions_map.setdefault(p.match_id, {})[p.user_id] = p

	return render_template('matches.html',
		matches=match_list,
		users=users,
		predictions_map=predictions_map,
		now=now,
		filter_type=filter_type,
		group_names=group_names,
		knockout_rounds=knockout_rounds,
	)


@main_bp.route('/grid')
@login_required
def grid():
	now = get_now()
	filter_type = request.args.get('filter', 'today')
	group_names, knockout_rounds = get_filter_options()

	if filter_type == 'today':
		today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
		today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
		match_list = Match.query.filter(
			Match.kickoff_utc >= today_start,
			Match.kickoff_utc <= today_end
		).order_by(Match.kickoff_utc).all()
		if not match_list:
			match_list = Match.query.filter(
				Match.kickoff_utc > now
			).order_by(Match.kickoff_utc).limit(12).all()
			if match_list:
				filter_type = 'next'
	elif filter_type == 'all':
		match_list = Match.query.order_by(Match.kickoff_utc).all()
	elif filter_type.startswith('Group'):
		match_list = Match.query.filter_by(group_name=filter_type).order_by(Match.kickoff_utc).all()
	elif filter_type in KNOCKOUT_ROUNDS:
		match_list = Match.query.filter_by(round=filter_type).order_by(Match.kickoff_utc).all()
	else:
		match_list = Match.query.order_by(Match.kickoff_utc).all()

	users = User.query.order_by(User.display_name).all()

	predictions_map = {}
	if match_list:
		match_ids = [m.id for m in match_list]
		all_preds = Prediction.query.filter(Prediction.match_id.in_(match_ids)).all()
		for p in all_preds:
			predictions_map.setdefault(p.match_id, {})[p.user_id] = p

	return render_template('grid.html',
		matches=match_list,
		users=users,
		predictions_map=predictions_map,
		now=now,
		filter_type=filter_type,
		group_names=group_names,
		knockout_rounds=knockout_rounds,
	)


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

	return render_template('predictions.html',
		matches=upcoming,
		user_preds=user_preds,
		now=now,
	)


@main_bp.route('/leaderboard')
@login_required
def leaderboard():
	default_top = current_app.config.get('LEADERBOARD_TOP_N', 10)
	top_n = request.args.get('top', default=default_top, type=int)

	scores = db.session.query(
		User.id,
		User.display_name,
		func.coalesce(func.sum(Prediction.points_awarded), 0).label('total_points'),
		func.count(Prediction.id).label('predictions_made'),
	).outerjoin(Prediction, User.id == Prediction.user_id).group_by(
		User.id
	).order_by(func.sum(Prediction.points_awarded).desc()).all()

	if top_n > 0:
		scores = scores[:top_n]

	return render_template('leaderboard.html', scores=scores, top_n=top_n)
