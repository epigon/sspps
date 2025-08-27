from app import config
# from app.email import send_email_via_powershell
from logging.handlers import RotatingFileHandler
import base64
import logging
import os
import subprocess

class PowerShellEmailHandler(logging.Handler):
    """Custom handler that emails errors using PowerShell with EncodedCommand."""
    def __init__(self, app):
        super().__init__(level=logging.ERROR)
        self.app = app
        self.recipients = app.config.get('ADMINS', '').split(',')
        self.cc = 'epigon@health.ucsd.edu'
        self.sender = app.config.get('MAIL_DEFAULT_SENDER', 'epigon@health.ucsd.edu')

    def emit(self, record):
        try:
            log_entry = self.format(record)

            cc_addresses = normalize_recipients([self.cc, self.sender])
            to_addresses = normalize_recipients(self.recipients)

            ps_script = f"""
            Send-MailMessage `
                -From "{self.sender}" `
                -To ({to_addresses}) `
                -Cc ({cc_addresses}) `
                -Subject "[Flask Error] {record.levelname} in {record.module}" `
                -Body @'
{log_entry}
'@ `
                -SmtpServer "{config.MAIL_SERVER}" `
                -UseSsl
            """

            # Encode script to base64 for PowerShell -EncodedCommand
            encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")

            result = subprocess.run(
                ["powershell", "-EncodedCommand", encoded],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                # Log to console instead of breaking Flask
                print("Email send failed:", result.stderr)

        except Exception as e:
            print("PowerShellEmailHandler failed:", e)

def normalize_recipients(addresses):
    """Return a PowerShell array of quoted email strings"""
    if not addresses:
        return ""
    if isinstance(addresses, str):
        addresses = [a.strip() for a in addresses.replace(";", ",").split(",") if a.strip()]
    return ",".join(f'"{a}"' for a in addresses)

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
    app.logger.addHandler(file_handler)

    # PowerShell email handler for production
    if not app.debug:
        email_handler = PowerShellEmailHandler(app)
        email_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s'
        ))
        app.logger.addHandler(email_handler)

    app.logger.setLevel(logging.ERROR)

# def setup_logger(app):
#     # Ensure log directory exists
#     log_dir = os.path.join(app.root_path, 'logs')
#     os.makedirs(log_dir, exist_ok=True)

#     # File handler
#     file_handler = RotatingFileHandler(
#         os.path.join(log_dir, 'error.log'),
#         maxBytes=10240,
#         backupCount=10
#     )
#     file_handler.setLevel(logging.ERROR)
#     file_handler.setFormatter(logging.Formatter(
#         '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
#     ))

#     # Add file handler
#     app.logger.addHandler(file_handler)

#     # Email handler
#     # PowerShell email handler
#     if not app.debug:
#         email_handler = PowerShellEmailHandler(app)
#         email_handler.setFormatter(logging.Formatter(
#             '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s'
#         ))
#         app.logger.addHandler(email_handler)


    # if not app.debug:
        
        # try:
        #     # Send email with barcode
        #     subject = '[Flask Error] Unhandled Exception'
        #     admin_list = app.config.get('ADMINS').split(',')
        #     recipients = ", ".join(admin_list)
        #     cc = "epigon@health.ucsd.edu"
        #     sender = app.config.get('MAIL_DEFAULT_SENDER')
        #     body = logging.Formatter(
        #         '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s'
        #     )
        #     print('[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s')
        #     send_email_via_powershell(recipients, cc, sender, subject, body)
        # except Exception as e:
        #     app.logger.error("Failed to send error email: %s", e)

    # if not app.debug and app.config.get('MAIL_SERVER'):
    #     # auth = None
    #     # if app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'):
    #     #     auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])

    #     # secure = () if app.config.get('MAIL_USE_TLS') else None

    #     mail_handler = SMTPHandler(
    #         mailhost=(app.config.get('MAIL_SERVER'), 25),  # or port 587/465
    #         fromaddr=app.config.get('MAIL_DEFAULT_SENDER'),
    #         toaddrs=[app.config.get('ADMINS')],
    #         subject='[Flask Error] Unhandled Exception'
    #     )
    #     mail_handler.setLevel(logging.ERROR)
    #     mail_handler.setFormatter(logging.Formatter(
    #         '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n\n%(message)s'
    #     ))

        # try:
        #     app.logger.addHandler(mail_handler)
        #     app.logger.error("SMTPHandler attached successfully")
        # except Exception as e:
        #     print("Failed to attach mail handler:", e)

    # app.logger.setLevel(logging.ERROR)