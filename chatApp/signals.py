# chatApp/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from mentorshipApp.models import Mentorship
from .models import ChatRoom, ChatRoomType, ChatParticipant
from notificationApp.models import ChatNotification
from userApp.models import CustomUser


@receiver(post_save, sender=Mentorship)
def create_mentorship_chats(sender, instance, created, **kwargs):
    """Create chats when mentorship is created"""
    if created and instance.status == 'active':
        # Get the department from the mentorship
        department = instance.department
        
        # Create mentorship group chat
        chat_room = ChatRoom.objects.create(
            name=f"{instance.mentee.full_name}'s Mentorship Group - {department.name}",
            chat_type=ChatRoomType.MENTORSHIP_GROUP,
            mentorship=instance,
            department=department,
            created_by=instance.created_by if instance.created_by else instance.mentor,
            is_active=True
        )
        
        # Add mentor as participant
        ChatParticipant.objects.create(
            chat_room=chat_room,
            user=instance.mentor,
            role='admin'
        )
        
        # Add mentee as participant
        ChatParticipant.objects.create(
            chat_room=chat_room,
            user=instance.mentee,
            role='member'
        )
        
        # Get admin and HR users in the department
        admin_hr_users = CustomUser.objects.filter(
            department=department,
            role__in=['admin', 'hr'],
            status='approved'
        )
        
        # Add admin and HR users as participants
        for user in admin_hr_users:
            ChatParticipant.objects.create(
                chat_room=chat_room,
                user=user,
                role='admin'
            )
        
        # Create or get department-wide chat
        dept_chat_name = f"{department.name} Department Chat"
        dept_chat, dept_created = ChatRoom.objects.get_or_create(
            chat_type=ChatRoomType.DEPARTMENT_GROUP,
            department=department,
            defaults={
                'name': dept_chat_name,
                'created_by': chat_room.created_by,
                'is_active': True
            }
        )
        
        # Add mentee to department chat if not already a participant
        ChatParticipant.objects.get_or_create(
            chat_room=dept_chat,
            user=instance.mentee,
            defaults={'role': 'member'}
        )
        
        # Add mentor to department chat if not already a participant
        ChatParticipant.objects.get_or_create(
            chat_room=dept_chat,
            user=instance.mentor,
            defaults={'role': 'admin'}
        )


@receiver(post_save, sender=Mentorship)
def ensure_user_chats_exist(sender, instance, created, **kwargs):
    """Ensure all required chats exist for mentorship participants"""
    if instance.status == 'active':
        department = instance.department
        
        # Ensure mentorship group chat exists
        chat_room, group_created = ChatRoom.objects.get_or_create(
            mentorship=instance,
            chat_type=ChatRoomType.MENTORSHIP_GROUP,
            defaults={
                'name': f"{instance.mentee.full_name}'s Mentorship - {department.name}",
                'department': department,
                'created_by': instance.created_by if instance.created_by else instance.mentor,
                'is_active': True
            }
        )
        
        # Ensure mentor is in the group chat
        ChatParticipant.objects.get_or_create(
            chat_room=chat_room,
            user=instance.mentor,
            defaults={'role': 'admin'}
        )
        
        # Ensure mentee is in the group chat
        ChatParticipant.objects.get_or_create(
            chat_room=chat_room,
            user=instance.mentee,
            defaults={'role': 'member'}
        )
        
        # Add relevant admin/HR users from the same department
        department_staff = CustomUser.objects.filter(
            department=department,
            role__in=['admin', 'hr'],
            status='approved'
        )
        
        for staff_user in department_staff:
            ChatParticipant.objects.get_or_create(
                chat_room=chat_room,
                user=staff_user,
                defaults={'role': 'admin'}
            )
        
        # Ensure department group chat exists
        dept_chat_name = f"{department.name} Department Chat"
        dept_chat, dept_created = ChatRoom.objects.get_or_create(
            chat_type=ChatRoomType.DEPARTMENT_GROUP,
            department=department,
            defaults={
                'name': dept_chat_name,
                'created_by': chat_room.created_by,
                'is_active': True
            }
        )
        
        # Add mentee to department chat if not already a participant
        ChatParticipant.objects.get_or_create(
            chat_room=dept_chat,
            user=instance.mentee,
            defaults={'role': 'member'}
        )
        
        # Add mentor to department chat if not already a participant
        ChatParticipant.objects.get_or_create(
            chat_room=dept_chat,
            user=instance.mentor,
            defaults={'role': 'admin'}
        )


@receiver(post_save, sender=CustomUser)
def create_staff_chats_for_new_user(sender, instance, created, **kwargs):
    """Create chats for new users based on their role"""
    if created and instance.status == 'approved':
        # If user is admin or HR, add them to staff chat
        if instance.role in ['admin', 'hr']:
            # Get or create staff chat
            staff_chat, staff_created = ChatRoom.objects.get_or_create(
                chat_type=ChatRoomType.STAFF_CHAT,
                defaults={
                    'name': 'Staff Chat',
                    'created_by': instance,
                    'is_active': True
                }
            )
            
            # Add the new staff member to staff chat
            ChatParticipant.objects.get_or_create(
                chat_room=staff_chat,
                user=instance,
                defaults={'role': 'admin'}
            )
        
        # If user has a department, add them to department chat
        if instance.department:
            dept_chat, dept_created = ChatRoom.objects.get_or_create(
                chat_type=ChatRoomType.DEPARTMENT_GROUP,
                department=instance.department,
                defaults={
                    'name': f"{instance.department.name} Department Chat",
                    'created_by': instance,
                    'is_active': True
                }
            )
            
            # Determine role based on user role
            participant_role = 'admin' if instance.role in ['admin', 'hr'] else 'member'
            
            ChatParticipant.objects.get_or_create(
                chat_room=dept_chat,
                user=instance,
                defaults={'role': participant_role}
            )
        
        # Add to global chat if it exists
        global_chat = ChatRoom.objects.filter(
            chat_type=ChatRoomType.GLOBAL,
            is_active=True
        ).first()
        
        if global_chat:
            participant_role = 'admin' if instance.role in ['admin', 'hr'] else 'member'
            ChatParticipant.objects.get_or_create(
                chat_room=global_chat,
                user=instance,
                defaults={'role': participant_role}
            )


@receiver(post_save, sender=ChatNotification)
def send_realtime_notification(sender, instance, created, **kwargs):
    """Send real-time notification via WebSocket when a new notification is created"""
    if created:
        channel_layer = get_channel_layer()
        
        # Send to user's notification channel
        async_to_sync(channel_layer.group_send)(
            f"user_{instance.recipient.id}",
            {
                'type': 'notification_message',
                'notification': {
                    'id': instance.id,
                    'title': instance.title,
                    'message': instance.message,
                    'notification_type': instance.notification_type,
                    'created_at': instance.created_at.isoformat(),
                    'sender': {
                        'id': instance.sender.id,
                        'full_name': instance.sender.full_name
                    } if instance.sender else None
                }
            }
        )