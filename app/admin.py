import uuid
import logging
import threading
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

		now = get_now()
		if match.kickoff_utc and match.kickoff_utc > now:
			flash(_("Cannot enter results for a match that hasn't started yet."), "error")
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
	return render_template('admin/results.html', matches=match_list, now=get_now())


@admin_bp.route('/clear-result', methods=['POST'])
@admin_required
@limiter.limit("30 per minute")
def clear_result():
	match_id = request.form.get('match_id', type=int)
	match = db.session.get(Match, match_id) if match_id else None
	if not match:
		flash(_("Match not found."), "error")
		return redirect(url_for('admin.results'))

	match.team1_score = None
	match.team2_score = None
	match.team1_extra = None
	match.team2_extra = None
	match.team1_pen = None
	match.team2_pen = None
	match.penalty_winner = None
	match.status = 'scheduled'
	match.result_source = None

	preds = Prediction.query.filter_by(match_id=match.id).all()
	for pred in preds:
		pred.points_awarded = 0

	db.session.commit()
	flash(_("Result cleared for Match %(num)d: %(t1)s vs %(t2)s.", num=match.match_num, t1=match.team1, t2=match.team2), "success")
	return redirect(url_for('admin.results'))


@admin_bp.route('/predictions')
@admin_required
def all_predictions():
	now = get_now()
	filter_type = request.args.get('filter', 'today')

	from app.main import get_filter_options, _filter_matches, load_predictions_map
	group_names, knockout_rounds = get_filter_options()

	match_list, filter_type = _filter_matches(filter_type, now)

	other_users = User.query.filter(User.id != current_user.id).order_by(User.display_name).all()
	users = [current_user] + other_users
	predictions_map = load_predictions_map(match_list)

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
		if team1 and team2 and team1 == team2:
			flash(_("Team 1 and Team 2 cannot be the same!"), "error")
			return redirect(url_for('admin.knockout'))
		if team1:
			match.team1 = team1
		if team2:
			match.team2 = team2
		db.session.commit()
		flash(_("Updated Match %(num)d: %(t1)s vs %(t2)s.", num=match.match_num, t1=match.team1, t2=match.team2), "success")
		return redirect(url_for('admin.knockout'))

	knockout_matches = Match.query.filter_by(is_knockout=True).order_by(Match.kickoff_utc).all()

	placeholders = {'TBD', ''}
	team_names = sorted(set(
		row[0] for row in
		db.session.query(Match.team1).distinct().all() +
		db.session.query(Match.team2).distinct().all()
		if row[0] and row[0] not in placeholders
	))

	return render_template('admin/knockout.html', matches=knockout_matches, team_names=team_names)


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


@admin_bp.route('/edit-prediction', methods=['GET', 'POST'])
@admin_required
@limiter.limit("30 per minute", methods=["POST"])
def edit_prediction():
	user_id = request.args.get('user_id', type=int) or request.form.get('user_id', type=int)
	match_id = request.args.get('match_id', type=int) or request.form.get('match_id', type=int)

	user = db.session.get(User, user_id) if user_id else None
	match = db.session.get(Match, match_id) if match_id else None

	if not user or not match:
		flash(_("Match not found."), "error")
		return redirect(url_for('admin.all_predictions'))

	pred = Prediction.query.filter_by(user_id=user.id, match_id=match.id).first()

	if request.method == 'POST':
		t1_val = request.form.get('team1_score', '').strip()
		t2_val = request.form.get('team2_score', '').strip()

		if t1_val == '' and t2_val == '':
			if pred:
				db.session.delete(pred)
				db.session.commit()
				flash(_("Prediction deleted."), "success")
			return redirect(url_for('admin.all_predictions', filter=request.args.get('filter', 'all')))

		try:
			t1 = int(t1_val)
			t2 = int(t2_val)
		except (ValueError, TypeError):
			flash(_("Please enter valid scores."), "error")
			return redirect(url_for('admin.edit_prediction', user_id=user.id, match_id=match.id))

		if not pred:
			pred = Prediction(user_id=user.id, match_id=match.id)
			db.session.add(pred)

		pred.team1_score = t1
		pred.team2_score = t2

		pen_val = request.form.get('penalty_winner', '').strip()
		if match.is_knockout and t1 == t2:
			pred.penalty_winner = pen_val if pen_val in (match.team1, match.team2) else None
		else:
			pred.penalty_winner = None

		db.session.commit()

		if match.status == 'finished':
			recalculate_match(match.id)

		flash(_("Prediction updated for %(user)s.", user=user.display_name), "success")
		return redirect(url_for('admin.all_predictions', filter=request.args.get('filter', 'all')))

	return render_template('admin/edit_prediction.html',
		user=user,
		match=match,
		pred=pred,
	)


@admin_bp.route('/users')
@admin_required
def users():
	all_users = User.query.order_by(User.created_at).all()
	return render_template('admin/users.html', users=all_users)


@admin_bp.route('/edit-user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
@limiter.limit("30 per minute", methods=["POST"])
def edit_user(user_id):
	user = db.session.get(User, user_id)
	if not user:
		flash(_("User not found."), "error")
		return redirect(url_for('admin.users'))

	if request.method == 'POST':
		action = request.form.get('action', '')

		if action == 'update':
			new_name = request.form.get('display_name', '').strip()
			new_email = request.form.get('email', '').strip().lower()
			new_tz = request.form.get('timezone', '').strip()
			new_lang = request.form.get('language', 'en')
			is_admin = request.form.get('is_admin') == '1'

			if new_email and new_email != user.email:
				if User.query.filter_by(email=new_email).first():
					flash(_("That email is already registered."), "error")
					return redirect(url_for('admin.edit_user', user_id=user.id))
				user.email = new_email

			if new_name and new_name != user.display_name:
				existing = User.query.filter(
					db.func.lower(User.display_name) == new_name.lower(),
					User.id != user.id
				).first()
				if existing:
					flash(_("That display name is already taken."), "error")
					return redirect(url_for('admin.edit_user', user_id=user.id))
				user.display_name = new_name

			user.timezone = new_tz or user.timezone
			user.language = new_lang
			user.is_admin = is_admin
			db.session.commit()
			flash(_("User %(name)s updated.", name=user.display_name), "success")

		elif action == 'reset_password':
			new_pw = request.form.get('new_password', '').strip()
			if len(new_pw) < 8:
				flash(_("Password must be at least 8 characters."), "error")
				return redirect(url_for('admin.edit_user', user_id=user.id))
			user.set_password(new_pw)
			db.session.commit()
			flash(_("Password reset for %(name)s.", name=user.display_name), "success")

		elif action == 'delete':
			if user.id == current_user.id:
				flash(_("You cannot delete yourself."), "error")
				return redirect(url_for('admin.edit_user', user_id=user.id))
			name = user.display_name
			Prediction.query.filter_by(user_id=user.id).delete()
			db.session.delete(user)
			db.session.commit()
			flash(_("User %(name)s deleted.", name=name), "success")
			return redirect(url_for('admin.users'))

		return redirect(url_for('admin.edit_user', user_id=user.id))

	import pytz
	timezones = sorted(pytz.common_timezones)
	pred_count = Prediction.query.filter_by(user_id=user.id).count()
	return render_template('admin/edit_user.html', user=user, timezones=timezones, pred_count=pred_count)


def _send_result_emails_for_match(match):
	"""Send result notification emails in background so admin gets instant response."""
	app = current_app._get_current_object()
	match_id = match.id

	def _send_in_background():
		with app.app_context():
			from app.notifications import send_results_email
			m = db.session.get(Match, match_id)
			if not m:
				return
			predictions = Prediction.query.filter_by(match_id=match_id).all()
			for pred in predictions:
				user = db.session.get(User, pred.user_id)
				if user:
					try:
						send_results_email(user, m, pred.points_awarded)
					except Exception as e:
						log.warning(f"Failed to send result email to {user.email}: {e}")

	threading.Thread(target=_send_in_background, daemon=True).start()
