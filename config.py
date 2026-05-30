import os
import uuid

basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.environ.get('DATA_DIR', os.path.join(basedir, 'instance'))


def _get_or_create_secret_key():
	"""Get secret key from env, or generate and persist one in data_dir."""
	key = os.environ.get('SECRET_KEY')
	if key:
		return key
	key_file = os.path.join(data_dir, '.secret_key')
	os.makedirs(data_dir, exist_ok=True)
	try:
		with open(key_file) as f:
			return f.read().strip()
	except FileNotFoundError:
		key = uuid.uuid4().hex + uuid.uuid4().hex
		with open(key_file, 'w') as f:
			f.write(key)
		return key


class Config:
	SECRET_KEY = _get_or_create_secret_key()
	SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(data_dir, 'tippmeister.db')}"
	SQLALCHEMY_TRACK_MODIFICATIONS = False

	ADMIN_EMAILS = [
		e.strip() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()
	]

	INVITE_TOKEN = os.environ.get('INVITE_TOKEN') or uuid.uuid4().hex

	# API-Football
	API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
	API_FOOTBALL_LEAGUE_ID = 1  # FIFA World Cup
	API_FOOTBALL_SEASON = 2026

	# Gmail SMTP
	GMAIL_USER = os.environ.get('GMAIL_USER', '')
	GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')
	GMAIL_FROM = os.environ.get('GMAIL_FROM', '')  # optional "From" address (e.g. a Google Group alias)

	# Public URL for links in emails (e.g. "https://bastion:9443")
	SITE_URL = os.environ.get('SITE_URL', '')

	# Display
	LEADERBOARD_TOP_N = int(os.environ.get('LEADERBOARD_TOP_N', '10'))

	# Server
	PORT = int(os.environ.get('PORT', '9443'))

	# Demo mode
	DEMO_SCHEDULE = os.environ.get('DEMO_SCHEDULE', 'false').lower() == 'true'

	# Default timezone and language
	DEFAULT_TIMEZONE = 'Europe/Berlin'
	DEFAULT_LANGUAGE = 'en'
	BABEL_DEFAULT_LOCALE = 'en'
	BABEL_DEFAULT_TIMEZONE = 'UTC'
	BABEL_TRANSLATION_DIRECTORIES = os.path.join(basedir, 'translations')

	DISPLAY_NAME_MIN = 3
	DISPLAY_NAME_MAX = 12

	# Session timeout: 7 days (re-login required after this)
	PERMANENT_SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME_DAYS', '7')) * 86400
	SESSION_COOKIE_HTTPONLY = True
	SESSION_COOKIE_SAMESITE = 'Lax'

	# CSRF protection (Flask-WTF)
	WTF_CSRF_ENABLED = True
	WTF_CSRF_SSL_STRICT = False  # don't require Referer header on HTTPS (self-signed certs strip it)

	# Cache static files for 1 hour in browser
	SEND_FILE_MAX_AGE_DEFAULT = 3600
