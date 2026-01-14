# notificationApp/serializers.py - UPDATED

from rest_framework import serializers
from .models import (
    ChatNotification, SystemNotification,
    UserNotificationPreference, NotificationLog
)
from userApp.models import CustomUser


class UserDepartmentSerializer(serializers.Serializer):
    """Serializer for user departments"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()

class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info"""
    department = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'full_name', 'email', 'phone_number', 
            'work_mail_address', 'role', 'department', 
            'status', 'availability_status'
        ]
        read_only_fields = fields
    
    def get_department(self, obj):
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name
            }
        return None


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile information"""
    departments = UserDepartmentSerializer(many=True, read_only=True)
    single_department = UserDepartmentSerializer(source='department', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'email', 'work_mail_address',
            'full_name', 'role', 'department', 'departments',
            'single_department', 'status', 'availability_status',
            'created_at'
        ]
        read_only_fields = fields


class ChatNotificationSerializer(serializers.ModelSerializer):
    """Serializer for chat notifications"""
    sender = UserProfileSerializer(read_only=True)
    recipient = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = ChatNotification
        fields = [
            'id', 'recipient', 'sender', 'notification_type', 
            'title', 'message', 'metadata', 'is_read', 'is_archived',
            'created_at', 'read_at', 'archived_at'
        ]
        read_only_fields = fields


class DeleteNotificationsSerializer(serializers.Serializer):
    """Serializer for deleting notifications"""
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True
    )
    delete_all = serializers.BooleanField(default=False)
    delete_all_read = serializers.BooleanField(default=False)
    delete_all_archived = serializers.BooleanField(default=False)


class ChatNotificationSerializer(serializers.ModelSerializer):
    """Serializer for chat notifications"""
    sender = UserBasicSerializer(read_only=True)
    recipient = UserBasicSerializer(read_only=True)
    chat_room_info = serializers.SerializerMethodField()
    group_chat_room_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatNotification
        fields = [
            'id', 'recipient', 'sender', 'notification_type', 'title', 'message',
            'chat_room', 'chat_room_info', 'group_chat_room', 'group_chat_room_info',
            'is_read', 'is_archived', 'created_at', 'read_at', 'archived_at'
        ]
        read_only_fields = fields
    
    def get_chat_room_info(self, obj):
        if obj.chat_room:
            return {
                'id': obj.chat_room.id,
                'type': 'one_on_one',
                'other_user': {
                    'id': obj.chat_room.user1.id if obj.recipient != obj.chat_room.user1 else obj.chat_room.user2.id,
                    'name': obj.chat_room.user1.full_name if obj.recipient != obj.chat_room.user1 else obj.chat_room.user2.full_name,
                }
            }
        return None
    
    def get_group_chat_room_info(self, obj):
        if obj.group_chat_room:
            return {
                'id': obj.group_chat_room.id,
                'name': obj.group_chat_room.name,
                'type': obj.group_chat_room.chat_type
            }
        return None


class SystemNotificationSerializer(serializers.ModelSerializer):
    """Serializer for system notifications"""
    created_by = UserBasicSerializer(read_only=True)
    is_active_now = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = SystemNotification
        fields = [
            'id', 'title', 'message', 'level', 'is_active', 'is_active_now',
            'is_global', 'target_roles', 'target_departments',
            'start_date', 'end_date', 'created_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'created_by', 'is_active_now']


class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for user notification preferences"""
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = UserNotificationPreference
        fields = [
            'id', 'user', 'enable_chat_notifications', 'enable_message_notifications',
            'enable_group_chat_notifications', 'enable_cross_department_notifications',
            'enable_system_notifications', 'enable_announcements', 'enable_updates',
            'enable_email_notifications', 'email_frequency', 'enable_push_notifications',
            'quiet_hours_start', 'quiet_hours_end', 'enable_quiet_hours',
            'enable_sound', 'sound_name', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'updated_at']
    
    def validate_quiet_hours_start(self, value):
        if value and not self.initial_data.get('quiet_hours_end'):
            raise serializers.ValidationError("Both start and end times must be provided for quiet hours")
        return value
    
    def validate_quiet_hours_end(self, value):
        if value and not self.initial_data.get('quiet_hours_start'):
            raise serializers.ValidationError("Both start and end times must be provided for quiet hours")
        return value
    
    def validate(self, data):
        start = data.get('quiet_hours_start')
        end = data.get('quiet_hours_end')
        
        if start and end and start == end:
            raise serializers.ValidationError("Quiet hours start and end times cannot be the same")
        
        return data


class NotificationLogSerializer(serializers.ModelSerializer):
    """Serializer for notification logs"""
    recipient = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = NotificationLog
        fields = [
            'id', 'recipient', 'notification_type', 'title', 'message',
            'sent_via', 'success', 'error_message', 'created_at'
        ]
        read_only_fields = fields


class MarkNotificationsReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False
    )
    mark_all = serializers.BooleanField(default=False)


class CreateSystemNotificationSerializer(serializers.ModelSerializer):
    """Serializer for creating system notifications"""
    class Meta:
        model = SystemNotification
        fields = [
            'title', 'message', 'level', 'is_active', 'is_global',
            'target_roles', 'target_departments', 'start_date', 'end_date'
        ]
    
    def validate_target_roles(self, value):
        valid_roles = ['admin', 'hr', 'mentor', 'mentee']
        if value:
            invalid_roles = [role for role in value if role not in valid_roles]
            if invalid_roles:
                raise serializers.ValidationError(f"Invalid roles: {invalid_roles}. Valid roles are: {valid_roles}")
        return value