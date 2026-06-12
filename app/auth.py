import re
import secrets
import logging
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_babel import gettext as _
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter
from app.models import User

auth_bp = Blueprint('auth', __name__)
log = logging.getLogger(__name__)


def validate_display_name(name):
	min_len = current_app.config['DISPLAY_NAME_MIN']
	max_len = current_app.config['DISPLAY_NAME_MAX']
	if not name or len(name) < min_len or len(name) > max_len:
		return _("Display name must be %(min)d-%(max)d characters.", min=min_len, max=max_len)
	if not re.match(r'^[A-Za-z0-9]+$', name):
		return _("Display name can only contain letters and numbers.")
	if User.query.filter(db.func.lower(User.display_name) == name.lower()).first():
		return _("That display name is already taken.")
	return None


def validate_password(password):
	if len(password) < 8:
		return _("Password must be at least 8 characters.")
	if not re.search(r'[A-Za-z]', password):
		return _("Password must contain at least one letter.")
	if not re.search(r'[0-9]', password):
		return _("Password must contain at least one number.")
	return None


@auth_bp.route('/register/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def register(token):
	if token != current_app.config['INVITE_TOKEN']:
		flash(_("Invalid or expired invite link."), "error")
		return redirect(url_for('auth.login'))

	if request.method == 'POST':
		email = request.form.get('email', '').strip().lower()
		display_name = request.form.get('display_name', '').strip()
		password = request.form.get('password', '')
		password2 = request.form.get('password2', '')

		errors = []
		if not email or '@' not in email:
			errors.append(_("Please enter a valid email address."))
		elif User.query.filter_by(email=email).first():
			errors.append(_("That email is already registered."))

		name_err = validate_display_name(display_name)
		if name_err:
			errors.append(name_err)

		pwd_err = validate_password(password)
		if pwd_err:
			errors.append(pwd_err)

		if password != password2:
			errors.append(_("Passwords do not match."))

		if errors:
			for e in errors:
				flash(e, "error")
			return render_template('register.html', token=token,
								   email=email, display_name=display_name)

		is_admin = email in current_app.config['ADMIN_EMAILS']
		user = User(email=email, display_name=display_name, is_admin=is_admin)
		user.set_password(password)
		user.verify_token = secrets.token_urlsafe(48)
		user.verify_sent_at = datetime.utcnow()

		language = request.form.get('language', '').strip()
		if language in ('en', 'de'):
			user.language = language

		detected_tz = request.form.get('timezone', '').strip()
		if detected_tz:
			import pytz
			if detected_tz in pytz.all_timezones:
				user.timezone = detected_tz
		db.session.add(user)
		db.session.commit()

		from app.notifications import send_verification_email
		send_verification_email(user)

		login_user(user)
		flash(_("A verification email has been sent to %(email)s. Please verify within 24 hours.", email=email), "info")
		return redirect(url_for('auth.verify_pending'))

	return render_template('register.html', token=token, email='', display_name='')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("15 per minute")
def login():
	if current_user.is_authenticated:
		return redirect(url_for('main.matches'))

	if request.method == 'POST':
		email = request.form.get('email', '').strip().lower()
		password = request.form.get('password', '')

		user = User.query.filter_by(email=email).first()
		if user and user.check_password(password):
			detected_tz = request.form.get('timezone', '').strip()
			if detected_tz and not user.timezone:
				import pytz
				if detected_tz in pytz.all_timezones:
					user.timezone = detected_tz
					db.session.commit()
			login_user(user, remember=True)
			log.info("LOGIN OK: user=%s ip=%s", user.display_name, request.remote_addr)
			if not user.email_verified:
				return redirect(url_for('auth.verify_pending'))
			next_page = request.args.get('next', '')
			if not next_page or not next_page.startswith('/') or next_page.startswith('//'):
				next_page = url_for('main.matches')
			return redirect(next_page)

		flash(_("Invalid email or password."), "error")
		log.warning("FAILED LOGIN: email=%s ip=%s at=%s",
			email, request.remote_addr, datetime.utcnow().isoformat())
		return render_template('login.html', email=email)

	return render_template('login.html', email='')


@auth_bp.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
	if request.method == 'POST':
		tz = request.form.get('timezone', 'Europe/Berlin')
		lang = request.form.get('language', 'en')

		current_user.timezone = tz
		current_user.language = lang
		db.session.commit()
		flash(_("Profile updated."), "success")
		return redirect(url_for('auth.profile'))

	import pytz
	timezones = sorted(pytz.common_timezones)
	return render_template('profile.html', timezones=timezones)


@auth_bp.route('/verify-pending')
@login_required
def verify_pending():
	if current_user.email_verified:
		return redirect(url_for('main.matches'))
	return render_template('verify_pending.html')


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
	user = User.query.filter_by(verify_token=token).first()
	if not user:
		flash(_("Invalid verification link."), "error")
		return redirect(url_for('auth.login'))

	if user.verify_sent_at and (datetime.utcnow() - user.verify_sent_at) > timedelta(hours=24):
		flash(_("Verification link has expired. Please request a new one."), "error")
		if current_user.is_authenticated:
			return redirect(url_for('auth.verify_pending'))
		return redirect(url_for('auth.login'))

	user.email_verified = True
	user.verify_token = None
	db.session.commit()

	from app.notifications import send_welcome_email
	send_welcome_email(user)

	if not current_user.is_authenticated:
		login_user(user)

	flash(_("Email verified! Welcome, %(name)s!", name=user.display_name), "success")
	return redirect(url_for('main.matches'))


@auth_bp.route('/resend-verification', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def resend_verification():
	if current_user.email_verified:
		return redirect(url_for('main.matches'))

	current_user.verify_token = secrets.token_urlsafe(48)
	current_user.verify_sent_at = datetime.utcnow()
	db.session.commit()

	from app.notifications import send_verification_email
	send_verification_email(current_user)

	flash(_("Verification email resent to %(email)s.", email=current_user.email), "info")
	return redirect(url_for('auth.verify_pending'))


@auth_bp.route('/change-password', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def change_password():
	current_pw = request.form.get('current_password', '')
	new_pw = request.form.get('new_password', '')
	confirm_pw = request.form.get('confirm_password', '')

	if not current_user.check_password(current_pw):
		flash(_("Current password is incorrect."), "error")
		return redirect(url_for('auth.profile'))

	pwd_err = validate_password(new_pw)
	if pwd_err:
		flash(pwd_err, "error")
		return redirect(url_for('auth.profile'))

	if new_pw != confirm_pw:
		flash(_("New passwords do not match."), "error")
		return redirect(url_for('auth.profile'))

	current_user.set_password(new_pw)
	db.session.commit()
	flash(_("Password changed successfully."), "success")
	return redirect(url_for('auth.profile'))
