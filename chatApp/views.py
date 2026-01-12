from datetime import timedelta
import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.timezone import now

from .models import CallParticipant, ChatRoom, ChatParticipant, Message, ChatRoomType, TypingIndicator, VideoCall
from .serializers import (
    ChatRoomSerializer, MessageSerializer, ChatParticipantSerializer,
    CreateChatRoomSerializer, SendMessageSerializer, TypingIndicatorSerializer, UserBasicSerializer, VideoCallInitiateSerializer, VideoCallSerializer, WebRTCSignalSerializer
)
from userApp.models import CustomUser
from mentorshipApp.models import Mentorship
from departmentApp.models import Department
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Setup logger
logger = logging.getLogger(__name__)

# ====== Helper Functions ======

def handle_exception(e, context=""):
    """Handle exceptions consistently with logging and appropriate response"""
    error_message = f"{context}: {str(e)}" if context else str(e)
    logger.error(f"ERROR: {error_message}")
    print(f"ERROR: {error_message}")
    
    # Return appropriate response based on exception type
    if isinstance(e, ValidationError):
        return Response(
            {'error': 'Validation error', 'details': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    elif isinstance(e, PermissionDenied):
        return Response(
            {'error': 'Permission denied', 'details': str(e)},
            status=status.HTTP_403_FORBIDDEN
        )
    elif isinstance(e, DatabaseError) or isinstance(e, IntegrityError):
        return Response(
            {'error': 'Database error', 'details': 'Please try again later'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    else:
        return Response(
            {'error': 'Internal server error', 'details': 'An unexpected error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# ====== Chat Room Management ======

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_chat_rooms(request):
    """Get all chat rooms the user belongs to"""
    try:
        logger.info(f"Getting chat rooms for user: {request.user.id}")
        user = request.user
        
        # Validate user is active
        if not user.is_active:
            logger.warning(f"Inactive user {user.id} attempted to access chats")
            return Response(
                {'error': 'User account is inactive'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get user's chat rooms
        chat_rooms = ChatRoom.objects.filter(
            participants=user,
            is_active=True
        ).prefetch_related('participants', 'messages')
        # print debug info
        logger.info(f"Found {chat_rooms.count()} chat rooms for user {user.id}")
                
        serializer = ChatRoomSerializer(chat_rooms, many=True, context={'request': request})

        print(f"DEBUG: Serialized chat rooms for user {user.id}: {serializer.data}")

        return Response({
            'success': True,
            'count': chat_rooms.count(),
            'chats': serializer.data
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to get chat rooms")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_chat_room(request):
    """Create a new chat room"""
    try:
        logger.info(f"User {request.user.id} attempting to create chat room")
        user = request.user
        
        # Validate user can create chats
        if user.status != 'approved':
            logger.warning(f"Non-approved user {user.id} attempted to create chat room")
            return Response(
                {'error': 'Your account must be approved to create chat rooms'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate request data
        serializer = CreateChatRoomSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            logger.warning(f"Invalid chat room creation data: {serializer.errors}")
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        chat_type = data['chat_type']
        
        logger.info(f"Creating {chat_type} chat room")
        
        # Create chat room
        chat_room = ChatRoom.objects.create(
            chat_type=chat_type,
            created_by=user
        )
        
        # Validate and set relationships based on chat type
        if chat_type == ChatRoomType.MENTORSHIP_GROUP:
            if 'mentorship_id' not in data:
                raise ValidationError('mentorship_id is required for mentorship group chat')
            
            mentorship = get_object_or_404(Mentorship, id=data['mentorship_id'])
            
            # Validate mentorship is active
            if mentorship.status != 'active':
                raise ValidationError('Cannot create chat for inactive mentorship')
            
            chat_room.mentorship = mentorship
            chat_room.save()
            
            # Validate both mentor and mentee exist and are approved
            if not mentorship.mentor or mentorship.mentor.status != 'approved':
                raise ValidationError('Mentor is not approved or does not exist')
            if not mentorship.mentee or mentorship.mentee.status != 'approved':
                raise ValidationError('Mentee is not approved or does not exist')
            
            # Auto-add mentor and mentee
            chat_room.participants.add(mentorship.mentor, mentorship.mentee)
            
            # Add admin/hr if they should have access
            if user.role in ['admin', 'hr']:
                chat_room.participants.add(user)
        
        elif chat_type == ChatRoomType.DEPARTMENT_GROUP:
            if 'department_id' not in data:
                raise ValidationError('department_id is required for department group chat')
            
            department = get_object_or_404(Department, id=data['department_id'])
            chat_room.department = department
            chat_room.save()
            
            # Validate department exists and is active
            if not department.is_active:
                raise ValidationError('Cannot create chat for inactive department')
            
            # Add all approved users in department
            department_users = CustomUser.objects.filter(
                department=department,
                status='approved'
            )
            if not department_users.exists():
                raise ValidationError('No approved users in this department')
            
            chat_room.participants.add(*department_users)
            
            # Add admin/hr
            admin_hr_users = CustomUser.objects.filter(
                role__in=['admin', 'hr'],
                status='approved'
            )
            if admin_hr_users.exists():
                chat_room.participants.add(*admin_hr_users)
        
        elif chat_type == ChatRoomType.STAFF_CHAT:
            # Validate user is admin/hr
            if user.role not in ['admin', 'hr']:
                raise PermissionDenied('Only admin/HR can create staff chats')
            
            # Add all admin/hr users
            staff_users = CustomUser.objects.filter(
                role__in=['admin', 'hr'],
                status='approved'
            )
            if not staff_users.exists():
                raise ValidationError('No approved admin/HR users found')
            
            chat_room.participants.add(*staff_users)
        
        elif chat_type == ChatRoomType.GLOBAL:
            # Validate user is admin
            if user.role != 'admin':
                raise PermissionDenied('Only admin can create global chat')
            
            # Add all approved users
            approved_users = CustomUser.objects.filter(status='approved')
            if not approved_users.exists():
                raise ValidationError('No approved users found')
            
            chat_room.participants.add(*approved_users)
        
        elif chat_type == ChatRoomType.ONE_ON_ONE:
            # Validate participant IDs
            if not data.get('participant_ids'):
                raise ValidationError('participant_ids is required for one-on-one chat')
            
            if len(data['participant_ids']) != 1:
                raise ValidationError('One-on-one chat requires exactly one other participant')
            
            participant_id = data['participant_ids'][0]
            
            # Prevent self-chat
            if participant_id == user.id:
                raise ValidationError('Cannot create one-on-one chat with yourself')
            
            # Get and validate participant
            try:
                participant = CustomUser.objects.get(
                    id=participant_id,
                    status='approved'
                )
            except CustomUser.DoesNotExist:
                raise ValidationError('Participant not found or not approved')
            
            # Check if chat already exists
            existing_chat = ChatRoom.objects.filter(
                chat_type=ChatRoomType.ONE_ON_ONE,
                participants=user
            ).filter(participants=participant).first()
            
            if existing_chat:
                return Response({
                    'success': True,
                    'message': 'Chat already exists',
                    'chat': ChatRoomSerializer(existing_chat, context={'request': request}).data
                }, status=status.HTTP_200_OK)
            
            # Add participants
            chat_room.participants.add(user, participant)
        
        else:
            raise ValidationError(f'Invalid chat type: {chat_type}')
        
        # Save name after participants are added
        chat_room.save()
        
        logger.info(f"Successfully created chat room {chat_room.id} of type {chat_type}")
        
        return Response({
            'success': True,
            'message': 'Chat room created successfully',
            'chat': ChatRoomSerializer(chat_room, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in chat room creation")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in chat room creation")
    except Exception as e:
        return handle_exception(e, "Failed to create chat room")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_room(request, room_id):
    """Get specific chat room"""
    try:
        logger.info(f"User {request.user.id} accessing chat room {room_id}")
        user = request.user
        
        # Validate room ID format
        if not room_id or not str(room_id).isdigit():
            raise ValidationError('Invalid chat room ID format')
        
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        
        # Check if user is participant
        is_participant = chat_room.participants.filter(id=user.id).exists()
        
        # Allow admin/hr to view all chats
        if not is_participant and user.role not in ['admin', 'hr']:
            logger.warning(f"User {user.id} attempted to access non-participant chat {room_id}")
            raise PermissionDenied('You are not a participant in this chat')
        
        # If admin/hr viewing but not a participant, add them temporarily
        if user.role in ['admin', 'hr'] and not is_participant:
            logger.info(f"Admin/HR user {user.id} accessing non-participant chat {room_id}")
        
        serializer = ChatRoomSerializer(chat_room, context={'request': request})
        
        return Response({
            'success': True,
            'access_type': 'participant' if is_participant else 'admin/hr_privilege',
            'chat': serializer.data
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in get_chat_room")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in get_chat_room")
    except Exception as e:
        return handle_exception(e, f"Failed to get chat room {room_id}")

# ====== Message Handling ======

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_messages(request, room_id):
    """Get messages in a chat room"""
    try:
        logger.info(f"User {request.user.id} getting messages from chat {room_id}")
        user = request.user
        
        # Validate room ID
        if not room_id or not str(room_id).isdigit():
            raise ValidationError('Invalid chat room ID format')
        
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        
        # Check access
        is_participant = chat_room.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            logger.warning(f"User {user.id} attempted to access messages in non-participant chat {room_id}")
            raise PermissionDenied('Access denied to chat messages')
        
        # Get messages with pagination support
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))
        
        messages = chat_room.messages.filter(
            is_deleted=False
        ).order_by('created_at')[offset:offset + limit]
        
        total_count = chat_room.messages.filter(is_deleted=False).count()
        
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        
        # Update last read time if user is participant
        if is_participant:
            ChatParticipant.objects.filter(
                chat_room=chat_room,
                user=user
            ).update(last_read_at=now())
            logger.debug(f"Updated last read time for user {user.id} in chat {room_id}")
        
        return Response({
            'success': True,
            'messages': serializer.data,
            'pagination': {
                'total': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in get_messages")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in get_messages")
    except Exception as e:
        return handle_exception(e, f"Failed to get messages for chat {room_id}")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request):
    """Send a message to any chat room"""
    try:
        logger.info(f"User {request.user.id} attempting to send message")
        user = request.user
        
        # Validate user is approved
        if user.status != 'approved':
            raise PermissionDenied('Your account must be approved to send messages')
        
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid message data: {serializer.errors}")
            return Response({
                'error': 'Invalid message data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        chat_room_id = data['chat_room_id']
        
        # Validate chat room exists and is active
        chat_room = get_object_or_404(ChatRoom, id=chat_room_id, is_active=True)
        
        # Check if user can send messages in this chat
        is_participant = chat_room.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            logger.warning(f"User {user.id} attempted to send message in non-participant chat {chat_room_id}")
            raise PermissionDenied('You cannot send messages in this chat')
        
        # Validate content
        content = data['content']
        message_type = data['message_type']
        
        if message_type == 'text' and not content.strip():
            raise ValidationError('Message content cannot be empty')
        
        # Check for spam/rate limiting (simplified example)
        recent_messages = Message.objects.filter(
            sender=user,
            created_at__gte=now() - timedelta(seconds=10)
        ).count()
        
        if recent_messages > 5:  # More than 5 messages in 10 seconds
            logger.warning(f"Possible spam from user {user.id}: {recent_messages} messages in 10s")
            raise ValidationError('Message rate limit exceeded. Please wait before sending more messages.')
        
        # Create message
        message = Message.objects.create(
            chat_room=chat_room,
            sender=user,
            message_type=message_type,
            content=content,
            attachment=data.get('attachment')
        )
        
        # Update chat room timestamp
        chat_room.updated_at = now()
        chat_room.save()
        
        logger.info(f"Message {message.id} sent by user {user.id} in chat {chat_room_id}")
        
        return Response({
            'success': True,
            'message': 'Message sent successfully',
            'data': MessageSerializer(message, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in send_message")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in send_message")
    except Exception as e:
        return handle_exception(e, "Failed to send message")

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_message(request, message_id):
    """Delete a message"""
    try:
        logger.info(f"User {request.user.id} attempting to delete message {message_id}")
        user = request.user
        
        # Validate message ID
        if not message_id or not str(message_id).isdigit():
            raise ValidationError('Invalid message ID format')
        
        message = get_object_or_404(Message, id=message_id)
        
        # Check if message is already deleted
        if message.is_deleted:
            return Response({
                'success': True,
                'message': 'Message already deleted'
            }, status=status.HTTP_200_OK)
        
        # Check permissions
        if not message.can_delete(user):
            logger.warning(f"User {user.id} attempted to delete unauthorized message {message_id}")
            raise PermissionDenied('You cannot delete this message')
        
        # Soft delete the message
        message.is_deleted = True
        message.deleted_at = now()
        message.deleted_by = user
        message.save()
        
        logger.info(f"Message {message_id} deleted by user {user.id}")
        
        return Response({
            'success': True,
            'message': 'Message deleted successfully'
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in delete_message")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in delete_message")
    except Exception as e:
        return handle_exception(e, f"Failed to delete message {message_id}")

# ====== Participant Management ======

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_participant(request, room_id):
    """Add participant to chat room"""
    try:
        logger.info(f"User {request.user.id} adding participant to chat {room_id}")
        user = request.user
        
        # Validate room ID
        if not room_id or not str(room_id).isdigit():
            raise ValidationError('Invalid chat room ID format')
        
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        
        # Check permissions
        if not chat_room.can_add_participants(user):
            logger.warning(f"User {user.id} attempted to add participant without permission to chat {room_id}")
            raise PermissionDenied('You cannot add participants to this chat')
        
        participant_id = request.data.get('user_id')
        if not participant_id:
            raise ValidationError('User ID is required')
        
        # Validate participant ID format
        if not str(participant_id).isdigit():
            raise ValidationError('Invalid user ID format')
        
        # Get and validate participant
        try:
            participant = CustomUser.objects.get(id=participant_id, status='approved')
        except CustomUser.DoesNotExist:
            raise ValidationError('User not found or not approved')
        
        # Check if participant is already in chat
        if chat_room.participants.filter(id=participant_id).exists():
            return Response({
                'success': True,
                'message': 'User is already a participant in this chat'
            }, status=status.HTTP_200_OK)
        
        # Check chat type restrictions
        if chat_room.chat_type == ChatRoomType.ONE_ON_ONE:
            raise ValidationError('Cannot add participants to one-on-one chat')
        
        # Add participant
        ChatParticipant.objects.create(
            chat_room=chat_room,
            user=participant,
            role='member',
            joined_at=now()
        )
        
        logger.info(f"User {participant_id} added to chat {room_id} by user {user.id}")
        
        return Response({
            'success': True,
            'message': 'Participant added successfully',
            'participant': UserBasicSerializer(participant).data
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in add_participant")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in add_participant")
    except Exception as e:
        return handle_exception(e, f"Failed to add participant to chat {room_id}")

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_participant(request, room_id, user_id):
    print( f"User {request.user.id} removing participant {user_id} from chat {room_id}" )
    """Remove participant from chat room"""
    try:
        logger.info(f"User {request.user.id} removing participant {user_id} from chat {room_id}")
        user = request.user
        
        # Validate IDs
        if not room_id or not str(room_id).isdigit():
            raise ValidationError('Invalid chat room ID format')
        if not user_id or not str(user_id).isdigit():
            raise ValidationError('Invalid user ID format')
        
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        target_user = get_object_or_404(CustomUser, id=user_id)
        
        # Check permissions - only admin can remove
        if user.role != 'admin':
            logger.warning(f"Non-admin user {user.id} attempted to remove participant {user_id} from chat {room_id}")
            raise PermissionDenied('Only admin can remove participants')
        
        # Check if target user is a participant
        if not chat_room.participants.filter(id=user_id).exists():
            return Response({
                'success': True,
                'message': 'User is not a participant in this chat'
            }, status=status.HTTP_200_OK)
        
        # Can't remove yourself if you're the last admin
        if user_id == user.id:
            admin_participants = chat_room.chat_participants.filter(
                user__role='admin'
            ).count()
            if admin_participants <= 1:
                raise ValidationError('Cannot remove the last admin from the chat')
        
        # Remove participant
        ChatParticipant.objects.filter(
            chat_room=chat_room,
            user_id=user_id
        ).delete()
        
        logger.info(f"User {user_id} removed from chat {room_id} by admin {user.id}")
        
        return Response({
            'success': True,
            'message': 'Participant removed successfully'
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in remove_participant")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in remove_participant")
    except Exception as e:
        return handle_exception(e, f"Failed to remove participant {user_id} from chat {room_id}")

# ====== Chat Discovery ======

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def discover_chats(request):
    """Discover available chats based on user role"""
    try:
        logger.info(f"User {request.user.id} discovering chats")
        user = request.user
        
        if not user.is_active:
            raise PermissionDenied('User account is inactive')
        
        response_data = {
            'success': True,
            'my_chats': []
        }
        
        # All users see chats they participate in
        my_chats = ChatRoom.objects.filter(
            participants=user,
            is_active=True
        ).order_by('-updated_at')
        
        response_data['my_chats'] = ChatRoomSerializer(
            my_chats, many=True, context={'request': request}
        ).data
        response_data['my_chats_count'] = my_chats.count()
        
        # Mentors see mentorship chats
        if user.role == 'mentor':
            try:
                mentorships = Mentorship.objects.filter(mentor=user, status='active')
                mentorship_rooms = ChatRoom.objects.filter(
                    mentorship__in=mentorships,
                    chat_type=ChatRoomType.MENTORSHIP_GROUP,
                    is_active=True
                )
                response_data['mentorship_chats'] = ChatRoomSerializer(
                    mentorship_rooms, many=True, context={'request': request}
                ).data
                response_data['mentorship_chats_count'] = mentorship_rooms.count()
            except Exception as e:
                logger.error(f"Error fetching mentorship chats: {str(e)}")
                response_data['mentorship_chats_error'] = 'Failed to load mentorship chats'
        
        # Department chats for users with department
        if user.department:
            try:
                dept_chats = ChatRoom.objects.filter(
                    department=user.department,
                    chat_type=ChatRoomType.DEPARTMENT_GROUP,
                    is_active=True
                )
                response_data['department_chats'] = ChatRoomSerializer(
                    dept_chats, many=True, context={'request': request}
                ).data
                response_data['department_chats_count'] = dept_chats.count()
            except Exception as e:
                logger.error(f"Error fetching department chats: {str(e)}")
                response_data['department_chats_error'] = 'Failed to load department chats'
        
        # Admin/HR see all chats
        if user.role in ['admin', 'hr']:
            try:
                all_chats = ChatRoom.objects.filter(is_active=True).order_by('-updated_at')
                response_data['all_chats'] = ChatRoomSerializer(
                    all_chats, many=True, context={'request': request}
                ).data[:50]  # Limit to 50 for performance
                response_data['all_chats_count'] = all_chats.count()
            except Exception as e:
                logger.error(f"Error fetching all chats: {str(e)}")
                response_data['all_chats_error'] = 'Failed to load all chats'
        
        # Global chat (if exists)
        try:
            global_chat = ChatRoom.objects.filter(
                chat_type=ChatRoomType.GLOBAL,
                is_active=True
            ).first()
            if global_chat and global_chat.participants.filter(id=user.id).exists():
                response_data['global_chat'] = ChatRoomSerializer(
                    global_chat, context={'request': request}
                ).data
        except Exception as e:
            logger.error(f"Error fetching global chat: {str(e)}")
        
        logger.info(f"Successfully discovered chats for user {user.id}")
        return Response(response_data)
        
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in discover_chats")
    except Exception as e:
        return handle_exception(e, "Failed to discover chats")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_or_create_one_on_one(request, user_id):
    """Get or create one-on-one chat with another user"""
    try:
        logger.info(f"User {request.user.id} getting/creating 1:1 chat with user {user_id}")
        current_user = request.user
        
        # Validate user IDs
        if not user_id or not str(user_id).isdigit():
            raise ValidationError('Invalid user ID format')
        
        if int(user_id) == current_user.id:
            raise ValidationError('Cannot create one-on-one chat with yourself')
        
        # Get other user
        try:
            other_user = CustomUser.objects.get(id=user_id, status='approved')
        except CustomUser.DoesNotExist:
            raise ValidationError('User not found or not approved')
        
        # Validate both users are active
        if not current_user.is_active:
            raise PermissionDenied('Your account is inactive')
        if not other_user.is_active:
            raise ValidationError('The other user account is inactive')
        
        # Find existing one-on-one chat
        existing_chat = ChatRoom.objects.filter(
            chat_type=ChatRoomType.ONE_ON_ONE,
            participants=current_user
        ).filter(participants=other_user).first()
        
        if existing_chat:
            logger.info(f"Found existing 1:1 chat {existing_chat.id} between {current_user.id} and {user_id}")
            return Response({
                'success': True,
                'message': 'Existing chat found',
                'chat': ChatRoomSerializer(existing_chat, context={'request': request}).data
            })
        
        # Create new one-on-one chat
        logger.info(f"Creating new 1:1 chat between {current_user.id} and {user_id}")
        chat_room = ChatRoom.objects.create(
            chat_type=ChatRoomType.ONE_ON_ONE,
            created_by=current_user,
            name=f"Chat: {current_user.full_name} & {other_user.full_name}"
        )
        chat_room.participants.add(current_user, other_user)
        chat_room.save()
        
        logger.info(f"Created new 1:1 chat {chat_room.id}")
        
        return Response({
            'success': True,
            'message': 'New chat created',
            'chat': ChatRoomSerializer(chat_room, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in get_or_create_one_on_one")
    except PermissionDenied as e:
        return handle_exception(e, "Permission error in get_or_create_one_on_one")
    except Exception as e:
        return handle_exception(e, f"Failed to get/create 1:1 chat with user {user_id}")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_by_id(request, chat_id):
    """Get a specific chat room by ID with all its messages"""
    try:
        logger.info(f"User {request.user.id} accessing chat by ID: {chat_id}")
        user = request.user
        
        # Validate chat ID format
        if not chat_id or not str(chat_id).isdigit():
            raise ValidationError('Invalid chat ID format')
        
        # Get the chat room
        try:
            chat_room = ChatRoom.objects.get(id=chat_id, is_active=True)
        except ChatRoom.DoesNotExist:
            logger.warning(f"Chat room {chat_id} not found or inactive")
            return Response({
                'error': 'Chat room not found or has been deleted'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has access
        is_participant = chat_room.participants.filter(id=user.id).exists()
        is_admin_or_hr = user.role in ['admin', 'hr']
        
        if not is_participant and not is_admin_or_hr:
            logger.warning(f"User {user.id} denied access to chat {chat_id}")
            return Response({
                'error': 'Access denied. You must be a participant in this chat.',
                'user_role': user.role,
                'is_participant': False
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all chat details
        chat_serializer = ChatRoomSerializer(chat_room, context={'request': request})
        
        # Get messages with pagination
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))
        
        messages = chat_room.messages.filter(
            is_deleted=False
        ).order_by('created_at')[offset:offset + limit]
        
        total_messages = chat_room.messages.filter(is_deleted=False).count()
        message_serializer = MessageSerializer(messages, many=True, context={'request': request})
        
        # Update user's last read time
        if is_participant:
            ChatParticipant.objects.filter(
                chat_room=chat_room,
                user=user
            ).update(last_read_at=now())
            logger.debug(f"Updated last read for user {user.id} in chat {chat_id}")
        
        # If admin/hr viewing but not a participant, add them as participant
        if is_admin_or_hr and not is_participant:
            ChatParticipant.objects.get_or_create(
                chat_room=chat_room,
                user=user,
                defaults={'role': 'observer', 'joined_at': now()}
            )
            logger.info(f"Added admin/hr user {user.id} as observer to chat {chat_id}")
        
        logger.info(f"Successfully retrieved chat {chat_id} for user {user.id}")
        
        return Response({
            'success': True,
            'access_type': 'participant' if is_participant else 'admin/hr_privilege',
            'chat': chat_serializer.data,
            'messages': message_serializer.data,
            'total_messages': total_messages,
            'pagination': {
                'total': total_messages,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_messages
            },
            'unread_count': 0,  # All marked as read now
            'permissions': {
                'can_send_messages': True if (is_participant or is_admin_or_hr) else False,
                'can_manage_chat': chat_room.can_manage(user),
                'can_add_participants': chat_room.can_add_participants(user),
                'can_delete_messages': user.role in ['admin', 'hr']
            }
        })
        
    except ValidationError as e:
        return handle_exception(e, "Validation error in get_chat_by_id")
    except Exception as e:
        return handle_exception(e, f"Failed to retrieve chat {chat_id}")
    







@api_view(['POST'])
@permission_classes([IsAuthenticated])
def handle_webrtc_signal(request):
    """Handle WebRTC signaling"""
    try:
        user = request.user
        serializer = WebRTCSignalSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid signal data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        call_id = data['call_id']
        signal_type = data['signal_type']
        signal_data = data['data']
        target_user_id = data.get('target_user_id')
        
        # Get call
        call = get_object_or_404(VideoCall, call_id=call_id)
        
        # Check if user is participant
        is_participant = call.participants.filter(id=user.id).exists()
        if not is_participant:
            raise PermissionDenied('You are not a participant in this call')
        
        # Handle different signal types
        if signal_type == 'offer':
            call.offer = signal_data
            call.status = 'ringing'
            call.save()
            
            # Broadcast to target user or all participants
            channel_layer = get_channel_layer()
            if target_user_id:
                # Send to specific user
                async_to_sync(channel_layer.group_send)(
                    f"user_{target_user_id}",
                    {
                        'type': 'webrtc_signal',
                        'call_id': call_id,
                        'signal_type': 'offer',
                        'data': signal_data,
                        'from_user_id': user.id
                    }
                )
            else:
                # Send to all other participants
                for participant in call.participants.exclude(id=user.id):
                    async_to_sync(channel_layer.group_send)(
                        f"user_{participant.id}",
                        {
                            'type': 'webrtc_signal',
                            'call_id': call_id,
                            'signal_type': 'offer',
                            'data': signal_data,
                            'from_user_id': user.id
                        }
                    )
        
        elif signal_type == 'answer':
            call.answer = signal_data
            call.status = 'ongoing'
            call.started_at = now()
            call.save()
            
            # Send answer to caller
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{call.caller.id}",
                {
                    'type': 'webrtc_signal',
                    'call_id': call_id,
                    'signal_type': 'answer',
                    'data': signal_data,
                    'from_user_id': user.id
                }
            )
        
        elif signal_type == 'candidate':
            # Add ICE candidate
            if 'ice_candidates' not in call.ice_candidates:
                call.ice_candidates = []
            
            call.ice_candidates.append(signal_data)
            call.save()
            
            # Forward candidate
            channel_layer = get_channel_layer()
            if target_user_id:
                async_to_sync(channel_layer.group_send)(
                    f"user_{target_user_id}",
                    {
                        'type': 'webrtc_signal',
                        'call_id': call_id,
                        'signal_type': 'candidate',
                        'data': signal_data,
                        'from_user_id': user.id
                    }
                )
        
        elif signal_type == 'end':
            call.status = 'ended'
            call.ended_at = now()
            call.duration = (call.ended_at - call.started_at).seconds if call.started_at else 0
            call.save()
            
            # Notify all participants
            channel_layer = get_channel_layer()
            for participant in call.participants.all():
                async_to_sync(channel_layer.group_send)(
                    f"user_{participant.id}",
                    {
                        'type': 'webrtc_signal',
                        'call_id': call_id,
                        'signal_type': 'end',
                        'data': {'reason': signal_data.get('reason', 'Call ended')},
                        'from_user_id': user.id
                    }
                )
        
        return Response({
            'success': True,
            'message': f'Signal {signal_type} processed'
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to handle WebRTC signal")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_typing_status(request):
    """Update user's typing status"""
    try:
        user = request.user
        chat_room_id = request.data.get('chat_room_id')
        is_typing = request.data.get('is_typing', False)
        
        if not chat_room_id:
            return Response({
                'error': 'chat_room_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get chat room
        chat_room = get_object_or_404(ChatRoom, id=chat_room_id, is_active=True)
        
        # Check if user is participant
        if not chat_room.participants.filter(id=user.id).exists():
            raise PermissionDenied('You are not a participant in this chat')
        
        # Update or create typing indicator
        typing_indicator, created = TypingIndicator.objects.update_or_create(
            chat_room=chat_room,
            user=user,
            defaults={
                'is_typing': is_typing,
                'last_typing_at': now()
            }
        )
        
        # Broadcast typing status via WebSocket
        channel_layer = get_channel_layer()
        for participant in chat_room.participants.exclude(id=user.id):
            async_to_sync(channel_layer.group_send)(
                f"chat_{chat_room_id}",
                {
                    'type': 'typing_status',
                    'user_id': user.id,
                    'full_name': user.full_name,
                    'is_typing': is_typing,
                    'timestamp': now().isoformat()
                }
            )
        
        return Response({
            'success': True,
            'message': f'Typing status updated to {is_typing}'
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to update typing status")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_typing(request, room_id):
    """Get active typing indicators for a chat room"""
    try:
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        
        # Get active typing indicators (within last 3 seconds)
        from django.utils.timezone import now
        from datetime import timedelta
        
        active_typing = TypingIndicator.objects.filter(
            chat_room=chat_room,
            is_typing=True,
            last_typing_at__gte=now() - timedelta(seconds=3)
        ).select_related('user')
        
        serializer = TypingIndicatorSerializer(active_typing, many=True)
        
        return Response({
            'success': True,
            'typing_users': serializer.data
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to get typing indicators")
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_call_details(request, call_id):
    """Get details of a specific video call"""
    try:
        user = request.user
        
        # Get call
        video_call = get_object_or_404(VideoCall, call_id=call_id)
        
        # Check if user is participant or admin/hr
        is_participant = video_call.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            raise PermissionDenied('You are not a participant in this call')
        
        serializer = VideoCallSerializer(video_call, context={'request': request})
        
        return Response({
            'success': True,
            'call': serializer.data
        })
        
    except PermissionDenied as e:
        return Response({
            'error': 'Permission denied',
            'details': str(e)
        }, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        return Response({
            'error': 'Failed to get call details',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_file(request):
    """Handle file upload for chat messages"""
    try:
        user = request.user
        
        # Validate user is approved
        if user.status != 'approved':
            print("User not approved to send files")
            raise PermissionDenied('Your account must be approved to send files')
        
        # Get form data
        chat_room_id = request.POST.get('chat_room_id')
        file = request.FILES.get('file')
        message = request.POST.get('message', '')
        message_type = request.POST.get('message_type', 'file')
        
        if not chat_room_id:
            raise ValidationError('chat_room_id is required')
        
        if not file:
            raise ValidationError('No file provided')
        
        # Validate file size (max 50MB)
        if file.size > 50 * 1024 * 1024:  # 50MB
            raise ValidationError('File size exceeds 50MB limit')
        
        # Get chat room
        chat_room = get_object_or_404(ChatRoom, id=chat_room_id, is_active=True)
        
        # Check if user can send messages in this chat
        is_participant = chat_room.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            raise PermissionDenied('You cannot send files in this chat')
        
        # Create message with file
        message_obj = Message.objects.create(
            chat_room=chat_room,
            sender=user,
            message_type=message_type,
            content=message or f"Sent a file: {file.name}",
            attachment=file
        )
        
        # Update chat room timestamp
        chat_room.updated_at = now()
        chat_room.save()
        
        # Broadcast via WebSocket
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Your existing async_to_sync code here
                async_to_sync(channel_layer.group_send)(...)
            else:
                print("Warning: Channel layer not available. Skipping WebSocket notification.")
        except Exception as e:
            print(f"WebSocket notification error: {e}")
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_room_id}",
            {
                'type': 'chat_message',
                'message_id': message_obj.id,
                'sender_id': user.id,
                'sender_name': user.full_name,
                'message': message_obj.content,
                'message_type': message_type,
                'attachment': message_obj.attachment.url if message_obj.attachment else None,
                'timestamp': message_obj.created_at.isoformat()
            }
        )
        
        return Response({
            'success': True,
            'message': 'File uploaded successfully',
            'data': MessageSerializer(message_obj, context={'request': request}).data
        })
        
    except ValidationError as e:
        print("Validation error during file upload:", str(e))
        return Response({
            'error': 'Validation error',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    except PermissionDenied as e:
        print("Permission denied during file upload:", str(e))
        return Response({
            'error': 'Permission denied',
            'details': str(e)
        }, status=status.HTTP_403_FORBIDDEN)
    except Exception as e:
        print("Error during file upload:", str(e))
        return Response({
            'error': 'Failed to upload file',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




import uuid
from datetime import datetime

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_video_call(request):
    """Initiate a video/audio call"""
    print(f"User {request.user.id} initiating call with data: {request.data}")
    try:
        user = request.user
        serializer = VideoCallInitiateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        chat_room_id = data['chat_room_id']
        call_type = data['call_type']
        
        # Get chat room
        chat_room = get_object_or_404(ChatRoom, id=chat_room_id, is_active=True)
        
        # Check if user can initiate call
        is_participant = chat_room.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            raise PermissionDenied('You cannot initiate calls in this chat')
        
        # Generate unique call ID
        import uuid
        call_id = f"call_{uuid.uuid4().hex[:10]}_{chat_room_id}"
        
        # Create video call
        video_call = VideoCall.objects.create(
            chat_room=chat_room,
            call_id=call_id,
            caller=user,
            status='ringing'
        )
        
        # Add caller as participant
        CallParticipant.objects.create(
            call=video_call,
            user=user,
            joined_at=now(),
            is_active=True
        )
        
        # FIXED: Get all OTHER participants in the chat room (excluding caller)
        other_participants = chat_room.participants.exclude(id=user.id)
        
        print(f"📞 Call initiated by {user.full_name}")
        print(f"👥 Notifying {other_participants.count()} participant(s)")
        
        # Send notification to ALL other participants via WebSocket
        channel_layer = get_channel_layer()
        
        for participant in other_participants:
            print(f"  📤 Sending call notification to user {participant.id} ({participant.full_name})")
            
            # Create call participant record for each user
            CallParticipant.objects.get_or_create(
                call=video_call,
                user=participant,
                defaults={'is_active': False}  # Will become active when they join
            )
            
            # Send individual notification to each participant
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{participant.id}",
                    {
                        'type': 'video_call_incoming',
                        'call_id': call_id,
                        'caller': {
                            'id': user.id,
                            'full_name': user.full_name
                        },
                        'chat_room': {
                            'id': chat_room.id,
                            'name': chat_room.name
                        },
                        'call_type': call_type,
                        'timestamp': now().isoformat()
                    }
                )
                print(f"  ✅ Notification sent to {participant.full_name}")
            except Exception as e:
                print(f"  ❌ Failed to notify {participant.full_name}: {e}")
        
        # Also broadcast to the chat room group (for real-time updates)
        try:
            async_to_sync(channel_layer.group_send)(
                f"chat_{chat_room_id}",
                {
                    'type': 'video_call_offer',
                    'call_id': call_id,
                    'caller_id': user.id,
                    'caller_name': user.full_name,
                    'call_type': call_type,
                    'chat_room': {
                        'id': chat_room.id,
                        'name': chat_room.name
                    }
                }
            )
            print(f"  ✅ Broadcast to chat room {chat_room_id}")
        except Exception as e:
            print(f"  ❌ Failed to broadcast to chat room: {e}")
        
        print(f"✅ Call {call_id} initiated successfully")
        
        return Response({
            'success': True,
            'message': 'Call initiated',
            'call': VideoCallSerializer(video_call, context={'request': request}).data
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to initiate video call")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_conference_call(request):
    """Start a conference call with multiple participants"""
    try:
        user = request.user
        chat_room_id = request.data.get('chat_room_id')
        call_type = request.data.get('call_type', 'video')
        
        if not chat_room_id:
            return Response({
                'error': 'chat_room_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get chat room
        chat_room = get_object_or_404(ChatRoom, id=chat_room_id, is_active=True)
        
        # Check if user can start call
        is_participant = chat_room.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            raise PermissionDenied('You cannot start calls in this chat')
        
        # Generate unique call ID
        import uuid
        call_id = f"conf_{uuid.uuid4().hex[:10]}_{int(now().timestamp())}"
        
        # Create conference call
        video_call = VideoCall.objects.create(
            chat_room=chat_room,
            call_id=call_id,
            caller=user,
            status='conference'
        )
        
        # Add caller as first participant
        CallParticipant.objects.create(
            call=video_call,
            user=user,
            joined_at=now(),
            is_active=True
        )
        
        # FIXED: Add all other chat participants to the call
        other_participants = chat_room.participants.exclude(id=user.id)
        
        print(f"📞 Conference call initiated by {user.full_name}")
        print(f"👥 Notifying {other_participants.count()} participant(s)")
        
        for participant in other_participants:
            print(f"  📤 Adding {participant.full_name} to conference call")
            
            # Create call participant record
            CallParticipant.objects.create(
                call=video_call,
                user=participant,
                is_active=False  # Will become active when they join
            )
        
        # Notify all participants via WebSocket
        channel_layer = get_channel_layer()
        
        for participant in other_participants:
            print(f"  📤 Sending conference notification to {participant.full_name}")
            
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{participant.id}",
                    {
                        'type': 'conference_call_incoming',
                        'call_id': call_id,
                        'caller': {
                            'id': user.id,
                            'full_name': user.full_name
                        },
                        'chat_room': {
                            'id': chat_room.id,
                            'name': chat_room.name
                        },
                        'call_type': call_type,
                        'participants_count': chat_room.participants.count(),
                        'is_conference': True,
                        'timestamp': now().isoformat()
                    }
                )
                print(f"  ✅ Conference notification sent to {participant.full_name}")
            except Exception as e:
                print(f"  ❌ Failed to notify {participant.full_name}: {e}")
        
        print(f"✅ Conference call {call_id} started successfully")
        
        return Response({
            'success': True,
            'message': 'Conference call started',
            'call': {
                'id': video_call.id,
                'call_id': call_id,
                'call_type': call_type,
                'participants_count': chat_room.participants.count(),
                'is_conference': True,
                'chat_room': {
                    'id': chat_room.id,
                    'name': chat_room.name
                }
            }
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to start conference call")

        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_conference_call(request):
    """Join an existing conference call"""
    try:
        user = request.user
        call_id = request.data.get('call_id')
        
        if not call_id:
            return Response({
                'error': 'call_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get call
        video_call = get_object_or_404(VideoCall, call_id=call_id)
        
        # Check if user is allowed to join
        is_participant = video_call.participants.filter(id=user.id).exists()
        if not is_participant:
            raise PermissionDenied('You are not invited to this call')
        
        # Update participant status
        participant, created = CallParticipant.objects.update_or_create(
            call=video_call,
            user=user,
            defaults={
                'joined_at': now(),
                'is_active': True
            }
        )
        
        # Update call status if needed
        if video_call.status == 'ringing':
            video_call.status = 'ongoing'
            video_call.started_at = now()
            video_call.save()
        
        # Notify other participants via call WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"video_call_{call_id}",
            {
                'type': 'user_joined_call',
                'user_id': user.id,
                'full_name': user.full_name,
                'timestamp': now().isoformat(),
                'participant_count': video_call.call_participants.filter(is_active=True).count()
            }
        )
        
        # Get active participants
        active_participants = video_call.call_participants.filter(
            is_active=True
        ).select_related('user')
        
        participants_data = []
        for p in active_participants:
            participants_data.append({
                'id': p.user.id,
                'full_name': p.user.full_name,
                'role': p.user.role,
                'joined_at': p.joined_at.isoformat() if p.joined_at else None,
                'is_active': p.is_active
            })
        
        return Response({
            'success': True,
            'message': 'Joined conference call',
            'call': {
                'id': video_call.id,
                'call_id': call_id,
                'status': video_call.status,
                'started_at': video_call.started_at.isoformat() if video_call.started_at else None,
                'participants': participants_data,
                'total_participants': video_call.call_participants.count(),
                'active_participants': video_call.call_participants.filter(is_active=True).count()
            }
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to join conference call")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conference_participants(request, call_id):
    """Get all participants in a conference call"""
    try:
        user = request.user
        
        # Get call
        video_call = get_object_or_404(VideoCall, call_id=call_id)
        
        # Check if user is participant
        is_participant = video_call.participants.filter(id=user.id).exists()
        if not is_participant and user.role not in ['admin', 'hr']:
            raise PermissionDenied('You are not a participant in this call')
        
        # Get all participants
        participants = video_call.call_participants.select_related('user')
        
        participants_data = []
        for participant in participants:
            participants_data.append({
                'id': participant.user.id,
                'full_name': participant.user.full_name,
                'role': participant.user.role,
                'joined_at': participant.joined_at.isoformat() if participant.joined_at else None,
                'left_at': participant.left_at.isoformat() if participant.left_at else None,
                'is_active': participant.is_active,
                'duration': (participant.left_at - participant.joined_at).seconds if participant.joined_at and participant.left_at else None
            })
        
        return Response({
            'success': True,
            'call_id': call_id,
            'total_participants': participants.count(),
            'active_participants': participants.filter(is_active=True).count(),
            'participants': participants_data
        })
        
    except Exception as e:
        return handle_exception(e, "Failed to get conference participants")
    


# In your Django backend (views.py), add this endpoint:
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_messages_as_read(request, room_id):
    """Mark all messages as read for current user in chat room"""
    try:
        user = request.user
        chat_room = get_object_or_404(ChatRoom, id=room_id, is_active=True)
        
        # Check if user is participant
        if not chat_room.participants.filter(id=user.id).exists():
            raise PermissionDenied('You are not a participant in this chat')
        
        # Update last read time
        participant, created = ChatParticipant.objects.update_or_create(
            chat_room=chat_room,
            user=user,
            defaults={'last_read_at': now()}
        )
        
        return Response({
            'success': True,
            'message': 'Messages marked as read'
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to mark messages as read',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)