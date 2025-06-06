from app import create_app
from app.scheduler.routes import generate_scheduled_ics
from flask_bootstrap import Bootstrap5
from flask_apscheduler import APScheduler 

app = create_app()
bootstrap = Bootstrap5(app)

class Config:
    JOBS = [
        {
            "id": "job1",
            "func": "run:run_generate_scheduled_ics",          
            "trigger": "interval",
            "minutes": 2,
        }
    ]

    SCHEDULER_API_ENABLED = True

def run_generate_scheduled_ics():
    with app.app_context():
        generate_scheduled_ics()

if __name__ == '__main__':
    app.config.from_object(Config())    
    scheduler = APScheduler()   
    scheduler.init_app(app)
    scheduler.start()
    app.run(host="0.0.0.0",debug=False,threaded=True) 