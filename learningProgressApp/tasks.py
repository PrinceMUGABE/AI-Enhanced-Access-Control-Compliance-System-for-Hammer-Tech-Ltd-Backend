# learningProgressApp/tasks.py
from celery import shared_task
from django.db import transaction
from .models import LearningProgress
import logging

logger = logging.getLogger(__name__)

@shared_task
def update_all_learning_progress():
    """Background task to update all learning progress"""
    try:
        with transaction.atomic():
            all_progress = LearningProgress.objects.select_related(
                'candidate', 'training'
            ).all()
            
            for progress in all_progress:
                progress.update_progress()
            
            logger.info(f"Updated {len(all_progress)} learning progress records")
            
    except Exception as e:
        logger.error(f"Error updating learning progress: {str(e)}", exc_info=True)
        raise