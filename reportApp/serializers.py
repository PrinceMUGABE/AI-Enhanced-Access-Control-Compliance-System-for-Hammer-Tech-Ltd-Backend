# reportApp/serializers.py

from rest_framework import serializers
from userApp.models import CustomUser
from departmentApp.models import Department
from onboarding.models import (
    OnboardingModule, MenteeOnboardingProgress, 
    OnboardingChecklist, MenteeChecklistProgress,
    OnboardingNotification, OnboardingDeadline
)
from mentorshipApp.models import (
    ProgramSessionTemplate, MentorshipProgram, Mentorship,
    MentorshipProgramProgress, MentorshipSession,
    MentorshipMessage, MentorshipReview
)
from chatApp.models import (
    ChatRoom, ChatParticipant, Message, 
    VideoCall, CallParticipant, TypingIndicator
)
from notificationApp.models import (
    ChatNotification, SystemNotification,
    UserNotificationPreference, NotificationLog
)


# ==================== USER APP SERIALIZERS ====================
class CustomUserSerializer(serializers.ModelSerializer):
    """Serializer for CustomUser model"""
    department_name = serializers.SerializerMethodField()
    departments_list = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'email', 'work_mail_address',
            'full_name', 'role', 'department', 'department_name',
            'departments_list', 'status', 'availability_status',
            'is_active', 'is_staff', 'created_at', 'created_by'
        ]
    
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
    
    def get_departments_list(self, obj):
        if obj.role == 'mentor':
            return list(obj.departments.values_list('name', flat=True))
        return []


# ==================== DEPARTMENT APP SERIALIZERS ====================
class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model"""
    mentee_count = serializers.SerializerMethodField()
    mentor_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'status',
            'created_at', 'created_by', 'created_by_name',
            'updated_at', 'mentee_count', 'mentor_count'
        ]
    
    def get_mentee_count(self, obj):
        return obj.get_mentee_count()
    
    def get_mentor_count(self, obj):
        return obj.get_mentor_count()
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None


# ==================== ONBOARDING APP SERIALIZERS ====================
class OnboardingModuleSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingModule model"""
    department_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingModule
        fields = [
            'id', 'title', 'description', 'module_type',
            'departments', 'department_names', 'order',
            'is_required', 'duration_minutes', 'content',
            'resources', 'multimedia_files', 'is_active',
            'created_at', 'updated_at', 'created_by',
            'created_by_name', 'completion_rate'
        ]
    
    def get_department_names(self, obj):
        return list(obj.departments.values_list('name', flat=True))
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None
    
    def get_completion_rate(self, obj):
        return obj.get_completion_rate()


class MenteeOnboardingProgressSerializer(serializers.ModelSerializer):
    """Serializer for MenteeOnboardingProgress model"""
    mentee_name = serializers.SerializerMethodField()
    module_title = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = MenteeOnboardingProgress
        fields = [
            'id', 'mentee', 'mentee_name', 'module',
            'module_title', 'department_name', 'status',
            'progress_percentage', 'started_at', 'completed_at',
            'due_date', 'notes', 'time_spent_minutes',
            'last_updated', 'assigned_by', 'assigned_by_name',
            'assigned_at', 'is_overdue'
        ]
    
    def get_mentee_name(self, obj):
        return obj.mentee.full_name
    
    def get_module_title(self, obj):
        return obj.module.title
    
    def get_department_name(self, obj):
        return obj.mentee.department.name if obj.mentee.department else None
    
    def get_assigned_by_name(self, obj):
        return obj.assigned_by.full_name if obj.assigned_by else None
    
    def get_is_overdue(self, obj):
        return obj.is_overdue()


class OnboardingChecklistSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingChecklist model"""
    module_title = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingChecklist
        fields = [
            'id', 'module', 'module_title', 'title',
            'description', 'order', 'is_required',
            'estimated_minutes'
        ]
    
    def get_module_title(self, obj):
        return obj.module.title


class MenteeChecklistProgressSerializer(serializers.ModelSerializer):
    """Serializer for MenteeChecklistProgress model"""
    mentee_name = serializers.SerializerMethodField()
    checklist_title = serializers.SerializerMethodField()
    
    class Meta:
        model = MenteeChecklistProgress
        fields = [
            'id', 'mentee', 'mentee_name', 'checklist_item',
            'checklist_title', 'is_completed', 'completed_at',
            'time_spent_minutes', 'notes'
        ]
    
    def get_mentee_name(self, obj):
        return obj.mentee.full_name
    
    def get_checklist_title(self, obj):
        return obj.checklist_item.title


class OnboardingNotificationSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingNotification model"""
    recipient_name = serializers.SerializerMethodField()
    module_title = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingNotification
        fields = [
            'id', 'recipient', 'recipient_name',
            'notification_type', 'title', 'message',
            'related_module', 'module_title',
            'related_progress', 'sent_at', 'is_read', 'read_at'
        ]
    
    def get_recipient_name(self, obj):
        return obj.recipient.full_name
    
    def get_module_title(self, obj):
        return obj.related_module.title if obj.related_module else None


class OnboardingDeadlineSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingDeadline model"""
    module_title = serializers.SerializerMethodField()
    mentee_name = serializers.SerializerMethodField()
    extension_granted_by_name = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingDeadline
        fields = [
            'id', 'module', 'module_title', 'mentee',
            'mentee_name', 'due_date', 'original_due_date',
            'is_extended', 'extension_reason',
            'extension_granted_by', 'extension_granted_by_name',
            'created_at', 'updated_at', 'days_remaining'
        ]
    
    def get_module_title(self, obj):
        return obj.module.title
    
    def get_mentee_name(self, obj):
        return obj.mentee.full_name
    
    def get_extension_granted_by_name(self, obj):
        return obj.extension_granted_by.full_name if obj.extension_granted_by else None
    
    def get_days_remaining(self, obj):
        return obj.get_days_remaining()


# ==================== MENTORSHIP APP SERIALIZERS ====================
class ProgramSessionTemplateSerializer(serializers.ModelSerializer):
    """Serializer for ProgramSessionTemplate model"""
    
    class Meta:
        model = ProgramSessionTemplate
        fields = [
            'id', 'title', 'session_type', 'description',
            'objectives', 'requirements', 'duration_minutes',
            'order', 'is_required', 'is_active',
            'created_at', 'updated_at'
        ]


class MentorshipProgramSerializer(serializers.ModelSerializer):
    """Serializer for MentorshipProgram model"""
    department_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    total_sessions = serializers.SerializerMethodField()
    total_duration_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipProgram
        fields = [
            'id', 'name', 'department', 'department_name',
            'description', 'status', 'total_days',
            'objectives', 'prerequisites', 'created_at',
            'updated_at', 'created_by', 'created_by_name',
            'total_sessions', 'total_duration_hours'
        ]
    
    def get_department_name(self, obj):
        return obj.department.name
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None
    
    def get_total_sessions(self, obj):
        return obj.get_total_sessions()
    
    def get_total_duration_hours(self, obj):
        return obj.get_total_duration_hours()


class MentorshipSerializer(serializers.ModelSerializer):
    """Serializer for Mentorship model"""
    mentor_name = serializers.SerializerMethodField()
    mentee_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    current_program_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    sessions_completed = serializers.SerializerMethodField()
    total_sessions = serializers.SerializerMethodField()
    
    class Meta:
        model = Mentorship
        fields = [
            'id', 'mentor', 'mentor_name', 'mentee', 'mentee_name',
            'department', 'department_name', 'current_program',
            'current_program_name', 'status', 'start_date',
            'expected_end_date', 'actual_end_date', 'rating',
            'goals', 'achievements', 'feedback', 'notes',
            'created_by', 'created_by_name', 'created_at',
            'updated_at', 'progress_percentage', 'sessions_completed',
            'total_sessions'
        ]
    
    def get_mentor_name(self, obj):
        return obj.mentor.full_name
    
    def get_mentee_name(self, obj):
        return obj.mentee.full_name
    
    def get_department_name(self, obj):
        return obj.department.name
    
    def get_current_program_name(self, obj):
        return obj.current_program.name if obj.current_program else None
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None
    
    def get_progress_percentage(self, obj):
        return obj.get_progress_percentage()
    
    def get_sessions_completed(self, obj):
        return obj.get_sessions_completed()
    
    def get_total_sessions(self, obj):
        return obj.get_total_sessions()


class MentorshipProgramProgressSerializer(serializers.ModelSerializer):
    """Serializer for MentorshipProgramProgress model"""
    mentorship_info = serializers.SerializerMethodField()
    program_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipProgramProgress
        fields = [
            'id', 'mentorship', 'mentorship_info', 'program',
            'program_name', 'status', 'sessions_completed',
            'total_sessions', 'progress_percentage',
            'started_at', 'completed_at'
        ]
    
    def get_mentorship_info(self, obj):
        return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"
    
    def get_program_name(self, obj):
        return obj.program.name


class MentorshipSessionSerializer(serializers.ModelSerializer):
    """Serializer for MentorshipSession model"""
    mentorship_info = serializers.SerializerMethodField()
    program_name = serializers.SerializerMethodField()
    template_title = serializers.SerializerMethodField()
    completed_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipSession
        fields = [
            'id', 'mentorship', 'mentorship_info', 'program',
            'program_name', 'session_template', 'template_title',
            'program_session_number', 'overall_session_number',
            'status', 'scheduled_date', 'actual_date',
            'duration_minutes', 'agenda', 'objectives',
            'notes', 'action_items', 'mentor_rating',
            'mentor_feedback', 'mentee_feedback',
            'meeting_link', 'location', 'completed_by',
            'completed_by_name', 'created_at', 'updated_at'
        ]
    
    def get_mentorship_info(self, obj):
        return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"
    
    def get_program_name(self, obj):
        return obj.program.name if obj.program else None
    
    def get_template_title(self, obj):
        return obj.session_template.title if obj.session_template else None
    
    def get_completed_by_name(self, obj):
        return obj.completed_by.full_name if obj.completed_by else None


class MentorshipMessageSerializer(serializers.ModelSerializer):
    """Serializer for MentorshipMessage model"""
    sender_name = serializers.SerializerMethodField()
    mentorship_info = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipMessage
        fields = [
            'id', 'mentorship', 'mentorship_info', 'sender',
            'sender_name', 'message', 'message_type',
            'attachments', 'is_read', 'read_at', 'created_at'
        ]
    
    def get_sender_name(self, obj):
        return obj.sender.full_name
    
    def get_mentorship_info(self, obj):
        return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"


class MentorshipReviewSerializer(serializers.ModelSerializer):
    """Serializer for MentorshipReview model"""
    mentorship_info = serializers.SerializerMethodField()
    reviewer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipReview
        fields = [
            'id', 'mentorship', 'mentorship_info', 'reviewer',
            'reviewer_name', 'reviewer_type', 'rating',
            'communication_rating', 'knowledge_rating',
            'helpfulness_rating', 'review_text',
            'would_recommend', 'created_at', 'updated_at'
        ]
    
    def get_mentorship_info(self, obj):
        return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"
    
    def get_reviewer_name(self, obj):
        return obj.reviewer.full_name


# ==================== CHAT APP SERIALIZERS ====================
class ChatRoomSerializer(serializers.ModelSerializer):
    """Serializer for ChatRoom model"""
    created_by_name = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    mentorship_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatRoom
        fields = [
            'id', 'name', 'chat_type', 'mentorship',
            'mentorship_info', 'department', 'department_name',
            'created_by', 'created_by_name', 'is_active',
            'created_at', 'updated_at', 'participant_count'
        ]
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None
    
    def get_participant_count(self, obj):
        return obj.participants.count()
    
    def get_department_name(self, obj):
        return obj.department.name if obj.department else None
    
    def get_mentorship_info(self, obj):
        if obj.mentorship:
            return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"
        return None


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model"""
    sender_name = serializers.SerializerMethodField()
    chat_room_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'chat_room', 'chat_room_name', 'sender',
            'sender_name', 'message_type', 'content',
            'attachment', 'is_deleted', 'deleted_at',
            'created_at', 'updated_at'
        ]
    
    def get_sender_name(self, obj):
        return obj.sender.full_name
    
    def get_chat_room_name(self, obj):
        return obj.chat_room.name


class VideoCallSerializer(serializers.ModelSerializer):
    """Serializer for VideoCall model"""
    caller_name = serializers.SerializerMethodField()
    chat_room_name = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = VideoCall
        fields = [
            'id', 'chat_room', 'chat_room_name', 'call_id',
            'caller', 'caller_name', 'status', 'started_at',
            'ended_at', 'duration', 'created_at',
            'updated_at', 'participant_count'
        ]
    
    def get_caller_name(self, obj):
        return obj.caller.full_name
    
    def get_chat_room_name(self, obj):
        return obj.chat_room.name
    
    def get_participant_count(self, obj):
        return obj.participants.count()


# ==================== NOTIFICATION APP SERIALIZERS ====================
class ChatNotificationSerializer(serializers.ModelSerializer):
    """Serializer for ChatNotification model"""
    recipient_name = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()
    chat_room_name = serializers.SerializerMethodField()
    mentorship_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatNotification
        fields = [
            'id', 'recipient', 'recipient_name', 'sender',
            'sender_name', 'chat_room', 'chat_room_name',
            'mentorship', 'mentorship_info', 'notification_type',
            'title', 'message', 'metadata', 'is_read',
            'is_archived', 'created_at', 'read_at', 'archived_at'
        ]
    
    def get_recipient_name(self, obj):
        return obj.recipient.full_name
    
    def get_sender_name(self, obj):
        return obj.sender.full_name if obj.sender else None
    
    def get_chat_room_name(self, obj):
        return obj.chat_room.name if obj.chat_room else None
    
    def get_mentorship_info(self, obj):
        if obj.mentorship:
            return f"{obj.mentorship.mentor.full_name} → {obj.mentorship.mentee.full_name}"
        return None


class SystemNotificationSerializer(serializers.ModelSerializer):
    """Serializer for SystemNotification model"""
    created_by_name = serializers.SerializerMethodField()
    is_active_now = serializers.SerializerMethodField()
    
    class Meta:
        model = SystemNotification
        fields = [
            'id', 'title', 'message', 'level', 'is_active',
            'is_global', 'target_roles', 'target_departments',
            'start_date', 'end_date', 'created_at',
            'created_by', 'created_by_name', 'is_active_now'
        ]
    
    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None
    
    def get_is_active_now(self, obj):
        return obj.is_active_now()


class NotificationLogSerializer(serializers.ModelSerializer):
    """Serializer for NotificationLog model"""
    recipient_name = serializers.SerializerMethodField()
    
    class Meta:
        model = NotificationLog
        fields = [
            'id', 'recipient', 'recipient_name',
            'notification_type', 'title', 'message',
            'sent_via', 'success', 'error_message', 'created_at'
        ]
    
    def get_recipient_name(self, obj):
        return obj.recipient.full_name