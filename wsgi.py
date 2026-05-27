"""WSGI entry point for Der Tippmeister."""

from app import create_app
from app.results_fetcher import setup_scheduler
from app.notifications import setup_reminder_scheduler

application = create_app()
scheduler = setup_scheduler(application)
reminder_scheduler = setup_reminder_scheduler(application)


if __name__ == '__main__':
	application.run(host='0.0.0.0', port=application.config['PORT'], debug=True)
