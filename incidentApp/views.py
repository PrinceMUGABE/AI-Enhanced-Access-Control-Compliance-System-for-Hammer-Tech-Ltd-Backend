import os
import traceback
import logging
from datetime import timedelta, datetime
import json
import csv
import io

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, F
from django.utils.timezone import now
from django.http import FileResponse, HttpResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, generics, filters
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import pandas as pd

from .models import Incident, IncidentComment, IncidentAttachment, Report, ReportSchedule
from .serializers import (
    IncidentListSerializer, IncidentSLAUpdateSerializer, IncidentSerializer, 
    CreateIncidentFromLogSerializer, IncidentCommentSerializer, IncidentAttachmentSerializer,
    ManualIncidentAssignmentSerializer, ReportSerializer, ReportScheduleSerializer, 
    GenerateReportSerializer, UpdateAssignedIncidentStatusSerializer
)
from .utils import (
    IncidentUtils, ReportGenerator, DangerZoneAnalyzer,
    ExportUtils, NotificationUtils, get_incident_data_for_report,
    save_report_file
)
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department
from userApp.utils import ActivityLogger

# ============================================================
# NOTIFICATION INTEGRATION IMPORTS
# ============================================================
from notificationApp.models import Notification
from notificationApp.views import NotificationUtils as NotificationUtilsClass

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================

from datetime import date, datetime
import json

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles date and datetime objects"""
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)

def log_error(error_type, error_msg, exc_info=True):
    """Helper to log errors consistently"""
    logger.error(f"{error_type}: {error_msg}", exc_info=exc_info)
    print(f"\n❌ {error_type}: {error_msg}")
    if exc_info and logger.isEnabledFor(logging.DEBUG):
        traceback.print_exc()

def handle_exception(e, context="", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR):
    """Handle exceptions consistently"""
    error_type = type(e).__name__
    error_msg = str(e)
    full_context = f"{context}: " if context else ""
    
    log_error(f"{full_context}{error_type}", error_msg, exc_info=True)
    
    return Response(
        {
            "success": False,
            "error": f"An error occurred: {error_type}",
            "message": error_msg,
            "context": context
        },
        status=status_code
    )

def can_create_incident(user):
    """Check if user can create incidents"""
    try:
        return user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']
    except Exception as e:
        log_error("Permission check error", str(e))
        return False

def can_update_incident(user, incident):
    """Check if user can update incident"""
    try:
        if user.is_admin or user.is_hr:
            return True
        
        if user.role in ['security_analyst', 'compliance_officer']:
            if incident.assigned_to == user:
                return True
            if user.role == 'security_analyst' and incident.department in user.departments.all():
                return True
        
        if user.role == 'employee' and incident.log.user_email == user.email:
            return True
        
        return False
    except Exception as e:
        log_error("Update permission check error", str(e))
        return False

def can_comment_on_incident(user, incident):
    """Check if user can comment on incident"""
    try:
        if user.is_admin or user.is_hr:
            return True
        
        if incident.assigned_to == user or incident.created_by == user:
            return True
        
        if user.role == 'employee' and incident.log.user_email == user.email:
            return True
        
        if user.role == 'security_analyst' and incident.department in user.departments.all():
            return True
        
        return False
    except Exception as e:
        log_error("Comment permission check error", str(e))
        return False

def can_view_incident(user, incident):
    """Check if user can view incident"""
    try:
        if user.is_admin or user.is_hr:
            return True
        if incident.assigned_to == user or incident.created_by == user:
            return True
        if user.role == 'employee' and incident.log.user_email == user.email:
            return True
        if user.role == 'security_analyst' and incident.department in user.departments.all():
            return True
        if user.role == 'compliance_officer' and incident.severity in ['high', 'critical']:
            return True
        return False
    except Exception as e:
        log_error("View permission check error", str(e))
        return False

def can_generate_report_type(user, report_type):
    """Check if user can generate specific report type"""
    try:
        report_permissions = {
            'security': ['admin', 'hr_manager', 'security_analyst'],
            'compliance': ['admin', 'hr_manager', 'compliance_officer'],
            'access_control': ['admin', 'hr_manager'],
            'incident': ['admin', 'hr_manager', 'security_analyst', 'compliance_officer'],
            'user_activity': ['admin', 'hr_manager'],
            'ai_analytics': ['admin'],
            'custom': ['admin', 'hr_manager', 'security_analyst', 'compliance_officer', 'employee'],
        }
        
        allowed_roles = report_permissions.get(report_type, ['admin'])
        return user.role in allowed_roles
    except Exception as e:
        log_error("Report type permission check error", str(e))
        return False


# ============================================================
# NOTIFICATION HELPER FUNCTIONS
# ============================================================

def create_incident_notifications(incident, user, action_type='created', old_data=None):
    """
    Centralized function to create notifications for incident events
    """
    try:
        if action_type == 'created':
            # Notify assigned user
            if incident.assigned_to:
                NotificationUtilsClass.create_incident_assigned_notification(incident)
            
            # Notify security analysts for critical/high severity
            if incident.severity in ['critical', 'high']:
                security_analysts = CustomUser.objects.filter(
                    role='security_analyst',
                    is_active=True
                )
                for analyst in security_analysts:
                    if not incident.assigned_to or incident.assigned_to.id != analyst.id:
                        NotificationUtilsClass.create_notification(
                            user=analyst,
                            notification_type='system_alert',
                            title=f"Critical Incident Created: {incident.incident_number}",
                            message=f"Critical incident {incident.incident_number}: {incident.title} requires attention!",
                            priority='urgent' if incident.severity == 'critical' else 'high',
                            incident=incident,
                            action_link=f"/incidents/{incident.id}",
                            action_text="View Incident"
                        )
            
            # Notify compliance officers for critical incidents
            if incident.severity == 'critical':
                compliance_officers = CustomUser.objects.filter(
                    role='compliance_officer',
                    is_active=True
                )
                for officer in compliance_officers:
                    if not incident.assigned_to or incident.assigned_to.id != officer.id:
                        NotificationUtilsClass.create_audit_required_notification(officer, incident)
            
            # Notify creator's manager/HR if employee created
            if user and user.role == 'employee' and user.department:
                hr_users = CustomUser.objects.filter(
                    role='hr_manager',
                    is_active=True
                )
                for hr in hr_users:
                    NotificationUtilsClass.create_notification(
                        user=hr,
                        notification_type='system_alert',
                        title=f"New Incident Report: {incident.incident_number}",
                        message=f"Employee {user.full_name} reported incident {incident.incident_number}: {incident.title}",
                        priority='medium',
                        incident=incident,
                        action_link=f"/incidents/{incident.id}",
                        action_text="View Incident"
                    )
            
            # Notify log user if different from creator
            if incident.log and incident.log.user:
                log_user = incident.log.user
                if log_user != user and (not incident.assigned_to or incident.assigned_to.id != log_user.id):
                    NotificationUtilsClass.create_notification(
                        user=log_user,
                        notification_type='system_alert',
                        title=f"Security Alert: {incident.incident_number}",
                        message=f"A security incident has been created related to your account: {incident.title}",
                        priority='medium',
                        incident=incident,
                        action_link=f"/incidents/{incident.id}",
                        action_text="View Incident"
                    )
        
        elif action_type == 'updated':
            old_status = old_data.get('status') if old_data else None
            old_assigned_to = old_data.get('assigned_to') if old_data else None
            old_severity = old_data.get('severity') if old_data else None
            
            # Status change notifications
            if old_status and incident.status != old_status:
                # Notify assigned user
                if incident.assigned_to:
                    NotificationUtilsClass.create_incident_updated_notification(
                        incident, user, old_status, incident.status
                    )
                
                # If resolved
                if incident.status == 'resolved':
                    # Notify creator
                    if incident.created_by and incident.created_by != incident.assigned_to:
                        NotificationUtilsClass.create_notification(
                            user=incident.created_by,
                            notification_type='incident_resolved',
                            title=f"Incident Resolved: {incident.incident_number}",
                            message=f"Incident {incident.incident_number}: {incident.title} has been resolved by {user.full_name}",
                            priority='medium',
                            incident=incident,
                            action_link=f"/incidents/{incident.id}",
                            action_text="View Incident"
                        )
                    
                    # Notify log user
                    if incident.log and incident.log.user:
                        if incident.log.user != incident.assigned_to:
                            NotificationUtilsClass.create_notification(
                                user=incident.log.user,
                                notification_type='incident_resolved',
                                title=f"Incident Resolved: {incident.incident_number}",
                                message=f"Incident {incident.incident_number} related to your account has been resolved",
                                priority='medium',
                                incident=incident,
                                action_link=f"/incidents/{incident.id}",
                                action_text="View Incident"
                            )
                
                # If escalated
                elif incident.status == 'escalated':
                    admins = CustomUser.objects.filter(role='admin', is_active=True)
                    for admin in admins:
                        NotificationUtilsClass.create_notification(
                            user=admin,
                            notification_type='incident_escalated',
                            title=f"Incident Escalated: {incident.incident_number}",
                            message=f"Incident {incident.incident_number}: {incident.title} has been escalated by {user.full_name}",
                            priority='urgent',
                            incident=incident,
                            action_link=f"/incidents/{incident.id}",
                            action_text="View Incident"
                        )
            
            # Assignment change notifications
            if old_assigned_to and incident.assigned_to != old_assigned_to:
                if incident.assigned_to:
                    NotificationUtilsClass.create_incident_assigned_notification(incident)
                    
                    if old_assigned_to and old_assigned_to != incident.assigned_to:
                        NotificationUtilsClass.create_notification(
                            user=old_assigned_to,
                            notification_type='incident_updated',
                            title=f"Incident Reassigned: {incident.incident_number}",
                            message=f"Incident {incident.incident_number} has been reassigned from you to {incident.assigned_to.full_name}",
                            priority='medium',
                            incident=incident,
                            action_link=f"/incidents/{incident.id}",
                            action_text="View Incident"
                        )
            
            # Severity change notifications
            if old_severity and incident.severity != old_severity:
                if incident.assigned_to:
                    NotificationUtilsClass.create_notification(
                        user=incident.assigned_to,
                        notification_type='incident_updated',
                        title=f"Incident Severity Updated: {incident.incident_number}",
                        message=f"Incident {incident.incident_number} severity changed from {old_severity} to {incident.severity}",
                        priority='high' if incident.severity in ['critical', 'high'] else 'medium',
                        incident=incident,
                        action_link=f"/incidents/{incident.id}",
                        action_text="View Incident"
                    )
                
                # If severity increased to critical
                if incident.severity in ['critical', 'high'] and old_severity not in ['critical', 'high']:
                    security_analysts = CustomUser.objects.filter(
                        role='security_analyst',
                        is_active=True
                    )
                    for analyst in security_analysts:
                        if not incident.assigned_to or incident.assigned_to.id != analyst.id:
                            NotificationUtilsClass.create_notification(
                                user=analyst,
                                notification_type='system_alert',
                                title=f"Critical Severity Increase: {incident.incident_number}",
                                message=f"Incident {incident.incident_number} severity increased to {incident.severity}",
                                priority='urgent',
                                incident=incident,
                                action_link=f"/incidents/{incident.id}",
                                action_text="View Incident"
                            )
    
    except Exception as e:
        logger.error(f"Error creating incident notifications: {str(e)}", exc_info=True)


# ==================== INCIDENT VIEWS ====================

class IncidentListCreateAPIView(generics.ListCreateAPIView):
    """List and create incidents with notifications"""
    
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'severity', 'priority', 'danger_zone', 'department']
    search_fields = ['incident_number', 'title', 'description', 'log__user_email']
    ordering_fields = ['created_at', 'updated_at', 'severity', 'priority']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Get incidents based on user role"""
        try:
            user = self.request.user
            
            queryset = Incident.objects.select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).prefetch_related('comments', 'attachments')
            
            if user.is_admin:
                return queryset
            elif user.is_hr:
                return queryset
            elif user.role == 'security_analyst':
                if user.departments.exists():
                    return queryset.filter(
                        Q(department__in=user.departments.all()) |
                        Q(assigned_to=user) |
                        Q(created_by=user)
                    )
                else:
                    return queryset.filter(
                        Q(assigned_to=user) |
                        Q(created_by=user)
                    )
            elif user.role == 'compliance_officer':
                return queryset.filter(
                    Q(assigned_to=user) |
                    Q(created_by=user) |
                    Q(severity__in=['high', 'critical'])
                )
            elif user.role == 'employee':
                return queryset.filter(
                    Q(log__user_email=user.email) |
                    Q(assigned_to=user) |
                    Q(created_by=user)
                )
            else:
                return queryset.filter(
                    Q(assigned_to=user) |
                    Q(created_by=user)
                )
        except Exception as e:
            log_error("Get queryset error", str(e))
            return Incident.objects.none()
    
    def perform_create(self, serializer):
        """Create incident with notifications"""
        try:
            user = self.request.user
            
            if not can_create_incident(user):
                raise PermissionDenied("You don't have permission to create incidents.")
            
            incident = serializer.save()
            
            if not incident.sla_due_date:
                incident.sla_due_date = now() + timedelta(hours=24)
                incident.save()
            
            # ============================================================
            # CREATE NOTIFICATIONS
            # ============================================================
            create_incident_notifications(incident, user, 'created')
            
            # Log activity
            ActivityLogger.create_log(
                user=user,
                log_type='user_management',
                activity='incident_create',
                description=f'Created incident {incident.incident_number}: {incident.title}',
                request=self.request,
                response=None,
                is_success=True,
                target_user=incident.assigned_to
            )
            
        except PermissionDenied as e:
            raise e
        except Exception as e:
            log_error("Create incident error", str(e))
            raise
    
    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return handle_exception(e, "Creating incident")


class IncidentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an incident with notifications"""
    
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        try:
            view = IncidentListCreateAPIView()
            view.request = self.request
            return view.get_queryset()
        except Exception as e:
            log_error("Get queryset error", str(e))
            return Incident.objects.none()
    
    def get_object(self):
        try:
            obj = super().get_object()
            self.check_object_permissions(self.request, obj)
            return obj
        except Exception as e:
            log_error("Get object error", str(e))
            raise
    
    def perform_update(self, serializer):
        try:
            user = self.request.user
            instance = self.get_object()
            
            if not can_update_incident(user, instance):
                raise PermissionDenied("You don't have permission to update this incident.")
            
            # Track changes
            old_assigned_to = instance.assigned_to
            old_status = instance.status
            old_severity = instance.severity
            
            new_assigned_to_id = self.request.data.get('assigned_to')
            if new_assigned_to_id and new_assigned_to_id != getattr(old_assigned_to, 'id', None):
                try:
                    new_assigned_to = CustomUser.objects.get(
                        id=new_assigned_to_id,
                        role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
                    )
                except CustomUser.DoesNotExist:
                    raise ValidationError(f"User with ID {new_assigned_to_id} cannot be assigned incidents.")
            
            # Save updated instance
            updated_instance = serializer.save()
            
            # ============================================================
            # CREATE NOTIFICATIONS FOR UPDATES
            # ============================================================
            old_data = {
                'status': old_status,
                'assigned_to': old_assigned_to,
                'severity': old_severity
            }
            create_incident_notifications(updated_instance, user, 'updated', old_data)
            
            # Log status change
            if updated_instance.status != old_status:
                ActivityLogger.create_log(
                    user=user,
                    log_type='user_management',
                    activity='incident_status_update',
                    description=f'Changed incident {instance.incident_number} status from {old_status} to {updated_instance.status}',
                    request=self.request,
                    response=None,
                    is_success=True,
                    target_user=updated_instance.assigned_to
                )
            
            # Log assignment change
            if updated_instance.assigned_to != old_assigned_to:
                current_assigned = updated_instance.assigned_to
                activity = 'incident_reassignment' if old_assigned_to else 'incident_assignment'
                description = f'{activity.replace("_", " ").title()} incident {instance.incident_number} to {current_assigned.email if current_assigned else "unassigned"}'
                
                ActivityLogger.create_log(
                    user=user,
                    log_type='user_management',
                    activity=activity,
                    description=description,
                    request=self.request,
                    response=None,
                    is_success=True,
                    target_user=current_assigned
                )
            
        except (PermissionDenied, ValidationError) as e:
            raise e
        except Exception as e:
            log_error("Update incident error", str(e))
            raise
    
    def perform_destroy(self, instance):
        try:
            user = self.request.user
            
            if not user.is_admin:
                raise PermissionDenied("Only admin can delete incidents.")
            
            # Notify assigned user about deletion
            if instance.assigned_to:
                NotificationUtilsClass.create_notification(
                    user=instance.assigned_to,
                    notification_type='system_alert',
                    title=f"Incident Deleted: {instance.incident_number}",
                    message=f"Incident {instance.incident_number}: {instance.title} has been deleted by {user.full_name}",
                    priority='medium',
                    incident=instance,
                    action_link=None,
                    action_text=None
                )
            
            ActivityLogger.create_log(
                user=user,
                log_type='user_management',
                activity='incident_delete',
                description=f'Deleted incident {instance.incident_number}',
                request=self.request,
                response=None,
                is_success=True,
                target_user=instance.assigned_to
            )
            
            instance.delete()
            
        except PermissionDenied as e:
            raise e
        except Exception as e:
            log_error("Delete incident error", str(e))
            raise
    
    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except (PermissionDenied, ValidationError) as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return handle_exception(e, "Updating incident")
    
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return handle_exception(e, "Deleting incident")


@api_view(['POST'])
@permission_classes([IsAuthenticated])


def create_incident_from_log(request):
    """Create an incident from a user log with notifications"""
    try:
        print(f"Creating incident from log - User: {request.user.email}")
        
        serializer = CreateIncidentFromLogSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        if not can_create_incident(user):
            return Response(
                {"success": False, "error": "You don't have permission to create incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        incident = serializer.save()
        
        # Auto-assign department
        if incident.log and incident.log.user and incident.log.user.department:
            incident.department = incident.log.user.department
            incident.save()
        
        # Auto-assign to a user
        if not incident.assigned_to:
            assigned_user = IncidentUtils.assign_incident_to_user(incident)
            if assigned_user:
                incident.refresh_from_db()
        
        # ============================================================
        # CREATE NOTIFICATIONS
        # ============================================================
        create_incident_notifications(incident, user, 'created')
        
        # Additional notification for auto-created incidents
        if incident.severity in ['critical', 'high']:
            security_analysts = CustomUser.objects.filter(
                role='security_analyst',
                is_active=True
            )
            for analyst in security_analysts:
                if not incident.assigned_to or incident.assigned_to.id != analyst.id:
                    NotificationUtilsClass.create_notification(
                        user=analyst,
                        notification_type='system_alert',
                        title=f"Auto-created Incident: {incident.incident_number}",
                        message=f"Incident {incident.incident_number}: {incident.title} was auto-created from log analysis",
                        priority='urgent' if incident.severity == 'critical' else 'high',
                        incident=incident,
                        action_link=f"/incidents/{incident.id}",
                        action_text="View Incident"
                    )
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_create_from_log',
            description=f'Created incident {incident.incident_number} from log {incident.log.id}',
            request=request,
            response=None,
            is_success=True,
            target_user=incident.assigned_to
        )
        
        return Response(
            {
                "success": True,
                "message": "Incident created successfully",
                "incident": IncidentSerializer(incident).data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        return handle_exception(e, "Creating incident from log")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_incidents(request):
    """Get all incidents in the system (admin only)"""
    try:
        user = request.user
        
        if not (user.is_admin or user.role == 'security_analyst'):
            return Response(
                {"success": False, "error": "Only administrators can view all incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        incidents = Incident.objects.select_related(
            'log', 'assigned_to', 'created_by', 'department'
        ).prefetch_related('comments', 'attachments').order_by('-created_at')
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            incidents = incidents.filter(status=status_filter)
        
        severity_filter = request.query_params.get('severity')
        if severity_filter:
            incidents = incidents.filter(severity=severity_filter)
        
        priority_filter = request.query_params.get('priority')
        if priority_filter:
            incidents = incidents.filter(priority=priority_filter)
        
        department_filter = request.query_params.get('department')
        if department_filter:
            incidents = incidents.filter(department_id=department_filter)
        
        search_filter = request.query_params.get('search')
        if search_filter:
            incidents = incidents.filter(
                Q(title__icontains=search_filter) |
                Q(description__icontains=search_filter) |
                Q(incident_number__icontains=search_filter)
            )
        
        date_from = request.query_params.get('dateFrom')
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        
        date_to = request.query_params.get('dateTo')
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        total_count = incidents.count()
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_incidents = incidents[start_index:end_index]
        
        serializer = IncidentListSerializer(paginated_incidents, many=True)
        
        return Response({
            "success": True,
            "incidents": serializer.data,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1,
                "has_next": end_index < total_count,
                "has_previous": start_index > 0
            }
        })
    
    except Exception as e:
        return handle_exception(e, "Getting all incidents")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_incidents(request):
    """Get incidents based on user role"""
    try:
        user = request.user
        logger.info(f"Getting incidents for user: {user.email}")
        
        if user.is_admin or user.role == 'security_analyst':
            incidents = Incident.objects.all().select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).order_by('-created_at')
        else:
            incidents = Incident.objects.filter(
                Q(log__user_email=user.email) |
                Q(assigned_to=user) |
                Q(created_by=user)
            ).select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).order_by('-created_at')
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            incidents = incidents.filter(status=status_filter)
        
        severity_filter = request.query_params.get('severity')
        if severity_filter:
            incidents = incidents.filter(severity=severity_filter)
        
        priority_filter = request.query_params.get('priority')
        if priority_filter:
            incidents = incidents.filter(priority=priority_filter)
        
        assigned_to_filter = request.query_params.get('assigned_to')
        if assigned_to_filter:
            incidents = incidents.filter(assigned_to_id=assigned_to_filter)
        
        department_filter = request.query_params.get('department')
        if department_filter:
            incidents = incidents.filter(department_id=department_filter)
        
        search_filter = request.query_params.get('search')
        if search_filter:
            incidents = incidents.filter(
                Q(title__icontains=search_filter) |
                Q(description__icontains=search_filter) |
                Q(incident_number__icontains=search_filter)
            )
        
        date_from = request.query_params.get('dateFrom')
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        
        date_to = request.query_params.get('dateTo')
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        
        danger_zone = request.query_params.get('dangerZone')
        if danger_zone and danger_zone.lower() == 'true':
            incidents = incidents.filter(danger_zone=True)
        
        # Apply sorting
        sort_by = request.query_params.get('sortBy', 'created_at')
        sort_order = request.query_params.get('sortOrder', 'desc')
        sort_by_field = f'-{sort_by}' if sort_order == 'desc' else sort_by
        incidents = incidents.order_by(sort_by_field)
        
        total_count = incidents.count()
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_incidents = incidents[start_index:end_index]
        
        serializer = IncidentListSerializer(paginated_incidents, many=True)
        
        open_incidents = incidents.filter(status__in=['pending', 'investigating', 'assigned', 'in_progress']).count()
        resolved = incidents.filter(status__in=['resolved', 'closed']).count()
        
        return Response({
            "success": True,
            "incidents": serializer.data,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1,
                "has_next": end_index < total_count,
                "has_previous": start_index > 0
            },
            "statistics": {
                "total": total_count,
                "open": open_incidents,
                "resolved": resolved,
                "resolution_rate": round((resolved / total_count * 100) if total_count > 0 else 0, 1)
            }
        })
    
    except Exception as e:
        return handle_exception(e, "Getting user incidents")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_incident_comment(request, incident_id):
    """Add comment to incident with notification"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not can_comment_on_incident(user, incident):
            return Response(
                {"success": False, "error": "You don't have permission to comment on this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        data = request.data.copy()
        data['incident'] = incident.id
        
        serializer = IncidentCommentSerializer(
            data=data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comment = serializer.save()
        
        # ============================================================
        # NOTIFY ASSIGNED USER ABOUT COMMENT
        # ============================================================
        if incident.assigned_to and incident.assigned_to != user:
            NotificationUtilsClass.create_notification(
                user=incident.assigned_to,
                notification_type='incident_updated',
                title=f"New Comment on Incident: {incident.incident_number}",
                message=f"{user.full_name} added a comment to incident {incident.incident_number}: {incident.title}",
                priority='medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Comment"
            )
        
        # Notify creator if different from assignee and commenter
        if incident.created_by and incident.created_by != incident.assigned_to and incident.created_by != user:
            NotificationUtilsClass.create_notification(
                user=incident.created_by,
                notification_type='incident_updated',
                title=f"New Comment on Incident: {incident.incident_number}",
                message=f"{user.full_name} added a comment to incident {incident.incident_number}: {incident.title}",
                priority='medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Comment"
            )
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_comment',
            description=f'Added comment to incident {incident.incident_number}',
            request=request,
            response=None,
            is_success=True,
            target_user=incident.assigned_to
        )
        
        return Response(
            {
                "success": True,
                "message": "Comment added successfully",
                "comment": IncidentCommentSerializer(comment).data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        return handle_exception(e, "Adding incident comment")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_comments(request, incident_id):
    """Get all comments for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                incident.created_by == user or incident.log.user_email == user.email):
            return Response(
                {"success": False, "error": "You don't have permission to view comments for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        comments = incident.comments.all()
        serializer = IncidentCommentSerializer(comments, many=True)
        
        return Response({
            "success": True,
            "count": comments.count(),
            "comments": serializer.data
        })
    
    except Exception as e:
        return handle_exception(e, "Getting incident comments")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_incident_attachment(request, incident_id):
    """Upload attachment for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                incident.created_by == user):
            return Response(
                {"success": False, "error": "You don't have permission to upload attachments for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = IncidentAttachmentSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attachment = serializer.save(incident=incident)
        
        # Notify assigned user
        if incident.assigned_to and incident.assigned_to != user:
            NotificationUtilsClass.create_notification(
                user=incident.assigned_to,
                notification_type='incident_updated',
                title=f"New Attachment on Incident: {incident.incident_number}",
                message=f"{user.full_name} uploaded an attachment to incident {incident.incident_number}: {incident.title}",
                priority='medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Attachment"
            )
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_attachment_upload',
            description=f'Uploaded attachment {attachment.file_name} to incident {incident.incident_number}',
            request=request,
            response=None,
            is_success=True,
            target_user=incident.assigned_to
        )
        
        return Response(
            {
                "success": True,
                "message": "Attachment uploaded successfully",
                "attachment": IncidentAttachmentSerializer(attachment).data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        return handle_exception(e, "Uploading incident attachment")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manual_assign_incident(request):
    """Manually assign incident to a specific user with notifications"""
    try:
        user = request.user
        logger.info(f"Manual incident assignment requested by {user.email}")
        
        if not (user.is_admin or user.is_hr or user.role == 'security_analyst'):
            return Response(
                {"success": False, "error": "You don't have permission to assign incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ManualIncidentAssignmentSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        incident = serializer.save()
        
        old_assigned_to = getattr(incident, '_old_assigned_to', None)
        new_assigned_to = incident.assigned_to
        is_reassignment = old_assigned_to and new_assigned_to and old_assigned_to.id != new_assigned_to.id
        
        # ============================================================
        # CREATE NOTIFICATIONS
        # ============================================================
        
        # Notify new assignee
        if new_assigned_to:
            NotificationUtilsClass.create_incident_assigned_notification(incident)
        
        # Notify old assignee if reassigned
        if is_reassignment and old_assigned_to:
            NotificationUtilsClass.create_notification(
                user=old_assigned_to,
                notification_type='incident_updated',
                title=f"Incident Reassigned: {incident.incident_number}",
                message=f"Incident {incident.incident_number} has been reassigned from you to {new_assigned_to.full_name}",
                priority='medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Incident"
            )
        
        # Notify creator
        if incident.created_by and incident.created_by != new_assigned_to and incident.created_by != old_assigned_to:
            NotificationUtilsClass.create_notification(
                user=incident.created_by,
                notification_type='incident_updated',
                title=f"Incident Assigned: {incident.incident_number}",
                message=f"Incident {incident.incident_number} has been assigned to {new_assigned_to.full_name if new_assigned_to else 'unassigned'}",
                priority='medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Incident"
            )
        
        # Log activity
        if is_reassignment:
            activity_type = 'incident_reassignment'
            description = f'Reassigned incident {incident.incident_number} from {old_assigned_to.email} to {new_assigned_to.email}'
        else:
            activity_type = 'incident_manual_assignment'
            description = f'Manually assigned incident {incident.incident_number} to {new_assigned_to.email if new_assigned_to else "unassigned"}'
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity=activity_type,
            description=description,
            request=request,
            response=None,
            is_success=True,
            target_user=new_assigned_to
        )
        
        return Response({
            "success": True,
            "message": f"Incident {'reassigned' if is_reassignment else 'assigned'} successfully",
            "incident": IncidentSerializer(incident).data,
            "old_assigned_to": {
                "id": old_assigned_to.id if old_assigned_to else None,
                "email": old_assigned_to.email if old_assigned_to else None,
                "full_name": old_assigned_to.full_name if old_assigned_to else None
            } if is_reassignment else None,
            "new_assigned_to": {
                "id": new_assigned_to.id if new_assigned_to else None,
                "email": new_assigned_to.email if new_assigned_to else None,
                "full_name": new_assigned_to.full_name if new_assigned_to else None
            }
        })
    
    except Exception as e:
        return handle_exception(e, "Manually assigning incident")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_incident_sla(request, incident_id):
    """Update incident SLA due date with notification"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user):
            return Response(
                {"success": False, "error": "You don't have permission to update SLA for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        data = request.data.copy()
        data['incident_id'] = incident_id
        
        serializer = IncidentSLAUpdateSerializer(
            data=data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_due_date = incident.sla_due_date
        incident = serializer.save()
        
        # ============================================================
        # NOTIFY ASSIGNED USER ABOUT SLA UPDATE
        # ============================================================
        if incident.assigned_to and incident.assigned_to != user:
            NotificationUtilsClass.create_notification(
                user=incident.assigned_to,
                notification_type='sla_violation',
                title=f"SLA Updated: {incident.incident_number}",
                message=f"SLA for incident {incident.incident_number} has been updated to {incident.sla_due_date.strftime('%Y-%m-%d %H:%M')}",
                priority='high' if incident.is_overdue else 'medium',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Incident"
            )
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_sla_update',
            description=f'Updated SLA for incident {incident.incident_number} to {incident.sla_due_date}',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": "SLA updated successfully",
            "incident": IncidentSerializer(incident).data
        })
    
    except Exception as e:
        return handle_exception(e, "Updating incident SLA")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assignable_users(request, incident_id=None):
    """Get list of users who can be assigned incidents"""
    try:
        user = request.user
        logger.info(f"Getting assignable users for user: {user.email}, incident: {incident_id}")
        
        assignable_users = CustomUser.objects.filter(
            is_active=True,
            role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
        )
        
        if incident_id:
            try:
                incident = Incident.objects.get(id=incident_id)
                if incident.department:
                    if not (user.is_admin or user.is_hr):
                        assignable_users = assignable_users.filter(
                            Q(department=incident.department) |
                            Q(departments=incident.department) |
                            Q(role__in=['admin', 'hr_manager'])
                        ).distinct()
            except Incident.DoesNotExist:
                pass
        
        users_data = []
        for assignable_user in assignable_users:
            users_data.append({
                'id': assignable_user.id,
                'full_name': assignable_user.full_name,
                'email': assignable_user.email,
                'work_mail': assignable_user.work_mail_address,
                'role': assignable_user.role,
                'status': assignable_user.status,
                'availability_status': assignable_user.availability_status,
                'department': assignable_user.department.name if assignable_user.department else None,
                'departments': [dept.name for dept in assignable_user.departments.all()] if assignable_user.role == 'security_analyst' else [],
                'current_incident_count': assignable_user.assigned_incidents.filter(
                    status__in=['pending', 'investigating', 'assigned', 'in_progress']
                ).count()
            })
        
        users_data.sort(key=lambda x: (
            ['admin', 'hr_manager', 'security_analyst', 'compliance_officer'].index(x['role']),
            x['current_incident_count']
        ))
        
        return Response({
            "success": True,
            "count": len(users_data),
            "users": users_data
        })
    
    except Exception as e:
        return handle_exception(e, "Getting assignable users")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def escalate_incident(request, incident_id):
    """Escalate an incident to higher severity with notifications"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"success": False, "error": "You don't have permission to escalate this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reason = request.data.get('reason', '')
        old_severity = incident.severity
        old_priority = incident.priority
        
        # Escalate incident
        IncidentUtils.escalate_incident(incident, reason, user)
        
        # ============================================================
        # CREATE NOTIFICATIONS FOR ESCALATION
        # ============================================================
        
        # Notify assigned user
        if incident.assigned_to and incident.assigned_to != user:
            NotificationUtilsClass.create_notification(
                user=incident.assigned_to,
                notification_type='incident_escalated',
                title=f"Incident Escalated: {incident.incident_number}",
                message=f"Incident {incident.incident_number} has been escalated by {user.full_name}. Reason: {reason}",
                priority='urgent',
                incident=incident,
                action_link=f"/incidents/{incident.id}",
                action_text="View Incident"
            )
        
        # Notify admins
        admins = CustomUser.objects.filter(role='admin', is_active=True)
        for admin in admins:
            if not incident.assigned_to or incident.assigned_to.id != admin.id:
                NotificationUtilsClass.create_notification(
                    user=admin,
                    notification_type='incident_escalated',
                    title=f"Incident Escalated: {incident.incident_number}",
                    message=f"Incident {incident.incident_number}: {incident.title} has been escalated. Severity: {incident.severity}",
                    priority='urgent',
                    incident=incident,
                    action_link=f"/incidents/{incident.id}",
                    action_text="View Incident"
                )
        
        # Notify security analysts for critical escalations
        if incident.severity == 'critical':
            security_analysts = CustomUser.objects.filter(
                role='security_analyst',
                is_active=True
            )
            for analyst in security_analysts:
                if not incident.assigned_to or incident.assigned_to.id != analyst.id:
                    NotificationUtilsClass.create_notification(
                        user=analyst,
                        notification_type='system_alert',
                        title=f"Critical Escalation: {incident.incident_number}",
                        message=f"Incident {incident.incident_number} escalated to CRITICAL severity",
                        priority='urgent',
                        incident=incident,
                        action_link=f"/incidents/{incident.id}",
                        action_text="View Incident"
                    )
        
        serializer = IncidentSerializer(incident)
        
        return Response({
            "success": True,
            "message": "Incident escalated successfully",
            "incident": serializer.data
        })
    
    except Exception as e:
        return handle_exception(e, "Escalating incident")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_timeline(request, incident_id):
    """Get timeline of activities for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                incident.created_by == user or incident.log.user_email == user.email):
            return Response(
                {"success": False, "error": "You don't have permission to view timeline for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeline = [{
            'type': 'incident_created',
            'timestamp': incident.created_at,
            'user': incident.created_by.full_name if incident.created_by else 'System',
            'description': f'Incident {incident.incident_number} created: {incident.title}'
        }]
        
        if incident.assigned_at and incident.assigned_to:
            timeline.append({
                'type': 'incident_assigned',
                'timestamp': incident.assigned_at,
                'user': incident.assigned_to.full_name,
                'description': f'Incident assigned to {incident.assigned_to.full_name}'
            })
        
        status_logs = UserLog.objects.filter(
            Q(description__icontains=incident.incident_number) &
            Q(activity='incident_status_update')
        ).order_by('timestamp')
        
        for log in status_logs:
            timeline.append({
                'type': 'status_change',
                'timestamp': log.timestamp,
                'user': log.user_email,
                'description': log.description
            })
        
        comments = incident.comments.all().order_by('created_at')
        for comment in comments:
            timeline.append({
                'type': 'comment',
                'timestamp': comment.created_at,
                'user': comment.user.full_name,
                'description': f'Comment added: {comment.comment[:50]}...'
            })
        
        if incident.resolved_at:
            timeline.append({
                'type': 'incident_resolved',
                'timestamp': incident.resolved_at,
                'user': incident.assigned_to.full_name if incident.assigned_to else 'System',
                'description': f'Incident resolved: {incident.resolution_notes[:100] if incident.resolution_notes else "No resolution notes"}'
            })
        
        timeline.sort(key=lambda x: x['timestamp'])
        
        return Response({
            "success": True,
            "incident_number": incident.incident_number,
            "title": incident.title,
            "timeline": timeline
        })
    
    except Exception as e:
        return handle_exception(e, "Getting incident timeline")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_tracking(request, incident_id):
    """Get detailed tracking information for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not can_view_incident(user, incident):
            return Response(
                {"success": False, "error": "You don't have permission to view this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        tracking_data = IncidentUtils.get_incident_tracking_data(incident)
        
        recent_activities = UserLog.objects.filter(
            description__icontains=incident.incident_number
        ).order_by('-timestamp')[:10]
        
        comments_count = incident.comments.count()
        sla_status = IncidentUtils.track_incident_progress(incident)
        
        return Response({
            "success": True,
            "incident": IncidentSerializer(incident).data,
            "tracking": tracking_data,
            "sla_status": sla_status,
            "recent_activities": [
                {
                    'activity': log.activity,
                    'description': log.description,
                    'timestamp': log.timestamp,
                    'user': log.user_email
                }
                for log in recent_activities
            ],
            "comments_count": comments_count
        })
    
    except Exception as e:
        return handle_exception(e, "Getting incident tracking")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_statistics(request):
    """Get incident statistics for dashboard"""
    try:
        user = request.user
        timeframe = int(request.query_params.get('timeframe', 30))
        
        statistics = IncidentUtils.get_incident_statistics(user, timeframe)
        
        if statistics is None:
            statistics = {
                'total_incidents': 0,
                'open_incidents': 0,
                'resolved_incidents': 0,
                'closed_incidents': 0,
                'overdue_incidents': 0,
                'resolution_rate': 0,
                'avg_resolution_hours': 0,
                'by_status': {},
                'by_severity': {},
                'by_priority': {},
                'by_department': {},
                'timeframe_days': timeframe,
                'sla_violations': []
            }
        
        if user.is_admin or user.is_hr:
            try:
                sla_violations = IncidentUtils.check_sla_compliance()
                statistics['sla_violations'] = sla_violations if sla_violations is not None else []
            except Exception as e:
                logger.error(f"Error getting SLA violations: {str(e)}")
                statistics['sla_violations'] = []
        
        return Response({
            "success": True,
            "statistics": statistics
        })
    
    except ValueError as e:
        return Response(
            {"success": False, "error": "Invalid timeframe parameter."},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return handle_exception(e, "Getting incident statistics")


# ============================================================
# ADDITIONAL VIEWS - DANGER ZONE, EXPORTS, NOTIFICATIONS
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_danger_zone_logs(request):
    """Get logs that are in danger zone and need attention"""
    try:
        user = request.user
        logger.info(f"Getting danger zone logs for user: {user.email}")
        
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=24,
            risk_threshold=50
        )
        
        if not (user.is_admin or user.is_hr):
            danger_logs = [log for log in danger_logs if log['user_email'] == user.email]
        
        summary = DangerZoneAnalyzer.get_danger_zone_summary(timeframe_hours=24)
        
        return Response({
            "success": True,
            "count": len(danger_logs),
            "logs": danger_logs,
            "summary": summary
        })
    
    except Exception as e:
        return handle_exception(e, "Getting danger zone logs")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_attachments(request, incident_id):
    """Get all attachments for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                incident.created_by == user or incident.log.user_email == user.email):
            return Response(
                {"success": False, "error": "You don't have permission to view attachments for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        attachments = incident.attachments.all()
        serializer = IncidentAttachmentSerializer(attachments, many=True)
        
        return Response({
            "success": True,
            "count": attachments.count(),
            "attachments": serializer.data
        })
    
    except Exception as e:
        return handle_exception(e, "Getting incident attachments")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_danger_zone_summary(request):
    """Get summary of danger zone activities"""
    try:
        user = request.user
        
        if not (user.is_admin or user.is_hr):
            return Response(
                {"success": False, "error": "You don't have permission to view danger zone summary."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeframe = int(request.query_params.get('timeframe', 24))
        summary = DangerZoneAnalyzer.get_danger_zone_summary(timeframe_hours=timeframe)
        
        return Response({
            "success": True,
            "summary": summary
        })
    
    except Exception as e:
        return handle_exception(e, "Getting danger zone summary")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_incidents(request):
    """Export incidents to CSV or Excel"""
    try:
        user = request.user
        format_type = request.query_params.get('format', 'csv')
        include_comments = request.query_params.get('include_comments', 'false').lower() == 'true'
        
        logger.info(f"Exporting incidents - User: {user.email}, Format: {format_type}")
        
        if user.is_admin or user.is_hr:
            incidents = Incident.objects.all()
        elif user.role == 'security_analyst':
            if user.departments.exists():
                incidents = Incident.objects.filter(department__in=user.departments.all())
            else:
                incidents = Incident.objects.filter(assigned_to=user)
        elif user.role == 'employee':
            incidents = Incident.objects.filter(
                Q(log__user_email=user.email) |
                Q(assigned_to=user)
            )
        else:
            incidents = Incident.objects.filter(assigned_to=user)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            incidents = incidents.filter(status=status_filter)
        
        severity_filter = request.query_params.get('severity')
        if severity_filter:
            incidents = incidents.filter(severity=severity_filter)
        
        date_from = request.query_params.get('date_from')
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        
        date_to = request.query_params.get('date_to')
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        
        if format_type == 'excel':
            content = ExportUtils.export_incidents_to_excel(incidents, include_comments)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f'incidents_export_{now().strftime("%Y%m%d")}.xlsx'
        else:
            content = ExportUtils.export_incidents_to_csv(incidents, include_comments)
            content_type = 'text/csv'
            filename = f'incidents_export_{now().strftime("%Y%m%d")}.csv'
        
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='incidents_export',
            description=f'Exported {incidents.count()} incidents to {format_type.upper()}',
            request=request,
            response=None,
            is_success=True
        )
        
        return response
    
    except Exception as e:
        return handle_exception(e, "Exporting incidents")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_incident_notification(request, incident_id):
    """Send notification for an incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        if not (user.is_admin or user.is_hr or incident.assigned_to == user):
            return Response(
                {"success": False, "error": "You don't have permission to send notifications for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        notification_type = request.data.get('type', 'assignment')
        
        success = False
        message = ""
        
        if notification_type == 'sla_violation':
            success = NotificationUtils.send_sla_violation_notification(incident)
            message = "SLA violation notification sent"
        elif notification_type == 'resolution':
            success = NotificationUtils.send_resolution_notification(incident)
            message = "Resolution notification sent"
        else:
            success = NotificationUtils.send_incident_assignment_notification(incident)
            message = "Assignment notification sent"
        
        if success:
            return Response({"success": True, "message": message})
        else:
            return Response({"success": False, "message": "Failed to send notification"})
    
    except Exception as e:
        return handle_exception(e, "Sending incident notification")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_incident_detection(request):
    """Manually trigger incident detection from danger zone logs"""
    try:
        user = request.user
        logger.info(f"Triggering incident detection - User: {user.email}")
        
        if not (user.is_admin or user.is_hr):
            return Response(
                {"success": False, "error": "You don't have permission to trigger incident detection."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeframe = int(request.data.get('timeframe', 24))
        risk_threshold = int(request.data.get('risk_threshold', 60))
        limit = int(request.data.get('limit', 50))
        
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=timeframe,
            risk_threshold=risk_threshold
        )
        
        created_incidents = []
        skipped_incidents = []
        failed_incidents = []
        
        for log_data in danger_logs[:limit]:
            try:
                log = UserLog.objects.get(id=log_data['id'])
                
                if log.incidents.exists():
                    skipped_incidents.append(log.id)
                    continue
                
                risk_score = log_data['risk_score']
                
                if risk_score >= 85:
                    severity = 'critical'
                    priority = 'urgent'
                elif risk_score >= 70:
                    severity = 'high'
                    priority = 'high'
                elif risk_score >= 50:
                    severity = 'medium'
                    priority = 'medium'
                else:
                    severity = 'low'
                    priority = 'low'
                
                title = f"[{log_data['danger_level'].upper()}] {log.activity}: {log.user_email}"
                description = f"""Risk Score: {risk_score}
                Danger Level: {log_data['danger_level']}
                Activity: {log.activity}
                User: {log.user_email}
                Timestamp: {log.timestamp}
                
                Details: {log.description}
                
                Recommended Action: {log_data['recommended_action']}
                
                Original Log ID: {log.id}
                """
                
                incident = Incident.objects.create(
                    log=log,
                    title=title,
                    description=description,
                    severity=severity,
                    priority=priority,
                    risk_score=risk_score,
                    danger_zone=True,
                    status='pending',
                    created_by=user,
                    _request_user=user
                )
                
                incident.assign_department_based_on_user()
                
                assigned_user = IncidentUtils.assign_incident_to_user(incident)
                if assigned_user:
                    if not incident.department and assigned_user.department:
                        incident.department = assigned_user.department
                        incident.save()
                
                # ============================================================
                # CREATE NOTIFICATIONS FOR DETECTED INCIDENT
                # ============================================================
                create_incident_notifications(incident, user, 'created')
                
                created_incidents.append({
                    'incident_number': incident.incident_number,
                    'title': incident.title,
                    'severity': incident.severity,
                    'assigned_to': incident.assigned_to.email if incident.assigned_to else None,
                    'log_id': log.id
                })
                
            except UserLog.DoesNotExist:
                failed_incidents.append(log_data.get('id', 'unknown'))
                continue
            except Exception as e:
                logger.error(f"Error creating incident from log {log_data.get('id', 'unknown')}: {str(e)}")
                failed_incidents.append(log_data.get('id', 'unknown'))
                continue
        
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='incident_detection_triggered',
            description=f'Manually triggered incident detection. Created {len(created_incidents)} incidents from {len(danger_logs)} danger zone logs',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": "Incident detection completed",
            "summary": {
                "total_danger_logs": len(danger_logs),
                "logs_processed": min(limit, len(danger_logs)),
                "incidents_created": len(created_incidents),
                "incidents_skipped": len(skipped_incidents),
                "incidents_failed": len(failed_incidents)
            },
            "created_incidents": created_incidents[:10],
            "parameters": {
                "timeframe": timeframe,
                "risk_threshold": risk_threshold,
                "limit": limit
            }
        })
    
    except ValueError as e:
        return Response(
            {"success": False, "error": "Invalid parameter value", "message": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return handle_exception(e, "Triggering incident detection")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_assigned_incidents(request):
    """Check if current user has any assigned incidents"""
    try:
        user = request.user
        logger.info(f"Checking assigned incidents for user: {user.email}")
        
        assigned_incidents = Incident.objects.filter(
            assigned_to=user,
            status__in=['pending', 'investigating', 'assigned', 'in_progress', 'escalated']
        )
        
        total_assigned = assigned_incidents.count()
        pending_count = assigned_incidents.filter(status='pending').count()
        investigating_count = assigned_incidents.filter(status='investigating').count()
        assigned_count = assigned_incidents.filter(status='assigned').count()
        in_progress_count = assigned_incidents.filter(status='in_progress').count()
        escalated_count = assigned_incidents.filter(status='escalated').count()
        
        urgent_incidents = assigned_incidents.filter(
            Q(severity__in=['critical', 'high']) &
            Q(status__in=['pending', 'investigating', 'assigned'])
        ).count()
        
        has_assigned = total_assigned > 0
        
        return Response({
            "success": True,
            "has_assigned_incidents": has_assigned,
            "total_assigned": total_assigned,
            "by_status": {
                "pending": pending_count,
                "investigating": investigating_count,
                "assigned": assigned_count,
                "in_progress": in_progress_count,
                "escalated": escalated_count
            },
            "urgent": {
                "high_priority": urgent_incidents
            },
            "summary": {
                "user": {
                    "id": user.id,
                    "full_name": user.full_name,
                    "email": user.email,
                    "role": user.role
                },
                "last_checked": now().isoformat(),
                "message": f"You have {total_assigned} assigned incident{'s' if total_assigned != 1 else ''} to handle." if has_assigned else "You have no assigned incidents."
            }
        })
    
    except Exception as e:
        return handle_exception(e, "Checking assigned incidents")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_assigned_incident_status(request):
    """Update status of an incident assigned to current user"""
    try:
        user = request.user
        logger.info(f"Updating assigned incident status - User: {user.email}")
        
        serializer = UpdateAssignedIncidentStatusSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        incident = serializer.validated_data['incident']
        new_status = serializer.validated_data['new_status']
        resolution_notes = serializer.validated_data.get('resolution_notes', '')
        
        old_status = incident.status
        old_severity = incident.severity
        
        # Update incident
        incident.status = new_status
        if resolution_notes:
            incident.resolution_notes = resolution_notes
        if old_status != 'resolved' and new_status == 'resolved':
            incident.resolved_at = now()
        
        incident.check_sla_violation()
        incident.save()
        
        # ============================================================
        # CREATE NOTIFICATIONS FOR STATUS UPDATE
        # ============================================================
        old_data = {
            'status': old_status,
            'assigned_to': incident.assigned_to,
            'severity': old_severity
        }
        create_incident_notifications(incident, user, 'updated', old_data)
        
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_status_update',
            description=f'Updated status of assigned incident {incident.incident_number} from {old_status} to {new_status}',
            request=request,
            response=None,
            is_success=True
        )
        
        if new_status == 'resolved':
            try:
                NotificationUtils.send_resolution_notification(incident)
            except Exception as e:
                logger.error(f"Failed to send resolution notification: {str(e)}")
        
        updated_incident = IncidentSerializer(incident).data
        
        return Response({
            "success": True,
            "message": f"Incident status updated from {old_status} to {new_status}",
            "incident": updated_incident,
            "changes": {
                "old_status": old_status,
                "new_status": new_status,
                "updated_at": incident.updated_at,
                "resolved_at": incident.resolved_at if new_status == 'resolved' else None
            }
        })
    
    except Exception as e:
        return handle_exception(e, "Updating assigned incident status")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_assigned_incidents(request):
    """Get all incidents assigned to current user"""
    try:
        user = request.user
        logger.info(f"Getting assigned incidents for user: {user.email}")
        
        assigned_incidents = Incident.objects.filter(
            assigned_to=user
        ).select_related('log', 'department').order_by('-created_at')
        
        status_filter = request.query_params.get('status')
        if status_filter:
            assigned_incidents = assigned_incidents.filter(status=status_filter)
        
        severity_filter = request.query_params.get('severity')
        if severity_filter:
            assigned_incidents = assigned_incidents.filter(severity=severity_filter)
        
        priority_filter = request.query_params.get('priority')
        if priority_filter:
            assigned_incidents = assigned_incidents.filter(priority=priority_filter)
        
        danger_zone = request.query_params.get('dangerZone')
        if danger_zone and danger_zone.lower() == 'true':
            assigned_incidents = assigned_incidents.filter(danger_zone=True)
        
        search_filter = request.query_params.get('search')
        if search_filter:
            assigned_incidents = assigned_incidents.filter(
                Q(title__icontains=search_filter) |
                Q(description__icontains=search_filter) |
                Q(incident_number__icontains=search_filter)
            )
        
        sort_by = request.query_params.get('sortBy', 'created_at')
        sort_order = request.query_params.get('sortOrder', 'desc')
        sort_by_field = f'-{sort_by}' if sort_order == 'desc' else sort_by
        assigned_incidents = assigned_incidents.order_by(sort_by_field)
        
        total_count = assigned_incidents.count()
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_incidents = assigned_incidents[start_index:end_index]
        
        serializer = IncidentListSerializer(paginated_incidents, many=True)
        
        open_count = assigned_incidents.filter(
            status__in=['pending', 'investigating', 'assigned', 'in_progress']
        ).count()
        
        resolved_count = assigned_incidents.filter(
            status__in=['resolved', 'closed']
        ).count()
        
        from django.utils.timezone import now
        overdue_count = assigned_incidents.filter(
            sla_due_date__lt=now(),
            status__in=['pending', 'investigating', 'assigned', 'in_progress']
        ).count()
        
        return Response({
            "success": True,
            "incidents": serializer.data,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1,
                "has_next": end_index < total_count,
                "has_previous": start_index > 0
            },
            "statistics": {
                "total": total_count,
                "open": open_count,
                "resolved": resolved_count,
                "overdue": overdue_count,
                "resolution_rate": round((resolved_count / total_count * 100) if total_count > 0 else 0, 1)
            },
            "user_info": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role
            }
        })
    
    except Exception as e:
        logger.error(f"Error in get_my_assigned_incidents: {str(e)}", exc_info=True)
        return Response({
            "success": False,
            "error": str(e),
            "details": "An unexpected error occurred while fetching assigned incidents"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






# ============================================================
# REPORT VIEWS - ADD THESE FUNCTIONS
# ============================================================

class ReportListCreateAPIView(generics.ListCreateAPIView):
    """List and create reports"""
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['report_type', 'format', 'is_public']
    search_fields = ['title', 'description', 'report_number']
    ordering_fields = ['generated_at', 'download_count']
    ordering = ['-generated_at']
    
    def get_queryset(self):
        """Get reports based on user role"""
        try:
            user = self.request.user
            
            queryset = Report.objects.select_related('generated_by').prefetch_related('shared_with')
            
            if user.is_admin:
                return queryset
            elif user.is_hr:
                return queryset.filter(
                    Q(is_public=True) |
                    Q(shared_with=user) |
                    Q(generated_by=user)
                ).distinct()
            else:
                return queryset.filter(
                    Q(is_public=True) |
                    Q(shared_with=user) |
                    Q(generated_by=user)
                ).distinct()
        except Exception as e:
            log_error("Get reports queryset error", str(e))
            return Report.objects.none()
    
    def perform_create(self, serializer):
        """Create report - should be done through generate_report endpoint"""
        raise PermissionDenied("Use /api/reports/generate/ to create reports.")
    
    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            return handle_exception(e, "Listing reports")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """Generate a new report and send email"""
    try:
        logger.info(f"Generate report requested by {request.user.email}")
        
        serializer = GenerateReportSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.error(f"Report generation validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        data = serializer.validated_data
        
        # Check permissions for report type
        if not can_generate_report_type(user, data['report_type']):
            logger.warning(f"User {user.email} lacks permission for {data['report_type']} report")
            return Response(
                {"success": False, "error": "You don't have permission to generate this type of report."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Generate report
        report = create_report(user, data)
        
        if not report:
            logger.error("Failed to create report object")
            return Response(
                {"success": False, "error": "Failed to generate report."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Send email with report attached if requested
        send_email = data.get('send_email', True)
        if send_email:
            try:
                email_sent = send_report_email(report, user, data)
                if email_sent:
                    logger.info(f"Report email sent to {user.email}")
                else:
                    logger.warning(f"Failed to send report email to {user.email}")
            except Exception as e:
                logger.error(f"Email sending failed: {str(e)}")
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='report_generate',
            description=f'Generated report {report.report_number}: {report.title}',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response(
            {
                "success": True,
                "message": "Report generated successfully",
                "report": ReportSerializer(report, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        return handle_exception(e, "Generating report")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_report(request, report_id):
    """Download a report - Legacy endpoint for backward compatibility"""
    try:
        logger.info(f"Legacy download report endpoint called for report {report_id}")
        report = get_object_or_404(Report, id=report_id)
        
        return Response({
            "success": True,
            "message": "Use the file download endpoint for direct file access",
            "report": ReportSerializer(report, context={'request': request}).data,
            "download_url": f"/api/incidents/reports/{report.id}/file/"
        })
    
    except Exception as e:
        return handle_exception(e, "Downloading report (legacy endpoint)")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_report_file(request, report_id):
    """Download report file directly"""
    try:
        report = get_object_or_404(Report, id=report_id)
        user = request.user
        
        logger.info(f"Download report request - Report: {report.report_number}, User: {user.email}")
        
        # Check permissions
        if not (
            report.is_public or
            report.generated_by == user or
            user in report.shared_with.all() or
            user.is_admin or
            user.is_hr
        ):
            logger.warning(f"Permission denied for user {user.email} on report {report.id}")
            return Response(
                {"success": False, "error": "You don't have permission to download this report."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if file path exists
        if not report.file_path:
            logger.error(f"No file_path in database for report {report.id}")
            return Response(
                {"success": False, "error": "Report file not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get absolute path
        file_full_path = report.get_absolute_file_path()
        
        if not os.path.exists(file_full_path):
            logger.error(f"Report file not found at path: {file_full_path}")
            return Response(
                {"success": False, "error": "Report file not found on server."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        file_size = os.path.getsize(file_full_path)
        report.increment_download_count()
        
        file_extension = report.format.lower()
        content_types = {
            'pdf': 'application/pdf',
            'csv': 'text/csv',
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'json': 'application/json',
            'html': 'text/html'
        }
        
        content_type = content_types.get(file_extension, 'application/octet-stream')
        filename = f"{report.title.replace(' ', '_')}_{report.report_number}.{file_extension}"
        
        try:
            file = open(file_full_path, 'rb')
        except IOError as e:
            logger.error(f"Failed to open file: {str(e)}")
            return Response(
                {"success": False, "error": "Failed to open report file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        response = FileResponse(file, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = file_size
        
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='report_download',
            description=f'Downloaded report file: {report.report_number}',
            request=request,
            response=None,
            is_success=True
        )
        
        return response
    
    except Exception as e:
        return handle_exception(e, "Downloading report file")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_report_types(request):
    """Get available report types based on user role"""
    try:
        user = request.user
        
        all_report_types = [
            {'value': 'incident', 'label': 'Incident Report', 'description': 'Detailed incident analysis and statistics'},
            {'value': 'user_activity', 'label': 'User Activity Report', 'description': 'User login and activity patterns'},
            {'value': 'security', 'label': 'Security Report', 'description': 'Security metrics and threat analysis'},
            {'value': 'compliance', 'label': 'Compliance Report', 'description': 'Compliance status and audit findings'},
            {'value': 'access_control', 'label': 'Access Control Report', 'description': 'Access permissions and violations'},
            {'value': 'ai_analytics', 'label': 'AI Analytics Report', 'description': 'AI-powered behavioral analysis'},
            {'value': 'custom', 'label': 'Custom Report', 'description': 'Custom report with selected parameters'},
        ]
        
        role_permissions = {
            'admin': ['incident', 'user_activity', 'security', 'compliance', 'access_control', 'ai_analytics', 'custom'],
            'hr_manager': ['incident', 'user_activity', 'security', 'compliance', 'custom'],
            'security_analyst': ['incident', 'security', 'custom'],
            'compliance_officer': ['incident', 'compliance', 'custom'],
            'employee': ['incident', 'custom'],
        }
        
        allowed_types = role_permissions.get(user.role, ['custom'])
        available_types = [rt for rt in all_report_types if rt['value'] in allowed_types]
        
        return Response({
            "success": True,
            "report_types": available_types,
            "user_role": user.role
        })
    
    except Exception as e:
        return handle_exception(e, "Getting report types")


# ============================================================
# REPORT HELPER FUNCTIONS
# ============================================================

def send_report_email(report, user, data):
    """Send email with report attached"""
    try:
        file_path = report.get_absolute_file_path()
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Report file not found: {file_path}")
            return False
        
        subject = f"Hammer Tech - Generated Report: {report.title}"
        
        body = f"""
        Dear {user.full_name},
        
        Your report has been successfully generated.
        
        Report Details:
        • Report Number: {report.report_number}
        • Title: {report.title}
        • Type: {report.get_report_type_display()}
        • Format: {report.get_format_display()}
        • Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
        
        Description:
        {report.description or 'No description provided'}
        
        The report file is attached to this email. You can also download it from the system.
        
        Best regards,
        Hammer Tech AI-Enhanced Access Control & Compliance System
        """
        
        recipients = []
        
        if user.email:
            recipients.append(user.email)
        
        if data.get('email_recipients'):
            additional_emails = data['email_recipients'].split(',')
            for email in additional_emails:
                email = email.strip()
                if email and '@' in email:
                    recipients.append(email)
        
        recipients = list(set(recipients))
        
        if not recipients:
            logger.warning("No recipients specified for report email")
            return False
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        
        try:
            with open(file_path, 'rb') as file:
                file_content = file.read()
                filename = f"{report.title.replace(' ', '_')}_{report.report_number}.{report.format}"
                
                content_types = {
                    'pdf': 'application/pdf',
                    'csv': 'text/csv',
                    'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'json': 'application/json',
                    'html': 'text/html'
                }
                
                content_type = content_types.get(report.format.lower(), 'application/octet-stream')
                email.attach(filename, file_content, content_type)
        except IOError as e:
            logger.error(f"Failed to attach report file: {str(e)}")
            email.body += f"\n\nNote: The report file could not be attached. Please download it from the system."
        
        email.send()
        
        report.metadata = report.metadata or {}
        report.metadata['email_sent'] = True
        report.metadata['email_recipients'] = recipients
        report.metadata['email_sent_at'] = now().isoformat()
        report.save()
        
        return True
        
    except Exception as e:
        logger.error(f"Error sending report email: {str(e)}", exc_info=True)
        return False


def create_report(user, data):
    """Create report based on parameters"""
    try:
        report_type = data['report_type']
        title = data.get('title', f"{report_type.title()} Report")
        description = data.get('description', f"Generated {report_type} report")
        format_type = data['format']
        is_public = data.get('is_public', False)
        shared_with = data.get('shared_with', [])
        
        parameters = {}
        for key, value in data.items():
            if value is None:
                parameters[key] = None
            elif isinstance(value, (date, datetime)):
                parameters[key] = value.isoformat()
            elif isinstance(value, bool):
                parameters[key] = value
            elif isinstance(value, (int, float)):
                parameters[key] = value
            else:
                parameters[key] = str(value) if value else None
        
        report = Report.objects.create(
            title=title,
            description=description,
            report_type=report_type,
            format=format_type,
            generated_by=user,
            parameters=parameters,
            is_public=is_public
        )
        
        if shared_with:
            report.shared_with.set(shared_with)
        
        report_generator = ReportGenerator()
        
        if report_type == 'incident':
            report_data = get_incident_data_for_report(data)
        elif report_type == 'user_activity':
            report_data = get_user_activity_report_data(data)
        elif report_type == 'security':
            report_data = get_security_report_data(data)
        elif report_type == 'compliance':
            report_data = get_compliance_report_data(data)
        else:
            report_data = get_general_report_data(data)
        
        content = None
        if format_type == 'pdf':
            content = report_generator.generate_pdf_report(
                report_data, report_type, title, description
            )
        elif format_type == 'csv':
            content = report_generator.generate_csv_report(report_data, report_type)
        elif format_type == 'excel':
            content = report_generator.generate_excel_report(report_data, report_type)
        elif format_type == 'json':
            content = report_generator.generate_json_report(report_data, report_type)
        else:
            content = report_generator.generate_html_report(report_data, report_type)
        
        if content:
            save_report_file(report, content, format_type)
        
        return report
    
    except Exception as e:
        log_error("Create report error", str(e))
        return None


def get_user_activity_report_data(parameters):
    """Get data for user activity report"""
    try:
        queryset = UserLog.objects.all()
        
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        user_id = parameters.get('user_id')
        activity = parameters.get('activity')
        
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)
        if user_id:
            queryset = queryset.filter(user__id=user_id)
        if activity:
            queryset = queryset.filter(activity=activity)
        
        total = queryset.count()
        by_activity = list(queryset.values('activity').annotate(count=Count('id')).order_by('-count')[:10])
        by_user = list(queryset.values('user_email').annotate(count=Count('id')).order_by('-count')[:10])
        
        successful = queryset.filter(is_success=True).count()
        failed = queryset.filter(is_success=False).count()
        recent = queryset.order_by('-timestamp')[:20]
        
        return {
            'total_activities': total,
            'successful_activities': successful,
            'failed_activities': failed,
            'success_rate': round((successful / total * 100) if total > 0 else 0, 1),
            'by_activity': by_activity,
            'by_user': by_user,
            'recent_activities': [
                {
                    'id': log.id,
                    'activity': log.activity,
                    'user_email': log.user_email,
                    'timestamp': log.timestamp,
                    'is_success': log.is_success,
                    'endpoint': log.endpoint,
                    'ip_address': log.ip_address
                }
                for log in recent
            ],
            'filters_applied': parameters
        }
    except Exception as e:
        log_error("Getting user activity report data", str(e))
        return {}


def get_security_report_data(parameters):
    """Get data for security report"""
    try:
        incidents = Incident.objects.all()
        
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        severity = parameters.get('severity')
        
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        if severity:
            incidents = incidents.filter(severity=severity)
        
        total_incidents = incidents.count()
        critical_incidents = incidents.filter(severity='critical').count()
        high_incidents = incidents.filter(severity='high').count()
        
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(timeframe_hours=24, risk_threshold=60)
        
        user_risks = []
        users = CustomUser.objects.all()
        for user in users[:10]:
            user_incidents = incidents.filter(log__user_email=user.email)
            user_logs = UserLog.objects.filter(user_email=user.email, is_success=False).count()
            
            user_risks.append({
                'user': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'incident_count': user_incidents.count(),
                'failed_logins': user_logs,
                'risk_level': 'high' if user_incidents.filter(severity__in=['critical', 'high']).exists() else 'medium' if user_incidents.exists() else 'low'
            })
        
        return {
            'total_incidents': total_incidents,
            'critical_incidents': critical_incidents,
            'high_incidents': high_incidents,
            'danger_zone_logs_count': len(danger_logs),
            'user_risk_analysis': user_risks,
            'top_threats': [
                {
                    'type': 'Failed Logins',
                    'count': UserLog.objects.filter(activity='login_failed', is_success=False).count(),
                    'trend': 'increasing'
                },
                {
                    'type': 'Unauthorized Access',
                    'count': UserLog.objects.filter(activity='access_denied').count(),
                    'trend': 'stable'
                },
                {
                    'type': 'Policy Violations',
                    'count': incidents.filter(priority='high').count(),
                    'trend': 'decreasing'
                }
            ],
            'filters_applied': parameters
        }
    except Exception as e:
        log_error("Getting security report data", str(e))
        return {}


def get_compliance_report_data(parameters):
    """Get data for compliance report"""
    try:
        incidents = Incident.objects.filter(severity__in=['high', 'critical'])
        
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        
        total_compliance_issues = incidents.count()
        resolved_issues = incidents.filter(status__in=['resolved', 'closed']).count()
        pending_issues = incidents.filter(status__in=['pending', 'investigating', 'assigned', 'in_progress']).count()
        
        sla_violations = incidents.filter(sla_violated=True).count()
        sla_compliance_rate = round(((incidents.count() - sla_violations) / incidents.count() * 100) if incidents.count() > 0 else 100, 1)
        
        policy_violations = incidents.filter(title__icontains='policy').count()
        recent_compliance = incidents.order_by('-created_at')[:10]
        
        return {
            'total_compliance_issues': total_compliance_issues,
            'resolved_issues': resolved_issues,
            'pending_issues': pending_issues,
            'resolution_rate': round((resolved_issues / total_compliance_issues * 100) if total_compliance_issues > 0 else 0, 1),
            'sla_violations': sla_violations,
            'sla_compliance_rate': sla_compliance_rate,
            'policy_violations': policy_violations,
            'recent_compliance_incidents': [
                {
                    'incident_number': inc.incident_number,
                    'title': inc.title,
                    'severity': inc.severity,
                    'status': inc.status,
                    'created_at': inc.created_at,
                    'sla_status': 'violated' if inc.sla_violated else 'compliant'
                }
                for inc in recent_compliance
            ],
            'compliance_summary': {
                'data_protection': {
                    'status': 'compliant',
                    'issues': incidents.filter(description__icontains='data').count(),
                    'last_audit': (now() - timedelta(days=30)).strftime('%Y-%m-%d')
                },
                'access_control': {
                    'status': 'needs_attention',
                    'issues': incidents.filter(description__icontains='access').count(),
                    'last_audit': (now() - timedelta(days=15)).strftime('%Y-%m-%d')
                },
                'audit_trail': {
                    'status': 'compliant',
                    'issues': 0,
                    'last_audit': (now() - timedelta(days=7)).strftime('%Y-%m-%d')
                }
            },
            'filters_applied': parameters
        }
    except Exception as e:
        log_error("Getting compliance report data", str(e))
        return {}


def get_general_report_data(parameters):
    """Get data for general/custom report"""
    try:
        report_data = {
            'summary': {},
            'incidents': {},
            'user_activity': {},
            'compliance': {},
            'generated_at': now().isoformat()
        }
        
        if parameters.get('include_incidents', True):
            report_data['incidents'] = get_incident_report_data(parameters)
        
        if parameters.get('include_user_activity', False):
            report_data['user_activity'] = get_user_activity_report_data(parameters)
        
        if parameters.get('include_compliance', False):
            report_data['compliance'] = get_compliance_report_data(parameters)
        
        report_data['summary'] = {
            'report_type': 'custom',
            'generated_at': now().isoformat(),
            'time_period': f"{parameters.get('date_from', 'Start')} to {parameters.get('date_to', 'End')}",
            'data_points': len(report_data['incidents'].get('recent_incidents', [])) +
                          len(report_data['user_activity'].get('recent_activities', [])) +
                          len(report_data['compliance'].get('recent_compliance_incidents', [])),
            'filters_applied': parameters
        }
        
        return report_data
    except Exception as e:
        log_error("Getting general report data", str(e))
        return {}


def get_incident_report_data(parameters):
    """Get data for incident report"""
    try:
        queryset = Incident.objects.all()
        
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        severity = parameters.get('severity')
        status = parameters.get('status')
        department_id = parameters.get('department_id')
        user_id = parameters.get('user_id')
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        if severity:
            queryset = queryset.filter(severity=severity)
        if status:
            queryset = queryset.filter(status=status)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if user_id:
            queryset = queryset.filter(
                Q(log__user__id=user_id) |
                Q(assigned_to_id=user_id) |
                Q(created_by_id=user_id)
            )
        
        total = queryset.count()
        by_status = list(queryset.values('status').annotate(count=Count('id')))
        by_severity = list(queryset.values('severity').annotate(count=Count('id')))
        by_department = list(queryset.values('department__name').annotate(count=Count('id')))
        
        resolved = queryset.filter(status__in=['resolved', 'closed'])
        avg_resolution_time = resolved.aggregate(
            avg_time=Avg(F('resolved_at') - F('created_at'))
        )['avg_time']
        
        recent = queryset.order_by('-created_at')[:10]
        
        return {
            'total_incidents': total,
            'open_incidents': queryset.filter(status__in=['pending', 'investigating', 'assigned', 'in_progress']).count(),
            'resolved_incidents': resolved.count(),
            'by_status': by_status,
            'by_severity': by_severity,
            'by_department': by_department,
            'avg_resolution_time': avg_resolution_time.total_seconds() / 3600 if avg_resolution_time else 0,
            'resolution_rate': round((resolved.count() / total * 100) if total > 0 else 0, 1),
            'recent_incidents': [
                {
                    'incident_number': inc.incident_number,
                    'title': inc.title,
                    'status': inc.status,
                    'severity': inc.severity,
                    'created_at': inc.created_at,
                    'assigned_to': inc.assigned_to.full_name if inc.assigned_to else 'Unassigned'
                }
                for inc in recent
            ],
            'filters_applied': parameters
        }
    except Exception as e:
        log_error("Getting incident report data", str(e))
        return {}