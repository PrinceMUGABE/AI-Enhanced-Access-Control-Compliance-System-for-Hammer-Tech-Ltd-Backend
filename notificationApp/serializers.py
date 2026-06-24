from rest_framework import serializers
from .models import Notification, NotificationPreference
from userApp.models import CustomUser
from incidentApp.models import Incident

class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    
    user_details = serializers.SerializerMethodField()
    incident_details = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_details',
            'notification_type', 'title', 'message', 'priority',
            'incident', 'incident_details',
            'audit', 'is_read', 'read_at',
            'action_link', 'action_text',
            'created_at', 'updated_at', 'time_ago'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_details(self, obj):
        return {
            'id': obj.user.id,
            'email': obj.user.email,
            'full_name': obj.user.full_name,
            'role': obj.user.role
        }
    
    def get_incident_details(self, obj):
        if obj.incident:
            return {
                'id': obj.incident.id,
                'incident_number': obj.incident.incident_number,
                'title': obj.incident.title,
                'severity': obj.incident.severity,
                'status': obj.incident.status
            }
        return None
    
    def get_time_ago(self, obj):
        return obj.time_ago


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences"""
    
    class Meta:
        model = NotificationPreference
        fields = '__all__'
        read_only_fields = ['id', 'user', 'updated_at']


class MarkNotificationsReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""
    
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of notification IDs to mark as read. If empty, marks all as read."
    )


class NotificationCountSerializer(serializers.Serializer):
    """Serializer for notification count"""
    
    total = serializers.IntegerField()
    unread = serializers.IntegerField()
    urgent = serializers.IntegerField()





    