from rest_framework import serializers
from django.utils.timezone import now
from .models import CallParticipant, ChatRoom, ChatParticipant, Message, ChatRoomType, TypingIndicator, VideoCall
from userApp.models import CustomUser
from mentorshipApp.models import Mentorship


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info for chat"""
    class Meta:
        model = CustomUser
        fields = ['id', 'full_name', 'role', 'department', 'work_mail_address']
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for messages"""
    sender = UserBasicSerializer(read_only=True)
    is_own_message = serializers.SerializerMethodField()
    formatted_time = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'message_type', 'content', 'attachment',
            'created_at', 'updated_at', 'is_own_message', 'formatted_time'
        ]
        read_only_fields = fields

    def get_is_own_message(self, obj):
        request = self.context.get('request')
        return request and request.user == obj.sender

    def get_formatted_time(self, obj):
        return obj.created_at.strftime('%H:%M')


class ChatParticipantSerializer(serializers.ModelSerializer):
    """Serializer for chat participants"""
    user = UserBasicSerializer(read_only=True)

    class Meta:
        model = ChatParticipant
        fields = ['id', 'user', 'role', 'joined_at', 'last_read_at', 'is_muted']
        read_only_fields = fields


class ChatRoomSerializer(serializers.ModelSerializer):
    """Serializer for chat rooms"""
    participants = ChatParticipantSerializer(
        many=True,
        read_only=True,
        source='chat_participants'
    )
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'name', 'chat_type', 'mentorship', 'department',
            'participants', 'is_active', 'created_at', 'updated_at',
            'last_message', 'unread_count', 'can_manage', 'is_participant'
        ]
        read_only_fields = fields

    def get_last_message(self, obj):
        last_msg = obj.messages.filter(is_deleted=False).last()
        if last_msg:
            return {
                'content': last_msg.content[:100],
                'sender': last_msg.sender.full_name,
                'time': last_msg.created_at
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request:
            return 0
            
        user = request.user
        try:
            participant = ChatParticipant.objects.get(chat_room=obj, user=user)
            if not participant.last_read_at:
                return obj.messages.count()
            
            return obj.messages.filter(
                created_at__gt=participant.last_read_at
            ).exclude(sender=user).count()
        except ChatParticipant.DoesNotExist:
            return 0

    def get_can_manage(self, obj):
        request = self.context.get('request')
        return request and obj.can_manage(request.user)

    def get_is_participant(self, obj):
        request = self.context.get('request')
        return request and obj.participants.filter(id=request.user.id).exists()


class CreateChatRoomSerializer(serializers.Serializer):
    """Serializer for creating chat rooms"""
    chat_type = serializers.ChoiceField(choices=ChatRoomType.choices)
    mentorship_id = serializers.IntegerField(required=False)
    department_id = serializers.IntegerField(required=False)
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=[]
    )

    def validate(self, data):
        chat_type = data['chat_type']
        
        # Validate based on chat type
        if chat_type == ChatRoomType.MENTORSHIP_GROUP:
            if not data.get('mentorship_id'):
                raise serializers.ValidationError("Mentorship ID is required for mentorship group chats")
        elif chat_type == ChatRoomType.DEPARTMENT_GROUP:
            if not data.get('department_id'):
                raise serializers.ValidationError("Department ID is required for department group chats")
        elif chat_type == ChatRoomType.STAFF_CHAT:
            # Staff chat only for admin/hr
            request = self.context.get('request')
            if request and request.user.role not in ['admin', 'hr']:
                raise serializers.ValidationError("Only admin/HR can create staff chats")
        elif chat_type == ChatRoomType.GLOBAL:
            # Global chat only for admin
            request = self.context.get('request')
            if request and request.user.role != 'admin':
                raise serializers.ValidationError("Only admin can create global chats")
        
        return data


class SendMessageSerializer(serializers.Serializer):
    """Serializer for sending messages"""
    chat_room_id = serializers.IntegerField()
    content = serializers.CharField()
    message_type = serializers.ChoiceField(
        choices=Message.MESSAGE_TYPES,
        default='text'
    )
    attachment = serializers.FileField(required=False)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty")
        if len(value) > 5000:
            raise serializers.ValidationError("Message is too long (max 5000 characters)")
        return value
    





class VideoCallSerializer(serializers.ModelSerializer):
    """Serializer for video calls"""
    caller = UserBasicSerializer(read_only=True)
    participants = UserBasicSerializer(many=True, read_only=True)
    
    class Meta:
        model = VideoCall
        fields = [
            'id', 'call_id', 'chat_room', 'caller', 'status',
            'offer', 'answer', 'ice_candidates', 'participants',
            'started_at', 'ended_at', 'duration',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class CallParticipantSerializer(serializers.ModelSerializer):
    """Serializer for call participants"""
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = CallParticipant
        fields = ['id', 'user', 'joined_at', 'left_at', 'is_active']
        read_only_fields = fields


class TypingIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for typing indicators"""
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = TypingIndicator
        fields = ['id', 'user', 'is_typing', 'last_typing_at']
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    """Updated serializer for sending messages"""
    chat_room_id = serializers.IntegerField()
    content = serializers.CharField(required=False)
    message_type = serializers.ChoiceField(
        choices=Message.MESSAGE_TYPES,
        default='text'
    )
    attachment = serializers.FileField(required=False)
    reply_to_id = serializers.IntegerField(required=False)
    
    def validate(self, data):
        # For text messages, content is required
        if data.get('message_type') == 'text' and not data.get('content'):
            raise serializers.ValidationError("Content is required for text messages")
        
        # For file messages, either content or attachment is required
        if data.get('message_type') == 'file' and not data.get('content') and not data.get('attachment'):
            raise serializers.ValidationError("Either content or attachment is required for file messages")
        
        return data


class VideoCallInitiateSerializer(serializers.Serializer):
    """Serializer for initiating video calls"""
    chat_room_id = serializers.IntegerField()
    call_type = serializers.ChoiceField(choices=[('video', 'Video'), ('audio', 'Audio')], default='video')


class WebRTCSignalSerializer(serializers.Serializer):
    """Serializer for WebRTC signaling"""
    call_id = serializers.CharField()
    signal_type = serializers.ChoiceField(choices=[
        ('offer', 'Offer'),
        ('answer', 'Answer'),
        ('candidate', 'ICE Candidate'),
        ('end', 'End Call')
    ])
    data = serializers.JSONField()
    target_user_id = serializers.IntegerField(required=False)