# chatApp/utils.py
from xmlrpc import client
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import ChatRoom, GroupChatParticipant, GroupChatRoom
from userApp.models import CustomUser
from .serializers import MessageSerializer
from chatApp.models import ChatNotification


def send_notification_to_user(user_id, notification_data):
    """
    Send real-time notification to a specific user via WebSocket
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {
            'type': 'notification_message',
            'notification': notification_data
        }
    )


def send_email_notification(recipient_email, subject, template_name, context):
    """
    Send email notification
    """
    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def create_system_message(chat_room, content):
    """
    Create a system message in a chat room
    """
    from .models import Message
    
    # Get or create a system user (you might want to create a dedicated system user)
    try:
        system_user = CustomUser.objects.get(phone_number='system')
    except CustomUser.DoesNotExist:
        # Create system user if it doesn't exist
        system_user = CustomUser.objects.create_user(
            phone_number='system',
            role='admin',
            email='system@example.com'
        )
    
    message = Message.objects.create(
        chat_room=chat_room,
        sender=system_user,
        content=content,
        message_type='system'
    )
    
    # Send real-time update
    
    channel_layer = get_channel_layer()
    
    # Create mock request for serializer
    class MockRequest:
        def __init__(self):
            self.user = system_user
    
    serializer = MessageSerializer(message, context={'request': MockRequest()})
    
    async_to_sync(channel_layer.group_send)(
        f"chat_{chat_room.id}",
        {
            'type': 'chat_message',
            'message': serializer.data
        }
    )
    
    return message


def get_user_chat_stats(user):
    """
    Get chat statistics for a user
    """
    from .models import ChatRoom, Message
    from userApp.models import CustomUser
 
    
    stats = {
        'total_chat_rooms': 0,
        'active_chat_rooms': 0,
        'total_messages_sent': 0,
        'unread_messages': 0,
        'unread_notifications': 0
    }
    
    try:
        if user.role == 'mentee':
            mentee = CustomUser.objects.get(user=user)
            chat_rooms = ChatRoom.objects.filter(mentee=mentee)
        elif user.role == 'mentor':
            mentor = CustomUser.objects.get(user=user)
            chat_rooms = ChatRoom.objects.filter(mentor=mentor)
        else:
            return stats
        
        stats['total_chat_rooms'] = chat_rooms.count()
        stats['active_chat_rooms'] = chat_rooms.filter(is_active=True).count()
        stats['total_messages_sent'] = Message.objects.filter(
            chat_room__in=chat_rooms,
            sender=user,
            is_deleted=False
        ).count()
        stats['unread_messages'] = Message.objects.filter(
            chat_room__in=chat_rooms,
            is_deleted=False,
            is_read=False
        ).exclude(sender=user).count()
        stats['unread_notifications'] = ChatNotification.objects.filter(
            recipient=user,
            is_read=False
        ).count()
        
    except Exception as e:
        print(f"Error getting chat stats: {e}")
    
    return stats


def validate_file_upload(file):
    """
    Validate file uploads for chat attachments
    """
    max_size = 10 * 1024 * 1024  # 10MB
    allowed_types = [
        'image/jpeg', 'image/png', 'image/gif',
        'application/pdf', 'text/plain',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]
    
    if file.size > max_size:
        return False, "File size too large. Maximum size is 10MB."
    
    if file.content_type not in allowed_types:
        return False, "File type not allowed."
    
    return True, "File is valid."


def format_chat_room_name(mentorship):
    """
    Generate a formatted name for chat room
    """
    return f"Case {mentorship.case_number} - {mentorship.title[:30]}{'...' if len(mentorship.title) > 30 else ''}"

def get_online_users(chat_room_id):
    """
    Get list of online users in a chat room
    This would require implementing user presence tracking
    """
    # This is a placeholder - you'd need to implement Redis-based presence tracking
    # or use Django Channels' group management features
    return []











# Add to mentorshipApp/utils.py (create if it doesn't exist)

from django.db.models import Count, Q, Max
from django.utils import timezone
from datetime import timedelta

def get_user_chat_statistics(user):
    """Get comprehensive chat statistics for a user"""
    stats = {
        'total_chats': 0,
        'unread_messages': 0,
        'active_conversations': 0,
        'mentorship_chats': 0,
        'department_chats': 0,
        'staff_chats': 0
    }
    
    try:
        if user.role not in ['mentor', 'mentee']:
            return stats
        
        # One-on-one chat stats
        one_on_one_chats = ChatRoom.objects.filter(
            Q(user1=user) | Q(user2=user),
            is_active=True
        )
        
        # Group chat stats
        group_chats = GroupChatRoom.objects.filter(
            participants=user,
            is_active=True,
            is_archived=False
        )
        
        stats['total_chats'] = one_on_one_chats.count() + group_chats.count()
        
        # Calculate unread messages
        total_unread = 0
        
        # Unread in one-on-one chats
        for chat in one_on_one_chats:
            total_unread += chat.messages.filter(
                is_deleted=False,
                is_read=False
            ).exclude(sender=user).count()
        
        # Unread in group chats
        for chat in group_chats:
            participant = GroupChatParticipant.objects.filter(
                chat_room=chat,
                user=user
            ).first()
            
            if participant and participant.last_read_at:
                total_unread += chat.group_messages.filter(
                    created_at__gt=participant.last_read_at,
                    is_deleted=False
                ).exclude(sender=user).count()
            else:
                total_unread += chat.group_messages.filter(
                    is_deleted=False
                ).exclude(sender=user).count()
        
        stats['unread_messages'] = total_unread
        
        # Active conversations (chats with activity in last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        
        active_one_on_one = one_on_one_chats.filter(
            messages__created_at__gte=week_ago
        ).distinct().count()
        
        active_group = group_chats.filter(
            group_messages__created_at__gte=week_ago
        ).distinct().count()
        
        stats['active_conversations'] = active_one_on_one + active_group
        
        # Mentorship chats
        if user.role == 'mentor':
            mentorship_chats = GroupChatRoom.objects.filter(
                participants=user,
                chat_type='mentorship_group',
                is_active=True,
                is_archived=False
            ).count()
        else:
            mentorship_chats = GroupChatRoom.objects.filter(
                participants=user,
                chat_type__in=['mentorship_group', 'department_group'],
                is_active=True,
                is_archived=False
            ).count()
        
        stats['mentorship_chats'] = mentorship_chats
        
        # Department chats
        department_chats = GroupChatRoom.objects.filter(
            participants=user,
            chat_type='department_group',
            is_active=True,
            is_archived=False
        ).count()
        
        stats['department_chats'] = department_chats
        
        # Staff chats (for mentees)
        if user.role == 'mentee':
            staff_chats = ChatRoom.objects.filter(
                Q(user1=user) | Q(user2=user),
                chat_type__in=['mentee_admin', 'mentee_hr'],
                is_active=True
            ).count()
            
            stats['staff_chats'] = staff_chats
        
    except Exception as e:
        print(f"Error getting chat statistics: {e}")
    
    return stats


def get_recent_chat_activity(user, limit=5):
    """Get recent chat activity for a user"""
    recent_activity = []
    
    try:
        # Get recent one-on-one messages
        one_on_one_chats = ChatRoom.objects.filter(
            Q(user1=user) | Q(user2=user),
            is_active=True
        )
        
        for chat in one_on_one_chats:
            recent_messages = chat.messages.filter(
                is_deleted=False
            ).order_by('-created_at')[:3]
            
            for message in recent_messages:
                other_user = chat.user2 if chat.user1 == user else chat.user1
                recent_activity.append({
                    'type': 'one_on_one',
                    'chat_id': chat.id,
                    'other_user': other_user.full_name,
                    'message': message.content[:100],
                    'timestamp': message.created_at,
                    'sender': message.sender.full_name,
                    'is_own': message.sender == user,
                    'is_read': message.is_read if message.sender != user else True
                })
        
        # Get recent group messages
        group_chats = GroupChatRoom.objects.filter(
            participants=user,
            is_active=True,
            is_archived=False
        )
        
        for chat in group_chats:
            recent_messages = chat.group_messages.filter(
                is_deleted=False
            ).order_by('-created_at')[:3]
            
            for message in recent_messages:
                recent_activity.append({
                    'type': 'group',
                    'chat_id': chat.id,
                    'chat_name': chat.name,
                    'message': message.content[:100],
                    'timestamp': message.created_at,
                    'sender': message.sender.full_name,
                    'is_own': message.sender == user,
                    'is_read': message.get_read_by().filter(id=user.id).exists() if message.sender != user else True
                })
        
        # Sort by timestamp and limit
        recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)
        return recent_activity[:limit]
        
    except Exception as e:
        print(f"Error getting recent activity: {e}")
        return []