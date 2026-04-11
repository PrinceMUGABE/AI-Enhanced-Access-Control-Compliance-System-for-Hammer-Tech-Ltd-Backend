from django.db import models
from django.utils import timezone
from trainingApp.models import Training, Module
from userApp.models import CustomUser

# Candidate model tracks individual candidates participating in trainings
class Candidate(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
    ]

    learner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='candidates', null=True)
    training = models.ForeignKey(Training, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('learner', 'training')  # Ensure a learner registers for a training only once

    def __str__(self):
        return f'{self.learner} - {self.status}'

    def update_status_based_on_progress(self):
        """
        Update candidate status based on module completion progress
        Returns: The updated status
        """
        try:
            from learningProgressApp.models import LearningProgress
            
            # Get learning progress for this candidate
            learning_progress = LearningProgress.objects.filter(
                candidate=self
            ).first()
            
            if not learning_progress:
                # No progress yet, status remains pending
                return self.status
            
            total_modules = learning_progress.total_modules or 0
            completed_modules = learning_progress.completed_modules or 0
            
            # Determine status based on progress
            if total_modules == 0:
                new_status = 'pending'
            elif completed_modules == 0:
                new_status = 'pending'
            elif completed_modules == total_modules:
                new_status = 'completed'
            elif completed_modules > 0 and completed_modules < total_modules:
                new_status = 'in_progress'
            else:
                new_status = 'pending'
            
            # Update if status changed
            if self.status != new_status:
                self.status = new_status
                self.save(update_fields=['status'])
                return new_status
            
            return self.status
            
        except Exception as e:
            print(f"Error updating candidate status: {str(e)}")
            return self.status
    
    def has_completed_training(self):
        """
        Check if the candidate has completed all modules in their assigned training.
        """
        try:
            from learningProgressApp.models import LearningProgress
            
            learning_progress = LearningProgress.objects.filter(
                candidate=self
            ).first()
            
            if learning_progress:
                return learning_progress.is_completed()
            
            # Fallback to old method
            total_modules = self.training.modules.count()
            studied_modules = self.module_progresses.filter(is_studied=True).count()
            return total_modules == studied_modules and total_modules > 0
            
        except Exception as e:
            print(f"Error checking training completion: {str(e)}")
            return False


# ModuleProgress model tracks individual module completion status for each candidate
class ModuleProgress(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="module_progresses")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    is_studied = models.BooleanField(default=False)
    studied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('candidate', 'module')  # Ensure one progress entry per module per candidate

    def __str__(self):
        return f"{self.candidate} - {self.module.name} (Studied: {self.is_studied})"