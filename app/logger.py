import logging
from logging.handlers import RotatingFileHandler, SMTPHandler
import os

def setup_logger(app):
    # Ensure log directory exists
    log_dir = os.path.join(app.root_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # File handler
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'error.log'),
        maxBytes=10240,
        backupCount=10
    )
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))

    # Add file handler
    app.logger.addHandler(file_handler)

    # Email handler
    if not app.debug and app.config.get('MAIL_SERVER'):
        # auth = None
        # if app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'):
        #     auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])

        # secure = () if app.config.get('MAIL_USE_TLS') else None

        mail_handler = SMTPHandler(
            mailhost=(app.config.get('MAIL_SERVER'), 25),  # or port 587/465
            fromaddr=app.config.get('MAIL_DEFAULT_SENDER'),
            toaddrs=[app.config.get('ADMINS')],
            subject='[Flask Error] Unhandled Exception'
        )
        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s'
        ))

        # try:
        #     app.logger.addHandler(mail_handler)
        #     app.logger.error("SMTPHandler attached successfully")
        # except Exception as e:
        #     print("Failed to attach mail handler:", e)

    app.logger.setLevel(logging.ERROR)