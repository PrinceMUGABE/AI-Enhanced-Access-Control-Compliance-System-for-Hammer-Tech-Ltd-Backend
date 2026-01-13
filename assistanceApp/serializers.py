from rest_framework import serializers
from .models import FAQ, AssistanceChat, AssistanceMessage, EmailResponse
from userApp.models import CustomUser


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info for assistance"""
    class Meta:
        model = CustomUser
        fields = ['id', 'full_name', 'role', 'email', 'work_mail_address']
        read_only_fields = fields


class FAQSerializer(serializers.ModelSerializer):
    """Serializer for FAQs"""
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    created_by_info = serializers.SerializerMethodField()
    
    class Meta:
        model = FAQ
        fields = [
            'id', 'question', 'answer', 'category', 'category_display',
            'keywords', 'times_asked', 'helpful_count', 'not_helpful_count',
            'is_active', 'created_by_info', 'created_at', 'updated_at'
        ]
        read_only_fields = fields
    
    def get_created_by_info(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'full_name': obj.created_by.full_name,
                'role': obj.created_by.role
            }
        return None


class AssistanceMessageSerializer(serializers.ModelSerializer):
    """Serializer for assistance messages"""
    sender_info = serializers.SerializerMethodField()
    formatted_time = serializers.SerializerMethodField()
    
    class Meta:
        model = AssistanceMessage
        fields = [
            'id', 'message_type', 'content', 'sender_info',
            'ai_model', 'ai_response_quality', 'formatted_time', 'created_at'
        ]
        read_only_fields = fields
    
    def get_sender_info(self, obj):
        if obj.sender:
            return UserBasicSerializer(obj.sender).data
        elif obj.message_type == 'ai_response':
            return {
                'id': 'ai',
                'full_name': 'AI Assistant',
                'role': 'ai'
            }
        elif obj.message_type == 'system':
            return {
                'id': 'system',
                'full_name': 'System',
                'role': 'system'
            }
        return None
    
    def get_formatted_time(self, obj):
        from django.utils import timezone
        return obj.created_at.strftime('%I:%M %p')


class AssistanceChatSerializer(serializers.ModelSerializer):
    """Serializer for assistance chat"""
    messages = AssistanceMessageSerializer(many=True, read_only=True)
    user_info = serializers.SerializerMethodField()
    escalated_to_info = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    can_escalate = serializers.SerializerMethodField()
    
    class Meta:
        model = AssistanceChat
        fields = [
            'id', 'session_id', 'user_info', 'email', 'status',
            'messages', 'message_count', 'unread_count',
            'escalated_to_info', 'can_escalate',
            'created_at', 'updated_at', 'resolved_at'
        ]
        read_only_fields = fields
    
    def get_user_info(self, obj):
        if obj.user:
            return UserBasicSerializer(obj.user).data
        return None
    
    def get_escalated_to_info(self, obj):
        if obj.escalated_to:
            return UserBasicSerializer(obj.escalated_to).data
        return None
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_unread_count(self, obj):
        # For now, return 0. Can implement read receipts later
        return 0
    
    def get_can_escalate(self, obj):
        # Chat can be escalated if it's AI handled and has an email
        return obj.status == 'ai_handled' and (obj.email or obj.user)


class EmailResponseSerializer(serializers.ModelSerializer):
    """Serializer for email responses"""
    sent_by_info = serializers.SerializerMethodField()
    formatted_sent_at = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailResponse
        fields = [
            'id', 'subject', 'body', 'sent_to', 'sent_by_info',
            'is_sent', 'tracking_id', 'formatted_sent_at', 'sent_at'
        ]
        read_only_fields = fields
    
    def get_sent_by_info(self, obj):
        if obj.sent_by:
            return UserBasicSerializer(obj.sent_by).data
        return None
    
    def get_formatted_sent_at(self, obj):
        return obj.sent_at.strftime('%B %d, %Y at %I:%M %p') if obj.sent_at else None