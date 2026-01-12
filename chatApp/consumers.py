import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser

from .models import ChatParticipant, ChatRoom, Message
from userApp.models import CustomUser


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("="*50)
        print("ChatConsumer.connect() called")
        print(f"URL route kwargs: {self.scope['url_route']['kwargs']}")
        print(f"Query string: {self.scope['query_string']}")
        print("="*50)
        
        # Get chat room ID from URL - FIXED: Use room_id consistently
        try:
            kwargs = self.scope['url_route']['kwargs']
            self.room_id = kwargs.get('room_id')
            
            if not self.room_id:
                print(f"ERROR: No room ID found. Available kwargs: {list(kwargs.keys())}")
                await self.close()
                return
            
            print(f"✅ Successfully got room_id: {self.room_id}")
            
        except Exception as e:
            print(f"❌ Error getting room ID: {e}")
            import traceback
            traceback.print_exc()
            await self.close()
            return
            
        self.room_group_name = f'chat_{self.room_id}'
        
        # Authenticate user
        try:
            query_string = self.scope['query_string'].decode()
            
            if not query_string:
                print("❌ No query string provided")
                await self.close()
                return
            
            # Parse query parameters safely
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            token = params.get('token')
            
            if not token:
                print("❌ No token provided in query string")
                await self.close()
                return
                
            user = await self.get_user(token)
            
            if not user:
                print("❌ Invalid token or user not found")
                await self.close()
                return
                
            self.scope['user'] = user
            self.user_id = user.id
            
            print(f"✅ User authenticated: {user.id} ({user.full_name})")
            
            # Check if user is participant
            is_participant = await self.check_participation(user.id, self.room_id)
            if not is_participant and user.role not in ['admin', 'hr']:
                print(f"❌ User {user.id} is not a participant in room {self.room_id}")
                await self.close()
                return
            
            print(f"✅ User is participant or admin/hr")
            
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # FIXED: Get timestamp properly using database_sync_to_async
            timestamp = await database_sync_to_async(timezone.now)()
            
            # Notify others that user joined
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_joined',
                    'user_id': user.id,
                    'full_name': user.full_name,
                    'timestamp': timestamp.isoformat()
                }
            )
            
            print(f"✅ User {user.id} ({user.full_name}) connected to chat room {self.room_id}")
            print("="*50)
            
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            import traceback
            traceback.print_exc()
            await self.close()

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Notify others that user left
            if hasattr(self, 'user_id') and hasattr(self.scope, 'user'):
                timestamp = await database_sync_to_async(timezone.now)()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_left',
                        'user_id': self.user_id,
                        'timestamp': timestamp.isoformat()
                    }
                )
                print(f"User {self.user_id} disconnected from chat room {self.room_id}")

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
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")

    async def handle_chat_message(self, data):
        """Handle sending a chat message"""
        message_content = data.get('message', '')
        message_type = data.get('message_type', 'text')
        attachment = data.get('attachment')
        reply_to_id = data.get('reply_to_id')
        
        # Save message to database
        message_obj = await self.save_message(
            self.user_id,
            self.room_id,
            message_content,
            message_type,
            attachment,
            reply_to_id
        )
        
        if message_obj:
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': message_obj.id,
                    'sender_id': self.user_id,
                    'sender_name': self.scope['user'].full_name,
                    'message': message_content,
                    'message_type': message_type,
                    'attachment': attachment,
                    'timestamp': message_obj.created_at.isoformat()
                }
            )

    async def handle_typing_status(self, data):
        """Handle typing status updates"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status',
                'user_id': self.user_id,
                'full_name': self.scope['user'].full_name,
                'is_typing': is_typing
            }
        )

    async def handle_read_receipt(self, data):
        """Handle read receipts"""
        message_id = data.get('message_id')
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'read_receipt',
                'message_id': message_id,
                'user_id': self.user_id,
                'full_name': self.scope['user'].full_name
            }
        )

    # WebSocket message handlers
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'message': event['message'],
            'message_type': event['message_type'],
            'attachment': event.get('attachment'),
            'timestamp': event['timestamp']
        }))

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing_status',
            'user_id': event['user_id'],
            'full_name': event['full_name'],
            'is_typing': event['is_typing']
        }))

    # FIXED: Handle video call offer notifications properly
    async def video_call_offer(self, event):
        """Forward video call notification to chat participants"""
        print(f"📞 Forwarding video call notification in chat room {self.room_id}")
        
        await self.send(text_data=json.dumps({
            'type': 'video_call_offer',
            'call_id': event['call_id'],
            'caller_id': event['caller_id'],
            'caller_name': event['caller_name'],
            'call_type': event['call_type'],
            'chat_room': event.get('chat_room', {})
        }))

    async def read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'read_receipt',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'full_name': event['full_name']
        }))

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'full_name': event['full_name'],
            'timestamp': event['timestamp']
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user_id': event['user_id'],
            'timestamp': event['timestamp']
        }))

    # Database operations
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            return CustomUser.objects.get(id=access_token['user_id'])
        except Exception as e:
            print(f"Token validation error: {e}")
            return None

    @database_sync_to_async
    def check_participation(self, user_id, chat_room_id):
        try:
            return ChatParticipant.objects.filter(
                chat_room_id=chat_room_id,
                user_id=user_id
            ).exists()
        except Exception as e:
            print(f"Error checking participation: {e}")
            return False

    @database_sync_to_async
    def save_message(self, user_id, chat_room_id, content, message_type, attachment=None, reply_to_id=None):
        try:
            message = Message.objects.create(
                chat_room_id=chat_room_id,
                sender_id=user_id,
                message_type=message_type,
                content=content,
                reply_to_id=reply_to_id
            )
            
            if attachment:
                message.attachment = attachment
                message.save()
            
            return message
        except Exception as e:
            print(f"Error saving message: {e}")
            return None

class VideoCallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.call_id = self.scope['url_route']['kwargs']['call_id']
        self.call_group_name = f'video_call_{self.call_id}'
        
        # Authenticate user
        try:
            query_string = self.scope['query_string'].decode()
            
            if not query_string:
                print("No query string provided for video call")
                await self.close()
                return
            
            # Parse query parameters safely
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            token = params.get('token')
            
            if not token:
                print("No token provided for video call")
                await self.close()
                return
                
            user = await self.get_user(token)
            
            if not user:
                print("Invalid token for video call")
                await self.close()
                return
                
            self.scope['user'] = user
            self.user_id = user.id
            
            await self.accept()
            
            # Join call group
            await self.channel_layer.group_add(
                self.call_group_name,
                self.channel_name
            )
            
            # FIXED: Get timestamp properly
            timestamp = await database_sync_to_async(timezone.now)()
            
            # Notify others that user joined
            await self.channel_layer.group_send(
                self.call_group_name,
                {
                    'type': 'user_joined_call',
                    'user_id': user.id,
                    'full_name': user.full_name,
                    'timestamp': timestamp.isoformat()
                }
            )
            
            print(f"User {user.id} joined video call {self.call_id}")
            
        except Exception as e:
            print(f"VideoCall WebSocket connection error: {e}")
            import traceback
            traceback.print_exc()
            await self.close()

    async def disconnect(self, close_code):
        # Leave call group
        if hasattr(self, 'call_group_name'):
            await self.channel_layer.group_discard(
                self.call_group_name,
                self.channel_name
            )
            
            # Notify others that user left
            if hasattr(self, 'user_id') and hasattr(self.scope, 'user'):
                timestamp = await database_sync_to_async(timezone.now)()
                await self.channel_layer.group_send(
                    self.call_group_name,
                    {
                        'type': 'user_left_call',
                        'user_id': self.user_id,
                        'full_name': self.scope['user'].full_name,
                        'timestamp': timestamp.isoformat()
                    }
                )
            
            print(f"User {self.user_id} left video call {self.call_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            print(f"Received message type: {message_type} from user {self.user_id}")
            
            if message_type == 'webrtc_offer':
                await self.handle_webrtc_offer(data)
            elif message_type == 'webrtc_answer':
                await self.handle_webrtc_answer(data)
            elif message_type == 'ice_candidate':
                await self.handle_ice_candidate(data)
            elif message_type == 'media_state':
                await self.handle_media_state(data)
            elif message_type == 'screen_share':
                await self.handle_screen_share(data)
            elif message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'call_reject':
                await self.handle_call_reject(data)
            elif message_type == 'call_end':
                await self.handle_call_end(data)
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")

    async def handle_webrtc_offer(self, data):
        target_user_id = data.get('target_user_id')
        offer = data.get('offer')
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'webrtc_offer_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'target_user_id': target_user_id,
                'offer': offer
            }
        )

    async def handle_webrtc_answer(self, data):
        target_user_id = data.get('target_user_id')
        answer = data.get('answer')
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'webrtc_answer_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'target_user_id': target_user_id,
                'answer': answer
            }
        )

    async def handle_ice_candidate(self, data):
        target_user_id = data.get('target_user_id')
        candidate = data.get('candidate')
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'ice_candidate_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'target_user_id': target_user_id,
                'candidate': candidate
            }
        )

    async def handle_media_state(self, data):
        media_type = data.get('media_type')
        enabled = data.get('enabled', False)
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'media_state_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'media_type': media_type,
                'enabled': enabled
            }
        )

    async def handle_screen_share(self, data):
        is_sharing = data.get('is_sharing', False)
        stream_id = data.get('stream_id')
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'screen_share_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'is_sharing': is_sharing,
                'stream_id': stream_id
            }
        )

    async def handle_chat_message(self, data):
        message = data.get('message', '')
        timestamp = await database_sync_to_async(timezone.now)()
        
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'call_chat_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'message': message,
                'timestamp': timestamp.isoformat()
            }
        )

    async def handle_call_reject(self, data):
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'call_reject_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name
            }
        )

    async def handle_call_end(self, data):
        await self.channel_layer.group_send(
            self.call_group_name,
            {
                'type': 'call_end_message',
                'sender_id': self.user_id,
                'sender_name': self.scope['user'].full_name,
                'reason': data.get('reason', 'Call ended')
            }
        )

    # WebSocket message handlers
    async def webrtc_offer_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'webrtc_offer',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'target_user_id': event.get('target_user_id'),
            'offer': event['offer']
        }))

    async def webrtc_answer_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'webrtc_answer',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'target_user_id': event.get('target_user_id'),
            'answer': event['answer']
        }))

    async def ice_candidate_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ice_candidate',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'target_user_id': event.get('target_user_id'),
            'candidate': event['candidate']
        }))

    async def media_state_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'media_state',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'media_type': event['media_type'],
            'enabled': event['enabled']
        }))

    async def screen_share_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'screen_share',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'is_sharing': event['is_sharing'],
            'stream_id': event.get('stream_id')
        }))

    async def call_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_chat_message',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))

    async def call_reject_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_reject',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name']
        }))

    async def call_end_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_end',
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'reason': event.get('reason', 'Call ended')
        }))

    async def user_joined_call(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined_call',
            'user_id': event['user_id'],
            'full_name': event['full_name'],
            'timestamp': event['timestamp']
        }))

    async def user_left_call(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left_call',
            'user_id': event['user_id'],
            'full_name': event['full_name'],
            'timestamp': event.get('timestamp')
        }))

    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            user = CustomUser.objects.get(id=access_token['user_id'])
            return user
        except Exception as e:
            print(f"Token validation error: {e}")
            return None
        




class UserNotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for user-specific notifications (like incoming calls)"""
    
    async def connect(self):
        print("="*50)
        print("UserNotificationConsumer.connect() called")
        print("="*50)
        
        # Authenticate user
        try:
            query_string = self.scope['query_string'].decode()
            
            if not query_string:
                print("❌ No query string provided")
                await self.close()
                return
            
            # Parse query parameters
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            token = params.get('token')
            
            if not token:
                print("❌ No token provided")
                await self.close()
                return
                
            user = await self.get_user(token)
            
            if not user:
                print("❌ Invalid token or user not found")
                await self.close()
                return
                
            self.scope['user'] = user
            self.user_id = user.id
            self.user_group_name = f"user_{user.id}"
            
            print(f"✅ User authenticated: {user.id} ({user.full_name})")
            
            await self.accept()
            
            # Join user-specific group for notifications
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            print(f"✅ User {user.id} connected to notification channel: {self.user_group_name}")
            
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            import traceback
            traceback.print_exc()
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
            print(f"User {self.user_id} disconnected from notification channel")
    
    async def receive(self, text_data):
        """Handle incoming messages (not really used for notifications)"""
        pass
    
    # Handler for incoming video call notifications
    async def video_call_incoming(self, event):
        """Forward incoming call notification to user"""
        print(f"📞 Forwarding incoming call to user {self.user_id}")
        print(f"Call data: {event}")
        
        await self.send(text_data=json.dumps({
            'type': 'video_call_incoming',
            'call_id': event['call_id'],
            'caller': event['caller'],
            'chat_room': event['chat_room'],
            'call_type': event['call_type'],
            'timestamp': event['timestamp']
        }))
        
        print(f"✅ Incoming call notification sent to user {self.user_id}")
    
    # Handler for incoming conference call notifications
    async def conference_call_incoming(self, event):
        """Forward incoming conference call notification to user"""
        print(f"📞 Forwarding incoming conference call to user {self.user_id}")
        
        await self.send(text_data=json.dumps({
            'type': 'conference_call_incoming',
            'call_id': event['call_id'],
            'caller': event['caller'],
            'chat_room': event['chat_room'],
            'call_type': event['call_type'],
            'participants_count': event['participants_count'],
            'is_conference': event.get('is_conference', True),
            'timestamp': event['timestamp']
        }))
        
        print(f"✅ Conference call notification sent to user {self.user_id}")
    
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            user = CustomUser.objects.get(id=access_token['user_id'])
            return user
        except Exception as e:
            print(f"Token validation error: {e}")
            return None



class UserNotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for user-specific notifications (like incoming calls)"""
    
    async def connect(self):
        print("="*50)
        print("UserNotificationConsumer.connect() called")
        print("="*50)
        
        # Authenticate user
        try:
            query_string = self.scope['query_string'].decode()
            
            if not query_string:
                print("❌ No query string provided")
                await self.close()
                return
            
            # Parse query parameters
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            token = params.get('token')
            
            if not token:
                print("❌ No token provided")
                await self.close()
                return
                
            user = await self.get_user(token)
            
            if not user:
                print("❌ Invalid token or user not found")
                await self.close()
                return
                
            self.scope['user'] = user
            self.user_id = user.id
            self.user_group_name = f"user_{user.id}"
            
            print(f"✅ User authenticated: {user.id} ({user.full_name})")
            
            await self.accept()
            
            # Join user-specific group for notifications
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            print(f"✅ User {user.id} connected to notification channel: {self.user_group_name}")
            
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            import traceback
            traceback.print_exc()
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave user group
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
            print(f"User {self.user_id} disconnected from notification channel")
    
    async def receive(self, text_data):
        """Handle incoming messages (not really used for notifications)"""
        pass
    
    # Handler for incoming video call notifications
    async def video_call_incoming(self, event):
        """Forward incoming call notification to user"""
        print(f"📞 Forwarding incoming call to user {self.user_id}")
        print(f"Call data: {event}")
        
        await self.send(text_data=json.dumps({
            'type': 'video_call_incoming',
            'call_id': event['call_id'],
            'caller': event['caller'],
            'chat_room': event['chat_room'],
            'call_type': event['call_type'],
            'timestamp': event['timestamp']
        }))
        
        print(f"✅ Incoming call notification sent to user {self.user_id}")
    
    # Handler for incoming conference call notifications
    async def conference_call_incoming(self, event):
        """Forward incoming conference call notification to user"""
        print(f"📞 Forwarding incoming conference call to user {self.user_id}")
        
        await self.send(text_data=json.dumps({
            'type': 'conference_call_incoming',
            'call_id': event['call_id'],
            'caller': event['caller'],
            'chat_room': event['chat_room'],
            'call_type': event['call_type'],
            'participants_count': event['participants_count'],
            'is_conference': event.get('is_conference', True),
            'timestamp': event['timestamp']
        }))
        
        print(f"✅ Conference call notification sent to user {self.user_id}")
    
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            user = CustomUser.objects.get(id=access_token['user_id'])
            return user
        except Exception as e:
            print(f"Token validation error: {e}")
            return None