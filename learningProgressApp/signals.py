# learningProgressApp/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from trainingCandidateApp.models import Candidate
from trainingApp.models import Training, Module
from .models import LearningProgress, ModuleCompletion, MaterialProgress


@receiver(post_save, sender=Candidate)
def create_learning_progress(sender, instance, created, **kwargs):
    """
    Automatically create learning progress when a candidate is registered for a training
    """
    if created:
        # Create learning progress for the training
        learning_progress, lp_created = LearningProgress.objects.get_or_create(
            candidate=instance,
            training=instance.training,
            defaults={'total_modules': instance.training.modules.count()}
        )
        
        if lp_created:
            # Create module completions for all modules in the training
            for module in instance.training.modules.all():
                ModuleCompletion.objects.get_or_create(
                    learning_progress=learning_progress,
                    module=module
                )


@receiver(post_save, sender=Module)
def create_module_completion_for_existing_candidates(sender, instance, created, **kwargs):
    """
    When a new module is added to a training, create module completion records 
    for all existing candidates in that training
    """
    if created:
        # Update total modules count for all learning progress in this training
        learning_progresses = LearningProgress.objects.filter(training=instance.training)
        for lp in learning_progresses:
            lp.total_modules = instance.training.modules.count()
            lp.save()
            
            # Create module completion for this new module
            ModuleCompletion.objects.get_or_create(
                learning_progress=lp,
                module=instance
            )


@receiver(pre_save, sender=ModuleCompletion)
def update_completion_timestamp(sender, instance, **kwargs):
    """
    Update completed_at timestamp when module is marked as completed
    """
    if instance.pk:  # This is an update, not a new creation
        try:
            old_instance = ModuleCompletion.objects.get(pk=instance.pk)
            # If status changed from incomplete to complete
            if not old_instance.is_completed and instance.is_completed:
                instance.completed_at = timezone.now()
        except ModuleCompletion.DoesNotExist:
            pass


@receiver(post_save, sender=ModuleCompletion)
def update_learning_progress_on_module_completion(sender, instance, **kwargs):
    """
    Update overall learning progress when a module completion status changes
    """
    instance.learning_progress.update_progress()


@receiver(pre_save, sender=MaterialProgress)
def update_material_timestamps(sender, instance, **kwargs):
    """
    Update timestamps when material is viewed or downloaded
    """
    if instance.pk:  # This is an update
        try:
            old_instance = MaterialProgress.objects.get(pk=instance.pk)
            
            # If viewed status changed to True
            if not old_instance.is_viewed and instance.is_viewed and not instance.viewed_at:
                instance.viewed_at = timezone.now()
            
            # If downloaded status changed to True
            if not old_instance.is_downloaded and instance.is_downloaded and not instance.downloaded_at:
                instance.downloaded_at = timezone.now()
                
        except MaterialProgress.DoesNotExist:
            pass
    else:  # This is a new creation
        if instance.is_viewed and not instance.viewed_at:
            instance.viewed_at = timezone.now()
        if instance.is_downloaded and not instance.downloaded_at:
            instance.downloaded_at = timezone.now()