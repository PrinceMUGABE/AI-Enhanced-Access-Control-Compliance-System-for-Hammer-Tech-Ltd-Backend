import uuid
from django.db import models
from django.utils.timezone import now
from django.db.models import Avg, Sum
from userApp.models import CustomUser
from departmentApp.models import Department


class OnboardingModule(models.Model):
    MODULE_TYPES = [
        ('core', 'Core'),
        ('department', 'Department-Specific'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    module_type = models.CharField(max_length=20, choices=MODULE_TYPES, default='core')
    departments = models.ManyToManyField(Department, related_name='modules', blank=True)
    order = models.IntegerField(default=0)
    is_required = models.BooleanField(default=True)
    duration_minutes = models.IntegerField(default=30, help_text="Estimated completion time in minutes")
    content = models.JSONField(default=list, help_text="List of topics/sections")
    resources = models.JSONField(default=list, help_text="Links to documents, videos, etc.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_modules'
    )

    multimedia_files = models.JSONField(
        default=list,
        help_text="List of multimedia files (images, videos, audio, documents)"
    )
    
    # Update the resources field to be more specific
    resources = models.JSONField(
        default=list,
        help_text="List of external resources (links to documents, websites, etc.)"
    )
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'Onboarding Module'
        verbose_name_plural = 'Onboarding Modules'
        indexes = [
            models.Index(fields=['module_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        if self.module_type == 'core':
            return f"{self.title} (Core)"
        departments = self.departments.all()
        if departments.exists():
            dept_names = ", ".join([dept.name for dept in departments[:3]])
            if departments.count() > 3:
                dept_names += f" and {departments.count() - 3} more"
            return f"{self.title} - Departments: {dept_names}"
        return f"{self.title} (No Departments)"
    
    def get_applicable_departments(self):
        """Get list of departments this module applies to"""
        if self.module_type == 'core':
            return 'All Departments'
        departments = self.departments.all()
        if departments.exists():
            return [dept.name for dept in departments]
        return ['No Departments']
    
    def is_applicable_to_department(self, department):
        """Check if module applies to specific department"""
        if self.module_type == 'core':
            return True
        
        # Handle both Department object, department ID, and department name
        if isinstance(department, int):
            return self.departments.filter(id=department).exists()
        elif isinstance(department, str):
            return self.departments.filter(name=department).exists()
        else:
            return self.departments.filter(id=department.id).exists()
    
    def calculate_days_to_complete(self):
        """Calculate estimated days to complete based on duration"""
        hours_per_day = 4  # Assuming 4 hours per day for onboarding
        total_hours = self.duration_minutes / 60
        return round(total_hours / hours_per_day, 1)
    
    def get_completion_rate(self, department=None):
        """Get completion rate for this module, optionally filtered by department"""
        progress_query = self.mentee_progress.all()
        
        if department:
            progress_query = progress_query.filter(mentee__department=department)
        
        total_assigned = progress_query.count()
        if total_assigned == 0:
            return 0
        
        completed = progress_query.filter(status='completed').count()
        return round((completed / total_assigned) * 100, 2)
    
    def get_average_time_to_complete(self, department=None):
        """Get average time taken by mentees to complete this module"""
        completed_progress = self.mentee_progress.filter(
            status='completed',
            time_spent_minutes__gt=0
        )
        
        if department:
            # Handle both Department object and department ID
            if isinstance(department, int):
                completed_progress = completed_progress.filter(mentee__department_id=department)
            else:
                completed_progress = completed_progress.filter(mentee__department=department)
        
        if completed_progress.exists():
            avg_time = completed_progress.aggregate(
                avg_time=Avg('time_spent_minutes')
            )['avg_time']
            return round(avg_time, 1) if avg_time else None
        return None
    
    def get_department_stats(self):
        """Get statistics by department"""
        departments = self.departments.all()
        stats = []
        
        for department in departments:
            # FIXED: Use department FK relationship properly
            dept_progress = self.mentee_progress.filter(mentee__department=department)
            total = dept_progress.count()
            completed = dept_progress.filter(status='completed').count()
            completion_rate = round((completed / total * 100), 2) if total > 0 else 0
            
            # Calculate average time spent, handling None values
            avg_time_result = dept_progress.aggregate(avg=Avg('time_spent_minutes'))
            avg_time = avg_time_result['avg'] if avg_time_result['avg'] is not None else 0
            
            stats.append({
                'department_id': department.id,
                'department_name': department.name,
                'total_assigned': total,
                'completed': completed,
                'completion_rate': completion_rate,
                'avg_time_spent': round(avg_time, 2)
            })
        
        return stats
    

    def add_file(self, file_data):
        """Add a file to module's multimedia files"""
        if not self.multimedia_files:
            self.multimedia_files = []
        
        # Create unique ID for file
        if 'id' not in file_data:
            file_data['id'] = str(uuid.uuid4())
        
        self.multimedia_files.append(file_data)
        self.save()
    
    def remove_file(self, file_id):
        """Remove a file from module's multimedia files"""
        if not self.multimedia_files:
            return False
        
        original_length = len(self.multimedia_files)
        self.multimedia_files = [
            file for file in self.multimedia_files 
            if file.get('id') != file_id
        ]
        
        if len(self.multimedia_files) < original_length:
            self.save()
            return True
        
        return False
    
    def get_files_by_type(self, file_type=None):
        """Get files filtered by type"""
        if not self.multimedia_files:
            return []
        
        if file_type:
            return [
                file for file in self.multimedia_files 
                if file.get('type') == file_type
            ]
        
        return self.multimedia_files


class MenteeOnboardingProgress(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('overdue', 'Overdue'),
        ('paused', 'Paused'),
        ('needs_attention', 'Needs Attention'),
        ('off_track', 'Off Track'),
    ]
    
    mentee = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': 'mentee'},
        related_name='onboarding_progress'
    )
    module = models.ForeignKey(
        OnboardingModule, 
        on_delete=models.CASCADE,
        related_name='mentee_progress'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    progress_percentage = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True, help_text="Expected completion date")
    notes = models.TextField(blank=True, null=True, help_text="Mentee notes or feedback")
    time_spent_minutes = models.IntegerField(default=0, help_text="Time spent on this module")
    last_updated = models.DateTimeField(auto_now=True)
    assigned_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_onboarding_modules',
        help_text="User who assigned this module"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['mentee', 'module']
        ordering = ['module__order']
        verbose_name = 'Mentee Onboarding Progress'
        verbose_name_plural = 'Mentee Onboarding Progress'
        indexes = [
            models.Index(fields=['mentee', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            # Removed the problematic index on 'mentee__department'
        ]
    
    def __str__(self):
        return f"{self.mentee.full_name} - {self.module.title} ({self.status})"
    
    def save(self, *args, **kwargs):
        """Override save to set due date when started and auto-calculate status"""
        is_new = self.pk is None
        
        if self.started_at and not self.due_date:
            # Set due date to 2 weeks from start date
            from datetime import timedelta
            self.due_date = self.started_at + timedelta(days=14)
        
        # Auto-calculate status based on progress if not completed
        if self.status != 'completed' and not is_new:
            self.status = self.calculate_auto_status()
        
        super().save(*args, **kwargs)
    
    def calculate_auto_status(self):
        """Automatically calculate status based on progress and time"""
        if self.progress_percentage == 100:
            return 'completed'
        
        if self.progress_percentage == 0 and not self.started_at:
            return 'not_started'
        
        if self.progress_percentage > 0:
            if self.started_at:
                from datetime import timedelta
                days_since_start = (now() - self.started_at).days
                
                # Check for overdue
                if self.due_date and now() > self.due_date:
                    return 'overdue'
                
                # Check for off-track (very slow progress)
                if days_since_start >= 7 and self.progress_percentage < 30:
                    return 'off_track'
                
                # Check for needs attention (slow progress)
                if days_since_start >= 3 and self.progress_percentage < 50:
                    return 'needs_attention'
                
                return 'in_progress'
        
        return self.status
    
    def get_department(self):
        """Get mentee's department"""
        return self.mentee.department
    
    def mark_as_started(self):
        """Mark module as started"""
        if not self.started_at:
            self.started_at = now()
            self.status = 'in_progress'
            self.save()
    
    def mark_as_completed(self):
        """Mark module as completed"""
        if self.status != 'completed':
            self.status = 'completed'
            self.progress_percentage = 100
            self.completed_at = now()
            self.save()
    
    def update_progress(self, percentage):
        """Update progress percentage"""
        if 0 <= percentage <= 100:
            self.progress_percentage = percentage
            
            # Auto-start if not started
            if not self.started_at and percentage > 0:
                self.started_at = now()
            
            # Auto-complete if 100%
            if percentage == 100:
                self.status = 'completed'
                self.completed_at = now()
            elif percentage > 0:
                self.status = 'in_progress'
            
            self.save()
    
    def add_time_spent(self, minutes):
        """Add time spent on module"""
        if minutes > 0:
            self.time_spent_minutes += minutes
            self.save()
    
    def is_overdue(self):
        """Check if module is overdue"""
        if self.due_date and self.status != 'completed':
            return now() > self.due_date
        return False
    
    def get_progress_speed(self):
        """Calculate progress speed (percentage per day)"""
        if self.started_at and self.progress_percentage > 0:
            days_elapsed = (now() - self.started_at).days
            if days_elapsed > 0:
                return round(self.progress_percentage / days_elapsed, 2)
        return 0


class OnboardingChecklist(models.Model):
    """Individual checklist items within a module"""
    module = models.ForeignKey(
        OnboardingModule, 
        on_delete=models.CASCADE,
        related_name='checklist_items'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    is_required = models.BooleanField(default=True)
    estimated_minutes = models.IntegerField(default=15, help_text="Estimated time to complete this item")
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Checklist Item'
        verbose_name_plural = 'Checklist Items'
        indexes = [
            models.Index(fields=['module', 'order']),
        ]
    
    def __str__(self):
        return f"{self.module.title} - {self.title}"
    
    def get_completion_rate(self, department=None):
        """Get completion rate for this module, optionally filtered by department"""
        progress_query = self.mentee_progress.all()
        
        if department:
            # Handle both Department object and department ID
            if isinstance(department, int):
                progress_query = progress_query.filter(mentee__department_id=department)
            else:
                progress_query = progress_query.filter(mentee__department=department)
        
        total_assigned = progress_query.count()
        if total_assigned == 0:
            return 0
        
        completed = progress_query.filter(status='completed').count()
        return round((completed / total_assigned) * 100, 2)

class MenteeChecklistProgress(models.Model):
    """Track individual checklist item completion"""
    mentee = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='checklist_progress'
    )
    checklist_item = models.ForeignKey(
        OnboardingChecklist, 
        on_delete=models.CASCADE,
        related_name='mentee_completions'
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_minutes = models.IntegerField(default=0, help_text="Time spent on this checklist item")
    notes = models.TextField(blank=True, null=True, help_text="Notes about this checklist item")
    
    class Meta:
        unique_together = ['mentee', 'checklist_item']
        verbose_name = 'Checklist Progress'
        verbose_name_plural = 'Checklist Progress'
        indexes = [
            models.Index(fields=['mentee', 'is_completed']),
            models.Index(fields=['checklist_item', 'is_completed']),
        ]
    
    def __str__(self):
        status = "Completed" if self.is_completed else "Not Completed"
        return f"{self.mentee.full_name} - {self.checklist_item.title} ({status})"
    
    def mark_completed(self):
        """Mark checklist item as completed"""
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = now()
            self.save()
    
    def mark_incomplete(self):
        """Mark checklist item as incomplete"""
        self.is_completed = False
        self.completed_at = None
        self.save()
    
    def update_time_spent(self, minutes):
        """Update time spent on this checklist item"""
        if minutes >= 0:
            self.time_spent_minutes = minutes
            self.save()
    
    def add_time_spent(self, minutes):
        """Add time spent on this checklist item"""
        if minutes > 0:
            self.time_spent_minutes += minutes
            self.save()
    
    def get_completion_time(self):
        """Get completion time in minutes"""
        if self.completed_at and self.checklist_item.module:
            # Find the module progress record
            module_progress = MenteeOnboardingProgress.objects.filter(
                mentee=self.mentee,
                module=self.checklist_item.module
            ).first()
            
            if module_progress and module_progress.started_at:
                time_to_complete = (self.completed_at - module_progress.started_at).total_seconds() / 60
                return round(time_to_complete, 1)
        return None


class OnboardingNotification(models.Model):
    """Track notifications sent for onboarding activities"""
    NOTIFICATION_TYPES = [
        ('module_assigned', 'Module Assigned'),
        ('module_started', 'Module Started'),
        ('module_completed', 'Module Completed'),
        ('deadline_approaching', 'Deadline Approaching'),
        ('status_changed', 'Status Changed'),
        ('needs_attention', 'Needs Attention'),
        ('off_track', 'Off Track'),
        ('overdue', 'Overdue'),
    ]
    
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='onboarding_notifications'
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_module = models.ForeignKey(
        OnboardingModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_progress = models.ForeignKey(
        MenteeOnboardingProgress,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Onboarding Notification'
        verbose_name_plural = 'Onboarding Notifications'
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f"{self.recipient.full_name} - {self.notification_type} - {self.sent_at.strftime('%Y-%m-%d %H:%M')}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = now()
            self.save()


class OnboardingDeadline(models.Model):
    """Track deadlines for onboarding modules"""
    module = models.ForeignKey(
        OnboardingModule,
        on_delete=models.CASCADE,
        related_name='deadlines'
    )
    mentee = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'mentee'},
        related_name='onboarding_deadlines'
    )
    due_date = models.DateTimeField()
    original_due_date = models.DateTimeField(help_text="Original due date before any extensions")
    is_extended = models.BooleanField(default=False)
    extension_reason = models.TextField(blank=True, null=True, help_text="Reason for extension")
    extension_granted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_extensions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['module', 'mentee']
        ordering = ['due_date']
        verbose_name = 'Onboarding Deadline'
        verbose_name_plural = 'Onboarding Deadlines'
        indexes = [
            models.Index(fields=['due_date']),
            models.Index(fields=['mentee', 'due_date']),
        ]
    
    def __str__(self):
        status = "Extended" if self.is_extended else "Original"
        return f"{self.mentee.full_name} - {self.module.title} ({status})"
    
    def is_overdue(self):
        """Check if deadline is overdue"""
        return now() > self.due_date
    
    def get_days_remaining(self):
        """Get days remaining until deadline"""
        remaining = self.due_date - now()
        if remaining.days < 0:
            return 0
        return remaining.days
    
    def extend_deadline(self, new_due_date, reason=None, granted_by=None):
        """Extend the deadline"""
        self.is_extended = True
        self.original_due_date = self.due_date
        self.due_date = new_due_date
        self.extension_reason = reason
        self.extension_granted_by = granted_by
        self.save()