# trainingApp/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Training
from .email_utils import TrainingEmailNotifier
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Training)
def send_training_notification_on_create(sender, instance, created, **kwargs):
    """
    Automatically send notifications when a new training is created
    """
    if created:
        logger.info(f"New training created: {instance.name}. Sending notifications...")
        
        # Send notifications asynchronously to avoid blocking the response
        # You can use Celery for this in production
        try:
            result = TrainingEmailNotifier.send_training_created_notification(
                training=instance,
                created_by=instance.created_by
            )
            logger.info(f"Notification result for {instance.name}: {result}")
        except Exception as e:
            logger.error(f"Failed to send notifications for {instance.name}: {str(e)}")




            