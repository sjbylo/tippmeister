# Der Tippmeister -- FIFA World Cup 2026 Prediction Game

A simple, self-hosted prediction game for FIFA World Cup 2026.

## Quick Start (Container)

```bash
# Set your admin email and start
export ADMIN_EMAILS="you@example.com"
bash start.sh

# Open in browser
# https://bastion:9443
```

## Quick Start (Development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
export ADMIN_EMAILS="you@example.com"
python wsgi.py
```

## Demo / Testing

```bash
# Seed dummy users and predictions
python seed_demo.py --users 5 --predictions --results 6

# All demo users have password: demo123
```

## Configuration (Environment Variables)

| Variable | Description | Default |
|---|---|---|
| `ADMIN_EMAILS` | Comma-separated admin emails | (none) |
| `INVITE_TOKEN` | Registration invite token | auto-generated |
| `SECRET_KEY` | Flask secret key | auto-generated (persisted) |
| `API_FOOTBALL_KEY` | API-Football key for auto results | (none, manual mode) |
| `GMAIL_USER` | Gmail address for notifications | (none) |
| `GMAIL_APP_PASSWORD` | Gmail App Password | (none) |
| `GMAIL_FROM` | Custom "From" email address (e.g. group alias) | same as GMAIL_USER |
| `SITE_URL` | Public URL for email links | `https://localhost:9443` |
| `PORT` | HTTPS port | 9443 |
| `HTTP_PORT` | HTTP redirect port | 8080 |
| `DATA_DIR` | Database storage directory | ./instance |
| `LEADERBOARD_TOP_N` | Default leaderboard display size | 10 |
| `SESSION_LIFETIME_DAYS` | Session expiry in days | 7 |
| `DEMO_SCHEDULE` | Compress match schedule for testing | false |

## Features

- Secret invite-link registration
- Prediction entry with penalty winner validation for knockout draws
- Auto-result fetching from API-Football (free tier)
- Manual result entry/override by admin with input validation
- Leaderboard with configurable top-N display
- Match list view (mobile) + Grid view (desktop) with Today/Group/Knockout/All filters
- Email notifications: welcome, daily reminders, match results with links
- German/English language support (i18n with Flask-Babel)
- Time warp for testing + compressed demo schedule
- CSRF protection, rate limiting, session timeout
- HTTP to HTTPS redirect
- Custom 404/500 error pages
- Self-signed HTTPS
- Runs in Podman container on RHEL 8/9
