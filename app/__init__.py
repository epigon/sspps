from app.cred import server, user, pwd, database, secret  # ensure `database` is defined in cred.py
from app.logger import setup_logger
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
import urllib.parse

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.sso_redirect'

def create_app():

    app = Flask(__name__)

    app.config['SECRET_KEY'] = secret

    # pyodbc connection string
    params = urllib.parse.quote_plus(
        "DRIVER={ODBC Driver 17 for SQL Server};" 
        "SERVER="+server+";"
        "DATABASE="+database+";"
        "UID="+user+";"
        "PWD="+pwd+";"
        "TrustServerCertificate=yes;"
    )
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc:///?odbc_connect={params}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Set up error logging
    app.config.from_pyfile('config.py')
    setup_logger(app)

    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    from .models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Import your permission helpers
    from app.utils import has_permission, is_admin

    # Register context processor
    @app.context_processor
    def inject_permissions():
        return dict(has_permission=has_permission, is_admin=is_admin)
    
    # Register Blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.committeetracker.routes import committee_bp
    app.register_blueprint(committee_bp)

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    from app.scheduler.routes import scheduler_bp
    app.register_blueprint(scheduler_bp)

    from app.adsearch.routes import adsearch_bp
    app.register_blueprint(adsearch_bp)

    # @app.route('/cause-error')
    # def error():
    #     raise ValueError("This is a test error.")

    # @app.errorhandler(Exception)
    # def handle_exception(e):
    #     app.logger.error(f"Unhandled Exception: {e}", exc_info=True)  # ✅ Must include this line
    #     return "An error occurred", 500

    with app.app_context():
        db.create_all()    

    return app
    