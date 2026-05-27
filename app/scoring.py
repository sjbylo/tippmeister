from app import db
from app.models import Match, Prediction


def calculate_points(prediction, match):
	"""
	Calculate points for a single prediction against the actual match result.

	Scoring rules:
	  Non-draw actual: correct winner = 1pt; exact scoreline = 3pt total
	  Draw actual: any draw predicted = 1pt; exact draw score = 3pt total
	  Penalty bonus (knockout only): correctly predict advancing team = +1
	  Max per match: 4 points (3 exact draw + 1 penalty bonus)
	"""
	if prediction.team1_score is None or prediction.team2_score is None:
		return 0

	actual_t1, actual_t2 = match.effective_score
	if actual_t1 is None or actual_t2 is None:
		return 0

	pred_t1 = prediction.team1_score
	pred_t2 = prediction.team2_score
	points = 0

	actual_is_draw = (actual_t1 == actual_t2)
	pred_is_draw = (pred_t1 == pred_t2)

	if actual_is_draw:
		if pred_is_draw:
			if pred_t1 == actual_t1 and pred_t2 == actual_t2:
				points = 3  # exact draw
			else:
				points = 1  # any draw
	else:
		actual_winner = 1 if actual_t1 > actual_t2 else 2
		pred_winner = 1 if pred_t1 > pred_t2 else (2 if pred_t2 > pred_t1 else 0)
		if pred_winner == actual_winner:
			if pred_t1 == actual_t1 and pred_t2 == actual_t2:
				points = 3  # exact scoreline
			else:
				points = 1  # correct winner

	# Penalty bonus (knockout only)
	if match.is_knockout and match.penalty_winner:
		if prediction.penalty_winner == match.penalty_winner:
			points += 1

	return points


def recalculate_match(match_id):
	"""Recalculate all predictions for a finished match."""
	match = db.session.get(Match, match_id)
	if not match or match.status != 'finished':
		return

	predictions = Prediction.query.filter_by(match_id=match_id).all()
	for pred in predictions:
		pred.points_awarded = calculate_points(pred, match)

	db.session.commit()


def recalculate_all():
	"""Recalculate points for all finished matches."""
	finished = Match.query.filter_by(status='finished').all()
	for match in finished:
		predictions = Prediction.query.filter_by(match_id=match.id).all()
		for pred in predictions:
			pred.points_awarded = calculate_points(pred, match)

	db.session.commit()
