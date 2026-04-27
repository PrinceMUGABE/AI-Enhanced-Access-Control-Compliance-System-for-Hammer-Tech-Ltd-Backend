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


# Set timezone to match your database
SYSTEM_TZ = 'Africa/Johannesburg'  # Match your MySQL system_time_zone

# Celery configuration - MUST be set BEFORE beat_schedule
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=SYSTEM_TZ,  # Set timezone to match database
    enable_utc=False,     # Use non-UTC timezone
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    
    # Beat scheduler settings
    beat_scheduler='redbeat.RedBeatScheduler',
    redbeat_redis_url='redis://127.0.0.1:6379/1',
    
    # Timezone settings for beat scheduler
    timezone_aware=True,
    database_short_schedule_delta=True,
)

# Celery Beat Schedule - Run tasks periodically
# Note: crontab doesn't take a tz parameter directly
# The timezone is inherited from app.conf.timezone
app.conf.beat_schedule = {
    # Detect incidents every minute
    'detect-incidents-every-minute': {
        'task': 'incidentApp.tasks.detect_incidents_task',
        'schedule': 60.0,  # Every 60 seconds (1 minute)
        'options': {
            'expires': 50,
        }
    },
    
    # Check SLA compliance every 5 minutes
    'check-sla-compliance': {
        'task': 'incidentApp.tasks.check_sla_compliance_task',
        'schedule': 300.0,  # Every 300 seconds (5 minutes)
    },
    
    # Generate daily reports at 8 AM (in SYSTEM_TZ timezone)
    'generate-daily-report': {
        'task': 'incidentApp.tasks.generate_daily_report_task',
        'schedule': crontab(hour=8, minute=0),  # tz inherited from app.conf.timezone
    },
    
    # Clean old logs every day at 2 AM (in SYSTEM_TZ timezone)
    'clean-old-logs': {
        'task': 'incidentApp.tasks.clean_old_logs_task',
        'schedule': crontab(hour=2, minute=0),  # tz inherited from app.conf.timezone
    },
}

# Optional: Log timezone info on startup
import logging
logger = logging.getLogger(__name__)
logger.info(f"Celery configured with timezone: {app.conf.timezone}")
logger.info(f"UTC enabled: {app.conf.enable_utc}")