from django.db import models
from django.conf import settings
from django.utils.timezone import now
from userApp.models import CustomUser
from incidentApp.models import Incident
from complianceAuditApp.models import ComplianceAudit

class Notification(models.Model):
    """Model for user notifications"""
    
    NOTIFICATION_TYPES = [
        ('incident_assigned', 'Incident Assigned'),
        ('incident_updated', 'Incident Updated'),
        ('incident_resolved', 'Incident Resolved'),
        ('incident_escalated', 'Incident Escalated'),
        ('sla_violation', 'SLA Violation'),
        ('audit_required', 'Audit Required'),
        ('audit_completed', 'Audit Completed'),
        ('finding_assigned', 'Finding Assigned'),
        ('finding_due', 'Finding Due'),
        ('compliance_alert', 'Compliance Alert'),
        ('system_alert', 'System Alert'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # User who receives the notification
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    # Notification details
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Related objects (optional)
    incident = models.ForeignKey(
        Incident,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    audit = models.ForeignKey(
        ComplianceAudit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Status tracking
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Action link (where to go when clicked)
    action_link = models.CharField(max_length=500, blank=True, null=True)
    action_text = models.CharField(max_length=100, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.notification_type} - {self.created_at}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = now()
            self.save()
    
    def mark_as_unread(self):
        """Mark notification as unread"""
        self.is_read = False
        self.read_at = None
        self.save()
    
    @property
    def is_urgent(self):
        return self.priority in ['high', 'urgent']
    
    @property
    def time_ago(self):
        from django.utils.timesince import timesince
        return timesince(self.created_at)


class NotificationPreference(models.Model):
    """User preferences for notifications"""
    
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Enable/disable specific notification types
    incident_assigned = models.BooleanField(default=True)
    incident_updated = models.BooleanField(default=True)
    incident_resolved = models.BooleanField(default=True)
    incident_escalated = models.BooleanField(default=True)
    sla_violation = models.BooleanField(default=True)
    audit_required = models.BooleanField(default=True)
    audit_completed = models.BooleanField(default=True)
    finding_assigned = models.BooleanField(default=True)
    finding_due = models.BooleanField(default=True)
    compliance_alert = models.BooleanField(default=True)
    system_alert = models.BooleanField(default=True)
    
    # Email preferences
    email_notifications = models.BooleanField(default=True)
    in_app_notifications = models.BooleanField(default=True)
    
    # Frequency
    email_frequency = models.CharField(
        max_length=20,
        choices=[
            ('instant', 'Instant'),
            ('daily', 'Daily Digest'),
            ('weekly', 'Weekly Digest'),
        ],
        default='instant'
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"{self.user.email} - Notification Preferences"




        