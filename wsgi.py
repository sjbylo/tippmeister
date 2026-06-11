"""WSGI entry point for Der Tippmeister."""

from app import create_app

application = create_app()


if __name__ == '__main__':
	application.run(host='0.0.0.0', port=application.config['PORT'], debug=True)
