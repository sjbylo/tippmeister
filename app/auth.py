import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_babel import gettext as _
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter
from app.models import User

auth_bp = Blueprint('auth', __name__)


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
		db.session.add(user)
		db.session.commit()

		from app.notifications import send_welcome_email
		send_welcome_email(user)

		login_user(user)
		flash(_("Welcome, %(name)s!", name=display_name), "success")
		return redirect(url_for('main.matches'))

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
			login_user(user, remember=True)
			next_page = request.args.get('next', '')
			if not next_page or not next_page.startswith('/') or next_page.startswith('//'):
				next_page = url_for('main.matches')
			return redirect(next_page)

		flash(_("Invalid email or password."), "error")
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
