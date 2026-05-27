podman exec -it tippmeister python -c "
from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    user = User.query.filter_by(email='stephenbylo@gmail.com').first()
    user.set_password('2jsdhHSJH&^^%2ss')
    db.session.commit()
    print(f'Password reset for {user.display_name}')
"
