from datetime import timedelta, timezone
from django.utils.timezone import now
import logging
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import models

from .models import AssistanceChat, FAQ, AssistanceMessage, EmailResponse
from .services import AssistanceManager
from .serializers import FAQSerializer, AssistanceChatSerializer, EmailResponseSerializer


from datetime import timedelta
from django.utils import timezone
import logging
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import models

from .models import AssistanceChat, FAQ, AssistanceMessage, EmailResponse, AIResponseLog
from .services import AssistanceManager
from .serializers import FAQSerializer, AssistanceChatSerializer, EmailResponseSerializer

logger = logging.getLogger('assistance')

# Initialize manager
assistance_manager = AssistanceManager()


@api_view(['POST'])
@permission_classes([AllowAny])
def start_assistance_session(request):
    """
    Start a new AI assistance session
    Allows both authenticated and anonymous users
    """
    try:
        email = request.data.get('email')
        question = request.data.get('question', '').strip()
        
        # Create chat session
        chat_session = assistance_manager.create_chat_session(request, email)
        
        response_data = {
            'success': True,
            'session_id': chat_session.session_id,
            'message': 'Assistance session created successfully',
            'user_email': chat_session.get_user_email() or email
        }
        
        # Process question if provided
        if question:
            result = assistance_manager.process_question(chat_session, question)
            
            if result.get('requires_email') and not chat_session.get_user_email():
                response_data.update({
                    'requires_email': True,
                    'ai_response': result['response'],
                    'confidence': result['confidence']
                })
            else:
                response_data.update({
                    'ai_response': result['response'],
                    'requires_email': False,
                    'confidence': result['confidence'],
                    'escalated': result.get('escalated', False)
                })
        
        # Add FAQ suggestions
        faqs = FAQ.objects.filter(is_active=True).order_by('-times_asked')[:5]
        response_data['faq_suggestions'] = FAQSerializer(faqs, many=True).data
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Start session error: {e}")
        return Response({
            'error': 'Failed to start assistance session',
            'details': str(e) if settings.DEBUG else 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def ask_question(request):
    """
    Ask a question in an existing assistance session
    """
    try:
        session_id = request.data.get('session_id')
        question = request.data.get('question', '').strip()
        email = request.data.get('email')
        
        if not session_id or not question:
            return Response({
                'error': 'session_id and question are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get chat session
        chat_session = get_object_or_404(AssistanceChat, session_id=session_id, is_active=True)
        
        # Update email if provided and not already set
        if email and not chat_session.email and not chat_session.user:
            chat_session.email = email
            chat_session.save()
        
        # Process question
        result = assistance_manager.process_question(chat_session, question)
        
        # Prepare response
        response_data = {
            'success': True,
            'session_id': session_id,
            'response': result['response'],
            'confidence': result['confidence'],
            'requires_email': result.get('requires_email', False),
            'escalated': result.get('escalated', False)
        }
        
        # If escalated, add escalation info
        if result.get('escalated'):
            response_data['message'] = 'Question escalated to support team'
            response_data['support_email'] = settings.ASSISTANCE_FROM_EMAIL
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Ask question error: {e}")
        return Response({
            'error': 'Failed to process question'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_chat_session(request, session_id):
    """
    Get chat session details and messages
    """
    try:
        chat_session = get_object_or_404(AssistanceChat, session_id=session_id, is_active=True)
        serializer = AssistanceChatSerializer(chat_session)
        
        return Response({
            'success': True,
            'chat': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Get chat session error: {e}")
        return Response({
            'error': 'Failed to get chat session'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def escalate_chat(request):
    """
    Escalate chat to human support (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Only admin or HR can escalate chats'
            }, status=status.HTTP_403_FORBIDDEN)
        
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({
                'error': 'session_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        chat_session = get_object_or_404(AssistanceChat, session_id=session_id)
        
        # Escalate chat
        escalated_chat = assistance_manager.escalate_to_human(chat_session, user)
        print('')
        
        return Response({
            'success': True,
            'message': 'Chat escalated to human support',
            'session_id': session_id,
            'escalated_by': user.full_name,
            'escalated_at': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Escalate chat error: {e}")
        return Response({
            'error': 'Failed to escalate chat'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_human_response(request):
    """
    Send human response to escalated chat (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Only admin or HR can send human responses'
            }, status=status.HTTP_403_FORBIDDEN)
        
        session_id = request.data.get('session_id')
        response = request.data.get('response', '').strip()
        
        if not session_id or not response:
            return Response({
                'error': 'session_id and response are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        chat_session = get_object_or_404(AssistanceChat, session_id=session_id)
        
        # Check if chat is escalated
        if chat_session.status != 'escalated':
            return Response({
                'error': 'Chat must be escalated first'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Send human response
        success = assistance_manager.send_human_response(chat_session, response, user)
        
        if success:
            return Response({
                'success': True,
                'message': 'Response sent successfully',
                'session_id': session_id,
                'email_sent': True
            })
        else:
            return Response({
                'success': False,
                'message': 'Response saved but email failed',
                'session_id': session_id,
                'email_sent': False
            })
        
    except Exception as e:
        logger.error(f"Send human response error: {e}")
        return Response({
            'error': 'Failed to send response'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_faqs(request):
    """
    Get frequently asked questions with filtering
    """
    try:
        category = request.GET.get('category')
        search = request.GET.get('search', '')
        limit = int(request.GET.get('limit', 10))
        
        faqs = FAQ.objects.filter(is_active=True)
        
        if category:
            faqs = faqs.filter(category=category)
        
        if search:
            faqs = faqs.filter(
                models.Q(question__icontains=search) |
                models.Q(answer__icontains=search) |
                models.Q(keywords__icontains=search)
            )
        
        faqs = faqs.order_by('-times_asked')[:limit]
        serializer = FAQSerializer(faqs, many=True)
        
        return Response({
            'success': True,
            'count': faqs.count(),
            'faqs': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Get FAQs error: {e}")
        return Response({
            'error': 'Failed to get FAQs'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_escalated_chats(request):
    """
    Get escalated chats for Admin/HR
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Access denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        status_filter = request.GET.get('status', 'escalated')
        
        chats = AssistanceChat.objects.filter(status=status_filter).order_by('-created_at')
        
        if user.role == 'hr':
            # HR can only see chats from their department
            chats = chats.filter(
                models.Q(user__department=user.department) |
                models.Q(escalated_to=user)
            )
        
        serializer = AssistanceChatSerializer(chats, many=True)
        
        return Response({
            'success': True,
            'count': chats.count(),
            'chats': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Get escalated chats error: {e}")
        return Response({
            'error': 'Failed to get escalated chats'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_faq(request):
    """
    Create new FAQ (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Only admin or HR can create FAQs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        question = request.data.get('question')
        answer = request.data.get('answer')
        category = request.data.get('category', 'general')
        keywords = request.data.get('keywords', '')
        
        if not question or not answer:
            return Response({
                'error': 'question and answer are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        faq = FAQ.objects.create(
            question=question,
            answer=answer,
            category=category,
            keywords=keywords,
            created_by=user
        )
        
        serializer = FAQSerializer(faq)
        
        return Response({
            'success': True,
            'message': 'FAQ created successfully',
            'faq': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Create FAQ error: {e}")
        return Response({
            'error': 'Failed to create FAQ'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assistance_analytics(request):
    """
    Get analytics for assistance system (Admin only)
    """
    try:
        user = request.user
        if user.role != 'admin':
            return Response({
                'error': 'Only admin can view analytics'
            }, status=status.HTTP_403_FORBIDDEN)
        
        from django.utils import timezone
        from datetime import timedelta
        
        # Time period
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Statistics
        total_sessions = AssistanceChat.objects.filter(created_at__gte=start_date).count()
        ai_handled = AssistanceChat.objects.filter(
            created_at__gte=start_date,
            status='ai_handled'
        ).count()
        escalated = AssistanceChat.objects.filter(
            created_at__gte=start_date,
            status='escalated'
        ).count()
        resolved = AssistanceChat.objects.filter(
            created_at__gte=start_date,
            status='resolved'
        ).count()
        
        # Top FAQs
        top_faqs = FAQ.objects.filter(is_active=True).order_by('-times_asked')[:10]
        
        # Response time
        from .models import AIResponseLog
        ai_logs = AIResponseLog.objects.filter(created_at__gte=start_date)
        avg_response_time = ai_logs.aggregate(models.Avg('response_time'))['response_time__avg'] or 0
        
        return Response({
            'success': True,
            'analytics': {
                'period_days': days,
                'total_sessions': total_sessions,
                'ai_handled': ai_handled,
                'escalated': escalated,
                'resolved': resolved,
                'resolution_rate': (resolved / total_sessions * 100) if total_sessions > 0 else 0,
                'avg_response_time_seconds': round(avg_response_time, 2),
                'top_faqs': FAQSerializer(top_faqs, many=True).data
            }
        })
        
    except Exception as e:
        logger.error(f"Get analytics error: {e}")
        return Response({
            'error': 'Failed to get analytics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

# assistanceApp/views.py - Add this function
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def faq_detail(request, pk):
    """
    Retrieve, update or delete a FAQ (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Only admin or HR can manage FAQs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        faq = get_object_or_404(FAQ, id=pk)
        
        if request.method == 'GET':
            serializer = FAQSerializer(faq)
            return Response({
                'success': True,
                'faq': serializer.data
            })
            
        elif request.method == 'PUT':
            question = request.data.get('question')
            answer = request.data.get('answer')
            category = request.data.get('category', faq.category)
            keywords = request.data.get('keywords', faq.keywords)
            
            if not question or not answer:
                return Response({
                    'error': 'question and answer are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            faq.question = question
            faq.answer = answer
            faq.category = category
            faq.keywords = keywords
            faq.save()
            
            serializer = FAQSerializer(faq)
            
            return Response({
                'success': True,
                'message': 'FAQ updated successfully',
                'faq': serializer.data
            })
            
        elif request.method == 'DELETE':
            faq.delete()
            return Response({
                'success': True,
                'message': 'FAQ deleted successfully'
            }, status=status.HTTP_204_NO_CONTENT)
            
    except Exception as e:
        logger.error(f"FAQ detail error: {e}")
        return Response({
            'error': 'Failed to process FAQ request'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_chats(request):
    """
    Get all chat sessions with filters (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        status_filter = request.GET.get('status', 'all')
        search = request.GET.get('search', '')
        limit = int(request.GET.get('limit', 50))
        
        chats = AssistanceChat.objects.all().order_by('-created_at')
        
        if status_filter and status_filter != 'all':
            chats = chats.filter(status=status_filter)
        
        if search:
            chats = chats.filter(
                models.Q(session_id__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(user__email__icontains=search) |
                models.Q(user__full_name__icontains=search)
            )
        
        # Get chat statistics
        chat_stats = {
            'total': AssistanceChat.objects.count(),
            'ai_handled': AssistanceChat.objects.filter(status='ai_handled').count(),
            'human_requested': AssistanceChat.objects.filter(status='human_requested').count(),
            'escalated': AssistanceChat.objects.filter(status='escalated').count(),
            'human_responding': AssistanceChat.objects.filter(status='human_responding').count(),
            'resolved': AssistanceChat.objects.filter(status='resolved').count(),
        }
        
        chats = chats[:limit]
        serializer = AssistanceChatSerializer(chats, many=True)
        
        return Response({
            'success': True,
            'count': chats.count(),
            'total_count': chat_stats['total'],
            'stats': chat_stats,
            'chats': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Get all chats error: {e}")
        return Response({'error': 'Failed to get chats'}, status=500)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_chat_status(request, chat_id):
    """
    Update chat status (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        chat = get_object_or_404(AssistanceChat, id=chat_id)
        new_status = request.data.get('status')
        
        valid_statuses = dict(AssistanceChat.STATUS_CHOICES)
        if new_status not in valid_statuses:
            return Response({'error': 'Invalid status'}, status=400)
        
        old_status = chat.status
        chat.status = new_status
        
        # Update escalated_to if user is taking over
        if new_status == 'human_responding' and not chat.escalated_to:
            chat.escalated_to = user
        
        # Update resolved_at if marking as resolved
        if new_status == 'resolved' and not chat.resolved_at:
            chat.resolved_at = now()
            chat.is_active = False
        
        chat.save()
        
        # Log the status change
        AssistanceMessage.objects.create(
            chat=chat,
            message_type='system',
            content=f'Chat status changed from {old_status} to {new_status} by {user.full_name}',
            sender=user
        )
        
        return Response({
            'success': True,
            'message': f'Chat status updated to {valid_statuses[new_status]}',
            'chat': AssistanceChatSerializer(chat).data
        })
        
    except Exception as e:
        logger.error(f"Update chat status error: {e}")
        return Response({'error': 'Failed to update status'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resolve_chat(request, chat_id):
    """
    Mark chat as resolved (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        chat = get_object_or_404(AssistanceChat, id=chat_id)
        
        chat.status = 'resolved'
        chat.resolved_at = now()
        chat.is_active = False
        
        # Add system message
        AssistanceMessage.objects.create(
            chat=chat,
            message_type='system',
            content=f'Chat marked as resolved by {user.full_name}',
            sender=user
        )
        
        chat.save()
        
        return Response({
            'success': True,
            'message': 'Chat marked as resolved',
            'chat': AssistanceChatSerializer(chat).data
        })
        
    except Exception as e:
        logger.error(f"Resolve chat error: {e}")
        return Response({'error': 'Failed to resolve chat'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_popular_questions(request):
    """
    Get most frequently asked questions from chat history
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 20))
        
        from_date = timezone.now() - timedelta(days=days)
        
        # Get user questions from messages
        user_questions = AssistanceMessage.objects.filter(
            message_type='user_question',
            created_at__gte=from_date
        ).values('content').annotate(
            count=models.Count('id'),
            last_asked=models.Max('created_at')
        ).order_by('-count')[:limit]
        
        # Process questions to find patterns
        questions = []
        for item in user_questions:
            # Clean and normalize the question
            question_text = item['content'].strip().lower()
            
            # Check if this question matches any existing FAQ
            matching_faqs = FAQ.objects.filter(
                models.Q(question__icontains=question_text[:100]) |
                models.Q(keywords__icontains=question_text.split()[0]) if question_text else False
            )[:3]
            
            questions.append({
                'question': item['content'],
                'count': item['count'],
                'last_asked': item['last_asked'],
                'matching_faqs': FAQSerializer(matching_faqs, many=True).data if matching_faqs else []
            })
        
        return Response({
            'success': True,
            'period_days': days,
            'questions': questions
        })
        
    except Exception as e:
        logger.error(f"Get popular questions error: {e}")
        return Response({'error': 'Failed to get popular questions'}, status=500)
    



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def take_over_chat(request, chat_id):
    """
    Admin/HR takes over a chat (changes status to human_responding)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        chat = get_object_or_404(AssistanceChat, id=chat_id)
        
        # Check if chat can be taken over
        if chat.status not in ['human_requested', 'escalated']:
            return Response({
                'error': f'Chat status must be human_requested or escalated, not {chat.status}'
            }, status=400)
        
        old_status = chat.status
        chat.status = 'human_responding'
        chat.escalated_to = user
        chat.save()
        
        # Add system message
        AssistanceMessage.objects.create(
            chat=chat,
            message_type='system',
            content=f'{user.full_name} has taken over this chat',
            sender=user
        )
        
        serializer = AssistanceChatSerializer(chat)
        
        return Response({
            'success': True,
            'message': f'You have taken over chat {chat.session_id}',
            'chat': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Take over chat error: {e}")
        return Response({'error': 'Failed to take over chat'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_faq_effectiveness(request):
    """
    Get FAQ effectiveness metrics (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        days = int(request.GET.get('days', 30))
        
        faq_stats = assistance_manager.get_faq_effectiveness(days)
        
        return Response({
            'success': True,
            'period_days': days,
            'faq_stats': faq_stats
        })
        
    except Exception as e:
        logger.error(f"Get FAQ effectiveness error: {e}")
        return Response({'error': 'Failed to get FAQ effectiveness'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_faq_feedback(request, faq_id):
    """
    Update FAQ feedback (helpful/not helpful) from users
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        was_helpful = request.data.get('was_helpful')
        
        if was_helpful is None:
            return Response({'error': 'was_helpful field is required'}, status=400)
        
        success = assistance_manager.update_faq_feedback(faq_id, was_helpful)
        
        if success:
            return Response({
                'success': True,
                'message': 'FAQ feedback updated successfully'
            })
        else:
            return Response({
                'success': False,
                'error': 'FAQ not found'
            }, status=404)
        
    except Exception as e:
        logger.error(f"Update FAQ feedback error: {e}")
        return Response({'error': 'Failed to update FAQ feedback'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_system_health(request):
    """
    Get system health status (Admin only)
    """
    try:
        user = request.user
        if user.role != 'admin':
            return Response({'error': 'Access denied'}, status=403)
        
        health_report = assistance_manager.check_system_health()
        
        return Response({
            'success': True,
            'health_report': health_report
        })
        
    except Exception as e:
        logger.error(f"Get system health error: {e}")
        return Response({'error': 'Failed to get system health'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_faq_suggestions(request):
    """
    Get suggestions for new FAQs based on frequently asked questions
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr']:
            return Response({'error': 'Access denied'}, status=403)
        
        min_occurrences = int(request.GET.get('min_occurrences', 3))
        
        suggestions = assistance_manager.suggest_new_faqs(min_occurrences)
        
        return Response({
            'success': True,
            'suggestions': suggestions
        })
        
    except Exception as e:
        logger.error(f"Get FAQ suggestions error: {e}")
        return Response({'error': 'Failed to get FAQ suggestions'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def batch_update_faq_usage(request):
    """
    Batch update FAQ usage statistics (Admin only - typically run as cron job)
    """
    try:
        user = request.user
        if user.role != 'admin':
            return Response({'error': 'Access denied'}, status=403)
        
        updated_count = assistance_manager.batch_update_faq_usage()
        
        return Response({
            'success': True,
            'message': f'Batch update completed. Processed {updated_count} FAQs.',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Batch update FAQ usage error: {e}")
        return Response({'error': 'Failed to batch update FAQ usage'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_analytics_detailed(request):
    """
    Get detailed chat analytics (Admin only)
    """
    try:
        user = request.user
        if user.role != 'admin':
            return Response({'error': 'Access denied'}, status=403)
        
        days = int(request.GET.get('days', 30))
        from_date = timezone.now() - timedelta(days=days)
        
        # Detailed statistics
        total_chats = AssistanceChat.objects.filter(created_at__gte=from_date).count()
        
        # Status breakdown
        status_counts = {}
        for status_code, status_name in AssistanceChat.STATUS_CHOICES:
            count = AssistanceChat.objects.filter(
                created_at__gte=from_date,
                status=status_code
            ).count()
            status_counts[status_name] = count
        
        # Average messages per chat
        avg_messages = AssistanceMessage.objects.filter(
            created_at__gte=from_date
        ).count() / max(total_chats, 1)
        
        # Response time analysis
        ai_logs = AIResponseLog.objects.filter(created_at__gte=from_date)
        avg_response_time = ai_logs.aggregate(models.Avg('response_time'))['response_time__avg'] or 0
        
        # Confidence distribution
        high_confidence = ai_logs.filter(confidence_score__gte=0.7).count()
        medium_confidence = ai_logs.filter(confidence_score__gte=0.4, confidence_score__lt=0.7).count()
        low_confidence = ai_logs.filter(confidence_score__lt=0.4).count()
        
        # FAQ usage
        faq_usage = FAQ.objects.filter(is_active=True).order_by('-times_asked')[:10]
        
        # User type breakdown
        authenticated_chats = AssistanceChat.objects.filter(
            created_at__gte=from_date,
            user__isnull=False
        ).count()
        anonymous_chats = total_chats - authenticated_chats
        
        return Response({
            'success': True,
            'analytics': {
                'period_days': days,
                'total_chats': total_chats,
                'status_distribution': status_counts,
                'avg_messages_per_chat': round(avg_messages, 2),
                'avg_response_time_seconds': round(avg_response_time, 2),
                'confidence_distribution': {
                    'high': high_confidence,
                    'medium': medium_confidence,
                    'low': low_confidence
                },
                'user_type_breakdown': {
                    'authenticated': authenticated_chats,
                    'anonymous': anonymous_chats
                },
                'top_faqs': FAQSerializer(faq_usage, many=True).data
            }
        })
        
    except Exception as e:
        logger.error(f"Get detailed analytics error: {e}")
        return Response({'error': 'Failed to get detailed analytics'}, status=500)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_chats(request):
    """
    Get all chat sessions for the authenticated user (including linked anonymous sessions)
    """
    try:
        user = request.user
        status_filter = request.GET.get('status', 'all')
        limit = int(request.GET.get('limit', 20))
        
        # Get all chats for user (using the manager to include email-matched chats)
        all_chats = assistance_manager.get_user_chats(user)
        
        # Apply status filter
        if status_filter and status_filter != 'all':
            all_chats = [chat for chat in all_chats if chat.status == status_filter]
        
        # Apply limit
        chats = all_chats[:limit]
        
        # Get stats
        user_chats = AssistanceChat.objects.filter(user=user)
        email_chats = AssistanceChat.objects.filter(email__iexact=user.email, user__isnull=True)
        
        chat_stats = {
            'total': user_chats.count() + email_chats.count(),
            'ai_handled': user_chats.filter(status='ai_handled').count() + 
                          email_chats.filter(status='ai_handled').count(),
            'human_requested': user_chats.filter(status='human_requested').count() + 
                              email_chats.filter(status='human_requested').count(),
            'escalated': user_chats.filter(status='escalated').count() + 
                         email_chats.filter(status='escalated').count(),
            'human_responding': user_chats.filter(status='human_responding').count() + 
                               email_chats.filter(status='human_responding').count(),
            'resolved': user_chats.filter(status='resolved').count() + 
                        email_chats.filter(status='resolved').count(),
            'linked_sessions': user_chats.count(),
            'unlinked_sessions': email_chats.count()
        }
        
        serializer = AssistanceChatSerializer(chats, many=True)
        
        return Response({
            'success': True,
            'user_id': user.id,
            'user_email': user.email,
            'count': len(chats),
            'stats': chat_stats,
            'chats': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Get my chats error: {e}")
        return Response({
            'error': 'Failed to get your chat sessions'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@permission_classes([AllowAny])
def get_chat_by_session(request, session_id):
    """
    Get chat session by ID (public, but with access control)
    """
    try:
        chat = get_object_or_404(AssistanceChat, session_id=session_id)
        user = request.user if request.user.is_authenticated else None
        
        # Check access permissions
        can_access = False
        access_reason = ""
        
        if user:
            # Check if user can access this chat
            if chat.user == user:
                can_access = True
                access_reason = "owner"
            elif user.role in ['admin', 'hr']:
                can_access = True
                access_reason = "admin"
            elif chat.email and user.email and chat.email.lower() == user.email.lower():
                # User authenticated with same email as chat
                can_access = True
                access_reason = "email_match"
                # Auto-link if not already linked
                if not chat.user:
                    chat.user = user
                    chat.linked_at = timezone.now()
                    chat.save()
        else:
            # Anonymous user - can only access if they have the session
            # In a real app, you might want to use session cookies or tokens
            can_access = True
            access_reason = "session_holder"
        
        if not can_access:
            return Response({
                'error': 'You do not have permission to access this chat session'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = AssistanceChatSerializer(chat)
        
        return Response({
            'success': True,
            'chat': serializer.data,
            'access_reason': access_reason,
            'is_owner': chat.user == user if user else False,
            'can_continue': chat.is_active and chat.status != 'resolved'
        })
        
    except Exception as e:
        logger.error(f"Get chat by session error: {e}")
        return Response({
            'error': 'Failed to get chat session'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def link_my_sessions(request):
    """
    Manually link anonymous chat sessions to authenticated user
    Useful when auto-linking didn't work
    """
    try:
        user = request.user
        
        # Find sessions with matching email
        sessions_to_link = AssistanceChat.objects.filter(
            email__iexact=user.email,
            user__isnull=True
        )
        
        linked_count = 0
        linked_sessions = []
        
        for session in sessions_to_link:
            session.user = user
            session.linked_at = timezone.now()
            session.save()
            linked_count += 1
            linked_sessions.append({
                'session_id': session.session_id,
                'created_at': session.created_at,
                'status': session.status
            })
        
        return Response({
            'success': True,
            'message': f'Linked {linked_count} chat sessions to your account',
            'linked_count': linked_count,
            'linked_sessions': linked_sessions
        })
        
    except Exception as e:
        logger.error(f"Link my sessions error: {e}")
        return Response({
            'error': 'Failed to link chat sessions'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def find_my_unlinked_chats(request):
    """
    Find chat sessions that might belong to the user but aren't linked yet
    """
    try:
        user = request.user
        
        # Find potential matches
        potential_chats = []
        
        # 1. Chats with matching email but no user
        email_matches = AssistanceChat.objects.filter(
            email__iexact=user.email,
            user__isnull=True
        )
        
        for chat in email_matches:
            potential_chats.append({
                'session_id': chat.session_id,
                'created_at': chat.created_at,
                'status': chat.status,
                'match_reason': 'email_match',
                'email': chat.email,
                'message_count': chat.messages.count()
            })
        
        # 2. Chats from same IP (optional - privacy considerations)
        # last_ip = user.last_login_ip  # You'd need to track this
        # if last_ip:
        #     ip_matches = AssistanceChat.objects.filter(
        #         ip_address=last_ip,
        #         user__isnull=True,
        #         email__isnull=True
        #     )
        #     ... add to potential_chats
        
        return Response({
            'success': True,
            'user_email': user.email,
            'potential_matches': potential_chats,
            'total_matches': len(potential_chats)
        })
        
    except Exception as e:
        logger.error(f"Find unlinked chats error: {e}")
        return Response({
            'error': 'Failed to find unlinked chats'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['POST'])
@permission_classes([AllowAny])
def claim_chat_session(request):
    """
    Claim/transfer a chat session to authenticated user
    Useful when user started chat anonymously, then logged in
    """
    try:
        session_id = request.data.get('session_id')
        user_email = request.data.get('user_email')  # For verification
        
        if not session_id:
            return Response({
                'error': 'session_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        chat = get_object_or_404(AssistanceChat, session_id=session_id)
        
        # Check if user is authenticated
        if request.user.is_authenticated:
            user = request.user
            
            # Verify email matches (if email was provided in chat)
            if chat.email and user.email and chat.email.lower() == user.email.lower():
                if not chat.user:
                    chat.user = user
                    chat.linked_at = timezone.now()
                    chat.save()
                    
                    return Response({
                        'success': True,
                        'message': 'Chat session linked to your account',
                        'session_id': session_id,
                        'linked_at': chat.linked_at
                    })
                else:
                    return Response({
                        'success': False,
                        'error': 'Chat session already linked to another user'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    'success': False,
                    'error': 'Email does not match. Cannot link chat session.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        else:
            # User not authenticated - they need to login first
            return Response({
                'success': False,
                'error': 'Authentication required to claim chat session',
                'requires_login': True
            }, status=status.HTTP_401_UNAUTHORIZED)
        
    except Exception as e:
        logger.error(f"Claim chat session error: {e}")
        return Response({
            'error': 'Failed to claim chat session'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['POST'])
@permission_classes([AllowAny])
def continue_chat_session(request):
    """
    Continue a chat session (works for both authenticated and anonymous users)
    """
    try:
        session_id = request.data.get('session_id')
        question = request.data.get('question', '').strip()
        
        if not session_id or not question:
            return Response({
                'error': 'session_id and question are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get chat session
        chat = get_object_or_404(AssistanceChat, session_id=session_id)
        
        # Check if user can access this chat
        user = request.user if request.user.is_authenticated else None
        
        if user:
            # Authenticated user - check permissions
            if not chat.can_access(user):
                return Response({
                    'error': 'You do not have permission to access this chat'
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            # Anonymous user - can only continue if they started it
            # In production, you'd want to check session cookies or tokens
            pass  # Allow for now
        
        # Check if chat is active
        if not chat.is_active or chat.status == 'resolved':
            return Response({
                'error': 'This chat session is no longer active'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process question
        result = assistance_manager.process_question(chat, question)
        
        # Auto-link to user if authenticated and not already linked
        if user and not chat.user:
            # Check if email matches
            if chat.email and user.email and chat.email.lower() == user.email.lower():
                chat.user = user
                chat.linked_at = timezone.now()
                chat.save()
        
        response_data = {
            'success': True,
            'session_id': session_id,
            'response': result['response'],
            'confidence': result['confidence'],
            'requires_email': result.get('requires_email', False),
            'escalated': result.get('escalated', False),
            'current_status': chat.status,
            'is_linked': chat.user is not None,
            'user_authenticated': user is not None
        }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Continue chat session error: {e}")
        return Response({
            'error': 'Failed to process your question'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def mark_chat_resolved(request, chat_id):
    print(f'\nsubmitted data: {request.data}\n')
    """
    Update chat status (Admin/HR only)
    """
    try:
        user = request.user
        if user.role not in ['admin', 'hr', 'mentor', 'mentee']:
            return Response({'error': 'Access denied'}, status=403)
        
        chat = get_object_or_404(AssistanceChat, id=chat_id)
        new_status = request.data.get('status')
        
        valid_statuses = dict(AssistanceChat.STATUS_CHOICES)
        if new_status not in valid_statuses:
            return Response({'error': 'Invalid status'}, status=400)
        
        old_status = chat.status
        chat.status = new_status
        
        # Update escalated_to if user is taking over
        if new_status == 'human_responding' and not chat.escalated_to:
            chat.escalated_to = user
        
        # Update resolved_at if marking as resolved
        if new_status == 'resolved' and not chat.resolved_at:
            chat.resolved_at = now()
            chat.is_active = False
        
        chat.save()
        
        # Log the status change
        AssistanceMessage.objects.create(
            chat=chat,
            message_type='system',
            content=f'Chat status changed from {old_status} to {new_status} by {user.full_name}',
            sender=user
        )
        
        return Response({
            'success': True,
            'message': f'Chat status updated to {valid_statuses[new_status]}',
            'chat': AssistanceChatSerializer(chat).data
        })
        
    except Exception as e:
        logger.error(f"Update chat status error: {e}")
        return Response({'error': 'Failed to update status'}, status=500)

