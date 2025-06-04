from app import create_app
from app.scheduler.routes import generate_scheduled_ics
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask_bootstrap import Bootstrap5 

app = create_app()
bootstrap = Bootstrap5(app)
scheduler = BackgroundScheduler()

def run_generate_scheduled_ics():
    with app.app_context():
        generate_scheduled_ics()

# Schedule the cron job to run every day at 9:30 AM
scheduler.add_job(
    func=run_generate_scheduled_ics,
    # trigger=CronTrigger(second='*/10'), #every 10 seconds
    # trigger=CronTrigger(minute='*/2'), #every 2 minutes
    trigger=CronTrigger(hour='*'), #every hour
)

# Start the scheduler
scheduler.start()

if __name__ == '__main__':
    app.run(host="0.0.0.0",debug=True,threaded=True) 