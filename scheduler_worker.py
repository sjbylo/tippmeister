"""Standalone scheduler process for background tasks (reminders, admin status, API polling).

Runs separately from gunicorn so scheduler I/O never blocks request workers.
"""
import signal
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [scheduler] %(message)s')
log = logging.getLogger(__name__)


def main():
    from app import create_app
    from app.notifications import setup_reminder_scheduler
    from app.results_fetcher import setup_scheduler

    app = create_app()

    with app.app_context():
        api_scheduler = setup_scheduler(app)
        reminder_scheduler = setup_reminder_scheduler(app)

    schedulers = [s for s in (api_scheduler, reminder_scheduler) if s]
    log.info(f"Scheduler worker started with {len(schedulers)} scheduler(s)")

    def shutdown(signum, frame):
        log.info("Shutting down schedulers...")
        for s in schedulers:
            s.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    while True:
        time.sleep(60)


if __name__ == '__main__':
    main()
