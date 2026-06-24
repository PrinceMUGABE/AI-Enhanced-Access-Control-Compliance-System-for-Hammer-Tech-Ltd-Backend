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
    
    # Task result settings
    task_ignore_result=True,  # Don't store results for periodic tasks
    task_store_errors_even_if_ignored=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    worker_max_tasks_per_child=100,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# Celery Beat Schedule - Run tasks periodically
# Note: crontab doesn't take a tz parameter directly
# The timezone is inherited from app.conf.timezone
app.conf.beat_schedule = {
    # ============================================================
    # INCIDENT DETECTION TASKS
    # ============================================================
    
    # Detect incidents every minute
    'detect-incidents-every-minute': {
        'task': 'incidentApp.tasks.detect_incidents_task',
        'schedule': 60.0,  # Every 60 seconds (1 minute)
        'options': {
            'expires': 50,  # Expire after 50 seconds
            'queue': 'incident_detection',
        }
    },
    
    # Check SLA compliance every 5 minutes
    'check-sla-compliance': {
        'task': 'incidentApp.tasks.check_sla_compliance_task',
        'schedule': 300.0,  # Every 300 seconds (5 minutes)
        'options': {
            'expires': 280,
            'queue': 'sla_check',
        }
    },
    
    # ============================================================
    # NOTIFICATION TASKS
    # ============================================================
    
    # Generate notifications every minute
    'generate-notifications-every-minute': {
        'task': 'notificationApp.tasks.generate_notifications_task',
        'schedule': 60.0,  # Every 60 seconds (1 minute)
        'options': {
            'expires': 50,  # Expire after 50 seconds
            'queue': 'notifications',
        }
    },
    
    # Send daily notification digest at 8 AM (in SYSTEM_TZ timezone)
    'send-daily-notification-digest': {
        'task': 'notificationApp.tasks.send_daily_notification_digest',
        'schedule': crontab(hour=8, minute=0),  # tz inherited from app.conf.timezone
        'options': {
            'queue': 'email',
        }
    },
    
    # ============================================================
    # REPORT GENERATION TASKS
    # ============================================================
    
    # Generate daily reports at 8 AM (in SYSTEM_TZ timezone)
    'generate-daily-report': {
        'task': 'incidentApp.tasks.generate_daily_report_task',
        'schedule': crontab(hour=8, minute=0),  # tz inherited from app.conf.timezone
        'options': {
            'queue': 'reports',
        }
    },
    
    # ============================================================
    # CLEANUP TASKS
    # ============================================================
    
    # Clean old logs every day at 2 AM (in SYSTEM_TZ timezone)
    'clean-old-logs': {
        'task': 'incidentApp.tasks.clean_old_logs_task',
        'schedule': crontab(hour=2, minute=0),  # tz inherited from app.conf.timezone
        'options': {
            'queue': 'cleanup',
        }
    },
    
    # Clean old notifications every week on Sunday at 3 AM
    'clean-old-notifications': {
        'task': 'notificationApp.tasks.clean_old_notifications_task',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday at 3 AM
        'options': {
            'queue': 'cleanup',
        }
    },
}

# ============================================================
# ROUTING CONFIGURATION
# ============================================================

app.conf.task_routes = {
    'incidentApp.tasks.detect_incidents_task': {'queue': 'incident_detection'},
    'incidentApp.tasks.check_sla_compliance_task': {'queue': 'sla_check'},
    'incidentApp.tasks.generate_daily_report_task': {'queue': 'reports'},
    'incidentApp.tasks.clean_old_logs_task': {'queue': 'cleanup'},
    'notificationApp.tasks.generate_notifications_task': {'queue': 'notifications'},
    'notificationApp.tasks.send_daily_notification_digest': {'queue': 'email'},
    'notificationApp.tasks.clean_old_notifications_task': {'queue': 'cleanup'},
}

# ============================================================
# STARTUP LOGGING
# ============================================================

import logging
logger = logging.getLogger(__name__)

logger.info(f"🚀 Celery configured with timezone: {app.conf.timezone}")
logger.info(f"   UTC enabled: {app.conf.enable_utc}")
logger.info(f"   Beat scheduler: {app.conf.beat_scheduler}")
logger.info(f"   Redis URL: {app.conf.redbeat_redis_url}")

# Log all scheduled tasks
logger.info("\n📋 Scheduled Tasks:")
for task_name, task_config in app.conf.beat_schedule.items():
    schedule = task_config.get('schedule')
    if hasattr(schedule, 'schedule') and hasattr(schedule, 'nowfun'):
        # It's a crontab or similar
        logger.info(f"   - {task_name}: {schedule}")
    else:
        # It's a numeric interval (seconds)
        logger.info(f"   - {task_name}: Every {schedule} seconds")
    queue = task_config.get('options', {}).get('queue', 'default')
    logger.info(f"     → Queue: {queue}")




    