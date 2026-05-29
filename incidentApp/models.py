import os
from django.conf import settings
from django.db import models
from django.utils.timezone import now
from userApp.models import CustomUser
from django.core.exceptions import ValidationError
import uuid
import random
from django.utils.crypto import get_random_string
import re

class Incident(models.Model):
    """Model for tracking user log incidents that are in danger zone"""
    
    INCIDENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('investigating', 'Investigating'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('escalated', 'Escalated'),
    ]
    
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # System-generated incident number (different from primary key)
    incident_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        help_text="System-generated incident number"
    )
    
    # Reference to the log that triggered this incident
    log = models.ForeignKey(
        'userApp.UserLog',
        on_delete=models.CASCADE,
        related_name='incidents',
        help_text="The log that triggered this incident"
    )
    
    # Assignment information - NO AUTO-ASSIGNMENT
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_incidents',
        help_text="User assigned to handle this incident (manual assignment only)",
        limit_choices_to=models.Q(role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer'])
    )
    
    # Incident details
    title = models.CharField(
        max_length=200,
        help_text="Brief title describing the incident"
    )
    
    description = models.TextField(
        help_text="Detailed description of the incident"
    )
    
    status = models.CharField(
        max_length=20,
        choices=INCIDENT_STATUS_CHOICES,
        default='pending'
    )
    
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default='medium'
    )
    
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    
    # Risk assessment fields
    risk_score = models.IntegerField(
        default=0,
        help_text="Risk score (0-100)"
    )
    
    danger_zone = models.BooleanField(
        default=True,
        help_text="Whether this incident is in the danger zone"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Resolution information
    resolution_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes on how the incident was resolved"
    )
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_incidents',
        help_text="User who created/triggered this incident record"
    )
    
    # Department information - Better auto-detection
    department = models.ForeignKey(
        'departmentApp.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incidents',
        help_text="Department related to this incident (auto-detected from user)"
    )
    
    # SLA tracking - CONFIGURABLE, NOT AUTO-CALCULATED
    sla_due_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Due date based on SLA (must be set manually)"
    )
    
    sla_violated = models.BooleanField(
        default=False,
        help_text="Whether SLA was violated"
    )
    
    # Escalation tracking
    escalation_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for escalating the incident"
    )
    
    escalated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='escalated_incidents',
        help_text="User who escalated the incident"
    )
    
    escalated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['incident_number']),
            models.Index(fields=['status']),
            models.Index(fields=['severity']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['danger_zone']),
            models.Index(fields=['created_at']),
            models.Index(fields=['sla_due_date']),
            models.Index(fields=['sla_violated']),
        ]
        verbose_name = 'Incident'
        verbose_name_plural = 'Incidents'
    
    def __str__(self):
        return f"{self.incident_number} - {self.title}"
    
    def clean(self):
        """Validate the incident data"""
        super().clean()
        
        # Validate SLA due date is in future ONLY for new incidents or when actively updating SLA
        # Skip this validation if incident is being resolved/closed or already has a past SLA
        if self.sla_due_date:
            # Allow past SLA dates if:
            # 1. Incident already exists (self.pk is set)
            # 2. Status is resolved or closed
            # 3. Or we're just updating other fields
            is_resolved_or_closed = self.status in ['resolved', 'closed']
            is_existing_incident = bool(self.pk)
            
            # Only enforce future SLA for NEW incidents or when explicitly changing SLA
            if not is_existing_incident and not is_resolved_or_closed:
                if self.sla_due_date <= now():
                    raise ValidationError({
                        'sla_due_date': 'SLA due date must be in the future.'
                    })
            elif is_existing_incident and not is_resolved_or_closed:
                # For existing incidents, only validate if SLA is being actively changed
                try:
                    old_instance = Incident.objects.get(pk=self.pk)
                    # Only validate if SLA is being changed to a new value
                    if old_instance.sla_due_date != self.sla_due_date:
                        if self.sla_due_date <= now():
                            raise ValidationError({
                                'sla_due_date': 'SLA due date must be in the future when updating SLA.'
                            })
                except Incident.DoesNotExist:
                    pass
        
        # Validate assigned user has appropriate role
        if self.assigned_to and self.assigned_to.role not in ['admin', 'hr_manager', 'security_analyst', 'compliance_officer']:
            raise ValidationError({
                'assigned_to': 'Only admin, HR, security analysts, or compliance officers can be assigned incidents.'
            })
        
        # Validate status transitions
        if self.pk:
            old_instance = Incident.objects.get(pk=self.pk)
            self.validate_status_transition(old_instance.status, self.status)




    def validate_status_transition(self, old_status, new_status):
        """Validate status transitions"""
        # Allow same status (for reassignments, updates, etc.)
        if old_status == new_status:
            return
        
        allowed_transitions = {
            'pending': ['investigating', 'assigned'],
            'investigating': ['assigned', 'in_progress', 'pending'],
            'assigned': ['in_progress', 'escalated', 'investigating'],
            'in_progress': ['resolved', 'escalated', 'assigned'],
            'resolved': ['closed', 'in_progress'],
            'escalated': ['assigned', 'in_progress'],
            'closed': []  # No transitions from closed
        }
        
        if old_status in allowed_transitions:
            if new_status not in allowed_transitions[old_status]:
                raise ValidationError({
                    'status': f'Cannot change status from {old_status} to {new_status}.'
                })
            
    def save(self, *args, **kwargs):
        """Save incident with enhanced logic"""
        # Generate incident number if not exists
        if not self.incident_number:
            self.incident_number = self.generate_incident_number()
        
        # Set created_by if not set and we have a request context
        if not self.created_by and hasattr(self, '_request_user'):
            self.created_by = self._request_user
        
        # Auto-detect department if not set
        if not self.department:
            self.assign_department_based_on_user()
        
        # Set escalation timestamp if status changed to escalated
        if self.pk:
            old_instance = Incident.objects.get(pk=self.pk)
            if old_instance.status != 'escalated' and self.status == 'escalated':
                self.escalated_at = now()
        
        # Set resolved timestamp if status changed to resolved
        if self.pk:
            old_instance = Incident.objects.get(pk=self.pk)
            if old_instance.status != 'resolved' and self.status == 'resolved':
                self.resolved_at = now()
        
        # Set assigned timestamp if assigned_to changed
        if self.pk:
            old_instance = Incident.objects.get(pk=self.pk)
            if (not old_instance.assigned_to and self.assigned_to) or \
               (old_instance.assigned_to and self.assigned_to and 
                old_instance.assigned_to != self.assigned_to):
                self.assigned_at = now()
        
        # Check SLA violation
        self.check_sla_violation()
        
        # Full clean before save
        self.full_clean()
        
        super().save(*args, **kwargs)
        
        # Create activity log
        self.create_activity_log()
    
    @staticmethod
    def generate_incident_number():
        """Generate unique incident number"""
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        random_str = get_random_string(6, '0123456789')
        return f"INC-{date_str}-{random_str}"
    
    def assign_department_based_on_user(self):
        """Intelligently assign department based on user and log context"""
        if not self.log or not self.log.user:
            return
        
        user = self.log.user
        
        # 1. Try user's primary department
        if user.role == 'employee' and user.department:
            self.department = user.department
            return
        
        # 2. For security analysts, find relevant department
        if user.role == 'security_analyst' and user.departments.exists():
            relevant_dept = self.find_relevant_department_for_analyst(user)
            if relevant_dept:
                self.department = relevant_dept
                return
        
        # 3. Check log target department
        if self.log.target_department:
            self.department = self.log.target_department
            return
        
        # 4. Extract from description
        self.extract_department_from_description()
    
    def find_relevant_department_for_analyst(self, user):
        """Find relevant department for security analyst based on incident context"""
        from departmentApp.models import Department
        
        departments = user.departments.all()
        if not departments.exists():
            return None
        
        # Combine all text for searching
        search_text = ""
        if self.description:
            search_text += self.description.lower()
        if self.log and self.log.description:
            search_text += " " + self.log.description.lower()
        if self.title:
            search_text += " " + self.title.lower()
        
        # Try exact department name match
        for dept in departments:
            dept_name_lower = dept.name.lower()
            if dept_name_lower in search_text:
                return dept
        
        # Try partial match or keywords
        for dept in departments:
            # Check for department keywords
            keywords = dept.name.lower().split()
            for keyword in keywords:
                if len(keyword) > 3 and keyword in search_text:
                    return dept
        
        # Return first department as fallback
        return departments.first()
    
    def extract_department_from_description(self):
        """Extract department name from description using regex patterns"""
        if not self.description:
            return
        
        from departmentApp.models import Department
        
        description_lower = self.description.lower()
        
        # Common department name patterns
        patterns = [
            r'department[:\s]+([A-Za-z\s]+)',
            r'dept[:\s]+([A-Za-z\s]+)',
            r'team[:\s]+([A-Za-z\s]+)',
            r'division[:\s]+([A-Za-z\s]+)',
            r'unit[:\s]+([A-Za-z\s]+)',
        ]
        
        for pattern in patterns:
            matches = re.search(pattern, description_lower, re.IGNORECASE)
            if matches:
                dept_name = matches.group(1).strip().title()
                try:
                    dept = Department.objects.get(name__iexact=dept_name, status='active')
                    self.department = dept
                    break
                except Department.DoesNotExist:
                    continue
    
    def check_sla_violation(self):
        """Check and update SLA violation status"""
        from django.utils.timezone import now
        
        if self.sla_due_date and now() > self.sla_due_date:
            self.sla_violated = True
        else:
            self.sla_violated = False
    
    def set_sla_due_date(self, due_date=None, default_hours=24):
        """Set SLA due date with optional default"""
        from datetime import timedelta
        
        if due_date:
            self.sla_due_date = due_date
        elif not self.sla_due_date:
            # Set default based on severity if no date provided
            default_hours_map = {
                'critical': 2,
                'high': 4,
                'medium': 24,
                'low': 72
            }
            hours = default_hours_map.get(self.severity, default_hours)
            self.sla_due_date = now() + timedelta(hours=hours)
        
        # Re-check violation status
        self.check_sla_violation()
    
    def create_activity_log(self):
        """Create activity log entry for this incident"""
        from userApp.utils import ActivityLogger
        
        # Skip if no user context
        if not hasattr(self, '_request_user'):
            return
        
        user = self._request_user
        activity_type = 'incident_updated'
        
        # Determine activity type based on changes
        if not self.pk:  # New incident
            activity_type = 'incident_created'
        elif hasattr(self, '_status_changed') and self._status_changed:
            activity_type = 'incident_status_change'
        elif hasattr(self, '_assigned_changed') and self._assigned_changed:
            activity_type = 'incident_assigned'
        
        description = f"Incident {self.incident_number}: {self.title}"
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity=activity_type,
            description=description,
            is_success=True,
            target_user=self.assigned_to
        )
    
    def escalate(self, reason, escalated_by):
        """Escalate incident to higher priority"""
        severity_levels = ['low', 'medium', 'high', 'critical']
        current_index = severity_levels.index(self.severity)
        
        # Increase severity if not already critical
        if current_index < len(severity_levels) - 1:
            self.severity = severity_levels[current_index + 1]
        
        self.status = 'escalated'
        self.escalation_reason = reason
        self.escalated_by = escalated_by
        self.escalated_at = now()
        
        # Increase priority if not already urgent
        if self.priority != 'urgent':
            priority_levels = ['low', 'medium', 'high', 'urgent']
            current_priority_index = priority_levels.index(self.priority)
            if current_priority_index < len(priority_levels) - 1:
                self.priority = priority_levels[current_priority_index + 1]
    
    @property
    def is_overdue(self):
        """Check if incident is overdue (past SLA)"""
        from django.utils.timezone import now
        if self.sla_due_date:
            return now() > self.sla_due_date
        return False
    
    @property
    def time_to_resolution(self):
        """Calculate time to resolution"""
        if self.resolved_at and self.created_at:
            return self.resolved_at - self.created_at
        return None
    
    @property
    def time_to_deadline(self):
        """Calculate time remaining to SLA deadline"""
        from django.utils.timezone import now
        if self.sla_due_date and not self.sla_violated:
            return self.sla_due_date - now()
        return None
    
    @property
    def is_assigned(self):
        """Check if incident is assigned"""
        return self.assigned_to is not None and self.status == 'assigned'
    
    @property
    def requires_attention(self):
        """Check if incident requires attention"""
        if self.status in ['closed', 'resolved']:
            return False
        if self.sla_violated:
            return True
        if self.severity in ['critical', 'high'] and self.status not in ['in_progress', 'escalated']:
            return True
        return False
    
    def get_assigned_user_info(self):
        """Get information about assigned user"""
        if not self.assigned_to:
            return None
        
        return {
            'id': self.assigned_to.id,
            'full_name': self.assigned_to.full_name,
            'email': self.assigned_to.email,
            'work_mail': self.assigned_to.work_mail_address,
            'role': self.assigned_to.role,
            'phone_number': self.assigned_to.phone_number,
            'availability_status': self.assigned_to.availability_status
        }
    
    def get_progress_percentage(self):
        """Get progress percentage based on status"""
        progress_map = {
            'pending': 10,
            'investigating': 25,
            'assigned': 40,
            'in_progress': 70,
            'resolved': 90,
            'closed': 100,
            'escalated': 50
        }
        return progress_map.get(self.status, 0)
    
    def get_tracking_info(self):
        """Get comprehensive tracking information"""
        from django.utils.timezone import now
        
        info = {
            'incident_number': self.incident_number,
            'title': self.title,
            'status': self.status,
            'severity': self.severity,
            'priority': self.priority,
            'assigned_to': self.get_assigned_user_info(),
            'department': self.department.name if self.department else None,
            'progress_percentage': self.get_progress_percentage(),
            'created_at': self.created_at,
            'assigned_at': self.assigned_at,
            'resolved_at': self.resolved_at,
            'sla_due_date': self.sla_due_date,
            'sla_violated': self.sla_violated,
            'is_overdue': self.is_overdue,
            'requires_attention': self.requires_attention,
            'time_to_deadline': self.time_to_deadline.total_seconds() if self.time_to_deadline else None,
            'time_to_resolution': self.time_to_resolution.total_seconds() if self.time_to_resolution else None,
        }
        
        # Add status-specific information
        if self.status == 'pending':
            info['next_action'] = 'Assign to appropriate user'
            info['expected_duration'] = '24 hours max'
        elif self.status == 'assigned':
            info['next_action'] = 'Begin investigation'
            info['expected_duration'] = 'Based on severity'
        elif self.status == 'in_progress':
            info['next_action'] = 'Complete resolution steps'
            info['expected_duration'] = 'Until SLA deadline'
        elif self.status == 'resolved':
            info['next_action'] = 'Review and close incident'
            info['expected_duration'] = '48 hours for review'
        
        return info



        
class IncidentComment(models.Model):
    """Model for comments on incidents"""
    
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='incident_comments'
    )
    
    comment = models.TextField()
    
    is_internal = models.BooleanField(
        default=False,
        help_text="Whether this is an internal note (not visible to all)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['incident', 'created_at']),
        ]
    
    def __str__(self):
        return f"Comment by {self.user.email} on {self.incident.incident_number}"


class IncidentAttachment(models.Model):
    """Model for attachments related to incidents"""
    
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    
    file = models.FileField(
        upload_to='incident_attachments/%Y/%m/%d/'
    )
    
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.IntegerField()
    
    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True
    )
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.file_name} - {self.incident.incident_number}"


class Report(models.Model):
    """Model for generated reports"""
    
    REPORT_TYPE_CHOICES = [
        ('security', 'Security Report'),
        ('compliance', 'Compliance Report'),
        ('access_control', 'Access Control Report'),
        ('incident', 'Incident Report'),
        ('user_activity', 'User Activity Report'),
        ('ai_analytics', 'AI Analytics Report'),
        ('custom', 'Custom Report'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('html', 'HTML'),
        ('json', 'JSON'),
    ]
    
    # System-generated report number
    report_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPE_CHOICES
    )
    
    format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        default='pdf'
    )
    
    # File storage
    file_path = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Relative path to report file from MEDIA_ROOT"
    )
    
    file_size = models.IntegerField(null=True, blank=True)
    
    # Generation information
    generated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='incident_reports',  # Changed from 'generated_reports'
        related_query_name='incident_report'  # Added
    )
    
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Report parameters (stored as JSON)
    parameters = models.JSONField(
        default=dict,
        help_text="Parameters used to generate this report"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata about the report (email status, etc.)"
    )
    
    # Schedule information (if scheduled)
    is_scheduled = models.BooleanField(default=False)
    schedule_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Access control
    is_public = models.BooleanField(
        default=False,
        help_text="Whether this report is publicly accessible"
    )
    
    shared_with = models.ManyToManyField(
        CustomUser,
        related_name='shared_reports',
        blank=True,
        help_text="Users this report is shared with"
    )
    
    # Metadata
    download_count = models.IntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['report_number']),
            models.Index(fields=['report_type']),
            models.Index(fields=['generated_by']),
            models.Index(fields=['generated_at']),
        ]
    
    def __str__(self):
        return f"{self.report_number} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.report_number:
            self.report_number = self.generate_report_number()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_report_number():
        """Generate unique report number"""
        import datetime
        date_str = datetime.datetime.now().strftime('%Y%m%d')
        random_str = get_random_string(8, '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        return f"REP-{date_str}-{random_str}"
    
    def increment_download_count(self):
        """Increment download count"""
        from django.utils.timezone import now
        self.download_count += 1
        self.last_downloaded_at = now()
        self.save()
    
    @property
    def file_url(self):
        """Get absolute file URL"""
        if self.file_path:
            # Convert to absolute path for serving
            if self.file_path.startswith('http'):
                return self.file_path
            return f"{settings.MEDIA_URL}{self.file_path}"
        return None
    
    def get_absolute_file_path(self):
        """Get absolute file path on disk - FIXED VERSION"""
        if not self.file_path:
            return None
        
        # If file_path already contains MEDIA_ROOT (old bug), strip it
        if self.file_path.startswith(settings.MEDIA_ROOT):
            # This shouldn't happen with new code, but handle legacy data
            return self.file_path
        
        # Construct absolute path from MEDIA_ROOT + relative path
        absolute_path = os.path.join(settings.MEDIA_ROOT, self.file_path)
        
        # Normalize path (handle any .. or . in path)
        absolute_path = os.path.normpath(absolute_path)
        
        return absolute_path

class ReportSchedule(models.Model):
    """Model for scheduled report generation"""
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    report_type = models.CharField(
        max_length=20,
        choices=Report.REPORT_TYPE_CHOICES
    )
    
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES
    )
    
    # Schedule details
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Cron expression for custom schedules"
    )
    
    # Time settings
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField()
    last_run = models.DateTimeField(null=True, blank=True)
    
    # Generation parameters
    parameters = models.JSONField(
        default=dict,
        help_text="Parameters for report generation"
    )
    
    format = models.CharField(
        max_length=10,
        choices=Report.FORMAT_CHOICES,
        default='pdf'
    )
    
    # Recipients
    recipients = models.ManyToManyField(
        CustomUser,
        related_name='scheduled_reports',
        help_text="Users who receive this scheduled report"
    )
    
    # Additional email recipients
    additional_emails = models.TextField(
        blank=True,
        null=True,
        help_text="Comma-separated list of additional email addresses"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='created_schedules'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['next_run']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['next_run']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.frequency})"
    
    def save(self, *args, **kwargs):
        if not self.next_run:
            self.next_run = self.calculate_next_run()
        super().save(*args, **kwargs)
    
    def calculate_next_run(self):
        """Calculate next run based on frequency"""
        from django.utils.timezone import now
        from datetime import timedelta
        
        if self.frequency == 'daily':
            return now() + timedelta(days=1)
        elif self.frequency == 'weekly':
            return now() + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            return now() + timedelta(days=30)
        elif self.frequency == 'quarterly':
            return now() + timedelta(days=90)
        elif self.frequency == 'yearly':
            return now() + timedelta(days=365)
        
        return now() + timedelta(days=1)
    
    def execute_schedule(self):
        """Execute the scheduled report generation"""
        from .utils import generate_report
        
        try:
            # Generate report
            report = generate_report(
                report_type=self.report_type,
                parameters=self.parameters,
                format=self.format,
                generated_by=self.created_by,
                title=f"Scheduled: {self.name}"
            )
            
            # Update schedule
            self.last_run = now()
            self.next_run = self.calculate_next_run()
            self.save()
            
            # Send emails to recipients
            self.send_report_emails(report)
            
            return report
            
        except Exception as e:
            # Log error
            print(f"Error executing schedule {self.id}: {str(e)}")
            return None
    
    def send_report_emails(self, report):
        """Send report to recipients via email"""
        from django.core.mail import EmailMessage
        from django.conf import settings
        import os
        
        try:
            subject = f"Scheduled Report: {self.name}"
            message = f"""
            The scheduled report "{self.name}" has been generated.
            
            Report Details:
            - Title: {report.title}
            - Type: {report.get_report_type_display()}
            - Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
            - Format: {report.get_format_display()}
            
            You can download the report from the system.
            """
            
            # Get all recipient emails
            recipient_emails = list(self.recipients.values_list('email', flat=True))
            
            # Add additional emails
            if self.additional_emails:
                additional = [email.strip() for email in self.additional_emails.split(',')]
                recipient_emails.extend(additional)
            
            if recipient_emails:
                email = EmailMessage(
                    subject=subject,
                    body=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=recipient_emails,
                )
                
                # Attach report file if exists
                if report.file_path and os.path.exists(report.file_path.path):
                    with open(report.file_path.path, 'rb') as file:
                        email.attach(
                            f"{report.title}.{report.format}",
                            file.read(),
                            f'application/{report.format}'
                        )
                
                email.send()
                
        except Exception as e:
            print(f"Error sending report emails: {str(e)}")