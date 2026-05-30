import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

log = logging.getLogger(__name__)


def _site_url():
	"""Get the public site URL for email links."""
	url = current_app.config.get('SITE_URL', '')
	if not url:
		port = current_app.config.get('PORT', 9443)
		url = f"https://localhost:{port}"
	return url.rstrip('/')


def send_email(to_email, subject, body_html, body_text=None):
	"""Send an email via Gmail SMTP. Returns True on success."""
	gmail_user = current_app.config.get('GMAIL_USER')
	gmail_password = current_app.config.get('GMAIL_APP_PASSWORD')

	if not gmail_user or not gmail_password:
		log.warning("Gmail credentials not configured -- email not sent")
		return False

	from_addr = current_app.config.get('GMAIL_FROM') or gmail_user

	msg = MIMEMultipart('alternative')
	msg['Subject'] = subject
	msg['From'] = f"Der Tippmeister <{from_addr}>"
	msg['To'] = to_email

	if body_text:
		msg.attach(MIMEText(body_text, 'plain'))
	msg.attach(MIMEText(body_html, 'html'))

	try:
		with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
			server.login(gmail_user, gmail_password)
			server.send_message(msg)
		log.info(f"Email sent to {to_email}: {subject}")
		return True
	except Exception as e:
		log.error(f"Failed to send email to {to_email}: {e}")
		return False


def send_verification_email(user):
	url = _site_url()
	verify_link = f"{url}/verify-email/{user.verify_token}"
	subject = "Der Tippmeister: Verify your email"
	body_html = f"""
	<h2>Welcome, {user.display_name}!</h2>
	<p>Please verify your email address to start playing.</p>
	<p><a href="{verify_link}" style="color:#00a651;font-weight:bold;font-size:1.2em">Verify my email</a></p>
	<p style="color:#888;font-size:0.9em">This link expires in 24 hours.</p>
	<p><em>Der Tippmeister</em></p>
	"""
	body_text = f"Welcome, {user.display_name}!\n\nVerify your email: {verify_link}\n\nThis link expires in 24 hours."
	return send_email(user.email, subject, body_html, body_text)


def send_welcome_email(user):
	url = _site_url()
	subject = "Welcome to Der Tippmeister!"
	body_html = f"""
	<h2>Welcome, {user.display_name}!</h2>
	<p>You've joined the FIFA World Cup 2026 prediction game.</p>
	<p><a href="{url}/predictions" style="color:#00a651;font-weight:bold">Start making your predictions now</a> -- good luck!</p>
	<p><a href="{url}/leaderboard">View leaderboard</a> | <a href="{url}/matches">Browse matches</a></p>
	<p><em>Der Tippmeister</em></p>
	"""
	return send_email(user.email, subject, body_html)


def send_reminder_email(user, unpredicted_count, match_date_str):
	url = _site_url()
	subject = f"Der Tippmeister: {unpredicted_count} matches need your predictions!"
	body_html = f"""
	<h2>Hey {user.display_name}!</h2>
	<p>You have <strong>{unpredicted_count}</strong> upcoming match(es) on
	<strong>{match_date_str}</strong> without predictions.</p>
	<p><a href="{url}/predictions" style="color:#00a651;font-weight:bold">Submit your tips now</a> before kickoff!</p>
	<p><em>Der Tippmeister</em></p>
	"""
	return send_email(user.email, subject, body_html)


def send_results_email(user, match, points):
	url = _site_url()
	subject = f"Der Tippmeister: {match.team1} vs {match.team2} result is in!"
	body_html = f"""
	<h2>Match Result</h2>
	<p><strong>{match.team1} vs {match.team2}</strong>: {match.score_display}</p>
	<p>Your score for this match: <strong>{points} point(s)</strong></p>
	<p><a href="{url}/leaderboard" style="color:#00a651;font-weight:bold">Check the leaderboard</a> | <a href="{url}/matches">All matches</a></p>
	<p><em>Der Tippmeister</em></p>
	"""
	return send_email(user.email, subject, body_html)


def send_daily_reminders(app):
	"""Check for upcoming matches and send reminder emails to users who haven't predicted."""
	from app.models import Match, Prediction, User
	from app import db, get_now

	with app.app_context():
		now = get_now()
		from datetime import timedelta
		# Look ahead 12-36 hours to cover all timezones
		window_start = now + timedelta(hours=12)
		window_end = now + timedelta(hours=36)

		upcoming = Match.query.filter(
			Match.kickoff_utc >= window_start,
			Match.kickoff_utc <= window_end,
			Match.status == 'scheduled',
		).all()

		if not upcoming:
			return

		match_ids = [m.id for m in upcoming]
		date_str = (now + timedelta(days=1)).strftime('%B %d, %Y')

		users = User.query.filter_by(email_verified=True).all()
		for user in users:
			predicted = Prediction.query.filter(
				Prediction.user_id == user.id,
				Prediction.match_id.in_(match_ids),
			).count()
			unpredicted = len(match_ids) - predicted
			if unpredicted > 0:
				try:
					send_reminder_email(user, unpredicted, date_str)
				except Exception as e:
					log.warning(f"Failed to send reminder to {user.email}: {e}")

		log.info(f"Sent daily reminders for {len(upcoming)} matches on {date_str}")


def setup_reminder_scheduler(app):
	"""Schedule daily reminder emails (runs once per day at 18:00 UTC)."""
	from apscheduler.schedulers.background import BackgroundScheduler

	scheduler = BackgroundScheduler()
	scheduler.add_job(
		func=send_daily_reminders,
		args=[app],
		trigger='cron',
		hour=18,
		minute=0,
		id='daily_reminder',
		replace_existing=True,
	)
	scheduler.start()
	log.info("Reminder email scheduler started (daily at 18:00 UTC)")
	return scheduler
