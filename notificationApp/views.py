from django.conf import settings
from django.shortcuts import render
from django.forms import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, F
from django.utils.timezone import now, timedelta
from datetime import datetime

from .models import (
    ChatNotification, SystemNotification,
    UserNotificationPreference, NotificationLog
)
from .serializers import (
    ChatNotificationSerializer, SystemNotificationSerializer,
    UserNotificationPreferenceSerializer, NotificationLogSerializer,
    CreateSystemNotificationSerializer, MarkNotificationsReadSerializer
)
from userApp.models import CustomUser


# ==================== CHAT NOTIFICATION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_chat_notifications(request):
    """List all chat notifications for the authenticated user"""
    try:
        user = request.user
        notification_type = request.query_params.get('type')
        is_read = request.query_params.get('is_read')
        is_archived = request.query_params.get('is_archived', 'false').lower() == 'true'
        
        # Base queryset
        notifications = ChatNotification.objects.filter(recipient=user)
        
        # Apply filters
        if notification_type:
            notifications = notifications.filter(notification_type=notification_type)
        
        if is_read:
            is_read_bool = is_read.lower() == 'true'
            notifications = notifications.filter(is_read=is_read_bool)
        
        # By default, don't show archived notifications
        if not is_archived:
            notifications = notifications.filter(is_archived=False)
        
        # Apply ordering
        notifications = notifications.order_by('-created_at')
        
        # Pagination
        limit = request.query_params.get('limit', 20)
        try:
            limit = int(limit)
            if limit > 100:
                limit = 100
        except (ValueError, TypeError):
            limit = 20
        
        notifications = notifications[:limit]
        
        serializer = ChatNotificationSerializer(notifications, many=True)
        
        # Get counts for different notification types
        counts = {
            'total': ChatNotification.objects.filter(recipient=user, is_archived=False).count(),
            'unread': ChatNotification.objects.filter(recipient=user, is_read=False, is_archived=False).count(),
            'archived': ChatNotification.objects.filter(recipient=user, is_archived=True).count()
        }
        
        return Response({
            'success': True,
            'count': notifications.count(),
            'total_count': counts['total'],
            'unread_count': counts['unread'],
            'archived_count': counts['archived'],
            'notifications': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch chat notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_chat_notifications_read(request):
    """Mark specific chat notifications as read"""
    try:
        user = request.user
        serializer = MarkNotificationsReadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        notification_ids = data.get('notification_ids', [])
        mark_all = data.get('mark_all', False)
        
        if mark_all:
            # Mark all unread notifications as read
            updated_count = ChatNotification.objects.filter(
                recipient=user,
                is_read=False,
                is_archived=False
            ).update(
                is_read=True,
                read_at=now()
            )
            
            return Response({
                'success': True,
                'message': f'Marked {updated_count} notifications as read',
                'count': updated_count
            }, status=status.HTTP_200_OK)
        else:
            # Mark specific notifications as read
            updated_count = 0
            for notification_id in notification_ids:
                try:
                    notification = ChatNotification.objects.get(
                        id=notification_id,
                        recipient=user,
                        is_archived=False
                    )
                    if not notification.is_read:
                        notification.is_read = True
                        notification.read_at = now()
                        notification.save()
                        updated_count += 1
                except ChatNotification.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'message': f'Marked {updated_count} notifications as read',
                'count': updated_count
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to mark notifications as read',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_chat_notifications_read(request):
    """Mark all chat notifications as read for the authenticated user"""
    try:
        user = request.user
        
        updated_count = ChatNotification.objects.filter(
            recipient=user,
            is_read=False,
            is_archived=False
        ).update(
            is_read=True,
            read_at=now()
        )
        
        return Response({
            'success': True,
            'message': f'Marked all {updated_count} unread notifications as read',
            'count': updated_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to mark all notifications as read',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def archive_chat_notification(request, notification_id):
    """Archive a specific chat notification"""
    try:
        user = request.user
        
        notification = get_object_or_404(
            ChatNotification,
            id=notification_id,
            recipient=user
        )
        
        if notification.is_archived:
            return Response({
                'success': True,
                'message': 'Notification is already archived'
            }, status=status.HTTP_200_OK)
        
        notification.is_archived = True
        notification.archived_at = now()
        notification.save()
        
        return Response({
            'success': True,
            'message': 'Notification archived successfully',
            'notification_id': notification_id
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to archive notification',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def archive_all_read_chat_notifications(request):
    """Archive all read chat notifications"""
    try:
        user = request.user
        
        updated_count = ChatNotification.objects.filter(
            recipient=user,
            is_read=True,
            is_archived=False
        ).update(
            is_archived=True,
            archived_at=now()
        )
        
        return Response({
            'success': True,
            'message': f'Archived {updated_count} read notifications',
            'count': updated_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to archive notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== SYSTEM NOTIFICATION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_system_notifications(request):
    """List system notifications for the authenticated user"""
    try:
        user = request.user
        
        # Get active system notifications that apply to this user
        system_notifications = SystemNotification.objects.filter(
            is_active=True,
            start_date__lte=now()
        )
        
        # Filter by end date if exists
        system_notifications = system_notifications.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now())
        )
        
        # Filter by user role if not global
        system_notifications = system_notifications.filter(
            Q(is_global=True) |
            Q(target_roles__contains=[user.role]) |
            Q(target_departments__contains=[user.department])
        ).distinct()
        
        # Apply ordering
        system_notifications = system_notifications.order_by('-created_at')
        
        # Pagination
        limit = request.query_params.get('limit', 10)
        try:
            limit = int(limit)
            if limit > 50:
                limit = 50
        except (ValueError, TypeError):
            limit = 10
        
        system_notifications = system_notifications[:limit]
        
        serializer = SystemNotificationSerializer(system_notifications, many=True)
        
        return Response({
            'success': True,
            'count': system_notifications.count(),
            'notifications': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch system notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_system_notification(request):
    """Create a new system notification (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can create system notifications'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CreateSystemNotificationSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create system notification
        system_notification = serializer.save(created_by=user)
        
        # Log the creation
        NotificationLog.objects.create(
            recipient=user,
            notification_type='system_notification_created',
            title=f'System Notification Created: {system_notification.title}',
            message=f'Created by {user.full_name}',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': 'System notification created successfully',
            'notification': SystemNotificationSerializer(system_notification).data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to create system notification',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_system_notification(request, notification_id):
    """Get details of a specific system notification"""
    try:
        user = request.user
        
        system_notification = get_object_or_404(SystemNotification, id=notification_id)
        
        # Check if user has access
        if (not system_notification.is_global and 
            user.role not in system_notification.target_roles and
            user.department not in system_notification.target_departments):
            return Response({
                'success': False,
                'error': 'Permission denied. You do not have access to this notification'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = SystemNotificationSerializer(system_notification)
        
        return Response({
            'success': True,
            'notification': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch system notification',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_system_notification(request, notification_id):
    """Update a system notification (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can update system notifications'
            }, status=status.HTTP_403_FORBIDDEN)
        
        system_notification = get_object_or_404(SystemNotification, id=notification_id)
        
        partial = request.method == 'PATCH'
        serializer = SystemNotificationSerializer(
            system_notification,
            data=request.data,
            partial=partial
        )
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_notification = serializer.save()
        
        # Log the update
        NotificationLog.objects.create(
            recipient=user,
            notification_type='system_notification_updated',
            title=f'System Notification Updated: {updated_notification.title}',
            message=f'Updated by {user.full_name}',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': 'System notification updated successfully',
            'notification': SystemNotificationSerializer(updated_notification).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to update system notification',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def archive_system_notification(request, notification_id):
    """Archive a system notification (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can archive system notifications'
            }, status=status.HTTP_403_FORBIDDEN)
        
        system_notification = get_object_or_404(SystemNotification, id=notification_id)
        
        if not system_notification.is_active:
            return Response({
                'success': True,
                'message': 'System notification is already inactive'
            }, status=status.HTTP_200_OK)
        
        system_notification.is_active = False
        system_notification.save()
        
        # Log the archive
        NotificationLog.objects.create(
            recipient=user,
            notification_type='system_notification_archived',
            title=f'System Notification Archived: {system_notification.title}',
            message=f'Archived by {user.full_name}',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': 'System notification archived successfully',
            'notification_id': notification_id
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to archive system notification',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== USER PREFERENCE VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_notification_preferences(request):
    """Get notification preferences for the authenticated user"""
    try:
        user = request.user
        
        # Get or create preferences
        preferences, created = UserNotificationPreference.objects.get_or_create(
            user=user,
            defaults={
                'enable_chat_notifications': True,
                'enable_message_notifications': True,
                'enable_group_chat_notifications': True,
                'enable_cross_department_notifications': True,
                'enable_system_notifications': True,
                'enable_announcements': True,
                'enable_updates': True,
                'enable_email_notifications': True,
                'enable_push_notifications': True,
                'enable_quiet_hours': False,
                'enable_sound': True,
                'sound_name': 'default',
                'email_frequency': 'instant'
            }
        )
        
        serializer = UserNotificationPreferenceSerializer(preferences)
        
        return Response({
            'success': True,
            'created': created,
            'preferences': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch notification preferences',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_user_notification_preferences(request):
    """Update notification preferences for the authenticated user"""
    try:
        user = request.user
        
        # Get user preferences
        preferences = get_object_or_404(UserNotificationPreference, user=user)
        
        partial = request.method == 'PATCH'
        serializer = UserNotificationPreferenceSerializer(
            preferences,
            data=request.data,
            partial=partial
        )
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_preferences = serializer.save()
        
        # Log the update
        NotificationLog.objects.create(
            recipient=user,
            notification_type='notification_preferences_updated',
            title='Notification Preferences Updated',
            message=f'User updated their notification preferences',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': 'Notification preferences updated successfully',
            'preferences': UserNotificationPreferenceSerializer(updated_preferences).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to update notification preferences',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== NOTIFICATION STATISTICS VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notification_statistics(request):
    """Get notification statistics (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can view notification statistics'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Time periods for analysis
        now_time = now()
        today = now_time.date()
        week_ago = now_time - timedelta(days=7)
        month_ago = now_time - timedelta(days=30)
        
        # Chat notification statistics
        chat_stats = {
            'total': ChatNotification.objects.count(),
            'unread': ChatNotification.objects.filter(is_read=False, is_archived=False).count(),
            'today': ChatNotification.objects.filter(created_at__date=today).count(),
            'last_7_days': ChatNotification.objects.filter(created_at__gte=week_ago).count(),
            'last_30_days': ChatNotification.objects.filter(created_at__gte=month_ago).count(),
            'by_type': list(ChatNotification.objects.values('notification_type')
                          .annotate(count=Count('id'))
                          .order_by('-count'))
        }
        
        # System notification statistics
        system_stats = {
            'total': SystemNotification.objects.count(),
            'active': SystemNotification.objects.filter(is_active=True).count(),
            'global': SystemNotification.objects.filter(is_global=True).count(),
            'by_level': list(SystemNotification.objects.values('level')
                           .annotate(count=Count('id'))
                           .order_by('-count'))
        }
        
        # User preference statistics
        preference_stats = {
            'total_users_with_preferences': UserNotificationPreference.objects.count(),
            'email_notifications_enabled': UserNotificationPreference.objects.filter(
                enable_email_notifications=True
            ).count(),
            'push_notifications_enabled': UserNotificationPreference.objects.filter(
                enable_push_notifications=True
            ).count(),
            'quiet_hours_enabled': UserNotificationPreference.objects.filter(
                enable_quiet_hours=True
            ).count()
        }
        
        # Notification log statistics
        log_stats = {
            'total': NotificationLog.objects.count(),
            'successful': NotificationLog.objects.filter(success=True).count(),
            'failed': NotificationLog.objects.filter(success=False).count(),
            'today': NotificationLog.objects.filter(created_at__date=today).count(),
            'by_type': list(NotificationLog.objects.values('notification_type')
                          .annotate(count=Count('id'))
                          .order_by('-count')[:10])
        }
        
        return Response({
            'success': True,
            'statistics': {
                'chat_notifications': chat_stats,
                'system_notifications': system_stats,
                'user_preferences': preference_stats,
                'notification_logs': log_stats,
                'time_periods': {
                    'today': today,
                    'week_ago': week_ago.date(),
                    'month_ago': month_ago.date()
                }
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch notification statistics',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notification_logs(request):
    """Get notification logs (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can view notification logs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get query parameters
        recipient_id = request.query_params.get('recipient_id')
        notification_type = request.query_params.get('type')
        success = request.query_params.get('success')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Base queryset
        logs = NotificationLog.objects.all().select_related('recipient')
        
        # Apply filters
        if recipient_id:
            try:
                logs = logs.filter(recipient_id=int(recipient_id))
            except (ValueError, TypeError):
                pass
        
        if notification_type:
            logs = logs.filter(notification_type=notification_type)
        
        if success:
            success_bool = success.lower() == 'true'
            logs = logs.filter(success=success_bool)
        
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                logs = logs.filter(created_at__gte=start_date)
            except (ValueError, AttributeError):
                pass
        
        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                logs = logs.filter(created_at__lte=end_date)
            except (ValueError, AttributeError):
                pass
        
        # Apply ordering
        logs = logs.order_by('-created_at')
        
        # Pagination
        limit = request.query_params.get('limit', 50)
        try:
            limit = int(limit)
            if limit > 200:
                limit = 200
        except (ValueError, TypeError):
            limit = 50
        
        logs = logs[:limit]
        
        serializer = NotificationLogSerializer(logs, many=True)
        
        return Response({
            'success': True,
            'count': logs.count(),
            'logs': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch notification logs',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== BULK OPERATION VIEWS ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_archive_notifications(request):
    """Bulk archive notifications (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can perform bulk operations'
            }, status=status.HTTP_403_FORBIDDEN)
        
        notification_ids = request.data.get('notification_ids', [])
        archive_all_read = request.data.get('archive_all_read', False)
        archive_all_older_than = request.data.get('archive_all_older_than')
        
        if not notification_ids and not archive_all_read and not archive_all_older_than:
            return Response({
                'success': False,
                'error': 'No operation specified. Provide notification_ids, archive_all_read, or archive_all_older_than'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_count = 0
        
        if notification_ids:
            # Archive specific notifications
            updated_count = ChatNotification.objects.filter(
                id__in=notification_ids,
                is_archived=False
            ).update(
                is_archived=True,
                archived_at=now()
            )
        
        elif archive_all_read:
            # Archive all read notifications
            updated_count = ChatNotification.objects.filter(
                is_read=True,
                is_archived=False
            ).update(
                is_archived=True,
                archived_at=now()
            )
        
        elif archive_all_older_than:
            # Archive notifications older than specified date
            try:
                cutoff_date = datetime.fromisoformat(archive_all_older_than.replace('Z', '+00:00'))
                updated_count = ChatNotification.objects.filter(
                    created_at__lt=cutoff_date,
                    is_archived=False
                ).update(
                    is_archived=True,
                    archived_at=now()
                )
            except (ValueError, AttributeError):
                return Response({
                    'success': False,
                    'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log the bulk operation
        NotificationLog.objects.create(
            recipient=user,
            notification_type='bulk_archive_notifications',
            title=f'Bulk Archive Notifications',
            message=f'Archived {updated_count} notifications',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': f'Archived {updated_count} notifications',
            'count': updated_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to bulk archive notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def bulk_delete_notifications(request):
    """Bulk delete notifications (Admin/HR only)"""
    try:
        user = request.user
        
        if user.role not in ['admin', 'hr']:
            return Response({
                'success': False,
                'error': 'Permission denied. Only Admin and HR can perform bulk operations'
            }, status=status.HTTP_403_FORBIDDEN)
        
        notification_ids = request.data.get('notification_ids', [])
        delete_all_archived = request.data.get('delete_all_archived', False)
        
        if not notification_ids and not delete_all_archived:
            return Response({
                'success': False,
                'error': 'No operation specified. Provide notification_ids or delete_all_archived'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        deleted_count = 0
        
        if notification_ids:
            # Delete specific notifications
            deleted_count = ChatNotification.objects.filter(
                id__in=notification_ids
            ).count()
            ChatNotification.objects.filter(id__in=notification_ids).delete()
        
        elif delete_all_archived:
            # Delete all archived notifications
            deleted_count = ChatNotification.objects.filter(
                is_archived=True
            ).count()
            ChatNotification.objects.filter(is_archived=True).delete()
        
        # Log the bulk operation
        NotificationLog.objects.create(
            recipient=user,
            notification_type='bulk_delete_notifications',
            title=f'Bulk Delete Notifications',
            message=f'Deleted {deleted_count} notifications',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': f'Deleted {deleted_count} notifications',
            'count': deleted_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to bulk delete notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== NOTIFICATION DASHBOARD VIEW ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notification_dashboard(request):
    """Get comprehensive notification dashboard"""
    try:
        user = request.user
        
        # Get user preferences
        preferences, _ = UserNotificationPreference.objects.get_or_create(
            user=user,
            defaults={
                'enable_chat_notifications': True,
                'enable_message_notifications': True,
                'enable_group_chat_notifications': True,
                'enable_cross_department_notifications': True,
                'enable_system_notifications': True,
                'enable_announcements': True,
                'enable_updates': True,
                'enable_email_notifications': True,
                'enable_push_notifications': True,
                'enable_quiet_hours': False,
                'enable_sound': True,
                'sound_name': 'default',
                'email_frequency': 'instant'
            }
        )
        
        # Get chat notifications
        chat_notifications = ChatNotification.objects.filter(
            recipient=user,
            is_archived=False
        ).order_by('-created_at')[:10]
        
        # Get system notifications
        system_notifications = SystemNotification.objects.filter(
            is_active=True,
            start_date__lte=now()
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now())
        ).filter(
            Q(is_global=True) |
            Q(target_roles__contains=[user.role]) |
            Q(target_departments__contains=[user.department])
        ).distinct().order_by('-created_at')[:5]
        
        # Get statistics for the user
        user_stats = {
            'total_chat_notifications': ChatNotification.objects.filter(recipient=user).count(),
            'unread_chat_notifications': ChatNotification.objects.filter(
                recipient=user, 
                is_read=False,
                is_archived=False
            ).count(),
            'archived_chat_notifications': ChatNotification.objects.filter(
                recipient=user,
                is_archived=True
            ).count(),
            'total_system_notifications': system_notifications.count(),
            'notification_by_type': list(ChatNotification.objects.filter(recipient=user)
                                       .values('notification_type')
                                       .annotate(count=Count('id'))
                                       .order_by('-count'))
        }
        
        # Get recent notification activity
        today = now().date()
        week_ago = now() - timedelta(days=7)
        
        recent_activity = {
            'today': ChatNotification.objects.filter(
                recipient=user,
                created_at__date=today
            ).count(),
            'last_7_days': ChatNotification.objects.filter(
                recipient=user,
                created_at__gte=week_ago
            ).count(),
            'notification_trend': list(ChatNotification.objects.filter(
                recipient=user,
                created_at__gte=week_ago
            ).extra({'date': "date(created_at)"})
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date'))
        }
        
        # Check if user can receive notifications now (quiet hours)
        can_receive_now = preferences.can_send_notification_now()
        
        # Serialize data
        chat_serializer = ChatNotificationSerializer(chat_notifications, many=True)
        system_serializer = SystemNotificationSerializer(system_notifications, many=True)
        preferences_serializer = UserNotificationPreferenceSerializer(preferences)
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'role': user.role,
                'department': user.department
            },
            'preferences': preferences_serializer.data,
            'can_receive_notifications_now': can_receive_now,
            'statistics': user_stats,
            'recent_activity': recent_activity,
            'chat_notifications': {
                'count': chat_notifications.count(),
                'notifications': chat_serializer.data
            },
            'system_notifications': {
                'count': system_notifications.count(),
                'notifications': system_serializer.data
            },
            'quick_actions': {
                'mark_all_read_url': '/api/notifications/chat/mark-all-read/',
                'archive_all_read_url': '/api/notifications/chat/archive-all-read/',
                'update_preferences_url': '/api/notifications/preferences/update/'
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to load notification dashboard',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



# notificationApp/views.py - UPDATED

from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils.timezone import now
from datetime import datetime

from .models import (
    ChatNotification, SystemNotification,
    UserNotificationPreference, NotificationLog
)
from .serializers import (
    ChatNotificationSerializer, SystemNotificationSerializer,
    UserNotificationPreferenceSerializer, NotificationLogSerializer,
    CreateSystemNotificationSerializer, MarkNotificationsReadSerializer,
    DeleteNotificationsSerializer, UserProfileSerializer
)


# ==================== PROFILE VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """Get current user's profile information"""
    try:
        user = request.user
        serializer = UserProfileSerializer(user)
        
        # Determine what department information to show
        department_info = None
        if user.role == 'mentee' and user.department:
            department_info = {
                'type': 'single',
                'department': {
                    'id': user.department.id,
                    'name': user.department.name,
                    'status': user.department.status
                }
            }
        elif user.role == 'mentor' and user.departments.exists():
            departments = user.departments.all()
            department_info = {
                'type': 'multiple',
                'departments': [
                    {
                        'id': dept.id,
                        'name': dept.name,
                        'status': dept.status
                    }
                    for dept in departments
                ]
            }
        elif user.role in ['admin', 'hr']:
            department_info = {
                'type': 'none',
                'message': 'Admin/HR users are not assigned to specific departments'
            }
        
        profile_data = serializer.data
        profile_data['department_info'] = department_info
        
        return Response({
            'success': True,
            'profile': profile_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to fetch profile',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    """Update user profile (limited fields)"""
    try:
        user = request.user
        
        # Fields that can be updated by user
        allowed_fields = ['phone_number', 'email', 'full_name', 'availability_status']
        
        # Prevent role and department changes
        if 'role' in request.data:
            return Response({
                'success': False,
                'error': 'Role cannot be changed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if 'department' in request.data or 'departments' in request.data:
            return Response({
                'success': False,
                'error': 'Department(s) cannot be changed by user. Contact admin/HR.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prevent work mail address changes
        if 'work_mail_address' in request.data:
            return Response({
                'success': False,
                'error': 'Work email address cannot be changed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate email if provided
        if 'email' in request.data:
            from django.core.validators import validate_email
            try:
                validate_email(request.data['email'])
                # Check for duplicate email
                if CustomUser.objects.filter(email=request.data['email']).exclude(id=user.id).exists():
                    return Response({
                        'success': False,
                        'error': 'Email already exists'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except:
                return Response({
                    'success': False,
                    'error': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate phone if provided
        if 'phone_number' in request.data:
            # Check for duplicate phone
            if CustomUser.objects.filter(phone_number=request.data['phone_number']).exclude(id=user.id).exists():
                return Response({
                    'success': False,
                    'error': 'Phone number already exists'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update allowed fields
        for field in allowed_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
        
        user.save()
        
        serializer = UserProfileSerializer(user)
        
        return Response({
            'success': True,
            'message': 'Profile updated successfully',
            'profile': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to update profile',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== NOTIFICATION MANAGEMENT VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_notifications(request):
    """List all notifications for the authenticated user - FIXED VERSION"""
    try:
        user = request.user
        
        # Get query parameters
        notification_type = request.query_params.get('type')
        is_read = request.query_params.get('is_read')
        is_archived = request.query_params.get('is_archived', 'false').lower() == 'true'
        
        # Base queryset - user can only see their own notifications
        notifications = ChatNotification.objects.filter(recipient=user)
        
        # Admin/HR can see all notifications
        if user.role in ['admin', 'hr']:
            notifications = ChatNotification.objects.all()
        
        # Apply filters
        if notification_type:
            notifications = notifications.filter(notification_type=notification_type)
        
        if is_read:
            is_read_bool = is_read.lower() == 'true'
            notifications = notifications.filter(is_read=is_read_bool)
        
        # By default, don't show archived notifications
        if not is_archived:
            notifications = notifications.filter(is_archived=False)
        
        # Apply ordering
        notifications = notifications.order_by('-created_at')
        
        # Pagination - SAVE THE ORIGINAL QUERYSET BEFORE SLICING
        limit = request.query_params.get('limit', 20)
        try:
            limit = int(limit)
            if limit > 100:
                limit = 100
        except (ValueError, TypeError):
            limit = 20
        
        # Get the sliced queryset for response
        sliced_notifications = notifications[:limit]
        
        # Get counts FROM THE ORIGINAL QUERYSET (not the sliced one)
        total_count = notifications.count()
        unread_count = notifications.filter(is_read=False).count()
        
        # For archived count, we need the full queryset without is_archived filter
        if user.role in ['admin', 'hr']:
            archived_count = ChatNotification.objects.filter(is_archived=True).count()
        else:
            archived_count = ChatNotification.objects.filter(recipient=user, is_archived=True).count()
        
        serializer = ChatNotificationSerializer(sliced_notifications, many=True)
        
        return Response({
            'success': True,
            'count': len(sliced_notifications),  # Use len() for sliced queryset
            'total_count': total_count,
            'unread_count': unread_count,
            'archived_count': archived_count,
            'notifications': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in list_user_notifications: {str(e)}")
        print(f"Traceback: {error_trace}")
        
        return Response({
            'success': False,
            'error': 'Failed to fetch notifications',
            'detail': str(e),
            'traceback': error_trace if settings.DEBUG else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_notifications(request):
    """Delete notifications (soft delete by archiving)"""
    try:
        user = request.user
        serializer = DeleteNotificationsSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        notification_ids = data.get('notification_ids', [])
        delete_all = data.get('delete_all', False)
        delete_all_read = data.get('delete_all_read', False)
        delete_all_archived = data.get('delete_all_archived', False)
        
        deleted_count = 0
        
        if delete_all:
            # Delete all notifications (admin/HR can delete all, others only their own)
            if user.role in ['admin', 'hr']:
                deleted_count = ChatNotification.objects.filter(is_archived=False).count()
                ChatNotification.objects.filter(is_archived=False).update(
                    is_archived=True,
                    archived_at=now()
                )
            else:
                deleted_count = ChatNotification.objects.filter(recipient=user, is_archived=False).count()
                ChatNotification.objects.filter(recipient=user, is_archived=False).update(
                    is_archived=True,
                    archived_at=now()
                )
        
        elif delete_all_read:
            # Delete all read notifications
            if user.role in ['admin', 'hr']:
                deleted_count = ChatNotification.objects.filter(is_read=True, is_archived=False).count()
                ChatNotification.objects.filter(is_read=True, is_archived=False).update(
                    is_archived=True,
                    archived_at=now()
                )
            else:
                deleted_count = ChatNotification.objects.filter(recipient=user, is_read=True, is_archived=False).count()
                ChatNotification.objects.filter(recipient=user, is_read=True, is_archived=False).update(
                    is_archived=True,
                    archived_at=now()
                )
        
        elif delete_all_archived:
            # Permanently delete archived notifications (admin/HR only)
            if user.role not in ['admin', 'hr']:
                return Response({
                    'success': False,
                    'error': 'Only admin and HR can permanently delete archived notifications'
                }, status=status.HTTP_403_FORBIDDEN)
            
            deleted_count = ChatNotification.objects.filter(is_archived=True).count()
            ChatNotification.objects.filter(is_archived=True).delete()
        
        elif notification_ids:
            # Delete specific notifications
            for notification_id in notification_ids:
                try:
                    notification = ChatNotification.objects.get(id=notification_id)
                    
                    # Check permissions
                    if user.role not in ['admin', 'hr'] and notification.recipient != user:
                        continue
                    
                    if not notification.is_archived:
                        notification.delete_notification()
                        deleted_count += 1
                except ChatNotification.DoesNotExist:
                    continue
        
        else:
            return Response({
                'success': False,
                'error': 'No operation specified'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'message': f'Deleted {deleted_count} notifications',
            'count': deleted_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to delete notifications',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    """Mark a specific notification as read"""
    try:
        user = request.user
        
        notification = get_object_or_404(ChatNotification, id=notification_id)
        
        # Check permissions
        if user.role not in ['admin', 'hr'] and notification.recipient != user:
            return Response({
                'success': False,
                'error': 'You can only mark your own notifications as read'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if notification.is_read:
            return Response({
                'success': True,
                'message': 'Notification is already read'
            }, status=status.HTTP_200_OK)
        
        notification.mark_as_read()
        
        return Response({
            'success': True,
            'message': 'Notification marked as read',
            'notification_id': notification_id
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to mark notification as read',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    try:
        user = request.user
        
        if user.role in ['admin', 'hr']:
            # Admin/HR can mark all notifications as read
            updated_count = ChatNotification.objects.filter(
                is_read=False,
                is_archived=False
            ).update(
                is_read=True,
                read_at=now()
            )
        else:
            # Regular users can only mark their own notifications as read
            updated_count = ChatNotification.objects.filter(
                recipient=user,
                is_read=False,
                is_archived=False
            ).update(
                is_read=True,
                read_at=now()
            )
        
        return Response({
            'success': True,
            'message': f'Marked {updated_count} notifications as read',
            'count': updated_count
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to mark notifications as read',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






from django.contrib.auth.hashers import check_password, make_password

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change user password"""
    try:
        user = request.user
        
        # Validate required fields
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        if not current_password or not new_password or not confirm_password:
            return Response({
                'success': False,
                'error': 'All password fields are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify current password
        if not check_password(current_password, user.password):
            return Response({
                'success': False,
                'error': 'Current password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate new password
        if new_password != confirm_password:
            return Response({
                'success': False,
                'error': 'New passwords do not match'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_password) < 8:
            return Response({
                'success': False,
                'error': 'Password must be at least 8 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if new password is same as old
        if check_password(new_password, user.password):
            return Response({
                'success': False,
                'error': 'New password cannot be the same as current password'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        # Log the password change
        NotificationLog.objects.create(
            recipient=user,
            notification_type='password_changed',
            title='Password Changed',
            message='User changed their password',
            sent_via=['system'],
            success=True
        )
        
        return Response({
            'success': True,
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Failed to change password',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)