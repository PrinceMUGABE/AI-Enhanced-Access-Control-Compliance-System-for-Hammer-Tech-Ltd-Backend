# notificationApp/models.py - FIXED

from django.db import models
from django.utils.timezone import now
from userApp.models import CustomUser
from mentorshipApp.models import Mentorship
from chatApp.models import ChatRoom


class UserNotificationManager(models.Manager):
    """Custom manager for user notifications"""
    
    def get_user_notifications(self, user, include_archived=False):
        """Get notifications for a specific user"""
        queryset = self.filter(recipient=user)
        
        if not include_archived:
            queryset = queryset.filter(is_archived=False)
        
        return queryset
    
    def get_unread_count(self, user):
        """Get count of unread notifications for a user"""
        return self.filter(recipient=user, is_read=False, is_archived=False).count()


class ChatNotification(models.Model):
    """
    Notifications for chat events
    """
    NOTIFICATION_TYPES = [
        ('new_message', 'New Message'),
        ('case_assigned', 'Case Assigned'),
        ('case_status_changed', 'Case Status Changed'),
        ('chat_created', 'Chat Created'),
        ('participant_added', 'Participant Added'),
        ('participant_removed', 'Participant Removed'),
        ('chat_archived', 'Chat Archived'),
        ('session_scheduled', 'Session Scheduled'),
        ('session_completed', 'Session Completed'),
        ('session_cancelled', 'Session Cancelled'),
        ('session_rescheduled', 'Session Rescheduled'),
        ('session_reminder', 'Session Reminder'),
        ('program_completed', 'Program Completed'),
        ('mentorship_completed', 'Mentorship Completed'),
    ]
    
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='chat_notifications'
    )
    sender = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        related_name='sent_chat_notifications',
        null=True,
        blank=True
    )
    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.SET_NULL,
        related_name='notifications',
        null=True,
        blank=True
    )
    mentorship = models.ForeignKey(
        Mentorship,
        on_delete=models.SET_NULL,
        related_name='notifications',
        null=True,
        blank=True
    )
    
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    
    # Set the custom manager CORRECTLY
    objects = UserNotificationManager()
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Chat Notification'
        verbose_name_plural = 'Chat Notifications'
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['created_at']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['is_archived']),
        ]
    
    def __str__(self):
        return f"Notification for {self.recipient.full_name}: {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = now()
            self.save()
    
    def mark_as_archived(self):
        """Archive notification"""
        if not self.is_archived:
            self.is_archived = True
            self.archived_at = now()
            self.save()
    
    def delete_notification(self):
        """Soft delete notification"""
        self.is_archived = True
        self.archived_at = now()
        self.save()


class SystemNotification(models.Model):
    """System-wide notifications"""
    NOTIFICATION_LEVELS = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('alert', 'Alert'),
        ('success', 'Success'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=NOTIFICATION_LEVELS, default='info')
    is_active = models.BooleanField(default=True)
    is_global = models.BooleanField(default=False, help_text="Show to all users")
    target_roles = models.JSONField(
        default=list,
        help_text="Specific roles to show notification to (empty for all)"
    )
    target_departments = models.JSONField(
        default=list,
        help_text="Specific departments to show notification to"
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_system_notifications'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'System Notification'
        verbose_name_plural = 'System Notifications'
    
    def __str__(self):
        return f"{self.title} ({self.level})"
    
    def is_active_now(self):
        """Check if notification is currently active"""
        if not self.is_active:
            return False
        
        now_time = now()
        if self.start_date > now_time:
            return False
        
        if self.end_date and self.end_date < now_time:
            return False
        
        return True
    
    def soft_delete(self):
        """Soft delete system notification"""
        self.is_active = False
        self.save()


class UserNotificationPreference(models.Model):
    """User notification preferences"""
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Chat notifications
    enable_chat_notifications = models.BooleanField(default=True)
    enable_message_notifications = models.BooleanField(default=True)
    enable_group_chat_notifications = models.BooleanField(default=True)
    enable_cross_department_notifications = models.BooleanField(default=True)
    
    # System notifications
    enable_system_notifications = models.BooleanField(default=True)
    enable_announcements = models.BooleanField(default=True)
    enable_updates = models.BooleanField(default=True)
    
    # Email notifications
    enable_email_notifications = models.BooleanField(default=True)
    email_frequency = models.CharField(
        max_length=20,
        choices=[
            ('instant', 'Instant'),
            ('daily', 'Daily Digest'),
            ('weekly', 'Weekly Digest'),
        ],
        default='instant'
    )
    
    # Push notifications
    enable_push_notifications = models.BooleanField(default=True)
    
    # Quiet hours
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    enable_quiet_hours = models.BooleanField(default=False)
    
    # Notification sound
    enable_sound = models.BooleanField(default=True)
    sound_name = models.CharField(max_length=50, default='default')
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Notification Preference'
        verbose_name_plural = 'User Notification Preferences'
    
    def __str__(self):
        return f"Notification preferences for {self.user.full_name}"
    
    def can_send_notification_now(self):
        """Check if notifications can be sent during current time"""
        if not self.enable_quiet_hours:
            return True
        
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return True
        
        from datetime import datetime
        current_time = datetime.now().time()
        
        if self.quiet_hours_start <= self.quiet_hours_end:
            # Normal range (e.g., 22:00 - 06:00)
            return not (self.quiet_hours_start <= current_time <= self.quiet_hours_end)
        else:
            # Overnight range (e.g., 22:00 - 06:00)
            return not (current_time >= self.quiet_hours_start or current_time <= self.quiet_hours_end)


class NotificationLog(models.Model):
    """Log of all notifications sent"""
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    message = models.TextField()
    sent_via = models.JSONField(
        default=list,
        help_text="Channels used to send notification (email, push, in-app)"
    )
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        indexes = [
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['notification_type']),
        ]
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.recipient.full_name} - {self.notification_type} ({status})"