from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
	__tablename__ = 'users'

	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(255), unique=True, nullable=False, index=True)
	display_name = db.Column(db.String(12), unique=True, nullable=False, index=True)
	password_hash = db.Column(db.String(256), nullable=False)
	timezone = db.Column(db.String(64), default='Europe/Berlin')
	language = db.Column(db.String(5), default='en')
	is_admin = db.Column(db.Boolean, default=False)
	created_at = db.Column(db.DateTime, default=datetime.utcnow)

	predictions = db.relationship('Prediction', backref='user', lazy='dynamic')

	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)

	def __repr__(self):
		return f'<User {self.display_name}>'


class Match(db.Model):
	__tablename__ = 'matches'

	id = db.Column(db.Integer, primary_key=True)
	match_num = db.Column(db.Integer, unique=True, nullable=False)
	api_fixture_id = db.Column(db.Integer, nullable=True, index=True)
	round = db.Column(db.String(64), nullable=False)
	group_name = db.Column(db.String(32), default='')
	kickoff_utc = db.Column(db.DateTime, nullable=True, index=True)
	team1 = db.Column(db.String(64), nullable=False, default='TBD')
	team2 = db.Column(db.String(64), nullable=False, default='TBD')
	venue = db.Column(db.String(128), default='')
	is_knockout = db.Column(db.Boolean, default=False)

	# Full-time score (90 min)
	team1_score = db.Column(db.Integer, nullable=True)
	team2_score = db.Column(db.Integer, nullable=True)
	# Extra-time cumulative score (120 min)
	team1_extra = db.Column(db.Integer, nullable=True)
	team2_extra = db.Column(db.Integer, nullable=True)
	# Penalty shootout score
	team1_pen = db.Column(db.Integer, nullable=True)
	team2_pen = db.Column(db.Integer, nullable=True)
	# Which team advanced on penalties
	penalty_winner = db.Column(db.String(64), nullable=True)

	status = db.Column(db.String(16), default='scheduled')  # scheduled / live / finished
	result_source = db.Column(db.String(16), nullable=True)  # auto / manual

	predictions = db.relationship('Prediction', backref='match', lazy='dynamic')

	@property
	def has_known_teams(self):
		"""Teams are known (not placeholders like '1A', 'W73')."""
		if not self.team1 or not self.team2:
			return False
		placeholders = ('TBD',)
		import re
		placeholder_pattern = re.compile(r'^[0-9WL]+[A-Z0-9/]+$')
		for team in (self.team1, self.team2):
			if team in placeholders or placeholder_pattern.match(team):
				return False
		return True

	@property
	def score_display(self):
		"""Format the full scoreline for display."""
		if self.team1_score is None or self.team2_score is None:
			return ''
		base = f"{self.team1_score} - {self.team2_score}"
		if self.team1_extra is not None and self.team2_extra is not None:
			base = f"{self.team1_extra} - {self.team2_extra} (AET)"
			if self.team1_pen is not None and self.team2_pen is not None:
				base += f" | {self.team1_pen} - {self.team2_pen} (PEN)"
		return base

	@property
	def effective_score(self):
		"""Score used for scoring calculation (AET if available, else FT)."""
		if self.team1_extra is not None and self.team2_extra is not None:
			return (self.team1_extra, self.team2_extra)
		if self.team1_score is not None and self.team2_score is not None:
			return (self.team1_score, self.team2_score)
		return (None, None)

	def __repr__(self):
		return f'<Match {self.match_num}: {self.team1} vs {self.team2}>'


class Prediction(db.Model):
	__tablename__ = 'predictions'

	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
	match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
	team1_score = db.Column(db.Integer, nullable=True)
	team2_score = db.Column(db.Integer, nullable=True)
	penalty_winner = db.Column(db.String(64), nullable=True)
	points_awarded = db.Column(db.Integer, default=0)
	updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

	__table_args__ = (
		db.UniqueConstraint('user_id', 'match_id', name='uq_user_match'),
	)

	@property
	def is_draw_prediction(self):
		if self.team1_score is not None and self.team2_score is not None:
			return self.team1_score == self.team2_score
		return False

	@property
	def score_display(self):
		if self.team1_score is None or self.team2_score is None:
			return '-'
		text = f"{self.team1_score}-{self.team2_score}"
		if self.penalty_winner:
			text += f" (PEN: {self.penalty_winner})"
		return text

	def __repr__(self):
		return f'<Prediction {self.user_id}:{self.match_id} {self.team1_score}-{self.team2_score}>'


class AppSetting(db.Model):
	"""Simple key-value store for app settings (time warp, invite token, etc.)."""
	__tablename__ = 'app_settings'

	key = db.Column(db.String(64), primary_key=True)
	value = db.Column(db.Text, nullable=True)

	def __repr__(self):
		return f'<AppSetting {self.key}={self.value}>'
