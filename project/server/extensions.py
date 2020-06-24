import sentry_sdk
from celery import Celery
from flask_admin import Admin
from flask_alchemydumps import AlchemyDumps
from flask_bcrypt import Bcrypt
from flask_debugtoolbar import DebugToolbarExtension
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from sentry_sdk.integrations.flask import FlaskIntegration

from project.common.redis import FlaskRedis
from project.common.tricoma_api import TricomaAPI
from project.common.tricoma_client import TricomaClient
# instantiate the extensions
from project.server.config import TALISMAN_CONFIG

login_manager = LoginManager()
bcrypt = Bcrypt()
alchemydumps = AlchemyDumps()
toolbar = DebugToolbarExtension()
db = SQLAlchemy()
celery = Celery()
migrate = Migrate()
flask_admin = Admin(name='admin', base_template='admin/admin_master.html', template_mode='bootstrap3')

talisman = Talisman()

redis_client = FlaskRedis()

tricoma_api = TricomaAPI()
tricoma_client = TricomaClient()


def init_talisman(app):
    talisman.init_app(app, **TALISMAN_CONFIG)


def init_login(app):
    from project.server.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.filter(User.id == int(user_id)).first()


def init_celery(app=None):
    """ Setup celery with application factory """
    if app is None:
        from project.server import create_app
        app = create_app()
    celery.conf.broker_url = app.config["CELERY_BROKER_URL"]
    celery.conf.result_backend = app.config["CELERY_RESULT_BACKEND"]
    # This is needed to fix the indefinite hang of delay and apply_async if celery is down
    celery.conf.broker_transport_options = {"max_retries": 2, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5}
    celery.conf.redis_socket_timeout = 2.0
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context"""

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


def init_sentry(app):
    """ Enable remote logging to Sentry.io"""
    if app.config.get('SENTRY_DSN'):
        # Only init sentry if the DSN is set in the current environment
        sentry_sdk.init(
            app.config.get('SENTRY_DSN'),
            integrations=[
                FlaskIntegration()
            ]
        )


def init_dashboard(app):
    dashboard.bind(app)


def init_extensions(app):
    login_manager.init_app(app)
    bcrypt.init_app(app)
    toolbar.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    tricoma_client.init_app(app)
    tricoma_api.init_app(app)
    init_login(app)
    init_celery(app)
    alchemydumps.init_app(app, db)
    redis_client.init_app(app)
    init_talisman(app)
    # finally set up sentry
    init_sentry(app)
