from datetime import timezone
from django.db import models
from django.utils.timezone import now
from userApp.models import CustomUser




class AssistanceChat(models.Model):
    """AI assistance chat session"""
    STATUS_CHOICES = [
        ('ai_handled', 'AI Handled'),
        ('human_requested', 'Human Assistance Requested'),
        ('human_responding', 'Human Responding'),
        ('resolved', 'Resolved'),
        ('escalated', 'Escalated'),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assistance_chats'
    )
    session_id = models.CharField(max_length=100, unique=True)
    email = models.EmailField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ai_handled')
    is_active = models.BooleanField(default=True)
    escalated_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='escalated_chats'
    )
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Add fields for session linking
    anonymous_token = models.CharField(max_length=100, null=True, blank=True, unique=True)
    linked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Assistance: {self.session_id}"
    
    def get_user_email(self):
        """Get user's email, prioritizing authenticated user's email"""
        if self.user:
            return self.user.email
        return self.email
    
    def link_to_user(self, user):
        """Link an anonymous chat session to an authenticated user"""
        if not self.user and self.email == user.email:
            self.user = user
            self.linked_at = timezone.now()
            self.save()
            return True
        return False
    
    def can_access(self, user):
        """Check if user can access this chat"""
        # If user is owner
        if self.user == user:
            return True
        
        # If user is admin/hr
        if user.role in ['admin', 'hr']:
            return True
        
        # If chat was started with user's email (and user is authenticated with same email)
        if self.email and user.email and self.email.lower() == user.email.lower():
            # Auto-link if not already linked
            if not self.user:
                self.user = user
                self.linked_at = timezone.now()
                self.save()
            return True
        
        return False

class AssistanceMessage(models.Model):
    """Messages in assistance chat"""
    MESSAGE_TYPES = [
        ('user_question', 'User Question'),
        ('ai_response', 'AI Response'),
        ('human_response', 'Human Response'),
        ('system', 'System Message'),
    ]
    
    chat = models.ForeignKey(AssistanceChat, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    content = models.TextField()
    sender = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    ai_model = models.CharField(max_length=50, null=True, blank=True)
    ai_response_quality = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.message_type}: {self.content[:50]}"


class FAQ(models.Model):
    """Frequently Asked Questions"""
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('technical', 'Technical'),
        ('account', 'Account'),
        ('mentorship', 'Mentorship'),
        ('billing', 'Billing'),
    ]
    
    question = models.TextField()
    answer = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    keywords = models.TextField(help_text="Comma-separated keywords")
    times_asked = models.IntegerField(default=0)
    helpful_count = models.IntegerField(default=0)
    not_helpful_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'

    def __str__(self):
        return self.question[:100]
    
    def increment_times_asked(self):
        self.times_asked += 1
        self.save(update_fields=['times_asked'])


class AIResponseLog(models.Model):
    """Log AI responses"""
    chat = models.ForeignKey(AssistanceChat, on_delete=models.CASCADE, related_name='ai_logs')
    user_query = models.TextField()
    ai_response = models.TextField()
    model_used = models.CharField(max_length=50)
    confidence_score = models.FloatField()
    response_time = models.FloatField(help_text="Response time in seconds")
    was_helpful = models.BooleanField(null=True, blank=True)
    feedback_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=now)

    def __str__(self):
        return f"AI Log: {self.chat.session_id}"


class EmailResponse(models.Model):
    """Model for tracking email responses to users"""
    chat = models.ForeignKey(
        AssistanceChat,
        on_delete=models.CASCADE,
        related_name='email_responses'
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_to = models.EmailField()
    sent_at = models.DateTimeField(default=now)
    is_sent = models.BooleanField(default=False)
    sent_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    tracking_id = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Email to {self.sent_to} - {self.subject}"