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

logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================

from datetime import date, datetime
import json

# Also add this custom JSON encoder class:
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

# ==================== INCIDENT VIEWS ====================

class IncidentListCreateAPIView(generics.ListCreateAPIView):
    """List and create incidents"""
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
            
            # Build base queryset
            queryset = Incident.objects.select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).prefetch_related('comments', 'attachments')
            
            # Apply role-based filtering
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
        """Create incident with NO auto-assignment"""
        try:
            user = self.request.user
            
            # Check if user can create incidents
            if not can_create_incident(user):
                raise PermissionDenied("You don't have permission to create incidents.")
            
            # Save incident without auto-assignment
            incident = serializer.save()
            
            # Set default SLA (24 hours) if not provided
            if not incident.sla_due_date:
                incident.sla_due_date = now() + timedelta(hours=24)
                incident.save()
            
            # Log activity
            ActivityLogger.create_log(
                user=user,
                log_type='user_management',
                activity='incident_create',
                description=f'Created incident {incident.incident_number}: {incident.title}. Status: {incident.status}. Assigned to: {incident.assigned_to.email if incident.assigned_to else "Unassigned"}',
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
        """Override create to handle exceptions"""
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
    """Retrieve, update, or delete an incident"""
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        try:
            # Use the same filtering logic as list view
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
            
            # Check update permissions
            if not can_update_incident(user, instance):
                raise PermissionDenied("You don't have permission to update this incident.")
            
            # Track changes before saving
            old_assigned_to = instance.assigned_to
            old_status = instance.status
            
            # Get the new assigned_to from request data
            new_assigned_to_id = self.request.data.get('assigned_to')
            
            # If reassigning to a new user
            if new_assigned_to_id and new_assigned_to_id != getattr(old_assigned_to, 'id', None):
                try:
                    new_assigned_to = CustomUser.objects.get(
                        id=new_assigned_to_id,
                        role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
                    )
                    # Log reassignment before saving
                    ActivityLogger.create_log(
                        user=user,
                        log_type='user_management',
                        activity='incident_reassignment',
                        description=f'Reassigned incident {instance.incident_number} from {old_assigned_to.email if old_assigned_to else "unassigned"} to {new_assigned_to.email}',
                        request=self.request,
                        response=None,
                        is_success=True,
                        target_user=new_assigned_to
                    )
                except CustomUser.DoesNotExist:
                    raise ValidationError(f"User with ID {new_assigned_to_id} cannot be assigned incidents.")
            
            # Save the updated instance
            updated_instance = serializer.save()
            
            # Log status change if status changed
            if 'status' in serializer.validated_data and serializer.validated_data['status'] != old_status:
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
            
            # Log assignment change if assignment changed
            if 'assigned_to' in serializer.validated_data:
                current_assigned = updated_instance.assigned_to
                if current_assigned != old_assigned_to:
                    # This handles both assignment and reassignment
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
            
            # Only admin can delete incidents
            if not user.is_admin:
                raise PermissionDenied("Only admin can delete incidents.")
            
            # Log deletion
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
        """Override update to handle exceptions"""
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
        """Override destroy to handle exceptions"""
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
    """Create an incident from a user log"""
    try:
        print(f"Creating incident from log - User by: {request.user.email} with data: \n{request.data}\n")
        
        serializer = CreateIncidentFromLogSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            print(f"Serializer validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check permissions
        user = request.user
        if not can_create_incident(user):
            print(f"User {user.email} lacks permission to create incidents")
            return Response(
                {"success": False, "error": "You don't have permission to create incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        incident = serializer.save()
        
        # Auto-assign department based on the log's user
        if incident.log and incident.log.user:
            if incident.log.user.department:
                incident.department = incident.log.user.department
                incident.save()
                print(f"Auto-assigned department {incident.department.name} from log user")
        
        # Auto-assign to a user if not already assigned
        if not incident.assigned_to:
            assigned_user = IncidentUtils.assign_incident_to_user(incident)
            if assigned_user:
                print(f"Auto-assigned to {assigned_user.email}")
        
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
        
        print(f"Successfully created incident {incident.incident_number}")
        return Response(
            {
                "success": True,
                "message": "Incident created successfully",
                "incident": IncidentSerializer(incident).data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        print(f"Error creating incident from log: {str(e)}")
        return handle_exception(e, "Creating incident from log")
    
    
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_incidents(request):
    """Get all incidents in the system (admin only)"""
    try:
        user = request.user
        
        # Check if user is admin
        if not user.is_admin or user.role != 'security_analyst':
            return Response(
                {"success": False, "error": "Only administrators can view all incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        logger.info(f"Admin {user.email} fetching all incidents")
        
        # Get all incidents
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
    """Get incidents based on user role - ADMIN can see all incidents"""
    try:
        user = request.user
        logger.info(f"Getting incidents for user: {user.email} with role {user.role}")
        
        # For admin users, get ALL incidents (not just their own)
        if user.is_admin or user.role == 'security_analyst':
            incidents = Incident.objects.all().select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).order_by('-created_at')
            logger.info(f"Admin user - showing all {incidents.count()} incidents in system")
        else:
            # For non-admin users, get incidents where user is involved
            incidents = Incident.objects.filter(
                Q(log__user_email=user.email) |
                Q(assigned_to=user) |
                Q(created_by=user)
            ).select_related(
                'log', 'assigned_to', 'created_by', 'department'
            ).order_by('-created_at')
            logger.info(f"Non-admin user - found {incidents.count()} incidents for user {user.email}")
        
        # Apply filters (same for both cases)
        filters_applied = []
        
        status_filter = request.query_params.get('status')
        if status_filter:
            incidents = incidents.filter(status=status_filter)
            filters_applied.append(f"status={status_filter}")
        
        severity_filter = request.query_params.get('severity')
        if severity_filter:
            incidents = incidents.filter(severity=severity_filter)
            filters_applied.append(f"severity={severity_filter}")
        
        priority_filter = request.query_params.get('priority')
        if priority_filter:
            incidents = incidents.filter(priority=priority_filter)
            filters_applied.append(f"priority={priority_filter}")
        
        assigned_to_filter = request.query_params.get('assigned_to')
        if assigned_to_filter:
            incidents = incidents.filter(assigned_to_id=assigned_to_filter)
            filters_applied.append(f"assigned_to={assigned_to_filter}")
        
        department_filter = request.query_params.get('department')
        if department_filter:
            incidents = incidents.filter(department_id=department_filter)
            filters_applied.append(f"department={department_filter}")
        
        search_filter = request.query_params.get('search')
        if search_filter:
            incidents = incidents.filter(
                Q(title__icontains=search_filter) |
                Q(description__icontains=search_filter) |
                Q(incident_number__icontains=search_filter)
            )
            filters_applied.append(f"search={search_filter}")
        
        date_from = request.query_params.get('dateFrom')
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
            filters_applied.append(f"dateFrom={date_from}")
        
        date_to = request.query_params.get('dateTo')
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
            filters_applied.append(f"dateTo={date_to}")
        
        danger_zone = request.query_params.get('dangerZone')
        if danger_zone and danger_zone.lower() == 'true':
            incidents = incidents.filter(danger_zone=True)
            filters_applied.append("dangerZone=true")
        
        overdue_only = request.query_params.get('overdueOnly')
        if overdue_only and overdue_only.lower() == 'true':
            incidents = incidents.filter(is_overdue=True)
            filters_applied.append("overdueOnly=true")
        
        if filters_applied:
            logger.info(f"Filters applied: {', '.join(filters_applied)}")
            logger.info(f"Filtered incidents count: {incidents.count()}")
        
        # Apply sorting
        sort_by = request.query_params.get('sortBy', 'created_at')
        sort_order = request.query_params.get('sortOrder', 'desc')
        
        if sort_order == 'desc':
            sort_by_field = f'-{sort_by}'
        else:
            sort_by_field = sort_by
        incidents = incidents.order_by(sort_by_field)
        
        # Get total count for frontend pagination info
        total_count = incidents.count()
        
        # Apply page and page_size from frontend
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        logger.info(f"Pagination: Page {page}, Size {page_size}")
        
        # Calculate slice for pagination
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_incidents = incidents[start_index:end_index]
        
        # Use the list serializer for consistent format
        serializer = IncidentListSerializer(paginated_incidents, many=True)
        
        # Get statistics
        open_incidents = incidents.filter(status__in=['pending', 'investigating', 'assigned', 'in_progress']).count()
        resolved = incidents.filter(status__in=['resolved', 'closed']).count()
        
        # Build response
        response_data = {
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
        }
        
        logger.info(f"Returning {len(response_data['incidents'])} incidents")
        return Response(response_data)
    
    except Exception as e:
        return handle_exception(e, "Getting user incidents")
    
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_incident_comment(request, incident_id):
    """Add comment to incident"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        logger.info(f"Adding comment to incident {incident.incident_number}")
        
        # Check permissions
        user = request.user
        if not can_comment_on_incident(user, incident):
            logger.warning(f"User {user.email} cannot comment on incident {incident.incident_number}")
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
            logger.error(f"Comment serializer validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comment = serializer.save()
        
        # Log activity
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
        
        logger.info(f"Successfully added comment to incident {incident.incident_number}")
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
        
        # Check permissions
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
        
        # Check permissions
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
            logger.error(f"Attachment serializer validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attachment = serializer.save(incident=incident)
        
        # Log activity
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
    """Manually assign incident to a specific user - WITH REASSIGNMENT SUPPORT"""
    try:
        user = request.user
        logger.info(f"Manual incident assignment requested by {user.email}")
        
        # Only admin, HR, and security analysts can assign incidents
        if not (user.is_admin or user.is_hr or user.role == 'security_analyst'):
            logger.warning(f"User {user.email} lacks assignment permission")
            return Response(
                {"success": False, "error": "You don't have permission to assign incidents."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ManualIncidentAssignmentSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            logger.error(f"Manual assignment validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Save the assignment
        incident = serializer.save()
        
        # Get old assigned user info
        old_assigned_to = getattr(incident, '_old_assigned_to', None)
        new_assigned_to = incident.assigned_to
        
        # Determine if this is a reassignment
        is_reassignment = old_assigned_to and new_assigned_to and old_assigned_to.id != new_assigned_to.id
        
        # Log activity appropriately
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
        
        # Send notification to the new assigned user
        if new_assigned_to:
            try:
                NotificationUtils.send_incident_assignment_notification(incident)
                logger.info(f"Notification sent to {new_assigned_to.email}")
            except Exception as e:
                logger.error(f"Failed to send notification: {str(e)}")
        
        logger.info(f"Successfully {'reassigned' if is_reassignment else 'assigned'} incident {incident.incident_number}")
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
    """Update incident SLA due date"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        # Check permissions - only admin, HR, or assigned user can update SLA
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
            logger.error(f"SLA update validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        incident = serializer.save()
        
        # Log activity
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
        
        # Base queryset of users who can handle incidents
        assignable_users = CustomUser.objects.filter(
            is_active=True,
            role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
        )
        
        # If incident_id is provided, filter by relevant departments
        if incident_id:
            try:
                incident = Incident.objects.get(id=incident_id)
                if incident.department:
                    # Show users from same department first
                    if user.is_admin or user.is_hr:
                        # Admin/HR can see all users
                        pass
                    else:
                        # Filter users by relevant departments
                        assignable_users = assignable_users.filter(
                            Q(department=incident.department) |
                            Q(departments=incident.department) |
                            Q(role__in=['admin', 'hr_manager'])  # Always include admin/HR
                        ).distinct()
            except Incident.DoesNotExist:
                logger.warning(f"Incident {incident_id} not found")
                pass
        
        # Serialize user data
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
        
        # Sort by role and current workload
        users_data.sort(key=lambda x: (
            ['admin', 'hr_manager', 'security_analyst', 'compliance_officer'].index(x['role']),
            x['current_incident_count']
        ))
        
        logger.info(f"Found {len(users_data)} assignable users")
        return Response({
            "success": True,
            "count": len(users_data),
            "users": users_data
        })
    
    except Exception as e:
        return handle_exception(e, "Getting assignable users")

# ==================== REPORT VIEWS ====================

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
            
            # Base queryset
            queryset = Report.objects.select_related('generated_by').prefetch_related('shared_with')
            
            # Apply role-based filtering
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
        """Override list to handle exceptions"""
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
        
        # Generate report based on type
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
                # Don't fail the whole operation if email fails
        
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
        
        logger.info(f"Successfully generated report {report.report_number}")
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

def send_report_email(report, user, data):
    """Send email with report attached"""
    try:
        # Get absolute file path
        file_path = report.get_absolute_file_path()
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Report file not found: {file_path}")
            return False
        
        # Prepare email subject and body
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
        
        # Get recipient email(s)
        recipients = []
        
        # Primary recipient (user who generated the report)
        if user.email:
            recipients.append(user.email)
        
        # Additional recipients from form data
        if data.get('email_recipients'):
            additional_emails = data['email_recipients'].split(',')
            for email in additional_emails:
                email = email.strip()
                if email and '@' in email:
                    recipients.append(email)
        
        # Remove duplicates
        recipients = list(set(recipients))
        
        if not recipients:
            logger.warning("No recipients specified for report email")
            return False
        
        # Create email
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        
        # Attach report file
        try:
            with open(file_path, 'rb') as file:
                file_content = file.read()
                filename = f"{report.title.replace(' ', '_')}_{report.report_number}.{report.format}"
                
                # Set appropriate content type
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
            # Still send email without attachment
            email.body += f"\n\nNote: The report file could not be attached. Please download it from the system."
        
        # Send email
        email.send()
        
        # Log email sent
        logger.info(f"Report email sent to: {', '.join(recipients)}")
        
        # Update report metadata
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
    """Create report based on parameters - FIXED VERSION"""
    try:
        # Extract parameters
        report_type = data['report_type']
        title = data.get('title', f"{report_type.title()} Report")
        description = data.get('description', f"Generated {report_type} report")
        format_type = data['format']
        is_public = data.get('is_public', False)
        shared_with = data.get('shared_with', [])
        
        # FIX: Convert date objects to strings before storing in JSON
        parameters = {}
        for key, value in data.items():
            if value is None:
                parameters[key] = None
            elif isinstance(value, (date, datetime)):
                # Convert date/datetime to ISO format string
                parameters[key] = value.isoformat()
            elif isinstance(value, bool):
                parameters[key] = value
            elif isinstance(value, (int, float)):
                parameters[key] = value
            else:
                parameters[key] = str(value) if value else None
        
        # Create report record
        report = Report.objects.create(
            title=title,
            description=description,
            report_type=report_type,
            format=format_type,
            generated_by=user,
            parameters=parameters,  # Now safe for JSON
            is_public=is_public
        )
        
        # Add shared users
        if shared_with:
            report.shared_with.set(shared_with)
        
        # Generate file based on report type and format
        report_generator = ReportGenerator()
        
        # Get report data based on type
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
        
        # Generate content based on format
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
        else:  # html
            content = report_generator.generate_html_report(report_data, report_type)
        
        # Save file
        if content:
            save_report_file(report, content, format_type)
        
        return report
    
    except Exception as e:
        log_error("Create report error", str(e))
        return None
    


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
        
        # Check if file path exists in database
        if not report.file_path:
            logger.error(f"No file_path in database for report {report.id}")
            return Response(
                {"success": False, "error": "Report file not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get absolute path using the fixed method
        file_full_path = report.get_absolute_file_path()
        
        # Check file exists on disk
        if not os.path.exists(file_full_path):
            logger.error(f"Report file not found at path: {file_full_path}")
            return Response(
                {"success": False, "error": "Report file not found on server."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # File exists - proceed with download
        file_size = os.path.getsize(file_full_path)
        
        # Increment download count
        report.increment_download_count()
        
        # Get file extension and content type
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
        
        # Create filename for download
        filename = f"{report.title.replace(' ', '_')}_{report.report_number}.{file_extension}"
        
        # Open file
        try:
            file = open(file_full_path, 'rb')
        except IOError as e:
            logger.error(f"Failed to open file: {str(e)}")
            return Response(
                {"success": False, "error": "Failed to open report file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create response
        response = FileResponse(file, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = file_size
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='report_download',
            description=f'Downloaded report file: {report.report_number}',
            request=request,
            response=None,
            is_success=True
        )
        
        logger.info(f"Download initiated for report {report.report_number}")
        return response
    
    except Exception as e:
        return handle_exception(e, "Downloading report file")

# ==================== ADDITIONAL VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_statistics(request):
    """Get incident statistics for dashboard"""
    try:
        user = request.user
        timeframe = int(request.query_params.get('timeframe', 30))
        
        statistics = IncidentUtils.get_incident_statistics(user, timeframe)
        
        # Add SLA violations
        if user.is_admin or user.is_hr:
            sla_violations = IncidentUtils.check_sla_compliance()
            statistics['sla_violations'] = sla_violations
        
        return Response({
            "success": True,
            "statistics": statistics
        })
    
    except Exception as e:
        return handle_exception(e, "Getting incident statistics")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def escalate_incident(request, incident_id):
    """Escalate an incident to higher severity"""
    try:
        incident = get_object_or_404(Incident, id=incident_id)
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"success": False, "error": "You don't have permission to escalate this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reason = request.data.get('reason', '')
        
        # Use IncidentUtils to escalate
        IncidentUtils.escalate_incident(incident, reason, user)
        
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
        
        # Check permissions
        if not (user.is_admin or user.is_hr or incident.assigned_to == user or 
                incident.created_by == user or incident.log.user_email == user.email):
            return Response(
                {"success": False, "error": "You don't have permission to view timeline for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get incident creation
        timeline = [{
            'type': 'incident_created',
            'timestamp': incident.created_at,
            'user': incident.created_by.full_name if incident.created_by else 'System',
            'description': f'Incident {incident.incident_number} created: {incident.title}'
        }]
        
        # Get assignment if exists
        if incident.assigned_at and incident.assigned_to:
            timeline.append({
                'type': 'incident_assigned',
                'timestamp': incident.assigned_at,
                'user': incident.assigned_to.full_name,
                'description': f'Incident assigned to {incident.assigned_to.full_name}'
            })
        
        # Get status changes from logs
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
        
        # Get comments
        comments = incident.comments.all().order_by('created_at')
        for comment in comments:
            timeline.append({
                'type': 'comment',
                'timestamp': comment.created_at,
                'user': comment.user.full_name,
                'description': f'Comment added: {comment.comment[:50]}...'
            })
        
        # Get resolution if exists
        if incident.resolved_at:
            timeline.append({
                'type': 'incident_resolved',
                'timestamp': incident.resolved_at,
                'user': incident.assigned_to.full_name if incident.assigned_to else 'System',
                'description': f'Incident resolved: {incident.resolution_notes[:100] if incident.resolution_notes else "No resolution notes"}'
            })
        
        # Sort timeline by timestamp
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
        
        # Check permissions
        if not can_view_incident(user, incident):
            return Response(
                {"success": False, "error": "You don't have permission to view this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get tracking data
        tracking_data = IncidentUtils.get_incident_tracking_data(incident)
        
        # Get recent activities
        recent_activities = UserLog.objects.filter(
            description__icontains=incident.incident_number
        ).order_by('-timestamp')[:10]
        
        # Get comments count
        comments_count = incident.comments.count()
        
        # Get SLA status
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
def get_report_types(request):
    """Get available report types based on user role"""
    try:
        user = request.user
        
        # Define report types with role permissions
        all_report_types = [
            {'value': 'incident', 'label': 'Incident Report', 'description': 'Detailed incident analysis and statistics'},
            {'value': 'user_activity', 'label': 'User Activity Report', 'description': 'User login and activity patterns'},
            {'value': 'security', 'label': 'Security Report', 'description': 'Security metrics and threat analysis'},
            {'value': 'compliance', 'label': 'Compliance Report', 'description': 'Compliance status and audit findings'},
            {'value': 'access_control', 'label': 'Access Control Report', 'description': 'Access permissions and violations'},
            {'value': 'ai_analytics', 'label': 'AI Analytics Report', 'description': 'AI-powered behavioral analysis'},
            {'value': 'custom', 'label': 'Custom Report', 'description': 'Custom report with selected parameters'},
        ]
        
        # Filter based on user role
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

# ==================== HELPER FUNCTIONS FOR REPORTS ====================

def get_user_activity_report_data(parameters):
    """Get data for user activity report"""
    try:
        queryset = UserLog.objects.all()
        
        # Apply filters
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
        
        # Get statistics
        total = queryset.count()
        by_activity = list(queryset.values('activity').annotate(count=Count('id')).order_by('-count')[:10])
        by_user = list(queryset.values('user_email').annotate(count=Count('id')).order_by('-count')[:10])
        
        # Success rate
        successful = queryset.filter(is_success=True).count()
        failed = queryset.filter(is_success=False).count()
        
        # Recent activities
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
        # Get incidents for security analysis
        incidents = Incident.objects.all()
        
        # Apply filters
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        severity = parameters.get('severity')
        
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        if severity:
            incidents = incidents.filter(severity=severity)
        
        # Get security statistics
        total_incidents = incidents.count()
        critical_incidents = incidents.filter(severity='critical').count()
        high_incidents = incidents.filter(severity='high').count()
        
        # Get danger zone logs
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(timeframe_hours=24, risk_threshold=60)
        
        # Get user risk analysis
        user_risks = []
        users = CustomUser.objects.all()
        for user in users[:10]:  # Limit to 10 users for report
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
        # Get compliance-related data
        incidents = Incident.objects.filter(severity__in=['high', 'critical'])
        
        # Apply filters
        date_from = parameters.get('date_from')
        date_to = parameters.get('date_to')
        
        if date_from:
            incidents = incidents.filter(created_at__date__gte=date_from)
        if date_to:
            incidents = incidents.filter(created_at__date__lte=date_to)
        
        # Compliance statistics
        total_compliance_issues = incidents.count()
        resolved_issues = incidents.filter(status__in=['resolved', 'closed']).count()
        pending_issues = incidents.filter(status__in=['pending', 'investigating', 'assigned', 'in_progress']).count()
        
        # SLA compliance
        sla_violations = incidents.filter(sla_violated=True).count()
        sla_compliance_rate = round(((incidents.count() - sla_violations) / incidents.count() * 100) if incidents.count() > 0 else 100, 1)
        
        # Policy violations
        policy_violations = incidents.filter(title__icontains='policy').count()
        
        # Recent compliance incidents
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
        
        # Include incident data if requested
        if parameters.get('include_incidents', True):
            report_data['incidents'] = get_incident_report_data(parameters)
        
        # Include user activity data if requested
        if parameters.get('include_user_activity', False):
            report_data['user_activity'] = get_user_activity_report_data(parameters)
        
        # Include compliance data if requested
        if parameters.get('include_compliance', False):
            report_data['compliance'] = get_compliance_report_data(parameters)
        
        # Generate overall summary
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
        
        # Apply filters
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
        
        # Get statistics
        total = queryset.count()
        by_status = list(queryset.values('status').annotate(count=Count('id')))
        by_severity = list(queryset.values('severity').annotate(count=Count('id')))
        by_department = list(queryset.values('department__name').annotate(count=Count('id')))
        
        # Calculate resolution time
        resolved = queryset.filter(status__in=['resolved', 'closed'])
        avg_resolution_time = resolved.aggregate(
            avg_time=Avg(F('resolved_at') - F('created_at'))
        )['avg_time']
        
        # Recent incidents
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
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_danger_zone_logs(request):
    """Get logs that are in danger zone and need attention"""
    try:
        user = request.user
        logger.info(f"Getting danger zone logs for user: {user.email}")
        
        # Get danger zone logs using analyzer
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=24,
            risk_threshold=50
        )
        
        # Filter based on user role
        if not (user.is_admin or user.is_hr):
            # Non-admin users can only see their own logs
            danger_logs = [log for log in danger_logs if log['user_email'] == user.email]
        
        # Get summary
        summary = DangerZoneAnalyzer.get_danger_zone_summary(timeframe_hours=24)
        
        logger.info(f"Found {len(danger_logs)} danger zone logs")
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
        
        # Check permissions
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
def download_report(request, report_id):
    """Download a report - Legacy endpoint for backward compatibility"""
    try:
        # This is a legacy endpoint that redirects to the new file download endpoint
        logger.info(f"Legacy download report endpoint called for report {report_id}")
        
        # Get the report to ensure it exists
        report = get_object_or_404(Report, id=report_id)
        
        # Return the redirect information
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
def export_incidents(request):
    """Export incidents to CSV or Excel"""
    try:
        user = request.user
        format_type = request.query_params.get('format', 'csv')
        include_comments = request.query_params.get('include_comments', 'false').lower() == 'true'
        
        logger.info(f"Exporting incidents - User: {user.email}, Format: {format_type}")
        
        # Get incidents based on user role
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
        
        # Apply filters
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
        
        logger.info(f"Exporting {incidents.count()} incidents")
        
        # Export
        if format_type == 'excel':
            content = ExportUtils.export_incidents_to_excel(incidents, include_comments)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f'incidents_export_{now().strftime("%Y%m%d")}.xlsx'
        else:  # csv
            content = ExportUtils.export_incidents_to_csv(incidents, include_comments)
            content_type = 'text/csv'
            filename = f'incidents_export_{now().strftime("%Y%m%d")}.csv'
        
        # Create response
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Log export
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='incidents_export',
            description=f'Exported {incidents.count()} incidents to {format_type.upper()}',
            request=request,
            response=None,
            is_success=True
        )
        
        logger.info(f"Export completed successfully")
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
        
        logger.info(f"Sending notification for incident {incident.incident_number} by {user.email}")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or incident.assigned_to == user):
            logger.warning(f"User {user.email} lacks notification permission for incident {incident.id}")
            return Response(
                {"success": False, "error": "You don't have permission to send notifications for this incident."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        notification_type = request.data.get('type', 'assignment')
        logger.info(f"Notification type: {notification_type}")
        
        success = False
        message = ""
        
        if notification_type == 'sla_violation':
            success = NotificationUtils.send_sla_violation_notification(incident)
            message = "SLA violation notification sent"
        elif notification_type == 'resolution':
            success = NotificationUtils.send_resolution_notification(incident)
            message = "Resolution notification sent"
        else:  # assignment
            success = NotificationUtils.send_incident_assignment_notification(incident)
            message = "Assignment notification sent"
        
        if success:
            logger.info(f"Notification sent successfully for incident {incident.incident_number}")
            return Response({
                "success": True,
                "message": message
            })
        else:
            logger.error(f"Failed to send notification for incident {incident.incident_number}")
            return Response({
                "success": False,
                "message": "Failed to send notification"
            })
    
    except Exception as e:
        return handle_exception(e, "Sending incident notification")







@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_incident_detection(request):
    """Manually trigger incident detection from danger zone logs"""
    try:
        user = request.user
        logger.info(f"Triggering incident detection - User: {user.email}")
        
        # Only admin and HR can trigger detection
        if not (user.is_admin or user.is_hr):
            logger.warning(f"User {user.email} lacks permission to trigger incident detection")
            return Response(
                {"success": False, "error": "You don't have permission to trigger incident detection."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters from request
        timeframe = int(request.data.get('timeframe', 24))
        risk_threshold = int(request.data.get('risk_threshold', 60))
        limit = int(request.data.get('limit', 50))  # Limit number of logs to process
        
        logger.info(f"Detection parameters - Timeframe: {timeframe}h, Risk threshold: {risk_threshold}, Limit: {limit}")
        
        # Get danger zone logs
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=timeframe,
            risk_threshold=risk_threshold
        )
        
        logger.info(f"Found {len(danger_logs)} danger zone logs")
        
        created_incidents = []
        skipped_incidents = []
        failed_incidents = []
        
        for log_data in danger_logs[:limit]:  # Limit to prevent overwhelming the system
            try:
                log = UserLog.objects.get(id=log_data['id'])
                
                # Skip if incident already exists for this log
                if log.incidents.exists():
                    logger.debug(f"Skipping log {log.id} - incident already exists")
                    skipped_incidents.append(log.id)
                    continue
                
                # Calculate severity and priority based on risk score
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
                
                # Create incident title and description
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
                
                # Create incident
                print(f"   ⏳ Creating incident...")
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
                    _request_user=user  # Store for activity logging
                )
                
                # Auto-assign department based on user
                incident.assign_department_based_on_user()
                               
                # Try to auto-assign using IncidentUtils
                try:
                    
                    # Auto-assign to a user
                    print(f"   ⏳ Auto-assigning incident...")
                    assigned_user = IncidentUtils.assign_incident_to_user(incident)
                    if assigned_user:
                        print(f"   ✅ Assigned to: {assigned_user.email}")
                        
                        # Also set the department from the assigned user if still not set
                        if not incident.department and assigned_user.department:
                            incident.department = assigned_user.department
                            incident.save()
                    else:
                        print(f"   ⚠️  No eligible user found for assignment")
                except Exception as assign_error:
                    logger.warning(f"Failed to auto-assign incident {incident.incident_number}: {str(assign_error)}")
                    # Incident is still created, just not assigned
                
                created_incidents.append({
                    'incident_number': incident.incident_number,
                    'title': incident.title,
                    'severity': incident.severity,
                    'assigned_to': incident.assigned_to.email if incident.assigned_to else None,
                    'log_id': log.id
                })
                
                logger.debug(f"Created incident {incident.incident_number} from log {log.id}")
                
            except UserLog.DoesNotExist:
                logger.error(f"Log {log_data.get('id')} not found")
                failed_incidents.append(log_data.get('id', 'unknown'))
                continue
            except Exception as e:
                logger.error(f"Error creating incident from log {log_data.get('id', 'unknown')}: {str(e)}")
                failed_incidents.append(log_data.get('id', 'unknown'))
                continue
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='incident_detection_triggered',
            description=f'Manually triggered incident detection. Created {len(created_incidents)} incidents from {len(danger_logs)} danger zone logs',
            request=request,
            response=None,
            is_success=True
        )
        
        response_data = {
            "success": True,
            "message": f"Incident detection completed",
            "summary": {
                "total_danger_logs": len(danger_logs),
                "logs_processed": min(limit, len(danger_logs)),
                "incidents_created": len(created_incidents),
                "incidents_skipped": len(skipped_incidents),
                "incidents_failed": len(failed_incidents)
            },
            "created_incidents": created_incidents[:10],  # Return first 10 for reference
            "parameters": {
                "timeframe": timeframe,
                "risk_threshold": risk_threshold,
                "limit": limit
            }
        }
        
        if skipped_incidents:
            response_data["skipped_logs"] = skipped_incidents[:10]
        
        if failed_incidents:
            response_data["failed_logs"] = failed_incidents[:10]
        
        logger.info(f"Incident detection completed: Created {len(created_incidents)} incidents")
        return Response(response_data)
    
    except ValueError as e:
        logger.error(f"Invalid parameter value: {str(e)}")
        return Response(
            {
                "success": False,
                "error": "Invalid parameter value",
                "message": str(e)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return handle_exception(e, "Triggering incident detection")







# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_assignable_users(request, incident_id=None):
#     """Get list of users who can be assigned incidents"""
#     try:
#         user = request.user
#         logger.info(f"Getting assignable users - User: {user.email}, Incident ID: {incident_id}")
        
#         # Base queryset of users who can handle incidents
#         assignable_users = CustomUser.objects.filter(
#             is_active=True,
#             role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
#         )
        
#         # If incident_id is provided, filter by relevant departments
#         if incident_id:
#             try:
#                 incident = Incident.objects.get(id=incident_id)
#                 logger.info(f"Found incident: {incident.incident_number}")
                
#                 if incident.department:
#                     logger.info(f"Incident department: {incident.department.name}")
                    
#                     # Show users from same department first
#                     if user.is_admin or user.is_hr:
#                         # Admin/HR can see all users
#                         logger.info("User is admin/HR - showing all assignable users")
#                         pass
#                     else:
#                         # Filter users by relevant departments
#                         logger.info("Filtering users by relevant departments")
#                         assignable_users = assignable_users.filter(
#                             Q(department=incident.department) |
#                             Q(departments=incident.department) |
#                             Q(role__in=['admin', 'hr_manager'])  # Always include admin/HR
#                         ).distinct()
#                 else:
#                     logger.info("Incident has no department assigned")
                    
#             except Incident.DoesNotExist:
#                 logger.warning(f"Incident {incident_id} not found")
#                 return Response(
#                     {"success": False, "error": f"Incident with ID {incident_id} not found."},
#                     status=status.HTTP_404_NOT_FOUND
#                 )
        
#         # Get count before serializing
#         total_users = assignable_users.count()
#         logger.info(f"Found {total_users} assignable users")
        
#         # Serialize user data
#         users_data = []
#         for assignable_user in assignable_users:
#             # Count current incidents
#             current_incident_count = assignable_user.assigned_incidents.filter(
#                 status__in=['pending', 'investigating', 'assigned', 'in_progress']
#             ).count()
            
#             # Get departments for security analysts
#             departments_list = []
#             if assignable_user.role == 'security_analyst' and assignable_user.departments.exists():
#                 departments_list = [dept.name for dept in assignable_user.departments.all()]
            
#             user_data = {
#                 'id': assignable_user.id,
#                 'full_name': assignable_user.full_name or '',
#                 'email': assignable_user.email,
#                 'work_mail': assignable_user.work_mail_address or '',
#                 'role': assignable_user.role,
#                 'role_display': assignable_user.get_role_display() if hasattr(assignable_user, 'get_role_display') else assignable_user.role,
#                 'status': assignable_user.status or '',
#                 'availability_status': assignable_user.availability_status or 'available',
#                 'department': assignable_user.department.name if assignable_user.department else None,
#                 'departments': departments_list,
#                 'current_incident_count': current_incident_count,
#                 'workload_level': self.get_workload_level(current_incident_count),
#                 'is_available': self.check_user_availability(assignable_user)
#             }
#             users_data.append(user_data)
        
#         # Sort by:
#         # 1. Role priority (admin/HR first, then security analysts, then compliance officers)
#         # 2. Workload (fewer incidents first)
#         # 3. Availability status
#         def sort_key(user):
#             role_order = {
#                 'admin': 0,
#                 'hr_manager': 1,
#                 'security_analyst': 2,
#                 'compliance_officer': 3
#             }
#             return (
#                 role_order.get(user['role'], 99),
#                 user['current_incident_count'],
#                 0 if user['is_available'] else 1,
#                 user['full_name']
#             )
        
#         users_data.sort(key=sort_key)
        
#         # Get workload statistics
#         workload_stats = {
#             'total_users': total_users,
#             'available_users': len([u for u in users_data if u['is_available']]),
#             'busy_users': len([u for u in users_data if not u['is_available']]),
#             'average_workload': round(sum(u['current_incident_count'] for u in users_data) / total_users, 2) if total_users > 0 else 0,
#             'workload_distribution': {
#                 'light': len([u for u in users_data if u['current_incident_count'] <= 2]),
#                 'moderate': len([u for u in users_data if 3 <= u['current_incident_count'] <= 5]),
#                 'heavy': len([u for u in users_data if u['current_incident_count'] > 5])
#             }
#         }
        
#         response_data = {
#             "success": True,
#             "count": total_users,
#             "users": users_data,
#             "statistics": workload_stats,
#             "current_user": {
#                 "id": user.id,
#                 "email": user.email,
#                 "role": user.role,
#                 "can_assign": user.is_admin or user.is_hr or user.role == 'security_analyst'
#             }
#         }
        
#         logger.info(f"Returning {len(users_data)} assignable users with workload statistics")
#         return Response(response_data)
    
#     except Exception as e:
#         return handle_exception(e, "Getting assignable users")

def get_workload_level(incident_count):
    """Determine workload level based on incident count"""
    if incident_count <= 2:
        return 'light'
    elif incident_count <= 5:
        return 'moderate'
    else:
        return 'heavy'

def check_user_availability(user):
    """Check if user is available to take new incidents"""
    # Check if user is active
    if not user.is_active:
        return False
    
    # Check availability status
    if hasattr(user, 'availability_status'):
        if user.availability_status in ['busy', 'away', 'on_leave']:
            return False
    
    # Check if user has too many pending incidents
    pending_incidents = user.assigned_incidents.filter(
        status__in=['pending', 'investigating', 'assigned', 'in_progress']
    ).count()
    
    # If user has more than 7 pending incidents, consider them busy
    if pending_incidents > 7:
        return False
    
    return True






@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_assigned_incidents(request):
    """Check if current user has any assigned incidents"""
    try:
        user = request.user
        logger.info(f"Checking assigned incidents for user: {user.email}")
        
        # Get all incidents assigned to user
        assigned_incidents = Incident.objects.filter(
            assigned_to=user,
            status__in=['pending', 'investigating', 'assigned', 'in_progress', 'escalated']
        )
        
        # Get counts by status
        total_assigned = assigned_incidents.count()
        pending_count = assigned_incidents.filter(status='pending').count()
        investigating_count = assigned_incidents.filter(status='investigating').count()
        assigned_count = assigned_incidents.filter(status='assigned').count()
        in_progress_count = assigned_incidents.filter(status='in_progress').count()
        escalated_count = assigned_incidents.filter(status='escalated').count()
        
        
        # Get incidents requiring immediate attention
        urgent_incidents = assigned_incidents.filter(
            Q(severity__in=['critical', 'high']) &
            Q(status__in=['pending', 'investigating', 'assigned'])
        ).count()
        
        has_assigned = total_assigned > 0
        
        logger.info(f"User {user.email} has {total_assigned} assigned incidents")
        
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
            logger.error(f"Status update validation failed: {serializer.errors}")
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        incident = serializer.validated_data['incident']
        new_status = serializer.validated_data['new_status']
        resolution_notes = serializer.validated_data.get('resolution_notes', '')
        
        # Track old status for logging
        old_status = incident.status
        
        # Update incident
        incident.status = new_status
        
        # Set resolution notes if provided
        if resolution_notes:
            incident.resolution_notes = resolution_notes
        
        # Set resolved timestamp if status is changed to 'resolved'
        if old_status != 'resolved' and new_status == 'resolved':
            incident.resolved_at = now()
        
        # Check SLA violation after status change
        incident.check_sla_violation()
        
        # Save the incident
        incident.save()
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity='incident_status_update',
            description=f'Updated status of assigned incident {incident.incident_number} from {old_status} to {new_status}',
            request=request,
            response=None,
            is_success=True
        )
        
        # Send notification if incident is resolved
        if new_status == 'resolved':
            try:
                NotificationUtils.send_resolution_notification(incident)
                logger.info(f"Resolution notification sent for incident {incident.incident_number}")
            except Exception as e:
                logger.error(f"Failed to send resolution notification: {str(e)}")
        
        # Get updated incident data
        updated_incident = IncidentSerializer(incident).data
        
        logger.info(f"Successfully updated incident {incident.incident_number} status from {old_status} to {new_status}")
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
        
        try:
            # Get all incidents assigned to user
            assigned_incidents = Incident.objects.filter(
                assigned_to=user
            ).select_related(
                'log', 'department'
            ).order_by('-created_at')
            
            # Apply filters
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
        except Exception as e:
            error_msg = f"Error filtering incidents: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Failed to apply filters to incidents"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            # Apply sorting
            sort_by = request.query_params.get('sortBy', 'created_at')
            sort_order = request.query_params.get('sortOrder', 'desc')
            
            if sort_order == 'desc':
                sort_by_field = f'-{sort_by}'
            else:
                sort_by_field = sort_by
            assigned_incidents = assigned_incidents.order_by(sort_by_field)
        except Exception as e:
            error_msg = f"Error sorting incidents: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Failed to sort incidents"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            # Get total count
            total_count = assigned_incidents.count()
            
            # Apply pagination
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
            
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_incidents = assigned_incidents[start_index:end_index]
        except ValueError as e:
            error_msg = f"Invalid pagination parameters: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Page and page_size must be valid integers"
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = f"Error in pagination: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Failed to paginate incidents"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            # Serialize data
            serializer = IncidentListSerializer(paginated_incidents, many=True)
        except Exception as e:
            error_msg = f"Error serializing incidents: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Failed to serialize incident data"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            # Get statistics - FIXED: Calculate overdue manually
            open_count = assigned_incidents.filter(
                status__in=['pending', 'investigating', 'assigned', 'in_progress']
            ).count()
            
            resolved_count = assigned_incidents.filter(
                status__in=['resolved', 'closed']
            ).count()
            
            # Calculate overdue count manually (can't filter on property)
            # Method 1: Use database query with sla_due_date
            from django.utils.timezone import now
            overdue_count = assigned_incidents.filter(
                sla_due_date__lt=now(),
                status__in=['pending', 'investigating', 'assigned', 'in_progress']
            ).count()
            
            # Alternative Method 2: Calculate in Python (use if Method 1 doesn't match your logic)
            # overdue_count = sum(1 for inc in assigned_incidents if inc.is_overdue)
            
        except Exception as e:
            error_msg = f"Error calculating statistics: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return Response({
                "success": False,
                "error": error_msg,
                "details": "Failed to calculate incident statistics"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        logger.info(f"Found {total_count} incidents assigned to user {user.email}")
        
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
        error_msg = f"Unexpected error in get_my_assigned_incidents: {str(e)}"
        logger.error(error_msg)
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()  # Print full stack trace to terminal
        return Response({
            "success": False,
            "error": error_msg,
            "details": "An unexpected error occurred while fetching assigned incidents"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    