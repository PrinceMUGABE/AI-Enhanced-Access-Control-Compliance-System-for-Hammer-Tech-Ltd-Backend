from django.db.models import Q
from django.utils.timezone import now
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, NotificationPreference
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    MarkNotificationsReadSerializer,
    NotificationCountSerializer
)
from incidentApp.models import Incident
from complianceAuditApp.models import ComplianceAudit
from userApp.models import CustomUser
from userApp.utils import ActivityLogger

import logging

logger = logging.getLogger(__name__)


class NotificationListAPIView(generics.ListAPIView):
    """Get notifications for the current user"""
    
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get notifications based on user role"""
        user = self.request.user
        
        # Base queryset
        queryset = Notification.objects.filter(user=user)
        
        # Filter by read status
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            if is_read.lower() == 'true':
                queryset = queryset.filter(is_read=True)
            elif is_read.lower() == 'false':
                queryset = queryset.filter(is_read=False)
        
        # Filter by notification type
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Order by most recent first
        return queryset.order_by('-created_at')


class NotificationDetailAPIView(generics.RetrieveUpdateAPIView):
    """Get or update a specific notification"""
    
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    def perform_update(self, serializer):
        """Handle marking notification as read"""
        instance = serializer.instance
        is_read = self.request.data.get('is_read')
        
        if is_read is not None:
            if is_read:
                instance.mark_as_read()
            else:
                instance.mark_as_unread()
        
        # Update other fields if needed
        serializer.save()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notifications_read(request):
    """Mark one or more notifications as read"""
    try:
        user = request.user
        serializer = MarkNotificationsReadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notification_ids = serializer.validated_data.get('notification_ids', [])
        
        if notification_ids:
            # Mark specific notifications as read
            notifications = Notification.objects.filter(
                id__in=notification_ids,
                user=user
            )
            count = notifications.update(is_read=True, read_at=now())
        else:
            # Mark all notifications as read
            count = Notification.objects.filter(
                user=user,
                is_read=False
            ).update(is_read=True, read_at=now())
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='notifications_read',
            description=f'Marked {count} notifications as read',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": f"Marked {count} notification(s) as read",
            "count": count
        })
        
    except Exception as e:
        logger.error(f"Error marking notifications as read: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user"""
    try:
        user = request.user
        
        count = Notification.objects.filter(
            user=user,
            is_read=False
        ).update(is_read=True, read_at=now())
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='notifications_read_all',
            description=f'Marked all {count} notifications as read',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": f"Marked {count} notification(s) as read",
            "count": count
        })
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notification_counts(request):
    """Get notification counts for the current user"""
    try:
        user = request.user
        
        # Get counts
        total = Notification.objects.filter(user=user).count()
        unread = Notification.objects.filter(user=user, is_read=False).count()
        urgent = Notification.objects.filter(
            user=user,
            is_read=False,
            priority__in=['high', 'urgent']
        ).count()
        
        # Get counts by type
        by_type = Notification.objects.filter(
            user=user,
            is_read=False
        ).values('notification_type').annotate(count=models.Count('id'))
        
        return Response({
            "success": True,
            "counts": {
                "total": total,
                "unread": unread,
                "urgent": urgent
            },
            "by_type": by_type
        })
        
    except Exception as e:
        logger.error(f"Error getting notification counts: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_preferences(request):
    """Get notification preferences for the current user"""
    try:
        user = request.user
        
        preferences, created = NotificationPreference.objects.get_or_create(user=user)
        serializer = NotificationPreferenceSerializer(preferences)
        
        return Response({
            "success": True,
            "preferences": serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error getting notification preferences: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_preferences(request):
    """Update notification preferences for the current user"""
    try:
        user = request.user
        
        preferences, created = NotificationPreference.objects.get_or_create(user=user)
        serializer = NotificationPreferenceSerializer(
            preferences,
            data=request.data,
            partial=True
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer.save()
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='notification_preferences_update',
            description='Updated notification preferences',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": "Preferences updated successfully",
            "preferences": serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error updating notification preferences: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================
# NOTIFICATION CREATION UTILITIES
# ============================================================

class NotificationUtils:
    """Utility class for creating notifications"""
    
    @staticmethod
    def create_notification(user, notification_type, title, message, 
                           priority='medium', incident=None, audit=None,
                           action_link=None, action_text=None):
        """Create a notification for a user"""
        try:
            # Check if user has preferences and if this type is enabled
            try:
                prefs = NotificationPreference.objects.get(user=user)
                # Check if this notification type is enabled
                type_field = notification_type.replace('_', '_')  # Already in correct format
                if hasattr(prefs, type_field):
                    if not getattr(prefs, type_field):
                        return None
            except NotificationPreference.DoesNotExist:
                # If no preferences, default to enabled
                pass
            
            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                incident=incident,
                audit=audit,
                action_link=action_link,
                action_text=action_text
            )
            
            return notification
            
        except Exception as e:
            logger.error(f"Error creating notification for {user.email}: {str(e)}")
            return None
    
    @staticmethod
    def create_incident_assigned_notification(incident):
        """Create notification when an incident is assigned"""
        if not incident.assigned_to:
            return
        
        title = f"Incident Assigned: {incident.incident_number}"
        message = f"You have been assigned incident {incident.incident_number}: {incident.title}"
        priority = 'high' if incident.severity in ['critical', 'high'] else 'medium'
        action_link = f"/assigned-incidents"
        action_text = "View Incident"
        
        NotificationUtils.create_notification(
            user=incident.assigned_to,
            notification_type='incident_assigned',
            title=title,
            message=message,
            priority=priority,
            incident=incident,
            action_link=action_link,
            action_text=action_text
        )
    
    @staticmethod
    def create_incident_updated_notification(incident, updated_by, old_status, new_status):
        """Create notification when an incident is updated"""
        if not incident.assigned_to:
            return
        
        # Don't notify if the user updated their own incident
        if updated_by == incident.assigned_to:
            return
        
        title = f"Incident Updated: {incident.incident_number}"
        message = f"Incident {incident.incident_number} status changed from {old_status} to {new_status} by {updated_by.full_name}"
        action_link = f"/incidents/{incident.id}"
        action_text = "View Incident"
        
        NotificationUtils.create_notification(
            user=incident.assigned_to,
            notification_type='incident_updated',
            title=title,
            message=message,
            priority='medium',
            incident=incident,
            action_link=action_link,
            action_text=action_text
        )
    
    @staticmethod
    def create_sla_violation_notification(incident):
        """Create notification when an incident violates SLA"""
        if not incident.assigned_to:
            return
        
        title = f"SLA Violation: {incident.incident_number}"
        message = f"Incident {incident.incident_number} has exceeded its SLA deadline!"
        action_link = f"/incidents/{incident.id}"
        action_text = "View Incident"
        
        NotificationUtils.create_notification(
            user=incident.assigned_to,
            notification_type='sla_violation',
            title=title,
            message=message,
            priority='urgent',
            incident=incident,
            action_link=action_link,
            action_text=action_text
        )
    
    @staticmethod
    def create_audit_required_notification(user, incident):
        """Create notification when an incident requires an audit"""
        title = f"Audit Required: {incident.incident_number}"
        message = f"Incident {incident.incident_number} requires a compliance audit based on severity level."
        action_link = f"/compliance/create-audit?incident={incident.id}"
        action_text = "Create Audit"
        
        NotificationUtils.create_notification(
            user=user,
            notification_type='audit_required',
            title=title,
            message=message,
            priority='high',
            incident=incident,
            action_link=action_link,
            action_text=action_text
        )
    
    @staticmethod
    def create_audit_completed_notification(audit):
        """Create notification when an audit is completed"""
        # Notify the lead auditor
        if audit.lead_auditor:
            title = f"Audit Completed: {audit.audit_id}"
            message = f"Audit {audit.audit_id}: {audit.title} has been completed."
            action_link = f"/compliance/audits/{audit.id}"
            action_text = "View Audit"
            
            NotificationUtils.create_notification(
                user=audit.lead_auditor,
                notification_type='audit_completed',
                title=title,
                message=message,
                priority='medium',
                audit=audit,
                action_link=action_link,
                action_text=action_text
            )
        
        # Notify users who created the audit
        if audit.created_by and audit.created_by != audit.lead_auditor:
            title = f"Audit Completed: {audit.audit_id}"
            message = f"Audit {audit.audit_id}: {audit.title} has been completed."
            action_link = f"/compliance/audits/{audit.id}"
            action_text = "View Audit"
            
            NotificationUtils.create_notification(
                user=audit.created_by,
                notification_type='audit_completed',
                title=title,
                message=message,
                priority='medium',
                audit=audit,
                action_link=action_link,
                action_text=action_text
            )
    
    @staticmethod
    def create_finding_assigned_notification(finding):
        """Create notification when a finding is assigned"""
        if not finding.assigned_to:
            return
        
        title = f"Finding Assigned: {finding.title}"
        message = f"You have been assigned a finding: {finding.title} with risk level {finding.risk_level}"
        priority = 'high' if finding.risk_level in ['critical', 'high'] else 'medium'
        action_link = f"/compliance/findings/{finding.id}"
        action_text = "View Finding"
        
        NotificationUtils.create_notification(
            user=finding.assigned_to,
            notification_type='finding_assigned',
            title=title,
            message=message,
            priority=priority,
            action_link=action_link,
            action_text=action_text
        )


# ============================================================
# GENERATE NOTIFICATIONS FOR COMPLIANCE OFFICERS AND EMPLOYEES
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_notifications(request):
    """
    Generate notifications for the current user based on their role.
    This endpoint is called to populate the notification dropdown.
    """
    try:
        user = request.user
        logger.info(f"Generating notifications for user: {user.email}, role: {user.role}")
        
        # Get existing notifications for the user
        existing_notifications = Notification.objects.filter(user=user)
        
        # Check if we need to generate new notifications
        if user.role == 'compliance_officer':
            # For compliance officers: show incidents that need auditing
            generate_compliance_officer_notifications(user)
        elif user.role == 'employee':
            # For employees: show their assigned incidents
            generate_employee_notifications(user)
        elif user.role in ['admin', 'hr_manager', 'security_analyst']:
            # For others: show relevant notifications
            generate_general_notifications(user)
        
        # Get all notifications for the user
        notifications = Notification.objects.filter(user=user).order_by('-created_at')
        
        # Get unread count
        unread_count = notifications.filter(is_read=False).count()
        
        serializer = NotificationSerializer(notifications, many=True)
        
        return Response({
            "success": True,
            "notifications": serializer.data,
            "unread_count": unread_count,
            "total_count": notifications.count()
        })
        
    except Exception as e:
        logger.error(f"Error generating notifications: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def generate_compliance_officer_notifications(user):
    """
    Generate notifications for compliance officers.
    Shows incidents that need auditing (not yet linked to an audit).
    """
    try:
        # Get incidents assigned to the user that don't have compliance audits
        incidents_without_audit = Incident.objects.filter(
            assigned_to=user,
            status__in=['assigned', 'in_progress', 'pending', 'investigating']
        ).exclude(
            compliance_audits__isnull=False
        )
        
        # Also get high severity incidents in the user's department that need auditing
        if user.departments.exists():
            dept_incidents = Incident.objects.filter(
                department__in=user.departments.all(),
                severity__in=['critical', 'high'],
                status__in=['assigned', 'in_progress', 'pending', 'investigating']
            ).exclude(
                compliance_audits__isnull=False
            ).distinct()
            
            # Combine and deduplicate
            incidents = incidents_without_audit | dept_incidents
        else:
            incidents = incidents_without_audit
        
        # Create notifications for each incident
        for incident in incidents:
            # Check if notification already exists
            existing = Notification.objects.filter(
                user=user,
                notification_type='audit_required',
                incident=incident
            ).exists()
            
            if not existing:
                NotificationUtils.create_audit_required_notification(user, incident)
                
    except Exception as e:
        logger.error(f"Error generating compliance officer notifications: {str(e)}", exc_info=True)


def generate_employee_notifications(user):
    """
    Generate notifications for employees.
    Shows incidents assigned to them.
    """
    try:
        # Get incidents assigned to the employee
        incidents = Incident.objects.filter(
            assigned_to=user,
            status__in=['pending', 'investigating', 'assigned', 'in_progress']
        )
        
        for incident in incidents:
            # Check if notification already exists
            existing = Notification.objects.filter(
                user=user,
                incident=incident,
                notification_type='incident_assigned'
            ).exists()
            
            if not existing:
                # Create notification for assigned incident
                title = f"Incident Assigned: {incident.incident_number}"
                message = f"You have been assigned incident {incident.incident_number}: {incident.title}"
                priority = 'high' if incident.severity in ['critical', 'high'] else 'medium'
                action_link = "/assigned-incidents"
                action_text = "View Incident"
                
                NotificationUtils.create_notification(
                    user=user,
                    notification_type='incident_assigned',
                    title=title,
                    message=message,
                    priority=priority,
                    incident=incident,
                    action_link=action_link,
                    action_text=action_text
                )
                
                # Also check SLA violations
                if incident.is_overdue:
                    title = f"SLA Violation: {incident.incident_number}"
                    message = f"Incident {incident.incident_number} has exceeded its SLA deadline!"
                    priority = 'urgent'
                    
                    NotificationUtils.create_notification(
                        user=user,
                        notification_type='sla_violation',
                        title=title,
                        message=message,
                        priority=priority,
                        incident=incident,
                        action_link=action_link,
                        action_text=action_text
                    )
                    
    except Exception as e:
        logger.error(f"Error generating employee notifications: {str(e)}", exc_info=True)


def generate_general_notifications(user):
    """
    Generate general notifications for other roles.
    """
    try:
        # For admins: show critical incidents
        if user.is_admin:
            critical_incidents = Incident.objects.filter(
                severity='critical',
                status__in=['pending', 'investigating', 'assigned']
            ).order_by('-created_at')[:5]
            
            for incident in critical_incidents:
                existing = Notification.objects.filter(
                    user=user,
                    incident=incident,
                    notification_type='system_alert'
                ).exists()
                
                if not existing:
                    title = f"Critical Incident Alert: {incident.incident_number}"
                    message = f"Critical incident {incident.incident_number}: {incident.title} requires immediate attention!"
                    priority = 'urgent'
                    action_link = f"/incidents/{incident.id}"
                    action_text = "View Incident"
                    
                    NotificationUtils.create_notification(
                        user=user,
                        notification_type='system_alert',
                        title=title,
                        message=message,
                        priority=priority,
                        incident=incident,
                        action_link=action_link,
                        action_text=action_text
                    )
                    
    except Exception as e:
        logger.error(f"Error generating general notifications: {str(e)}", exc_info=True)



@api_view(['POST'])  # Changed from DELETE to POST
@permission_classes([IsAuthenticated])
def clear_all_notifications(request):
    """Clear all notifications for the current user"""
    try:
        user = request.user
        
        # Delete all notifications for this user
        count = Notification.objects.filter(user=user).count()
        Notification.objects.filter(user=user).delete()
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='notifications_cleared',
            description=f'Cleared all {count} notifications',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": f"Cleared {count} notification(s)",
            "count": count
        })
        
    except Exception as e:
        logger.error(f"Error clearing notifications: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])  # Changed from DELETE to POST
@permission_classes([IsAuthenticated])
def delete_notification(request, notification_id):
    """Delete a specific notification"""
    try:
        user = request.user
        
        notification = get_object_or_404(Notification, id=notification_id, user=user)
        notification.delete()
        
        return Response({
            "success": True,
            "message": "Notification deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_notification_generation(request):
    """
    Manually trigger notification generation for the current user.
    Useful for testing or immediate updates.
    """
    try:
        user = request.user
        logger.info(f"Manually triggering notification generation for user: {user.email}")
        
        from .tasks import generate_user_notifications
        
        # Generate notifications for this user
        count = generate_user_notifications(user)
        
        # Get updated notifications
        notifications = Notification.objects.filter(user=user).order_by('-created_at')
        unread_count = notifications.filter(is_read=False).count()
        
        serializer = NotificationSerializer(notifications, many=True)
        
        return Response({
            "success": True,
            "message": f"Generated {count} new notification(s)",
            "notifications": serializer.data,
            "unread_count": unread_count,
            "total_count": notifications.count(),
            "generated_count": count
        })
        
    except Exception as e:
        logger.error(f"Error triggering notification generation: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )






