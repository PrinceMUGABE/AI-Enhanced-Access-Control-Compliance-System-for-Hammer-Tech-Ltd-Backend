# assistanceApp/consumers.py
import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

from .models import AssistanceChat, AssistanceMessage
from .services import AssistanceManager, FreeAIService  # Changed from AIService to FreeAIService
from userApp.models import CustomUser


class AssistanceConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time AI assistance"""
    
    async def connect(self):
        print("="*50)
        print("AssistanceConsumer.connect() called")
        print("="*50)
        
        # Get session ID from URL
        self.session_id = self.scope['url_route']['kwargs'].get('session_id')
        
        if not self.session_id:
            await self.close()
            return
        
        self.room_group_name = f'assistance_{self.session_id}'
        
        # Authenticate user if token provided
        try:
            query_string = self.scope['query_string'].decode()
            
            if query_string:
                params = {}
                for param in query_string.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
                
                token = params.get('token')
                
                if token:
                    user = await self.get_user(token)
                    if user:
                        self.scope['user'] = user
                        self.user_id = user.id
                        print(f"✅ User authenticated: {user.id} ({user.full_name})")
                else:
                    # Anonymous user
                    self.scope['user'] = None
                    self.user_id = None
            else:
                self.scope['user'] = None
                self.user_id = None
            
            await self.accept()
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            print(f"✅ Connected to assistance session: {self.session_id}")
            
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
            print(f"Disconnected from assistance session: {self.session_id}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'question':
                await self.handle_question(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'feedback':
                await self.handle_feedback(data)
            elif message_type == 'human_join':
                await self.handle_human_join(data)
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
    
    async def handle_question(self, data):
        """Handle user question"""
        question = data.get('question', '').strip()
        email = data.get('email')
        
        if not question:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Question cannot be empty'
            }))
            return
        
        # Get or create chat session
        chat_session = await self.get_chat_session()
        
        if not chat_session:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid session'
            }))
            return
        
        # Update email if provided
        if email and not chat_session.email:
            await self.update_chat_email(chat_session, email)
        
        # Send typing indicator
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'ai_typing',
                'is_typing': True
            }
        )
        
        # Save user question
        user_message = await self.save_user_message(chat_session, question)
        
        # Broadcast user message
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_message',
                'message_id': user_message.id,
                'content': question,
                'timestamp': user_message.created_at.isoformat()
            }
        )
        
        # Process with AI (async)
        await self.process_ai_response(chat_session, question)
    
    async def process_ai_response(self, chat_session, question):
        """Process question with AI and send response"""
        try:
            # Get chat context
            chat_context = await self.get_chat_context(chat_session)
            
            # Generate AI response using FreeAIService
            ai_service = FreeAIService()  # Changed from AIService to FreeAIService
            
            # Convert to sync call using database_sync_to_async
            ai_result = await database_sync_to_async(ai_service.generate_response)(
                question, chat_context
            )
            
            # Stop typing indicator
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'ai_typing',
                    'is_typing': False
                }
            )
            
            # Save AI response
            ai_message = await self.save_ai_message(chat_session, ai_result)
            
            # Broadcast AI response
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'ai_response',
                    'message_id': ai_message.id,
                    'content': ai_result['response'],
                    'confidence': ai_result['confidence'],
                    'requires_email': ai_result.get('requires_email', False),
                    'timestamp': ai_message.created_at.isoformat()
                }
            )
            
        except Exception as e:
            print(f"AI processing error: {e}")
            import traceback
            traceback.print_exc()
            
            # Stop typing indicator
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'ai_typing',
                    'is_typing': False
                }
            )
            
            # Send error message
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Sorry, I encountered an error. Please try again.'
            }))
    
    async def handle_typing(self, data):
        """Handle typing indicator"""
        is_typing = data.get('is_typing', False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_typing',
                'user_id': self.user_id,
                'is_typing': is_typing
            }
        )
    
    async def handle_feedback(self, data):
        """Handle feedback on AI response"""
        message_id = data.get('message_id')
        was_helpful = data.get('was_helpful', False)
        feedback = data.get('feedback', '')
        
        # Save feedback
        await self.save_feedback(message_id, was_helpful, feedback)
        
        await self.send(text_data=json.dumps({
            'type': 'feedback_received',
            'message': 'Thank you for your feedback!'
        }))
    
    async def handle_human_join(self, data):
        """Handle human support joining the chat"""
        if not self.user_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication required'
            }))
            return
        
        user = await self.get_user_by_id(self.user_id)
        
        if user.role not in ['admin', 'hr']:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Permission denied'
            }))
            return
        
        # Notify all participants that human support joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'human_joined',
                'user_id': user.id,
                'full_name': user.full_name,
                'role': user.role,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    # Message handlers
    async def user_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_message',
            'message_id': event['message_id'],
            'content': event['content'],
            'timestamp': event['timestamp']
        }))
    
    async def ai_response(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ai_response',
            'message_id': event['message_id'],
            'content': event['content'],
            'confidence': event['confidence'],
            'requires_email': event['requires_email'],
            'timestamp': event['timestamp']
        }))
    
    async def ai_typing(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ai_typing',
            'is_typing': event['is_typing']
        }))
    
    async def user_typing(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'user_id': event['user_id'],
            'is_typing': event['is_typing']
        }))
    
    async def human_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'human_joined',
            'user_id': event['user_id'],
            'full_name': event['full_name'],
            'role': event['role'],
            'timestamp': event['timestamp']
        }))
    
    async def human_response(self, event):
        await self.send(text_data=json.dumps({
            'type': 'human_response',
            'message_id': event['message_id'],
            'content': event['content'],
            'sender': event['sender'],
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
            print(f"Error getting user from token: {e}")
            return None
    
    @database_sync_to_async
    def get_user_by_id(self, user_id):
        try:
            return CustomUser.objects.get(id=user_id)
        except:
            return None
    
    @database_sync_to_async
    def get_chat_session(self):
        try:
            return AssistanceChat.objects.get(session_id=self.session_id, is_active=True)
        except Exception as e:
            print(f"Error getting chat session {self.session_id}: {e}")
            return None
    
    @database_sync_to_async
    def update_chat_email(self, chat_session, email):
        try:
            chat_session.email = email
            chat_session.save()
        except Exception as e:
            print(f"Error updating chat email: {e}")
    
    @database_sync_to_async
    def save_user_message(self, chat_session, content):
        try:
            return AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='user_question',
                content=content,
                sender=self.scope['user'] if self.scope['user'] else None
            )
        except Exception as e:
            print(f"Error saving user message: {e}")
            return None
    
    @database_sync_to_async
    def save_ai_message(self, chat_session, ai_result):
        try:
            return AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='ai_response',
                content=ai_result['response'],
                ai_model='free-local-model',
                ai_response_quality=int(ai_result.get('confidence', 0.5) * 100)
            )
        except Exception as e:
            print(f"Error saving AI message: {e}")
            return None
    
    @database_sync_to_async
    def get_chat_context(self, chat_session):
        try:
            messages = chat_session.messages.all().order_by('created_at')
            return list(messages.values('message_type', 'content', 'created_at'))
        except Exception as e:
            print(f"Error getting chat context: {e}")
            return []
    
    @database_sync_to_async
    def save_feedback(self, message_id, was_helpful, feedback):
        try:
            message = AssistanceMessage.objects.get(id=message_id)
            # Update AI log if exists
            from .models import AIResponseLog
            ai_log = AIResponseLog.objects.filter(
                chat=message.chat,
                ai_response=message.content
            ).first()
            
            if ai_log:
                ai_log.was_helpful = was_helpful
                ai_log.feedback_reason = feedback
                ai_log.save()
        except Exception as e:
            print(f"Error saving feedback: {e}")


class SupportNotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for support staff notifications"""
    
    async def connect(self):
        # Authenticate user
        try:
            query_string = self.scope['query_string'].decode()
            
            if not query_string:
                await self.close()
                return
            
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            token = params.get('token')
            
            if not token:
                await self.close()
                return
            
            user = await self.get_user(token)
            
            if not user or user.role not in ['admin', 'hr']:
                await self.close()
                return
            
            self.scope['user'] = user
            self.user_id = user.id
            self.user_group_name = f"support_{user.id}"
            
            await self.accept()
            
            # Join user-specific group
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            
            # Also join general support group
            await self.channel_layer.group_add(
                "support_staff",
                self.channel_name
            )
            
            print(f"✅ Support staff {user.id} connected to notifications")
            
        except Exception as e:
            print(f"❌ Support notification connection error: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
            await self.channel_layer.group_discard(
                "support_staff",
                self.channel_name
            )
    
    async def receive(self, text_data):
        pass  # Not used for notifications
    
    async def new_assistance_ticket(self, event):
        """Handle new assistance ticket notification"""
        await self.send(text_data=json.dumps({
            'type': 'new_ticket',
            'ticket_id': event['ticket_id'],
            'chat_session_id': event['chat_session_id'],
            'priority': event['priority'],
            'category': event['category'],
            'timestamp': event['timestamp']
        }))
    
    @database_sync_to_async
    def get_user(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(token)
            return CustomUser.objects.get(id=access_token['user_id'])
        except:
            return None