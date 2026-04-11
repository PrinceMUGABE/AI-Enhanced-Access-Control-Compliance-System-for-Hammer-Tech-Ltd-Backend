# learningProgressApp/models.py
from django.db import models
from django.utils import timezone
from django.conf import settings
from userApp.models import CustomUser
from trainingApp.models import Training, Module, TrainingMaterial
from trainingCandidateApp.models import Candidate


class LearningProgress(models.Model):
    """
    Main model to track overall learning progress for a candidate in a specific training
    """
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='learning_progress')
    training = models.ForeignKey(Training, on_delete=models.CASCADE)
    total_modules = models.PositiveIntegerField(default=0)
    completed_modules = models.PositiveIntegerField(default=0)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    estimated_completion_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('candidate', 'training')
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"{self.candidate.learner} - {self.training.name} ({self.progress_percentage}%)"
    
    def update_progress(self):
        """Update progress statistics"""
        self.total_modules = self.training.modules.count()
        self.completed_modules = self.module_completions.filter(is_completed=True).count()
        
        if self.total_modules > 0:
            self.progress_percentage = (self.completed_modules / self.total_modules) * 100
        else:
            self.progress_percentage = 0
            
        self.save()
    
    def is_completed(self):
        """Check if training is fully completed"""
        return self.completed_modules == self.total_modules and self.total_modules > 0


class ModuleCompletion(models.Model):
    """
    Track completion status of individual modules within a training
    """
    learning_progress = models.ForeignKey(LearningProgress, on_delete=models.CASCADE, related_name='module_completions')
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_minutes = models.PositiveIntegerField(default=0)  # Time spent on this module in minutes
    
    class Meta:
        unique_together = ('learning_progress', 'module')
        ordering = ['module__id']
    
    def __str__(self):
        status = "Completed" if self.is_completed else "In Progress"
        return f"{self.learning_progress.candidate.learner} - {self.module.name} ({status})"
    
    def save(self, *args, **kwargs):
        # Call parent save first
        super().save(*args, **kwargs)
        
        # Update the candidate's status based on completion
        try:
            candidate = self.learning_progress.candidate
            if candidate:
                # Import here to avoid circular imports
                from trainingCandidateApp.models import Candidate
                candidate_obj = Candidate.objects.get(id=candidate.id)
                candidate_obj.update_status_based_on_progress()
        except Exception as e:
            print(f"Error updating candidate status: {str(e)}")

    def mark_completed(self):
        """Mark module as completed"""
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()
            
            # Update overall learning progress
            self.learning_progress.update_progress()
            
            # Update candidate status
            try:
                candidate = self.learning_progress.candidate
                if candidate:
                    from trainingCandidateApp.models import Candidate
                    candidate_obj = Candidate.objects.get(id=candidate.id)
                    candidate_obj.update_status_based_on_progress()
            except Exception as e:
                print(f"Error updating candidate status: {str(e)}")

class MaterialProgress(models.Model):
    """
    Track progress on individual training materials within modules
    """
    module_completion = models.ForeignKey(ModuleCompletion, on_delete=models.CASCADE, related_name='material_progress')
    material = models.ForeignKey(TrainingMaterial, on_delete=models.CASCADE)
    is_viewed = models.BooleanField(default=False)
    is_downloaded = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    view_duration_seconds = models.PositiveIntegerField(default=0)  # How long material was viewed
    
    class Meta:
        unique_together = ('module_completion', 'material')
        ordering = ['material__id']
    
    def __str__(self):
        return f"{self.module_completion.learning_progress.candidate.learner} - {self.material.get_filename()}"
    
    def mark_viewed(self, duration_seconds=0):
        """Mark material as viewed"""
        if not self.is_viewed:
            self.is_viewed = True
            self.viewed_at = timezone.now()
        
        self.view_duration_seconds += duration_seconds
        self.save()
    
    def mark_downloaded(self):
        """Mark material as downloaded"""
        if not self.is_downloaded:
            self.is_downloaded = True
            self.downloaded_at = timezone.now()
            self.save()


class LearningSession(models.Model):
    """
    Track individual learning sessions for detailed analytics
    """
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='learning_sessions')
    training = models.ForeignKey(Training, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, null=True, blank=True)
    session_start = models.DateTimeField(auto_now_add=True)
    session_end = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    activities_completed = models.PositiveIntegerField(default=0)  # Number of materials/activities completed in session
    
    class Meta:
        ordering = ['-session_start']
    
    def __str__(self):
        return f"{self.candidate.learner} - {self.training.name} Session ({self.session_start.date()})"
    
    def end_session(self):
        """End the learning session and calculate duration"""
        if not self.session_end:
            self.session_end = timezone.now()
            duration = self.session_end - self.session_start
            self.duration_minutes = int(duration.total_seconds() / 60)
            self.save()


class LearningAchievement(models.Model):
    """
    Track achievements and milestones in learning progress
    """
    ACHIEVEMENT_TYPES = [
        ('first_module', 'First Module Completed'),
        ('fast_learner', 'Fast Learner'),
        ('consistent_learner', 'Consistent Learner'),
        ('training_completed', 'Training Completed'),
        ('perfect_attendance', 'Perfect Attendance'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='achievements')
    achievement_type = models.CharField(max_length=20, choices=ACHIEVEMENT_TYPES)
    training = models.ForeignKey(Training, on_delete=models.CASCADE, null=True, blank=True)
    earned_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    
    class Meta:
        unique_together = ('candidate', 'achievement_type', 'training')
        ordering = ['-earned_at']
    
    def __str__(self):
        return f"{self.candidate.learner} - {self.get_achievement_type_display()}"