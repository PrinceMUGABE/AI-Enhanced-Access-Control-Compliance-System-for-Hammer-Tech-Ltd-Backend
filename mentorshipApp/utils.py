# mentorshipApp/utils.py
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q, Max
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from notificationApp.models import ChatNotification
from chatApp.models import ChatRoom, ChatRoomType, ChatParticipant, Message
from userApp.models import CustomUser
import logging

logger = logging.getLogger(__name__)

def send_session_scheduled_notification(session):
    """Send notification about scheduled session"""
    try:
        # Create notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_scheduled',
            title='New Session Scheduled',
            message=f'Session {session.program_session_number}: {session.session_template.title} scheduled for {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
        )
        
        # Also send to mentor for confirmation
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_scheduled',
            title='Session Scheduled',
            message=f'You scheduled Session {session.program_session_number} with {session.mentorship.mentee.full_name} for {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
        )
        
        logger.info(f"Session scheduled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session scheduled notification: {str(e)}")


def send_session_completed_notification(session):
    """Send notification about completed session"""
    try:
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_completed',
            title='Session Completed',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been marked as completed',
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_completed',
            title='Session Completed',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been marked as completed',
        )
        
        logger.info(f"Session completed notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session completed notification: {str(e)}")


def send_session_cancelled_notification(session, reason):
    """Send notification about cancelled session"""
    try:
        # Determine who cancelled
        cancelled_by = session.completed_by.full_name if session.completed_by else 'System'
        
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_cancelled',
            title='Session Cancelled',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been cancelled by {cancelled_by}. Reason: {reason}',
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_cancelled',
            title='Session Cancelled',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been cancelled',
        )
        
        logger.info(f"Session cancelled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session cancelled notification: {str(e)}")


def send_session_rescheduled_notification(session, old_date):
    """Send notification about rescheduled session"""
    try:
        # Calculate time difference
        time_diff = session.scheduled_date - old_date
        days_diff = time_diff.days
        hours_diff = time_diff.seconds // 3600
        
        time_change_text = ""
        if days_diff != 0:
            time_change_text = f"{abs(days_diff)} day(s) {'later' if days_diff > 0 else 'earlier'}"
        elif hours_diff != 0:
            time_change_text = f"{abs(hours_diff)} hour(s) {'later' if hours_diff > 0 else 'earlier'}"
        else:
            time_change_text = "at the same time"
        
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_rescheduled',
            title='Session Rescheduled',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been rescheduled to {session.scheduled_date.strftime("%Y-%m-%d %H:%M")} ({time_change_text})',
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_rescheduled',
            title='Session Rescheduled',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been rescheduled to {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
        )
        
        logger.info(f"Session rescheduled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session rescheduled notification: {str(e)}")


def send_upcoming_session_reminder(session):
    """Send reminder for upcoming session (24 hours before)"""
    try:
        # Calculate time until session
        time_until = session.scheduled_date - timezone.now()
        hours_until = time_until.total_seconds() / 3600
        
        if 23 <= hours_until <= 25:  # Send 24 hour reminder
            # Notification for mentee
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Reminder - Tomorrow',
                message=f'Reminder: Session {session.program_session_number}: {session.session_template.title} is scheduled for tomorrow at {session.scheduled_date.strftime("%H:%M")}',
            )
            
            # Notification for mentor
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Reminder - Tomorrow',
                message=f'Reminder: Session {session.program_session_number} with {session.mentorship.mentee.full_name} is scheduled for tomorrow at {session.scheduled_date.strftime("%H:%M")}',
            )
            
            logger.info(f"24-hour reminder sent for session {session.id}")
            
        elif 0.5 <= hours_until <= 1.5:  # Send 1 hour reminder
            # Notification for mentee
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Starting Soon',
                message=f'Session {session.program_session_number}: {session.session_template.title} starts in 1 hour',
            )
            
            # Notification for mentor
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Starting Soon',
                message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} starts in 1 hour',
            )
            
            logger.info(f"1-hour reminder sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session reminder: {str(e)}")


def send_program_completed_notification(mentorship, program):
    """Send notification when a program is completed"""
    try:
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=mentorship.mentee,
            chat_room=get_chat_room(mentorship),
            notification_type='program_completed',
            title='Program Completed! 🎉',
            message=f'Congratulations! You have completed the {program.name} program',
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=mentorship.mentor,
            chat_room=get_chat_room(mentorship),
            notification_type='program_completed',
            title='Program Completed',
            message=f'{mentorship.mentee.full_name} has completed the {program.name} program',
        )
        
        logger.info(f"Program completed notification sent for program {program.id}")
        
    except Exception as e:
        logger.error(f"Error sending program completed notification: {str(e)}")


def send_mentorship_completed_notification(mentorship):
    """Send notification when mentorship is completed"""
    try:
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=mentorship.mentee,
            chat_room=get_chat_room(mentorship),
            notification_type='mentorship_completed',
            title='Mentorship Completed! 🎓',
            message=f'Congratulations on completing your mentorship journey!',
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=mentorship.mentor,
            chat_room=get_chat_room(mentorship),
            notification_type='mentorship_completed',
            title='Mentorship Completed',
            message=f'Your mentorship with {mentorship.mentee.full_name} has been completed',
        )
        
        # Notification for admin/HR if mentorship has high rating
        if mentorship.rating and mentorship.rating >= 4.5:
            admins = CustomUser.objects.filter(
                role__in=['admin', 'hr'],
                status='approved'
            )
            
            for admin in admins:
                ChatNotification.objects.create(
                    recipient=admin,
                    notification_type='mentorship_success',
                    title='High-Rated Mentorship Completed',
                    message=f'Mentorship between {mentorship.mentor.full_name} and {mentorship.mentee.full_name} completed with rating: {mentorship.rating}/5',
                )
        
        logger.info(f"Mentorship completed notification sent for mentorship {mentorship.id}")
        
    except Exception as e:
        logger.error(f"Error sending mentorship completed notification: {str(e)}")


# Helper functions
def get_chat_room(mentorship):
    """Get or create chat room for mentorship"""
    try:
        # Try to find existing mentorship chat room
        chat_room = ChatRoom.objects.filter(
            chat_type=ChatRoomType.MENTORSHIP_GROUP,
            mentorship=mentorship,
            is_active=True
        ).first()
        
        if chat_room:
            return chat_room
        
        # Create new mentorship chat room if it doesn't exist
        from chatApp.signals import create_mentorship_chats
        # The signal should have created it, but just in case
        chat_room = ChatRoom.objects.create(
            name=f'Mentorship: {mentorship.mentor.full_name} - {mentorship.mentee.full_name}',
            chat_type=ChatRoomType.MENTORSHIP_GROUP,
            mentorship=mentorship,
            created_by=mentorship.mentor,
            is_active=True
        )
        
        # Add participants
        ChatParticipant.objects.create(
            chat_room=chat_room,
            user=mentorship.mentor,
            role='admin'
        )
        ChatParticipant.objects.create(
            chat_room=chat_room,
            user=mentorship.mentee,
            role='member'
        )
        
        return chat_room
        
    except Exception as e:
        logger.error(f"Error getting chat room: {str(e)}")
        return None


def get_total_sessions_completed(mentorship):
    """Get total sessions completed in mentorship"""
    try:
        from mentorshipApp.models import MentorshipSession
        return MentorshipSession.objects.filter(
            mentorship=mentorship,
            status='completed'
        ).count()
        
    except Exception as e:
        logger.error(f"Error getting total sessions completed: {str(e)}")
        return 0


# Background task to send session reminders
def send_all_upcoming_session_reminders():
    """Send reminders for all upcoming sessions"""
    try:
        from mentorshipApp.models import MentorshipSession
        
        # Get all scheduled sessions in the next 25 hours
        time_threshold = timezone.now() + timedelta(hours=25)
        
        upcoming_sessions = MentorshipSession.objects.filter(
            status='scheduled',
            scheduled_date__gte=timezone.now(),
            scheduled_date__lte=time_threshold
        ).select_related('mentorship', 'mentorship__mentor', 'mentorship__mentee', 'session_template')
        
        logger.info(f"Checking {upcoming_sessions.count()} upcoming sessions for reminders")
        
        for session in upcoming_sessions:
            send_upcoming_session_reminder(session)
        
        logger.info("Session reminder check completed")
        
    except Exception as e:
        logger.error(f"Error sending session reminders: {str(e)}")


# WebSocket and real-time notification functions
def send_notification_to_user(user_id, notification_data):
    """Send real-time notification to a specific user via WebSocket"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {
            'type': 'notification_message',
            'notification': notification_data
        }
    )


def send_email_notification(recipient_email, subject, template_name, context):
    """Send email notification"""
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
        logger.error(f"Error sending email: {e}")
        return False


def create_system_message(chat_room, content):
    """Create a system message in a chat room"""
    try:
        # Get or create a system user
        system_user, created = CustomUser.objects.get_or_create(
            phone_number='system',
            defaults={
                'role': 'admin',
                'email': 'system@example.com',
                'full_name': 'System',
                'status': 'approved'
            }
        )
        
        message = Message.objects.create(
            chat_room=chat_room,
            sender=system_user,
            content=content,
            message_type='text'
        )
        
        # Send real-time update
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_room.id}",
            {
                'type': 'chat_message',
                'message': {
                    'id': message.id,
                    'content': message.content,
                    'sender': system_user.full_name,
                    'created_at': message.created_at.isoformat()
                }
            }
        )
        
        return message
    except Exception as e:
        logger.error(f"Error creating system message: {e}")
        return None


def get_user_chat_stats(user):
    """Get chat statistics for a user"""
    stats = {
        'total_chat_rooms': 0,
        'active_chat_rooms': 0,
        'total_messages_sent': 0,
        'unread_messages': 0,
        'unread_notifications': 0
    }
    
    try:
        # Get all chat rooms where user is a participant
        user_chat_rooms = ChatRoom.objects.filter(
            participants=user,
            is_active=True
        )
        
        stats['total_chat_rooms'] = user_chat_rooms.count()
        stats['active_chat_rooms'] = user_chat_rooms.count()
        
        # Count messages sent by user
        stats['total_messages_sent'] = Message.objects.filter(
            chat_room__in=user_chat_rooms,
            sender=user,
            is_deleted=False
        ).count()
        
        # Count unread messages
        unread_count = 0
        for chat_room in user_chat_rooms:
            participant = ChatParticipant.objects.filter(
                chat_room=chat_room,
                user=user
            ).first()
            
            if participant and participant.last_read_at:
                unread_count += Message.objects.filter(
                    chat_room=chat_room,
                    created_at__gt=participant.last_read_at,
                    is_deleted=False
                ).exclude(sender=user).count()
            else:
                unread_count += Message.objects.filter(
                    chat_room=chat_room,
                    is_deleted=False
                ).exclude(sender=user).count()
        
        stats['unread_messages'] = unread_count
        
        # Count unread notifications
        stats['unread_notifications'] = ChatNotification.objects.filter(
            recipient=user,
            is_read=False
        ).count()
        
    except Exception as e:
        logger.error(f"Error getting chat stats: {e}")
    
    return stats


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
        # Get all user chat rooms
        user_chats = ChatRoom.objects.filter(
            participants=user,
            is_active=True
        )
        
        stats['total_chats'] = user_chats.count()
        
        # Count unread messages
        total_unread = 0
        for chat in user_chats:
            participant = ChatParticipant.objects.filter(
                chat_room=chat,
                user=user
            ).first()
            
            if participant and participant.last_read_at:
                total_unread += Message.objects.filter(
                    chat_room=chat,
                    created_at__gt=participant.last_read_at,
                    is_deleted=False
                ).exclude(sender=user).count()
            else:
                total_unread += Message.objects.filter(
                    chat_room=chat,
                    is_deleted=False
                ).exclude(sender=user).count()
        
        stats['unread_messages'] = total_unread
        
        # Active conversations (chats with activity in last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        stats['active_conversations'] = user_chats.filter(
            messages__created_at__gte=week_ago
        ).distinct().count()
        
        # Count by chat type
        stats['mentorship_chats'] = user_chats.filter(
            chat_type=ChatRoomType.MENTORSHIP_GROUP
        ).count()
        
        stats['department_chats'] = user_chats.filter(
            chat_type=ChatRoomType.DEPARTMENT_GROUP
        ).count()
        
        stats['staff_chats'] = user_chats.filter(
            chat_type=ChatRoomType.STAFF_CHAT
        ).count()
        
    except Exception as e:
        logger.error(f"Error getting chat statistics: {e}")
    
    return stats


def validate_file_upload(file):
    """Validate file uploads for chat attachments"""
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