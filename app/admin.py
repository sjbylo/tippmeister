import uuid
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_babel import gettext as _
from flask_login import login_required, current_user
from app import db, get_now, limiter
from app.models import Match, Prediction, User, AppSetting
from app.scoring import recalculate_match

admin_bp = Blueprint('admin', __name__)
log = logging.getLogger(__name__)


def admin_required(f):
	"""Decorator: require logged-in admin user."""
	from functools import wraps

	@wraps(f)
	@login_required
	def decorated(*args, **kwargs):
		if not current_user.is_admin:
			flash(_("Admin access required."), "error")
			return redirect(url_for('main.matches'))
		return f(*args, **kwargs)
	return decorated


@admin_bp.route('/')
@admin_required
def dashboard():
	now = get_now()
	scheduled = Match.query.filter_by(status='scheduled').count()
	live = Match.query.filter_by(status='live').count()
	finished = Match.query.filter_by(status='finished').count()
	auto_count = Match.query.filter_by(result_source='auto').count()
	manual_count = Match.query.filter_by(result_source='manual').count()

	time_warp = db.session.get(AppSetting, 'time_warp')
	time_warp_value = time_warp.value if time_warp and time_warp.value else ''

	api_key_set = bool(current_app.config.get('API_FOOTBALL_KEY'))

	fetch_paused_setting = db.session.get(AppSetting, 'fetch_paused')
	fetch_paused = fetch_paused_setting and fetch_paused_setting.value == 'true'

	return render_template('admin/dashboard.html',
		now=now,
		scheduled=scheduled,
		live=live,
		finished=finished,
		auto_count=auto_count,
		manual_count=manual_count,
		time_warp_value=time_warp_value,
		invite_token=current_app.config['INVITE_TOKEN'],
		api_key_set=api_key_set,
		fetch_paused=fetch_paused,
	)


@admin_bp.route('/results', methods=['GET', 'POST'])
@admin_required
@limiter.limit("30 per minute", methods=["POST"])
def results():
	if request.method == 'POST':
		match_id = request.form.get('match_id', type=int)
		match = db.session.get(Match, match_id) if match_id else None
		if not match:
			flash(_("Match not found."), "error")
			return redirect(url_for('admin.results'))

		try:
			match.team1_score = int(request.form.get('team1_score', ''))
			match.team2_score = int(request.form.get('team2_score', ''))
		except (ValueError, TypeError):
			flash(_("Please enter valid scores."), "error")
			return redirect(url_for('admin.results'))

		t1_extra = request.form.get('team1_extra', '').strip()
		t2_extra = request.form.get('team2_extra', '').strip()
		if t1_extra and t2_extra:
			try:
				match.team1_extra = int(t1_extra)
				match.team2_extra = int(t2_extra)
			except ValueError:
				flash(_("Invalid extra-time scores -- must be integers."), "error")
				return redirect(url_for('admin.results'))
		else:
			match.team1_extra = None
			match.team2_extra = None

		t1_pen = request.form.get('team1_pen', '').strip()
		t2_pen = request.form.get('team2_pen', '').strip()
		if t1_pen and t2_pen:
			try:
				match.team1_pen = int(t1_pen)
				match.team2_pen = int(t2_pen)
			except ValueError:
				flash(_("Invalid penalty scores -- must be integers."), "error")
				return redirect(url_for('admin.results'))
		else:
			match.team1_pen = None
			match.team2_pen = None

		pen_winner = request.form.get('penalty_winner', '').strip()
		match.penalty_winner = pen_winner if pen_winner else None

		match.status = 'finished'
		match.result_source = 'manual'
		db.session.commit()

		recalculate_match(match.id)
		_send_result_emails_for_match(match)
		flash(_("Result saved for Match %(num)d: %(t1)s vs %(t2)s.", num=match.match_num, t1=match.team1, t2=match.team2), "success")
		return redirect(url_for('admin.results'))

	match_list = Match.query.order_by(Match.kickoff_utc).all()
	return render_template('admin/results.html', matches=match_list)


@admin_bp.route('/predictions')
@admin_required
def all_predictions():
	now = get_now()
	filter_type = request.args.get('filter', 'today')

	from app.main import KNOCKOUT_ROUNDS, get_filter_options
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

	return render_template('admin/predictions.html',
		matches=match_list,
		users=users,
		predictions_map=predictions_map,
		now=now,
		filter_type=filter_type,
		group_names=group_names,
		knockout_rounds=knockout_rounds,
	)


@admin_bp.route('/knockout', methods=['GET', 'POST'])
@admin_required
def knockout():
	if request.method == 'POST':
		match_id = request.form.get('match_id', type=int)
		match = db.session.get(Match, match_id) if match_id else None
		if not match:
			flash(_("Match not found."), "error")
			return redirect(url_for('admin.knockout'))

		team1 = request.form.get('team1', '').strip()
		team2 = request.form.get('team2', '').strip()
		if team1:
			match.team1 = team1
		if team2:
			match.team2 = team2
		db.session.commit()
		flash(_("Updated Match %(num)d: %(t1)s vs %(t2)s.", num=match.match_num, t1=match.team1, t2=match.team2), "success")
		return redirect(url_for('admin.knockout'))

	knockout_matches = Match.query.filter_by(is_knockout=True).order_by(Match.kickoff_utc).all()
	return render_template('admin/knockout.html', matches=knockout_matches)


@admin_bp.route('/time-warp', methods=['POST'])
@admin_required
@limiter.limit("10 per minute")
def time_warp():
	warp_value = request.form.get('time_warp', '').strip()
	setting = db.session.get(AppSetting, 'time_warp')
	if not setting:
		setting = AppSetting(key='time_warp')
		db.session.add(setting)
	setting.value = warp_value if warp_value else None
	db.session.commit()

	if warp_value:
		flash(_("Time warped to: %(val)s", val=warp_value), "success")
	else:
		flash(_("Time warp cleared -- using real time."), "success")
	return redirect(url_for('admin.dashboard'))


@admin_bp.route('/regenerate-invite', methods=['POST'])
@admin_required
@limiter.limit("5 per hour")
def regenerate_invite():
	new_token = uuid.uuid4().hex
	current_app.config['INVITE_TOKEN'] = new_token
	setting = db.session.get(AppSetting, 'invite_token')
	if not setting:
		setting = AppSetting(key='invite_token')
		db.session.add(setting)
	setting.value = new_token
	db.session.commit()
	flash(_("New invite link: /register/%(token)s", token=new_token), "success")
	return redirect(url_for('admin.dashboard'))


@admin_bp.route('/toggle-fetch', methods=['POST'])
@admin_required
@limiter.limit("10 per minute")
def toggle_fetch():
	setting = db.session.get(AppSetting, 'fetch_paused')
	if not setting:
		setting = AppSetting(key='fetch_paused', value='true')
		db.session.add(setting)
	else:
		setting.value = 'false' if setting.value == 'true' else 'true'
	db.session.commit()
	state = _("paused") if setting.value == 'true' else _("resumed")
	flash(_("Auto-fetch %(state)s.", state=state), "success")
	return redirect(url_for('admin.dashboard'))


def _send_result_emails_for_match(match):
	"""Send result notification emails to all users who predicted this match."""
	from app.notifications import send_results_email

	predictions = Prediction.query.filter_by(match_id=match.id).all()
	for pred in predictions:
		user = db.session.get(User, pred.user_id)
		if user:
			try:
				send_results_email(user, match, pred.points_awarded)
			except Exception as e:
				log.warning(f"Failed to send result email to {user.email}: {e}")
