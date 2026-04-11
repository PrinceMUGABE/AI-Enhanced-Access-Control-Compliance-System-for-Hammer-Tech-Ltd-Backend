# learningProgressApp/management/commands/sync_learning_progress.py
from django.core.management.base import BaseCommand
from django.db import transaction
from learningProgressApp.models import LearningProgress, ModuleCompletion
from trainingCandidateApp.models import Candidate
from trainingApp.models import Training, Module
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync learning progress for all candidates'

    def handle(self, *args, **options):
        self.stdout.write('Starting learning progress sync...')
        
        try:
            with transaction.atomic():
                # Get all candidates
                candidates = Candidate.objects.select_related('training').all()
                
                created_count = 0
                updated_count = 0
                
                for candidate in candidates:
                    # Get or create learning progress
                    progress, created = LearningProgress.objects.get_or_create(
                        candidate=candidate,
                        training=candidate.training,
                        defaults={
                            'total_modules': candidate.training.modules.count()
                        }
                    )
                    
                    # Update total modules if training has changed
                    if not created:
                        progress.total_modules = candidate.training.modules.count()
                        progress.update_progress()
                        updated_count += 1
                    else:
                        # Initialize module completions for new progress
                        modules = candidate.training.modules.all()
                        for module in modules:
                            ModuleCompletion.objects.get_or_create(
                                learning_progress=progress,
                                module=module
                            )
                        created_count += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully synced learning progress. '
                        f'Created: {created_count}, Updated: {updated_count}'
                    )
                )
                
        except Exception as e:
            logger.error(f"Error syncing learning progress: {str(e)}", exc_info=True)
            self.stdout.write(
                self.style.ERROR(f'Error syncing learning progress: {str(e)}')
            )