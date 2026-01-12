from django.db import models
from django.utils.timezone import now
from userApp.models import CustomUser
from mentorshipApp.models import Mentorship
from departmentApp.models import Department


class ChatRoomType(models.TextChoices):
    ONE_ON_ONE = 'one_on_one', 'One-on-One Chat'
    MENTORSHIP_GROUP = 'mentorship_group', 'Mentorship Group Chat'
    DEPARTMENT_GROUP = 'department_group', 'Department Group Chat'
    STAFF_CHAT = 'staff_chat', 'Staff Chat (Admin/HR)'
    GLOBAL = 'global', 'Global Chat'


class ChatRoom(models.Model):
    """Unified chat room model for all chat types"""
    name = models.CharField(max_length=200, default=None, blank=True, null=True)
    chat_type = models.CharField(
        max_length=50,
        choices=ChatRoomType.choices
    )
    
    # Optional relationships - only used for specific chat types
    mentorship = models.ForeignKey(
        Mentorship,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_rooms'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_rooms'
    )
    
    # Participants through join table
    participants = models.ManyToManyField(
        CustomUser,
        related_name='chat_rooms',
        through='ChatParticipant'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_chats'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['chat_type']),
            models.Index(fields=['department']),
            models.Index(fields=['mentorship']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_chat_type_display()})"

    def save(self, *args, **kwargs):
        # Auto-generate name if not provided
        if not self.name:
            if self.chat_type == ChatRoomType.GLOBAL:
                self.name = "mentorship_global_chat"
            elif self.chat_type == ChatRoomType.DEPARTMENT_GROUP and self.department:
                self.name = f"{self.department.name}_group"
            elif self.chat_type == ChatRoomType.MENTORSHIP_GROUP and self.mentorship:
                mentor = self.mentorship.mentor
                mentee = self.mentorship.mentee
                self.name = f"{mentor.full_name[:10]}_{mentee.full_name[:10]}"
            elif self.chat_type == ChatRoomType.STAFF_CHAT:
                self.name = f"staff_chat_{self.created_at.strftime('%Y%m%d')}"
            elif self.chat_type == ChatRoomType.ONE_ON_ONE:
                self.name = f"one_on_one_{self.created_at.strftime('%Y%m%d_%H%M')}"
        
        super().save(*args, **kwargs)

    def can_manage(self, user):
        """Check if user can manage this chat room"""
        if user.role == 'admin':
            return True
        if user.role == 'hr' and self.chat_type in [
            ChatRoomType.DEPARTMENT_GROUP,
            ChatRoomType.MENTORSHIP_GROUP,
            ChatRoomType.STAFF_CHAT
        ]:
            return True
        return False

    def can_add_participants(self, user):
        """Check if user can add participants to this chat"""
        if user.role in ['admin', 'hr']:
            return True
        return False

    def get_participant_roles(self):
        """Get all participant roles in this chat"""
        return set(self.participants.values_list('role', flat=True))


class ChatParticipant(models.Model):
    """Tracks participants in chat rooms with their roles"""
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    
    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='chat_participants'
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='chat_participations'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(default=now)
    last_read_at = models.DateTimeField(null=True, blank=True)
    is_muted = models.BooleanField(default=False)

    class Meta:
        unique_together = ['chat_room', 'user']
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.full_name} in {self.chat_room.name}"


class Message(models.Model):
    """Unified message model for all chat types"""
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('file', 'File'),
        ('image', 'Image'),
    ]
    
    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    content = models.TextField()
    attachment = models.FileField(
        upload_to='chat_attachments/',
        null=True,
        blank=True
    )
    
    # Message status
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['chat_room', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
        ]

    def __str__(self):
        return f"Message from {self.sender.full_name}"

    def can_delete(self, user):
        """Check if user can delete this message"""
        return user == self.sender or user.role == 'admin'
    


class VideoCall(models.Model):
    """Model for video call sessions"""
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('ringing', 'Ringing'),
        ('ongoing', 'Ongoing'),
        ('ended', 'Ended'),
        ('missed', 'Missed'),
        ('rejected', 'Rejected'),
    ]
    
    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='video_calls'
    )
    call_id = models.CharField(max_length=100, unique=True)
    caller = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='initiated_calls'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    participants = models.ManyToManyField(
        CustomUser,
        related_name='video_calls',
        through='CallParticipant'
    )
    
    # WebRTC data
    offer = models.JSONField(null=True, blank=True)
    answer = models.JSONField(null=True, blank=True)
    ice_candidates = models.JSONField(default=list)
    
    # Call metadata
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(default=0)  # in seconds
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Call {self.call_id} - {self.status}"


class CallParticipant(models.Model):
    """Track participants in video calls"""
    call = models.ForeignKey(VideoCall, on_delete=models.CASCADE, related_name='call_participants')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['call', 'user']


class TypingIndicator(models.Model):
    """Track typing status in chats"""
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='typing_indicators')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    is_typing = models.BooleanField(default=False)
    last_typing_at = models.DateTimeField(default=now)
    
    class Meta:
        unique_together = ['chat_room', 'user']