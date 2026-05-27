#!/usr/bin/env python3
"""
Seed script for Der Tippmeister demo/testing.

Usage:
    python seed_demo.py [--users N] [--predictions] [--results N]

    --users N       Create N dummy users (default 5), password: demo123
    --predictions   Generate random predictions for all dummy users
    --results N     Mark first N group-stage matches as finished with random scores
"""

import sys
import os
import random
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import User, Match, Prediction
from app.scoring import recalculate_match

DEMO_NAMES = [
	'Alice', 'Bob', 'Charlie', 'Diana', 'Eve',
	'Frank', 'Grace', 'Hank', 'Ivy', 'Jack',
	'FootyKing', 'BallMad', 'GoalGuru', 'TipTop', 'KickPro',
]

DEMO_EMAIL_DOMAIN = 'demo.tippmeister.local'


def create_demo_users(count, app):
	admin_emails = app.config.get('ADMIN_EMAILS', [])
	created = []
	for i in range(count):
		name = DEMO_NAMES[i % len(DEMO_NAMES)]
		email = f"{name.lower()}@{DEMO_EMAIL_DOMAIN}"

		if User.query.filter_by(email=email).first():
			print(f"  User {name} already exists, skipping")
			continue

		is_admin = email in admin_emails
		user = User(email=email, display_name=name, is_admin=is_admin)
		user.set_password('demo123')
		db.session.add(user)
		created.append(f"{name}{'*' if is_admin else ''}")

	db.session.commit()
	return created


def generate_predictions(users=None):
	if users is None:
		users = User.query.filter(
			User.email.like(f'%@{DEMO_EMAIL_DOMAIN}')
		).all()

	matches = Match.query.filter(Match.status == 'scheduled').all()
	known_matches = [m for m in matches if m.has_known_teams]

	count = 0
	for user in users:
		for match in known_matches:
			existing = Prediction.query.filter_by(
				user_id=user.id, match_id=match.id
			).first()
			if existing:
				continue

			t1 = random.randint(0, 4)
			t2 = random.randint(0, 4)

			pred = Prediction(
				user_id=user.id,
				match_id=match.id,
				team1_score=t1,
				team2_score=t2,
			)

			if match.is_knockout and t1 == t2:
				pred.penalty_winner = random.choice([match.team1, match.team2])

			db.session.add(pred)
			count += 1

	db.session.commit()
	return count


def generate_results(num_matches):
	matches = Match.query.filter_by(
		status='scheduled'
	).filter(
		Match.group_name != '', Match.group_name.isnot(None)
	).order_by(Match.kickoff_utc).limit(num_matches).all()

	count = 0
	for match in matches:
		match.team1_score = random.randint(0, 4)
		match.team2_score = random.randint(0, 4)
		match.status = 'finished'
		match.result_source = 'manual'
		count += 1

	db.session.commit()

	for match in matches:
		recalculate_match(match.id)

	return count


def main():
	parser = argparse.ArgumentParser(description='Seed Der Tippmeister with demo data')
	parser.add_argument('--users', type=int, default=5, help='Number of demo users to create')
	parser.add_argument('--predictions', action='store_true', help='Generate random predictions')
	parser.add_argument('--results', type=int, default=0, help='Finish N group matches with random scores')
	args = parser.parse_args()

	app = create_app()
	with app.app_context():
		print(f"\n=== Der Tippmeister Demo Seeder ===\n")

		names = create_demo_users(args.users, app)
		if names:
			print(f"Created {len(names)} users: {', '.join(names)}")
			print(f"Password for all: demo123")
		else:
			print(f"No new users created (may already exist)")

		if args.predictions:
			count = generate_predictions()
			print(f"Generated {count} predictions")

		if args.results > 0:
			count = generate_results(args.results)
			print(f"Finished {count} matches with random results")

		print(f"\nDemo users login:")
		demo_users = User.query.filter(
			User.email.like(f'%@{DEMO_EMAIL_DOMAIN}')
		).all()
		for u in demo_users:
			print(f"  {u.display_name:15s}  email: {u.email:35s}  password: demo123")

		print()


if __name__ == '__main__':
	main()
