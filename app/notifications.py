import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
import pytz

log = logging.getLogger(__name__)


def _to_local(dt, tz_name):
	"""Convert a naive UTC datetime to a timezone-aware local datetime."""
	if not dt or not tz_name:
		return dt
	try:
		tz = pytz.timezone(tz_name)
	except pytz.UnknownTimeZoneError:
		return dt
	return pytz.utc.localize(dt).astimezone(tz)


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


def get_tip_status_data(hours_ahead=48):
	"""Build tip status data for upcoming matches. Must be called within app context."""
	from app.models import Match, Prediction, User
	from app import db, get_now
	from datetime import timedelta

	now = get_now()
	window_end = now + timedelta(hours=hours_ahead)

	upcoming = Match.query.filter(
		Match.kickoff_utc >= now,
		Match.kickoff_utc <= window_end,
		Match.status == 'scheduled',
	).order_by(Match.kickoff_utc).all()

	users = User.query.filter_by(email_verified=True).order_by(User.display_name).all()

	if not upcoming:
		return {'matches': [], 'user_statuses': [], 'generated_at': now}

	match_ids = [m.id for m in upcoming]

	user_statuses = []
	for user in users:
		user_predictions = Prediction.query.filter(
			Prediction.user_id == user.id,
			Prediction.match_id.in_(match_ids),
		).all()

		predicted_match_ids = {p.match_id for p in user_predictions}
		missing_matches = [m for m in upcoming if m.id not in predicted_match_ids]

		last_tip = Prediction.query.filter(
			Prediction.user_id == user.id,
		).order_by(Prediction.updated_at.desc()).first()

		user_statuses.append({
			'user': user,
			'tipped_count': len(predicted_match_ids),
			'total_count': len(upcoming),
			'missing_matches': missing_matches,
			'last_tip_at': last_tip.updated_at if last_tip else None,
		})

	user_statuses.sort(key=lambda s: (-len(s['missing_matches']), s['user'].display_name))

	return {
		'matches': upcoming,
		'user_statuses': user_statuses,
		'generated_at': now,
	}


def _format_local(dt, tz_name):
	"""Format a UTC datetime in the given timezone as 'Jun 11, 15:00'."""
	if not dt:
		return "Never"
	local = _to_local(dt, tz_name)
	return local.strftime('%b %d, %H:%M')


def send_admin_status_email(app):
	"""Send tip status summary email to each admin in their local timezone."""
	from app.models import User

	with app.app_context():
		data = get_tip_status_data(hours_ahead=48)
		if not data['matches']:
			log.info("Admin status: no upcoming matches in 48h window, skipping email")
			return

		admins = User.query.filter_by(is_admin=True, email_verified=True).all()
		if not admins:
			return

		url = _site_url()

		for admin in admins:
			tz = admin.timezone or 'UTC'
			tz_label = tz.replace('_', ' ').split('/')[-1]

			match_rows = ""
			for m in data['matches']:
				kickoff = _format_local(m.kickoff_utc, tz) if m.kickoff_utc else 'TBD'
				match_rows += f"<tr><td>{m.match_num}</td><td>{m.team1} vs {m.team2}</td><td>{kickoff}</td></tr>\n"

			user_rows = ""
			for s in data['user_statuses']:
				missing_count = len(s['missing_matches'])
				color = "#d32f2f" if missing_count > 0 else "#388e3c"
				status_text = f"{s['tipped_count']}/{s['total_count']}"

				if missing_count > 0:
					missing_names = ", ".join(f"{m.team1} vs {m.team2}" for m in s['missing_matches'][:3])
					if missing_count > 3:
						missing_names += f" (+{missing_count - 3} more)"
				else:
					missing_names = "All done"

				last_tip_str = _format_local(s['last_tip_at'], tz) if s['last_tip_at'] else "Never"

				user_rows += (
					f'<tr style="color:{color}">'
					f'<td><strong>{s["user"].display_name}</strong></td>'
					f'<td>{status_text}</td>'
					f'<td>{missing_names}</td>'
					f'<td>{last_tip_str}</td>'
					f'</tr>\n'
				)

			subject = f"Der Tippmeister: Tip Status ({len(data['matches'])} upcoming matches)"
			body_html = f"""
			<h2>Tip Status Summary</h2>
			<p>{len(data['matches'])} match(es) in the next 48 hours (times in {tz_label}):</p>
			<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:14px">
			<tr style="background:#f5f5f5"><th>#</th><th>Match</th><th>Kickoff</th></tr>
			{match_rows}
			</table>
			<br>
			<h3>User Status</h3>
			<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:14px">
			<tr style="background:#f5f5f5"><th>User</th><th>Tipped</th><th>Missing</th><th>Last Tip</th></tr>
			{user_rows}
			</table>
			<br>
			<p><a href="{url}/admin/tip-status" style="color:#00a651;font-weight:bold">View full status in app</a></p>
			<p><em>Der Tippmeister</em></p>
			"""

			try:
				send_email(admin.email, subject, body_html)
			except Exception as e:
				log.warning(f"Failed to send admin status to {admin.email}: {e}")

		log.info(f"Admin status email sent to {len(admins)} admin(s)")


def _check_and_send_admin_status(app):
	"""Check if matches are 42-48h away and send admin status if so."""
	from app.models import Match
	from app import get_now
	from datetime import timedelta

	with app.app_context():
		now = get_now()
		window_start = now + timedelta(hours=42)
		window_end = now + timedelta(hours=48)

		has_matches = Match.query.filter(
			Match.kickoff_utc >= window_start,
			Match.kickoff_utc <= window_end,
			Match.status == 'scheduled',
		).first()

		if has_matches:
			send_admin_status_email(app)


def setup_reminder_scheduler(app):
	"""Schedule daily reminder emails and admin status checks."""
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
	scheduler.add_job(
		func=_check_and_send_admin_status,
		args=[app],
		trigger='cron',
		hour='*/6',
		minute=30,
		id='admin_status_check',
		replace_existing=True,
	)
	scheduler.start()
	log.info("Schedulers started (daily reminders at 18:00 UTC, admin status every 6h)")
	return scheduler
