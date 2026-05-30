#!/usr/bin/env python3
"""
Seed an APAC mini-tournament for testing.

Wipes ALL existing matches, predictions, and relevant settings,
then loads a compact 8-team tournament over 7 days.

Usage:
    python seed_apac.py
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Match, Prediction, AppSetting
from seed_demo import create_demo_users, generate_predictions

GROUPS = {
	'Group A': ['Japan', 'Australia', 'South Korea', 'Saudi Arabia'],
	'Group B': ['Iran', 'China', 'Thailand', 'India'],
}

VENUES = [
	'Tokyo National Stadium, Tokyo',
	'Melbourne Cricket Ground, Melbourne',
	'Seoul World Cup Stadium, Seoul',
	'King Fahd Stadium, Riyadh',
	'Azadi Stadium, Tehran',
	'Beijing National Stadium, Beijing',
]

# Base date: today midnight UTC (first matches kick off today)
BASE_DATE = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

# Kickoff slots per day in UTC -- these are 10:00, 13:00, 16:00 in GMT+8
SLOTS = [
	timedelta(hours=2),    # 10:00 GMT+8
	timedelta(hours=5),    # 13:00 GMT+8
	timedelta(hours=8),    # 16:00 GMT+8
]


def build_schedule():
	"""Build 16 matches: 12 group stage (days 1-4) + 4 knockouts (days 5-7)."""
	matches = []
	match_num = 0
	vi = 0  # venue index, cycles through

	def venue():
		nonlocal vi
		v = VENUES[vi % len(VENUES)]
		vi += 1
		return v

	# --- Group stage: each team plays the other 3 in its group ---
	# Group A pairings (6 matches across 4 days, interleaved with Group B)
	group_a = GROUPS['Group A']
	group_b = GROUPS['Group B']

	# Round-robin pairings for a group of 4
	def round_robin(teams):
		return [
			(teams[0], teams[1]),
			(teams[2], teams[3]),
			(teams[0], teams[2]),
			(teams[1], teams[3]),
			(teams[0], teams[3]),
			(teams[1], teams[2]),
		]

	a_pairs = round_robin(group_a)
	b_pairs = round_robin(group_b)

	# Interleave: day 1 gets A1, A2, B1; day 2 gets B2, A3, B3; etc.
	day_schedule = [
		[('Group A', a_pairs[0]), ('Group A', a_pairs[1]), ('Group B', b_pairs[0])],
		[('Group B', b_pairs[1]), ('Group A', a_pairs[2]), ('Group B', b_pairs[2])],
		[('Group A', a_pairs[3]), ('Group B', b_pairs[3]), ('Group A', a_pairs[4])],
		[('Group B', b_pairs[4]), ('Group A', a_pairs[5]), ('Group B', b_pairs[5])],
	]

	for day_idx, day_matches in enumerate(day_schedule):
		for slot_idx, (group, pair) in enumerate(day_matches):
			match_num += 1
			kickoff = BASE_DATE + timedelta(days=day_idx) + SLOTS[slot_idx]
			matches.append(dict(
				match_num=match_num,
				round='Group stage',
				group_name=group,
				team1=pair[0],
				team2=pair[1],
				venue=venue(),
				kickoff_utc=kickoff,
				is_knockout=False,
			))

	# --- Knockouts ---
	knockout_matches = [
		(4, 0, 'Semi-final', 'Winner A vs Runner B'),
		(4, 1, 'Semi-final', 'Winner B vs Runner A'),
		(5, 0, 'Match for third place', '3rd Place'),
		(6, 0, 'Final', 'Final'),
	]

	for day_offset, slot_idx, round_name, label in knockout_matches:
		match_num += 1
		kickoff = BASE_DATE + timedelta(days=day_offset) + SLOTS[slot_idx]
		matches.append(dict(
			match_num=match_num,
			round=round_name,
			group_name='',
			team1='TBD',
			team2='TBD',
			venue=venue(),
			kickoff_utc=kickoff,
			is_knockout=True,
		))

	return matches


def main():
	app = create_app()
	with app.app_context():
		print("\n=== APAC Mini-Tournament Seeder ===\n")

		# 1. Wipe existing data
		pred_count = Prediction.query.delete()
		match_count = Match.query.delete()
		for key in ('demo_schedule_applied', 'time_warp'):
			setting = db.session.get(AppSetting, key)
			if setting:
				db.session.delete(setting)
		db.session.commit()
		print(f"Wiped {match_count} matches, {pred_count} predictions, reset time warp")

		# 2. Insert APAC matches
		schedule = build_schedule()
		for m in schedule:
			db.session.add(Match(**m, status='scheduled'))
		db.session.commit()
		print(f"Inserted {len(schedule)} matches over 7 days")

		# Print schedule
		print("\nSchedule:")
		for m in schedule:
			ko = m['kickoff_utc']
			utc8 = ko + timedelta(hours=8)
			tag = f"[{m['group_name']}]" if m['group_name'] else f"[{m['round']}]"
			print(f"  Match {m['match_num']:2d}  {utc8.strftime('%b %d %H:%M')} UTC+8  "
				  f"{tag:28s} {m['team1']:15s} vs {m['team2']:15s}  @ {m['venue']}")

		# 3. Re-seed demo users (keeps existing, creates missing)
		names = create_demo_users(7, app)
		if names:
			print(f"\nCreated {len(names)} demo users: {', '.join(names)}")
		else:
			print(f"\nDemo users already exist")

		# 4. Generate predictions for group-stage matches
		count = generate_predictions()
		print(f"Generated {count} predictions for group-stage matches")

		print(f"\nDone! Tournament runs from {(BASE_DATE + SLOTS[0] + timedelta(hours=8)).strftime('%b %d')} "
			  f"to {(BASE_DATE + timedelta(days=6) + SLOTS[0] + timedelta(hours=8)).strftime('%b %d')} (UTC+8)")
		print()


if __name__ == '__main__':
	main()
