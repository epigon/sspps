from app import create_app
from app.routes.calendars import generate_scheduled_ics

app = create_app()

def generate_ics_with_app_context():
    with app.app_context():
       generate_scheduled_ics()

if __name__ == '__main__':
    generate_ics_with_app_context()  
