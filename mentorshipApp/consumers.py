import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from django.utils.timezone import now



class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['chat_room_id']
        self.room_group_name = f'chat_{self.room_name}'
        
        # Authenticate user
        try:
            token = self.scope['query_string'].decode().split('=')[1]
            user = await self.get_user(token)
            
            if not user or user.is_anonymous:
                await self.close()
                return
                
            self.scope['user'] = user
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close()

    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from userApp.models import CustomUser
            access_token = AccessToken(token)
            return CustomUser.objects.get(id=access_token['user_id'])
        except Exception as e:
            print(f"Token validation error: {e}")
            return None

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            # Handle different message types
            if data.get('type') == 'chat_message':
                message = data['message']
                
                # Send message to room group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message,
                        'sender_id': self.scope['user'].id
                    }
                )
            elif data.get('type') == 'video_call_offer':
                # Forward video call offer to the room group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'video_call_offer',
                        'chat_room_id': data.get('chat_room_id'),
                        'caller_id': data.get('caller_id')
                    }
                )
            elif data.get('type') == 'typing':
                # Handle typing notifications
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_status',
                        'user_id': self.scope['user'].id,
                        'is_typing': data.get('is_typing')
                    }
                )
            elif data.get('type') == 'join':
                # Handle user joining
                pass  # You might want to handle this case
            
        except json.JSONDecodeError:
            pass

    # Handler for chat messages
    async def chat_message(self, event):
        """Send message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender_id': event['sender_id']
        }))

    # Handler for video call offers
    async def video_call_offer(self, event):
        """Send video call offer to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'video_call_offer',
            'chat_room_id': event['chat_room_id'],
            'caller_id': event['caller_id'],
            'caller_name': event.get('caller_name', 'User'),
            'call_type': event.get('call_type', 'video'),
            'offer': {
                'type': event.get('offer', {}).get('type', 'offer'),
                'sdp': event.get('offer', {}).get('sdp', '')
            }
        }))

    # Handler for typing status
    async def typing_status(self, event):
        """Send typing status to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'typing_status',
            'user_id': event['user_id'],
            'is_typing': event['is_typing']
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notifications"""
    
    async def connect(self):
        # Import here to avoid import-time issues
        from django.contrib.auth.models import AnonymousUser
        
        # Check if user is authenticated
        if isinstance(self.scope.get('user'), type(AnonymousUser())) or not self.scope.get('user'):
            await self.close()
            return
        
        # Create user-specific group
        self.user_group_name = f'user_{self.scope["user"].id}'
        
        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_notification_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    # WebSocket message handlers
    async def notification_message(self, event):
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from notificationApp.models import ChatNotification
        try:
            notification = ChatNotification.objects.get(
                id=notification_id,
                recipient=self.scope['user']
            )
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        except ChatNotification.DoesNotExist:
            pass


class GroupChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for group chats"""
    
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['group_chat_id']
        self.room_group_name = f'group_chat_{self.room_id}'
        
        # Authenticate user
        try:
            token = self.scope['query_string'].decode().split('=')[1]
            user = await self.get_user(token)
            
            if not user or user.is_anonymous:
                await self.close()
                return
            
            # Check if user is participant
            is_participant = await self.check_participation(user.id, self.room_id)
            if not is_participant:
                await self.close()
                return
            
            self.scope['user'] = user
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Send online status
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status',
                    'user_id': user.id,
                    'status': 'online',
                    'username': user.full_name
                }
            )
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Send offline status
            if hasattr(self, 'scope') and 'user' in self.scope:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_status',
                        'user_id': self.scope['user'].id,
                        'status': 'offline',
                        'username': self.scope['user'].full_name
                    }
                )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing':
                await self.handle_typing_status(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            elif message_type == 'edit_message':
                await self.handle_edit_message(data)
            elif message_type == 'delete_message':
                await self.handle_delete_message(data)
            elif message_type == 'add_participant':
                await self.handle_add_participant(data)
            elif message_type == 'remove_participant':
                await self.handle_remove_participant(data)
            
        except json.JSONDecodeError:
            pass
    
    async def handle_chat_message(self, data):
        """Handle sending a chat message"""
        message = data.get('message', '')
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to_id')
        
        # Save message to database
        message_obj = await self.save_group_message(
            self.scope['user'].id,
            self.room_id,
            message,
            message_type,
            reply_to_id
        )
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_chat_message',
                'message_id': message_obj.id,
                'sender_id': self.scope['user'].id,
                'sender_name': self.scope['user'].full_name,
                'message': message,
                'message_type': message_type,
                'reply_to_id': reply_to_id,
                'timestamp': message_obj.created_at.isoformat()
            }
        )
    
    async def handle_typing_status(self, data):
        """Handle typing status updates"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_typing_status',
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name,
                'is_typing': is_typing
            }
        )
    
    async def handle_read_receipt(self, data):
        """Handle read receipts"""
        message_id = data.get('message_id')
        
        # Update read status in database
        await self.mark_message_as_read(
            message_id,
            self.scope['user'].id
        )
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_read_receipt',
                'message_id': message_id,
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name
            }
        )
    
    async def handle_edit_message(self, data):
        """Handle message editing"""
        message_id = data.get('message_id')
        new_content = data.get('new_content')
        
        # Update message in database
        updated = await self.update_group_message(
            message_id,
            self.scope['user'].id,
            new_content
        )
        
        if updated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_edited',
                    'message_id': message_id,
                    'new_content': new_content,
                    'edited_by': self.scope['user'].full_name,
                    'edited_at': now().isoformat()
                }
            )
    
    async def handle_delete_message(self, data):
        """Handle message deletion"""
        message_id = data.get('message_id')
        
        # Delete message in database
        deleted = await self.delete_group_message(
            message_id,
            self.scope['user'].id
        )
        
        if deleted:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_deleted',
                    'message_id': message_id,
                    'deleted_by': self.scope['user'].full_name
                }
            )
    
    async def handle_add_participant(self, data):
        """Handle adding participants"""
        user_id = data.get('user_id')
        role = data.get('role', 'member')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Add participant
        participant = await self.add_group_participant(
            self.room_id,
            user_id,
            self.scope['user'].id,
            role
        )
        
        if participant:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_added',
                    'user_id': user_id,
                    'added_by': self.scope['user'].full_name,
                    'role': role
                }
            )
    
    async def handle_remove_participant(self, data):
        """Handle removing participants"""
        user_id = data.get('user_id')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Remove participant
        removed = await self.remove_group_participant(
            self.room_id,
            user_id
        )
        
        if removed:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_removed',
                    'user_id': user_id,
                    'removed_by': self.scope['user'].full_name
                }
            )
    
    # WebSocket message handlers
    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_chat_message',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'message': event['message'],
            'message_type': event['message_type'],
            'reply_to_id': event.get('reply_to_id'),
            'timestamp': event['timestamp']
        }))
    
    async def group_typing_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_typing_status',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing']
        }))
    
    async def group_read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_read_receipt',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'username': event['username']
        }))
    
    async def group_message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_edited',
            'message_id': event['message_id'],
            'new_content': event['new_content'],
            'edited_by': event['edited_by'],
            'edited_at': event['edited_at']
        }))
    
    async def group_message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_deleted',
            'message_id': event['message_id'],
            'deleted_by': event['deleted_by']
        }))
    
    async def participant_added(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_added',
            'user_id': event['user_id'],
            'added_by': event['added_by'],
            'role': event['role']
        }))
    
    async def participant_removed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_removed',
            'user_id': event['user_id'],
            'removed_by': event['removed_by']
        }))
    
    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'user_id': event['user_id'],
            'status': event['status'],
            'username': event['username']
        }))
    
    # Database operations
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from userApp.models import CustomUser
            access_token = AccessToken(token)
            return CustomUser.objects.get(id=access_token['user_id'])
        except Exception as e:
            print(f"Token validation error: {e}")
            return None
    
    @database_sync_to_async
    def check_participation(self, user_id, chat_room_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            return GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).exists()
        except Exception as e:
            print(f"Error checking participation: {e}")
            return False
    
    @database_sync_to_async
    def save_group_message(self, user_id, chat_room_id, content, message_type, reply_to_id=None):
        try:
            from mentorshipApp.models import GroupChatMessage, GroupChatRoom, GroupChatParticipant
            
            # Update last read time
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            if participant:
                participant.last_read_at = now()
                participant.save(update_fields=['last_read_at'])
            
            # Create message
            message = GroupChatMessage.objects.create(
                chat_room_id=chat_room_id,
                sender_id=user_id,
                message_type=message_type,
                content=content,
                reply_to_id=reply_to_id
            )
            
            return message
        except Exception as e:
            print(f"Error saving group message: {e}")
            return None
    
    @database_sync_to_async
    def mark_message_as_read(self, message_id, user_id):
        try:
            from mentorshipApp.models import GroupMessageReadStatus
            GroupMessageReadStatus.objects.get_or_create(
                message_id=message_id,
                user_id=user_id,
                defaults={'read_at': now()}
            )
            return True
        except Exception as e:
            print(f"Error marking message as read: {e}")
            return False
    
    @database_sync_to_async
    def update_group_message(self, message_id, user_id, new_content):
        try:
            from mentorshipApp.models import GroupChatMessage
            message = GroupChatMessage.objects.get(
                id=message_id,
                sender_id=user_id,
                is_deleted=False
            )
            message.content = new_content
            message.is_edited = True
            message.edited_at = now()
            message.save()
            return True
        except Exception as e:
            print(f"Error updating message: {e}")
            return False
    
    @database_sync_to_async
    def delete_group_message(self, message_id, user_id):
        try:
            from mentorshipApp.models import GroupChatMessage
            from userApp.models import CustomUser
            
            message = GroupChatMessage.objects.get(id=message_id)
            user = CustomUser.objects.get(id=user_id)
            
            # Check if user can delete (sender or admin/moderator)
            if message.sender_id == user_id or user.role in ['admin', 'hr']:
                message.is_deleted = True
                message.deleted_at = now()
                message.save()
                return True
            return False
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False
    
    @database_sync_to_async
    def can_manage_participants(self, user_id, chat_room_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            from userApp.models import CustomUser
            
            user = CustomUser.objects.get(id=user_id)
            
            # Admin and HR can always manage
            if user.role in ['admin', 'hr']:
                return True
            
            # Check if user is admin or moderator in this chat
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            return participant and participant.can_manage_participants()
        except Exception as e:
            print(f"Error checking permissions: {e}")
            return False
    
    @database_sync_to_async
    def add_group_participant(self, chat_room_id, user_id, added_by_id, role):
        try:
            from mentorshipApp.models import GroupChatParticipant, GroupChatRoom
            chat_room = GroupChatRoom.objects.get(id=chat_room_id)
            participant, created = GroupChatParticipant.objects.get_or_create(
                chat_room=chat_room,
                user_id=user_id,
                defaults={
                    'added_by_id': added_by_id,
                    'role': role,
                    'joined_at': now()
                }
            )
            return participant
        except Exception as e:
            print(f"Error adding participant: {e}")
            return None
    
    @database_sync_to_async
    def remove_group_participant(self, chat_room_id, user_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            deleted, _ = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).delete()
            return deleted > 0
        except Exception as e:
            print(f"Error removing participant: {e}")
            return False

class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notifications"""
    
    async def connect(self):
        # Import here to avoid import-time issues
        from django.contrib.auth.models import AnonymousUser
        
        # Check if user is authenticated
        if isinstance(self.scope.get('user'), type(AnonymousUser())) or not self.scope.get('user'):
            await self.close()
            return
        
        # Create user-specific group
        self.user_group_name = f'user_{self.scope["user"].id}'
        
        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_notification_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    # WebSocket message handlers
    async def notification_message(self, event):
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from notificationApp.models import ChatNotification
        try:
            notification = ChatNotification.objects.get(
                id=notification_id,
                recipient=self.scope['user']
            )
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        except ChatNotification.DoesNotExist:
            pass


class GroupChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for group chats"""
    
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['group_chat_id']
        self.room_group_name = f'group_chat_{self.room_id}'
        
        # Authenticate user
        try:
            token = self.scope['query_string'].decode().split('=')[1]
            user = await self.get_user(token)
            
            if not user or user.is_anonymous:
                await self.close()
                return
            
            # Check if user is participant
            is_participant = await self.check_participation(user.id, self.room_id)
            if not is_participant:
                await self.close()
                return
            
            self.scope['user'] = user
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Send online status
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status',
                    'user_id': user.id,
                    'status': 'online',
                    'username': user.full_name
                }
            )
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Send offline status
            if hasattr(self, 'scope') and 'user' in self.scope:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_status',
                        'user_id': self.scope['user'].id,
                        'status': 'offline',
                        'username': self.scope['user'].full_name
                    }
                )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing':
                await self.handle_typing_status(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            elif message_type == 'edit_message':
                await self.handle_edit_message(data)
            elif message_type == 'delete_message':
                await self.handle_delete_message(data)
            elif message_type == 'add_participant':
                await self.handle_add_participant(data)
            elif message_type == 'remove_participant':
                await self.handle_remove_participant(data)
            
        except json.JSONDecodeError:
            pass
    
    async def handle_chat_message(self, data):
        """Handle sending a chat message"""
        message = data.get('message', '')
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to_id')
        
        # Save message to database
        message_obj = await self.save_group_message(
            self.scope['user'].id,
            self.room_id,
            message,
            message_type,
            reply_to_id
        )
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_chat_message',
                'message_id': message_obj.id,
                'sender_id': self.scope['user'].id,
                'sender_name': self.scope['user'].full_name,
                'message': message,
                'message_type': message_type,
                'reply_to_id': reply_to_id,
                'timestamp': message_obj.created_at.isoformat()
            }
        )
    
    async def handle_typing_status(self, data):
        """Handle typing status updates"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_typing_status',
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name,
                'is_typing': is_typing
            }
        )
    
    async def handle_read_receipt(self, data):
        """Handle read receipts"""
        message_id = data.get('message_id')
        
        # Update read status in database
        await self.mark_message_as_read(
            message_id,
            self.scope['user'].id
        )
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_read_receipt',
                'message_id': message_id,
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name
            }
        )
    
    async def handle_edit_message(self, data):
        """Handle message editing"""
        message_id = data.get('message_id')
        new_content = data.get('new_content')
        
        # Update message in database
        updated = await self.update_group_message(
            message_id,
            self.scope['user'].id,
            new_content
        )
        
        if updated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_edited',
                    'message_id': message_id,
                    'new_content': new_content,
                    'edited_by': self.scope['user'].full_name,
                    'edited_at': now().isoformat()
                }
            )
    
    async def handle_delete_message(self, data):
        """Handle message deletion"""
        message_id = data.get('message_id')
        
        # Delete message in database
        deleted = await self.delete_group_message(
            message_id,
            self.scope['user'].id
        )
        
        if deleted:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_deleted',
                    'message_id': message_id,
                    'deleted_by': self.scope['user'].full_name
                }
            )
    
    async def handle_add_participant(self, data):
        """Handle adding participants"""
        user_id = data.get('user_id')
        role = data.get('role', 'member')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Add participant
        participant = await self.add_group_participant(
            self.room_id,
            user_id,
            self.scope['user'].id,
            role
        )
        
        if participant:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_added',
                    'user_id': user_id,
                    'added_by': self.scope['user'].full_name,
                    'role': role
                }
            )
    
    async def handle_remove_participant(self, data):
        """Handle removing participants"""
        user_id = data.get('user_id')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Remove participant
        removed = await self.remove_group_participant(
            self.room_id,
            user_id
        )
        
        if removed:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_removed',
                    'user_id': user_id,
                    'removed_by': self.scope['user'].full_name
                }
            )
    
    # WebSocket message handlers
    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_chat_message',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'message': event['message'],
            'message_type': event['message_type'],
            'reply_to_id': event.get('reply_to_id'),
            'timestamp': event['timestamp']
        }))
    
    async def group_typing_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_typing_status',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing']
        }))
    
    async def group_read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_read_receipt',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'username': event['username']
        }))
    
    async def group_message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_edited',
            'message_id': event['message_id'],
            'new_content': event['new_content'],
            'edited_by': event['edited_by'],
            'edited_at': event['edited_at']
        }))
    
    async def group_message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_deleted',
            'message_id': event['message_id'],
            'deleted_by': event['deleted_by']
        }))
    
    async def participant_added(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_added',
            'user_id': event['user_id'],
            'added_by': event['added_by'],
            'role': event['role']
        }))
    
    async def participant_removed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_removed',
            'user_id': event['user_id'],
            'removed_by': event['removed_by']
        }))
    
    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'user_id': event['user_id'],
            'status': event['status'],
            'username': event['username']
        }))
    
    # Database operations
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from userApp.models import CustomUser
            access_token = AccessToken(token)
            return CustomUser.objects.get(id=access_token['user_id'])
        except Exception as e:
            print(f"Token validation error: {e}")
            return None
    
    @database_sync_to_async
    def check_participation(self, user_id, chat_room_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            return GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).exists()
        except Exception as e:
            print(f"Error checking participation: {e}")
            return False
    
    @database_sync_to_async
    def save_group_message(self, user_id, chat_room_id, content, message_type, reply_to_id=None):
        try:
            from mentorshipApp.models import GroupChatMessage, GroupChatRoom, GroupChatParticipant
            
            # Update last read time
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            if participant:
                participant.last_read_at = now()
                participant.save(update_fields=['last_read_at'])
            
            # Create message
            message = GroupChatMessage.objects.create(
                chat_room_id=chat_room_id,
                sender_id=user_id,
                message_type=message_type,
                content=content,
                reply_to_id=reply_to_id
            )
            
            return message
        except Exception as e:
            print(f"Error saving group message: {e}")
            return None
    
    @database_sync_to_async
    def mark_message_as_read(self, message_id, user_id):
        try:
            from mentorshipApp.models import GroupMessageReadStatus
            GroupMessageReadStatus.objects.get_or_create(
                message_id=message_id,
                user_id=user_id,
                defaults={'read_at': now()}
            )
            return True
        except Exception as e:
            print(f"Error marking message as read: {e}")
            return False
    
    @database_sync_to_async
    def update_group_message(self, message_id, user_id, new_content):
        try:
            from mentorshipApp.models import GroupChatMessage
            message = GroupChatMessage.objects.get(
                id=message_id,
                sender_id=user_id,
                is_deleted=False
            )
            message.content = new_content
            message.is_edited = True
            message.edited_at = now()
            message.save()
            return True
        except Exception as e:
            print(f"Error updating message: {e}")
            return False
    
    @database_sync_to_async
    def delete_group_message(self, message_id, user_id):
        try:
            from mentorshipApp.models import GroupChatMessage
            from userApp.models import CustomUser
            
            message = GroupChatMessage.objects.get(id=message_id)
            user = CustomUser.objects.get(id=user_id)
            
            # Check if user can delete (sender or admin/moderator)
            if message.sender_id == user_id or user.role in ['admin', 'hr']:
                message.is_deleted = True
                message.deleted_at = now()
                message.save()
                return True
            return False
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False
    
    @database_sync_to_async
    def can_manage_participants(self, user_id, chat_room_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            from userApp.models import CustomUser
            
            user = CustomUser.objects.get(id=user_id)
            
            # Admin and HR can always manage
            if user.role in ['admin', 'hr']:
                return True
            
            # Check if user is admin or moderator in this chat
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            return participant and participant.can_manage_participants()
        except Exception as e:
            print(f"Error checking permissions: {e}")
            return False
    
    @database_sync_to_async
    def add_group_participant(self, chat_room_id, user_id, added_by_id, role):
        try:
            from mentorshipApp.models import GroupChatParticipant, GroupChatRoom
            chat_room = GroupChatRoom.objects.get(id=chat_room_id)
            participant, created = GroupChatParticipant.objects.get_or_create(
                chat_room=chat_room,
                user_id=user_id,
                defaults={
                    'added_by_id': added_by_id,
                    'role': role,
                    'joined_at': now()
                }
            )
            return participant
        except Exception as e:
            print(f"Error adding participant: {e}")
            return None
    
    @database_sync_to_async
    def remove_group_participant(self, chat_room_id, user_id):
        try:
            from mentorshipApp.models import GroupChatParticipant
            deleted, _ = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).delete()
            return deleted > 0
        except Exception as e:
            print(f"Error removing participant: {e}")
            return False
class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notifications"""
    
    async def connect(self):
        # Check if user is authenticated
        if self.scope['user'] == AnonymousUser():
            await self.close()
            return
        
        # Create user-specific group
        self.user_group_name = f'user_{self.scope["user"].id}'
        
        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_notification_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    # WebSocket message handlers
    async def notification_message(self, event):
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from notificationApp.models import ChatNotification
        try:
            notification = ChatNotification.objects.get(
                id=notification_id,
                recipient=self.scope['user']
            )
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        except ChatNotification.DoesNotExist:
            pass


class GroupChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for group chats"""
    
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['group_chat_id']
        self.room_group_name = f'group_chat_{self.room_id}'
        
        # Authenticate user
        try:
            token = self.scope['query_string'].decode().split('=')[1]
            user = await self.get_user(token)
            
            if not user or user.is_anonymous:
                await self.close()
                return
            
            # Check if user is participant
            is_participant = await self.check_participation(user.id, self.room_id)
            if not is_participant:
                await self.close()
                return
            
            self.scope['user'] = user
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Send online status
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status',
                    'user_id': user.id,
                    'status': 'online',
                    'username': user.full_name
                }
            )
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Send offline status
            if hasattr(self.scope, 'user'):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_status',
                        'user_id': self.scope['user'].id,
                        'status': 'offline',
                        'username': self.scope['user'].full_name
                    }
                )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing':
                await self.handle_typing_status(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            elif message_type == 'edit_message':
                await self.handle_edit_message(data)
            elif message_type == 'delete_message':
                await self.handle_delete_message(data)
            elif message_type == 'add_participant':
                await self.handle_add_participant(data)
            elif message_type == 'remove_participant':
                await self.handle_remove_participant(data)
            
        except json.JSONDecodeError:
            pass
    
    async def handle_chat_message(self, data):
        """Handle sending a chat message"""
        message = data.get('message', '')
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to_id')
        
        # Save message to database
        message_obj = await self.save_group_message(
            self.scope['user'].id,
            self.room_id,
            message,
            message_type,
            reply_to_id
        )
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_chat_message',
                'message_id': message_obj.id,
                'sender_id': self.scope['user'].id,
                'sender_name': self.scope['user'].full_name,
                'message': message,
                'message_type': message_type,
                'reply_to_id': reply_to_id,
                'timestamp': message_obj.created_at.isoformat()
            }
        )
    
    async def handle_typing_status(self, data):
        """Handle typing status updates"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_typing_status',
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name,
                'is_typing': is_typing
            }
        )
    
    async def handle_read_receipt(self, data):
        """Handle read receipts"""
        message_id = data.get('message_id')
        
        # Update read status in database
        await self.mark_message_as_read(
            message_id,
            self.scope['user'].id
        )
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_read_receipt',
                'message_id': message_id,
                'user_id': self.scope['user'].id,
                'username': self.scope['user'].full_name
            }
        )
    
    async def handle_edit_message(self, data):
        """Handle message editing"""
        message_id = data.get('message_id')
        new_content = data.get('new_content')
        
        # Update message in database
        updated = await self.update_group_message(
            message_id,
            self.scope['user'].id,
            new_content
        )
        
        if updated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_edited',
                    'message_id': message_id,
                    'new_content': new_content,
                    'edited_by': self.scope['user'].full_name,
                    'edited_at': now().isoformat()
                }
            )
    
    async def handle_delete_message(self, data):
        """Handle message deletion"""
        message_id = data.get('message_id')
        
        # Delete message in database
        deleted = await self.delete_group_message(
            message_id,
            self.scope['user'].id
        )
        
        if deleted:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_message_deleted',
                    'message_id': message_id,
                    'deleted_by': self.scope['user'].full_name
                }
            )
    
    async def handle_add_participant(self, data):
        """Handle adding participants"""
        user_id = data.get('user_id')
        role = data.get('role', 'member')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Add participant
        participant = await self.add_group_participant(
            self.room_id,
            user_id,
            self.scope['user'].id,
            role
        )
        
        if participant:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_added',
                    'user_id': user_id,
                    'added_by': self.scope['user'].full_name,
                    'role': role
                }
            )
    
    async def handle_remove_participant(self, data):
        """Handle removing participants"""
        user_id = data.get('user_id')
        
        # Check if requester has permission
        can_manage = await self.can_manage_participants(
            self.scope['user'].id,
            self.room_id
        )
        
        if not can_manage:
            return
        
        # Remove participant
        removed = await self.remove_group_participant(
            self.room_id,
            user_id
        )
        
        if removed:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'participant_removed',
                    'user_id': user_id,
                    'removed_by': self.scope['user'].full_name
                }
            )
    
    # WebSocket message handlers
    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_chat_message',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'message': event['message'],
            'message_type': event['message_type'],
            'reply_to_id': event.get('reply_to_id'),
            'timestamp': event['timestamp']
        }))
    
    async def group_typing_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_typing_status',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing']
        }))
    
    async def group_read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_read_receipt',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'username': event['username']
        }))
    
    async def group_message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_edited',
            'message_id': event['message_id'],
            'new_content': event['new_content'],
            'edited_by': event['edited_by'],
            'edited_at': event['edited_at']
        }))
    
    async def group_message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'group_message_deleted',
            'message_id': event['message_id'],
            'deleted_by': event['deleted_by']
        }))
    
    async def participant_added(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_added',
            'user_id': event['user_id'],
            'added_by': event['added_by'],
            'role': event['role']
        }))
    
    async def participant_removed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'participant_removed',
            'user_id': event['user_id'],
            'removed_by': event['removed_by']
        }))
    
    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'user_id': event['user_id'],
            'status': event['status'],
            'username': event['username']
        }))
    
    # Database operations
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            from userApp.models import CustomUser
            return CustomUser.objects.get(id=access_token['user_id'])
        except Exception as e:
            print(f"Token validation error: {e}")
            return None
    

    
    @database_sync_to_async
    def save_group_message(self, user_id, chat_room_id, content, message_type, reply_to_id=None):
        try:
            from .models import GroupChatMessage, GroupChatRoom, GroupChatParticipant
            
            # Update last read time
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            if participant:
                participant.last_read_at = now()
                participant.save(update_fields=['last_read_at'])
            
            # Create message
            message = GroupChatMessage.objects.create(
                chat_room_id=chat_room_id,
                sender_id=user_id,
                message_type=message_type,
                content=content,
                reply_to_id=reply_to_id
            )
            
            return message
        except Exception as e:
            print(f"Error saving group message: {e}")
            return None
    
    @database_sync_to_async
    def mark_message_as_read(self, message_id, user_id):
        try:
            from .models import GroupMessageReadStatus
            GroupMessageReadStatus.objects.get_or_create(
                message_id=message_id,
                user_id=user_id,
                defaults={'read_at': now()}
            )
            return True
        except Exception as e:
            print(f"Error marking message as read: {e}")
            return False
    
    @database_sync_to_async
    def update_group_message(self, message_id, user_id, new_content):
        try:
            from .models import GroupChatMessage
            message = GroupChatMessage.objects.get(
                id=message_id,
                sender_id=user_id,
                is_deleted=False
            )
            message.content = new_content
            message.is_edited = True
            message.edited_at = now()
            message.save()
            return True
        except Exception as e:
            print(f"Error updating message: {e}")
            return False
    
    @database_sync_to_async
    def delete_group_message(self, message_id, user_id):
        try:
            from .models import GroupChatMessage
            message = GroupChatMessage.objects.get(id=message_id)
            
            # Check if user can delete (sender or admin/moderator)
            from userApp.models import CustomUser
            user = CustomUser.objects.get(id=user_id)
            
            if message.sender_id == user_id or user.role in ['admin', 'hr']:
                message.is_deleted = True
                message.deleted_at = now()
                message.save()
                return True
            return False
        except Exception as e:
            print(f"Error deleting message: {e}")
            return False
    
    @database_sync_to_async
    def can_manage_participants(self, user_id, chat_room_id):
        try:
            from .models import GroupChatParticipant
            from userApp.models import CustomUser
            
            user = CustomUser.objects.get(id=user_id)
            
            # Admin and HR can always manage
            if user.role in ['admin', 'hr']:
                return True
            
            # Check if user is admin or moderator in this chat
            participant = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).first()
            
            return participant and participant.can_manage_participants()
        except Exception as e:
            print(f"Error checking permissions: {e}")
            return False
    
    @database_sync_to_async
    def add_group_participant(self, chat_room_id, user_id, added_by_id, role):
        try:
            from .models import GroupChatParticipant, GroupChatRoom
            chat_room = GroupChatRoom.objects.get(id=chat_room_id)
            participant, created = GroupChatParticipant.objects.get_or_create(
                chat_room=chat_room,
                user_id=user_id,
                defaults={
                    'added_by_id': added_by_id,
                    'role': role,
                    'joined_at': now()
                }
            )
            return participant
        except Exception as e:
            print(f"Error adding participant: {e}")
            return None
    
    @database_sync_to_async
    def remove_group_participant(self, chat_room_id, user_id):
        try:
            from .models import GroupChatParticipant
            deleted, _ = GroupChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).delete()
            return deleted > 0
        except Exception as e:
            print(f"Error removing participant: {e}")
            return False