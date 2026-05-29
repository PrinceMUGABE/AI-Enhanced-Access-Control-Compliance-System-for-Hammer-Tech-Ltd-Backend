# trainingApp/management/commands/send_training_notifications.py

from django.core.management.base import BaseCommand
from trainingApp.models import Training
from trainingApp.email_utils import TrainingEmailNotifier
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Send training notifications to employees'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--training-id',
            type=int,
            help='Send notification for specific training ID'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Send notifications for all trainings'
        )
    
    def handle(self, *args, **options):
        if options['training_id']:
            try:
                training = Training.objects.get(id=options['training_id'])
                self.stdout.write(f"Sending notification for training: {training.name}")
                result = TrainingEmailNotifier.send_training_created_notification(
                    training=training,
                    created_by=training.created_by
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Notification sent: {result.get('total_notified', 0)} employees notified"
                ))
            except Training.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Training with ID {options['training_id']} not found"))
        
        elif options['all']:
            trainings = Training.objects.all()
            self.stdout.write(f"Sending notifications for {trainings.count()} trainings...")
            
            for training in trainings:
                result = TrainingEmailNotifier.send_training_created_notification(
                    training=training,
                    created_by=training.created_by
                )
                self.stdout.write(f"✓ {training.name}: {result.get('total_notified', 0)} employees notified")
            
            self.stdout.write(self.style.SUCCESS("All notifications sent!"))
        
        else:
            self.stdout.write(self.style.ERROR("Please specify --training-id or --all"))



            