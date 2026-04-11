# backend/celery.py

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Celery Beat Schedule - Run tasks periodically
app.conf.beat_schedule = {
    # Detect incidents every minute
    'detect-incidents-every-minute': {
        'task': 'incidentApp.tasks.detect_incidents_task',
        'schedule': 6000.0,  # Every 60 seconds (1 minute)
        'options': {
            'expires': 50,
        }
    },
    
    # Check SLA compliance every 5 minutes
    # 'check-sla-compliance': {
    #     'task': 'incidentApp.tasks.check_sla_compliance_task',
    #     'schedule': 300.0,  # Every 300 seconds (5 minutes)
    # },
    
    # Generate daily reports at 8 AM
    'generate-daily-report': {
        'task': 'incidentApp.tasks.generate_daily_report_task',
        'schedule': crontab(hour=8, minute=0),
    },
    
    # Clean old logs every day at 2 AM
    'clean-old-logs': {
        'task': 'incidentApp.tasks.clean_old_logs_task',
        'schedule': crontab(hour=2, minute=0),
    },
}

# Celery configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    # Use Redis for beat schedule persistence
    beat_scheduler='redbeat.RedBeatScheduler',
    redbeat_redis_url='redis://127.0.0.1:6379/1',
)