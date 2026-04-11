from decimal import Decimal
from uuid import UUID
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, F, ExpressionWrapper, FloatField
from django.utils.timezone import now
from datetime import datetime, timedelta, date, timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
import json
import logging

from .models import (
    ComplianceStandard, ComplianceAudit,
    AuditFinding, ControlAssessment, ComplianceReport
)
from .serializers import (
    ComplianceStandardSerializer,
    ComplianceAuditSerializer,
    AuditFindingSerializer,
    ControlAssessmentSerializer,
    ComplianceReportSerializer,
    DashboardStatisticsSerializer
)
from .filters import (
    AuditFilter,
    FindingFilter,
    ControlAssessmentFilter
)
from userApp.utils import ActivityLogger
from incidentApp.models import Incident

logger = logging.getLogger(__name__)

# ==================== DEBUGGING DECORATORS ====================

import json
from datetime import datetime, date, time
from django.utils.timezone import is_aware

class DateTimeJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""
    def default(self, obj):
        # Handle datetime objects
        if isinstance(obj, (datetime, date, time)):
            # Convert to ISO format string
            if isinstance(obj, datetime):
                if is_aware(obj):
                    # Convert aware datetime to UTC string
                    return obj.astimezone(timezone.utc).isoformat()
                return obj.isoformat()
            elif isinstance(obj, date):
                return obj.isoformat()
            elif isinstance(obj, time):
                return obj.isoformat()
        # Handle Decimal objects
        elif isinstance(obj, Decimal):
            return float(obj)
        # Handle UUID objects
        elif isinstance(obj, UUID):
            return str(obj)
        # Let the base class default method raise the TypeError
        return super().default(obj)

def debug_request_response(func):
    """Decorator to log request data and response for debugging"""
    def wrapper(*args, **kwargs):
        # Try to find the request object
        request = None
        for arg in args:
            if hasattr(arg, 'method') and hasattr(arg, 'user'):
                request = arg
                break
        
        # If not found in args, check kwargs
        if not request and 'request' in kwargs:
            request = kwargs['request']
        
        # Log request data if found
        if request and request.method in ['POST', 'PUT', 'PATCH']:
            logger.info(f"\n{'='*80}")
            # logger.info(f"REQUEST {request.method} {request.path}")
            # logger.info(f"User: {request.user.full_name if request.user else 'Anonymous'}")
            # logger.info(f"Submitted data: {json.dumps(request.data, indent=2)}")
            # logger.info(f"{'='*80}\n")
        
        # Call the original function
        response = func(*args, **kwargs)
        
        # Log response data
        if response and hasattr(response, 'data'):
            # logger.info(f"\n{'='*80}")
            # logger.info(f"RESPONSE for {request.method if request else 'unknown'} {request.path if request else 'unknown'}")
            # logger.info(f"Status: {response.status_code}")
            
            # Create a safe copy for logging and handle serialization errors
            try:
                response_data = response.data.copy() if hasattr(response.data, 'copy') else response.data
                
                # Truncate large data for readability
                if isinstance(response_data, dict) and 'data' in response_data and isinstance(response_data['data'], list):
                    # For lists, show first 2 items
                    truncated_data = response_data.copy()
                    if len(truncated_data['data']) > 2:
                        truncated_data['data'] = truncated_data['data'][:2] + [f"... and {len(truncated_data['data']) - 2} more items"]
                    # logger.info(f"Response data: {json.dumps(truncated_data, indent=2, cls=DateTimeJSONEncoder)}")
                else:
                    logger.info(f"Response data: {json.dumps(response_data, indent=2, cls=DateTimeJSONEncoder)}")
            except (TypeError, AttributeError) as json_error:
                # If serialization fails, log a simplified version
                # logger.warning(f"Could not serialize response data for logging: {str(json_error)}")
                # logger.info(f"Response structure: {type(response.data)}")
                if isinstance(response.data, dict):
                    logger.info(f"Response keys: {list(response.data.keys())}")
            
            # logger.info(f"{'='*80}\n")
        
        return response
    return wrapper
# ==================== STANDARD VIEWS ====================

class ComplianceStandardViewSet(APIView):
    """Manage compliance standards"""
    
    permission_classes = [IsAuthenticated]
    
    @debug_request_response
    def get(self, request):
        """List all compliance standards"""
        try:
            # logger.info(f"GET request for standards by user: {request.user.full_name}")
            
            standards = ComplianceStandard.objects.all()
            
            # Apply filters
            is_active = request.query_params.get('is_active')
            if is_active is not None:
                standards = standards.filter(is_active=is_active.lower() == 'true')
            
            standard_type = request.query_params.get('standard_type')
            if standard_type:
                standards = standards.filter(standard_type=standard_type)
            
            # Pagination
            paginator = PageNumberPagination()
            paginator.page_size = int(request.query_params.get('page_size', 20))
            result_page = paginator.paginate_queryset(standards, request)
            
            serializer = ComplianceStandardSerializer(result_page, many=True)
            
            # Log retrieved data
            # logger.info(f"Retrieved {len(serializer.data)} standards")
            
            return paginator.get_paginated_response({
                'success': True,
                'standards': serializer.data
            })
            
        except ValueError as ve:
            # logger.error(f"ValueError in standards list: {str(ve)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Invalid parameter value',
                'details': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # logger.error(f"Error listing standards: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to retrieve compliance standards',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @debug_request_response
    def post(self, request):
        """Create a new compliance standard"""
        try:
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                logger.warning(f"User {request.user.full_name} attempted to create standard without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can create standards'
                }, status=status.HTTP_403_FORBIDDEN)
            
            serializer = ComplianceStandardSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if serializer.is_valid():
                # logger.info(f"Creating standard with valid data: {serializer.validated_data}")
                standard = serializer.save(created_by=request.user)
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='standard_created',
                        description=f'Created compliance standard: {standard.name}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                # logger.info(f"Standard created successfully: {standard.name} (ID: {standard.id})")
                return Response({
                    'success': True,
                    'message': 'Standard created successfully',
                    'standard': ComplianceStandardSerializer(standard).data
                }, status=status.HTTP_201_CREATED)
            else:
                logger.warning(f"Standard creation validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating standard: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to create standard',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@debug_request_response
def standard_detail(request, standard_id):
    """Get, update, or delete a specific standard"""
    try:
        # logger.info(f"Standard detail request for ID: {standard_id} by user: {request.user.full_name}")
        
        try:
            standard = ComplianceStandard.objects.get(id=standard_id)
        except ComplianceStandard.DoesNotExist:
            # logger.warning(f"Standard with ID {standard_id} not found")
            return Response({
                'success': False,
                'error': f'Compliance standard with ID {standard_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'GET':
            serializer = ComplianceStandardSerializer(standard)
            # logger.info(f"Retrieved standard: {standard.name}")
            return Response({
                'success': True,
                'standard': serializer.data
            })
        
        elif request.method == 'PUT':
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                logger.warning(f"User {request.user.full_name} attempted to update standard without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can update standards'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # logger.info(f"Updating standard ID: {standard_id} with data: {request.data}")
            serializer = ComplianceStandardSerializer(
                standard,
                data=request.data,
                context={'request': request},
                partial=True
            )
            
            if serializer.is_valid():
                updated_standard = serializer.save()
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='standard_updated',
                        description=f'Updated compliance standard: {standard.name}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                # logger.info(f"Standard updated successfully: {updated_standard.name}")
                return Response({
                    'success': True,
                    'message': 'Standard updated successfully',
                    'standard': serializer.data
                })
            else:
                logger.warning(f"Standard update validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                logger.warning(f"User {request.user.full_name} attempted to delete standard without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can delete standards'
                }, status=status.HTTP_403_FORBIDDEN)
            
            standard_name = standard.name
            # logger.info(f"Deleting standard: {standard_name}")
            standard.delete()
            
            try:
                ActivityLogger.create_log(
                    user=request.user,
                    log_type='compliance',
                    activity='standard_deleted',
                    description=f'Deleted compliance standard: {standard_name}',
                    request=request,
                    response=None,
                    is_success=True
                )
            except Exception as log_error:
                logger.warning(f"Failed to create activity log: {str(log_error)}")
            
            # logger.info(f"Standard deleted successfully: {standard_name}")
            return Response({
                'success': True,
                'message': 'Standard deleted successfully'
            })
            
    except Exception as e:
        logger.error(f"Error in standard_detail: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to process request',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== AUDIT VIEWS ====================

class ComplianceAuditViewSet(APIView):
    """Manage compliance audits"""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AuditFilter
    search_fields = ['title', 'description', 'audit_id']
    ordering_fields = ['created_at', 'planned_start_date', 'overall_score']
    
    def get_queryset(self):
        """Return audits based on user role"""
        try:
            user = self.request.user
            
            if user.is_admin or user.role == 'compliance_officer':
                return ComplianceAudit.objects.select_related(
                    'standard', 'lead_auditor', 'created_by'
                ).prefetch_related(
                    'related_incidents',
                    'findings',
                    'control_assessments'
                ).all()
            
            # Non-admin users can only see completed audits they're involved in
            return ComplianceAudit.objects.filter(
                Q(status='completed') |
                Q(lead_auditor=user) |
                Q(created_by=user) |
                Q(findings__assigned_to=user)
            ).distinct().select_related(
                'standard', 'lead_auditor', 'created_by'
            ).prefetch_related(
                'related_incidents'
            )
        except Exception as e:
            logger.error(f"Error in get_queryset: {str(e)}", exc_info=True)
            return ComplianceAudit.objects.none()
    
    @debug_request_response
    def get(self, request):
        """List audits with filtering"""
        try:
            # logger.info(f"GET audits request by user: {request.user.full_name}")
            # logger.info(f"Query params: {dict(request.query_params)}")
            
            queryset = self.get_queryset()
            # logger.info(f"Initial queryset count: {queryset.count()}")
            
            # Apply filtering
            try:
                for backend in list(self.filter_backends):
                    if backend == DjangoFilterBackend:
                        queryset = self.filterset_class(request.GET, queryset=queryset).qs
                    else:
                        queryset = backend().filter_queryset(request, queryset, self)
                # logger.info(f"Filtered queryset count: {queryset.count()}")
            except Exception as filter_error:
                logger.warning(f"Error applying filters: {str(filter_error)}")
                # Continue with unfiltered queryset
            
            # Pagination
            paginator = PageNumberPagination()
            paginator.page_size = int(request.query_params.get('page_size', 10))
            result_page = paginator.paginate_queryset(queryset, request)
            
            serializer = ComplianceAuditSerializer(result_page, many=True)
            # logger.info(f"Retrieved {len(serializer.data)} audits")
            
            return paginator.get_paginated_response({
                'success': True,
                'audits': serializer.data
            })
            
        except ValueError as ve:
            logger.error(f"ValueError in audits list: {str(ve)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Invalid parameter value',
                'details': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error listing audits: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to retrieve audits',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @debug_request_response
    def post(self, request):
        """Create a new audit"""
        try:
            # logger.info(f"POST audit request by user: {request.user.full_name}")
            
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                # logger.warning(f"User {request.user.full_name} attempted to create audit without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can create audits'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # logger.info(f"Creating audit with data: {request.data}")
            serializer = ComplianceAuditSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if serializer.is_valid():
                # logger.info(f"Audit data is valid: {serializer.validated_data}")
                
                # Create audit first without incidents
                audit_data = serializer.validated_data.copy()
                
                # Temporarily remove incident_ids for audit creation
                incident_ids = []
                if 'incident_ids' in audit_data:
                    incident_ids = audit_data.pop('incident_ids')
                
                # Also remove related_incidents if it exists
                if 'related_incidents' in audit_data:
                    related_incidents = audit_data.pop('related_incidents')
                
                # Set created_by
                request_data = request.data.copy()
                audit_data['created_by'] = request.user
                
                # logger.info(f"Creating audit with cleaned data: {audit_data}")
                
                # Create the audit instance
                audit = ComplianceAudit.objects.create(**audit_data)
                # logger.info(f"Audit created with ID: {audit.id}, audit_id: {audit.audit_id}")
                
                # Add incidents after audit is created
                if incident_ids:
                    # logger.info(f"Adding incidents to audit: {incident_ids}")
                    incidents = Incident.objects.filter(id__in=incident_ids)
                    if incidents.exists():
                        audit.related_incidents.set(incidents)
                        logger.info(f"Added {incidents.count()} incidents to audit")
                        
                        # Calculate risk score
                        risk_score = audit.calculate_risk_score()
                        if risk_score:
                            audit.risk_score_from_incident = risk_score
                            audit.save(update_fields=['risk_score_from_incident'])
                            logger.info(f"Set risk score: {risk_score}")
                
                # Update metrics
                audit.update_metrics()
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='audit_created',
                        description=f'Created compliance audit: {audit.audit_id}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                # Return full audit data
                full_audit_data = ComplianceAuditSerializer(audit, context={'request': request}).data
                # logger.info(f"Audit created successfully: {audit.audit_id}")
                
                return Response({
                    'success': True,
                    'message': 'Audit created successfully',
                    'audit': full_audit_data
                }, status=status.HTTP_201_CREATED)
            else:
                logger.warning(f"Audit creation validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating audit: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to create audit',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'PUT', 'DELETE', 'PATCH'])
@permission_classes([IsAuthenticated])
@debug_request_response
def audit_detail(request, audit_id):
    """Get, update, or delete a specific audit"""
    try:
        # logger.info(f"Audit detail request for ID: {audit_id} by user: {request.user.full_name}")
        
        try:
            audit = ComplianceAudit.objects.get(id=audit_id)
        except ComplianceAudit.DoesNotExist:
            # logger.warning(f"Audit with ID {audit_id} not found")
            return Response({
                'success': False,
                'error': f'Audit with ID {audit_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check access permissions
        if not can_access_audit(request.user, audit):
            # logger.warning(f"User {request.user.full_name} does not have access to audit {audit_id}")
            return Response({
                'success': False,
                'error': 'You do not have permission to access this audit'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if request.method == 'GET' or request.method == 'PATCH':
            # logger.info(f"Retrieving audit details for: {audit.audit_id}")
            serializer = ComplianceAuditSerializer(audit)
            
            # Get related data
            try:
                findings = audit.findings.all()
                findings_serializer = AuditFindingSerializer(findings, many=True)
                
                controls = audit.control_assessments.all()
                controls_serializer = ControlAssessmentSerializer(controls, many=True)
                
                # logger.info(f"Found {findings.count()} findings and {controls.count()} controls")
                
                return Response({
                    'success': True,
                    'audit': serializer.data,
                    'findings': findings_serializer.data,
                    'control_assessments': controls_serializer.data
                })
            except Exception as related_error:
                # logger.warning(f"Error fetching related data: {str(related_error)}")
                return Response({
                    'success': True,
                    'audit': serializer.data,
                    'findings': [],
                    'control_assessments': []
                })
        
        elif request.method == 'PUT':
            if not can_update_audit(request.user, audit):
                # logger.warning(f"User {request.user.full_name} cannot update audit {audit_id}")
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update this audit'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # logger.info(f"Updating audit {audit.audit_id} with data: {request.data}")
            serializer = ComplianceAuditSerializer(
                audit,
                data=request.data,
                context={'request': request},
                partial=True
            )
            
            if serializer.is_valid():
                logger.info(f"Audit update data is valid: {serializer.validated_data}")
                updated_audit = serializer.save()
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='audit_updated',
                        description=f'Updated compliance audit: {audit.audit_id}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                logger.info(f"Audit updated successfully: {audit.audit_id}")
                return Response({
                    'success': True,
                    'message': 'Audit updated successfully',
                    'audit': ComplianceAuditSerializer(updated_audit).data
                })
            else:
                # logger.warning(f"Audit update validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            if not can_delete_audit(request.user, audit):
                # logger.warning(f"User {request.user.full_name} cannot delete audit {audit_id}")
                return Response({
                    'success': False,
                    'error': 'You do not have permission to delete this audit'
                }, status=status.HTTP_403_FORBIDDEN)
            
            audit_id_str = audit.audit_id
            # logger.info(f"Deleting audit: {audit_id_str}")
            audit.delete()
            
            try:
                ActivityLogger.create_log(
                    user=request.user,
                    log_type='compliance',
                    activity='audit_deleted',
                    description=f'Deleted compliance audit: {audit_id_str}',
                    request=request,
                    response=None,
                    is_success=True
                )
            except Exception as log_error:
                logger.warning(f"Failed to create activity log: {str(log_error)}")
            
            # logger.info(f"Audit deleted successfully: {audit_id_str}")
            return Response({
                'success': True,
                'message': 'Audit deleted successfully'
            })
            
    except Exception as e:
        logger.error(f"Error in audit_detail: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to process request',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== FINDING VIEWS ====================

class AuditFindingViewSet(APIView):
    """Manage audit findings"""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = FindingFilter
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'risk_level', 'target_completion_date']
    
    def get_queryset(self):
        """Return findings based on user role"""
        try:
            user = self.request.user
            
            if user.is_admin or user.role == 'compliance_officer':
                return AuditFinding.objects.select_related(
                    'audit', 'audit__standard', 'created_by', 'assigned_to'
                ).all()
            
            # Non-admin users can only see findings assigned to them
            return AuditFinding.objects.filter(
                Q(assigned_to=user) |
                Q(audit__created_by=user) |
                Q(audit__lead_auditor=user)
            ).distinct().select_related(
                'audit', 'audit__standard', 'created_by', 'assigned_to'
            )
        except Exception as e:
            # logger.error(f"Error in findings get_queryset: {str(e)}", exc_info=True)
            return AuditFinding.objects.none()
    
    @debug_request_response
    def get(self, request):
        """List findings with filtering"""
        try:
            # logger.info(f"GET findings request by user: {request.user.full_name}")
            
            queryset = self.get_queryset()
            # logger.info(f"Initial findings count: {queryset.count()}")
            
            # Apply filtering
            try:
                for backend in list(self.filter_backends):
                    if backend == DjangoFilterBackend:
                        queryset = self.filterset_class(request.GET, queryset=queryset).qs
                    else:
                        queryset = backend().filter_queryset(request, queryset, self)
                # logger.info(f"Filtered findings count: {queryset.count()}")
            except Exception as filter_error:
                logger.warning(f"Error applying filters: {str(filter_error)}")
            
            # Pagination
            paginator = PageNumberPagination()
            paginator.page_size = int(request.query_params.get('page_size', 20))
            result_page = paginator.paginate_queryset(queryset, request)
            
            serializer = AuditFindingSerializer(result_page, many=True)
            # logger.info(f"Retrieved {len(serializer.data)} findings")
            
            return paginator.get_paginated_response({
                'success': True,
                'findings': serializer.data
            })
            
        except ValueError as ve:
            # logger.error(f"ValueError in findings list: {str(ve)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Invalid parameter value',
                'details': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # logger.error(f"Error listing findings: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to retrieve findings',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @debug_request_response
    def post(self, request):
        """Create a new finding"""
        try:
            # logger.info(f"POST finding request by user: {request.user.full_name}")
            
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                # logger.warning(f"User {request.user.full_name} attempted to create finding without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can create findings'
                }, status=status.HTTP_403_FORBIDDEN)
            
            logger.info(f"Creating finding with data: {request.data}")
            serializer = AuditFindingSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if serializer.is_valid():
                # logger.info(f"Finding data is valid: {serializer.validated_data}")
                finding = serializer.save(created_by=request.user)
                
                # Update audit metrics
                try:
                    finding.audit.update_metrics()
                    # logger.info(f"Updated metrics for audit: {finding.audit.audit_id}")
                except Exception as metrics_error:
                    logger.warning(f"Failed to update audit metrics: {str(metrics_error)}")
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='finding_created',
                        description=f'Created audit finding: {finding.id}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                # logger.info(f"Finding created successfully: {finding.title}")
                return Response({
                    'success': True,
                    'message': 'Finding created successfully',
                    'finding': AuditFindingSerializer(finding).data
                }, status=status.HTTP_201_CREATED)
            else:
                logger.warning(f"Finding creation validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating finding: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to create finding',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== CONTROL ASSESSMENT VIEWS ====================

class ControlAssessmentViewSet(APIView):
    """Manage control assessments"""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ControlAssessmentFilter
    search_fields = ['control_id', 'control_name', 'control_description']
    ordering_fields = ['created_at', 'status', 'assessment_date']
    
    def get_queryset(self):
        """Return control assessments based on user role"""
        try:
            user = self.request.user
            
            if user.is_admin or user.role == 'compliance_officer':
                return ControlAssessment.objects.select_related(
                    'audit', 'assessed_by'
                ).all()
            
            # Non-admin users can only see controls for audits they're involved in
            return ControlAssessment.objects.filter(
                Q(audit__created_by=user) |
                Q(audit__lead_auditor=user) |
                Q(assessed_by=user)
            ).distinct().select_related(
                'audit', 'assessed_by'
            )
        except Exception as e:
            # logger.error(f"Error in controls get_queryset: {str(e)}", exc_info=True)
            return ControlAssessment.objects.none()
    
    @debug_request_response
    def get(self, request):
        """List control assessments with filtering"""
        try:
            logger.info(f"GET controls request by user: {request.user.full_name}")
            
            queryset = self.get_queryset()
            # logger.info(f"Initial controls count: {queryset.count()}")
            
            # Apply filtering
            try:
                for backend in list(self.filter_backends):
                    if backend == DjangoFilterBackend:
                        queryset = self.filterset_class(request.GET, queryset=queryset).qs
                    else:
                        queryset = backend().filter_queryset(request, queryset, self)
                # logger.info(f"Filtered controls count: {queryset.count()}")
            except Exception as filter_error:
                logger.warning(f"Error applying filters: {str(filter_error)}")
            
            # Pagination
            paginator = PageNumberPagination()
            paginator.page_size = int(request.query_params.get('page_size', 20))
            result_page = paginator.paginate_queryset(queryset, request)
            
            serializer = ControlAssessmentSerializer(result_page, many=True)
            # logger.info(f"Retrieved {len(serializer.data)} controls")
            
            return paginator.get_paginated_response({
                'success': True,
                'control_assessments': serializer.data
            })
            
        except ValueError as ve:
            # logger.error(f"ValueError in controls list: {str(ve)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Invalid parameter value',
                'details': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # logger.error(f"Error listing control assessments: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to retrieve control assessments',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @debug_request_response
    def post(self, request):
        """Create a new control assessment"""
        try:
            logger.info(f"POST control request by user: {request.user.full_name}")
            
            if not (request.user.is_admin or request.user.role == 'compliance_officer'):
                # logger.warning(f"User {request.user.full_name} attempted to create control without permission")
                return Response({
                    'success': False,
                    'error': 'Only admins and compliance officers can create control assessments'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # logger.info(f"Creating control with data: {request.data}")
            serializer = ControlAssessmentSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if serializer.is_valid():
                # logger.info(f"Control data is valid: {serializer.validated_data}")
                control = serializer.save()
                
                # Update audit metrics
                try:
                    control.audit.update_metrics()
                    # logger.info(f"Updated metrics for audit: {control.audit.audit_id}")
                except Exception as metrics_error:
                    logger.warning(f"Failed to update audit metrics: {str(metrics_error)}")
                
                try:
                    ActivityLogger.create_log(
                        user=request.user,
                        log_type='compliance',
                        activity='control_assessed',
                        description=f'Created control assessment: {control.control_id}',
                        request=request,
                        response=None,
                        is_success=True
                    )
                except Exception as log_error:
                    logger.warning(f"Failed to create activity log: {str(log_error)}")
                
                # logger.info(f"Control created successfully: {control.control_id}")
                return Response({
                    'success': True,
                    'message': 'Control assessment created successfully',
                    'control': ControlAssessmentSerializer(control).data
                }, status=status.HTTP_201_CREATED)
            else:
                logger.warning(f"Control creation validation failed: {serializer.errors}")
                return Response({
                    'success': False,
                    'error': 'Validation failed',
                    'details': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating control assessment: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Failed to create control assessment',
                'details': str(e),
                'error_type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== DASHBOARD & UTILITY VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@debug_request_response
def compliance_dashboard(request):
    """Get comprehensive compliance dashboard data"""
    try:
        user = request.user
        # logger.info(f"Dashboard request by user: {user.full_name}")
        
        if not (user.is_admin or user.role == 'compliance_officer'):
            # logger.warning(f"User {user.full_name} attempted to access dashboard without permission")
            return Response({
                'success': False,
                'error': 'Only admins and compliance officers can access dashboard'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Calculate overall statistics
        # logger.info("Calculating dashboard statistics...")
        
        try:
            total_audits = ComplianceAudit.objects.count()
            completed_audits = ComplianceAudit.objects.filter(status='completed').count()
            in_progress_audits = ComplianceAudit.objects.filter(status='in_progress').count()
            incident_audits = ComplianceAudit.objects.filter(audit_type='incident_response').count()
            # logger.info(f"Audit stats: total={total_audits}, completed={completed_audits}, in_progress={in_progress_audits}, incident={incident_audits}")
        except Exception as audit_error:
            # logger.error(f"Error getting audit stats: {str(audit_error)}")
            total_audits = completed_audits = in_progress_audits = incident_audits = 0
        
        try:
            total_findings = AuditFinding.objects.count()
            open_findings = AuditFinding.objects.filter(status='open').count()
            critical_findings = AuditFinding.objects.filter(risk_level='critical').count()
            # logger.info(f"Finding stats: total={total_findings}, open={open_findings}, critical={critical_findings}")
        except Exception as finding_error:
            # logger.error(f"Error getting finding stats: {str(finding_error)}")
            total_findings = open_findings = critical_findings = 0
        
        # Calculate overdue findings
        try:
            today = date.today()
            overdue_findings = AuditFinding.objects.filter(
                target_completion_date__lt=today,
                status__in=['open', 'in_progress']
            ).count()
            # logger.info(f"Overdue findings: {overdue_findings}")
        except Exception as overdue_error:
            # logger.error(f"Error calculating overdue findings: {str(overdue_error)}")
            overdue_findings = 0
        
        try:
            total_controls_assessed = ControlAssessment.objects.count()
            compliant_controls = ControlAssessment.objects.filter(status='compliant').count()
            compliance_rate = (compliant_controls / total_controls_assessed * 100) if total_controls_assessed > 0 else 0
            # logger.info(f"Control stats: total={total_controls_assessed}, compliant={compliant_controls}, rate={compliance_rate}")
        except Exception as control_error:
            # logger.error(f"Error getting control stats: {str(control_error)}")
            total_controls_assessed = compliant_controls = 0
            compliance_rate = 0
        
        try:
            total_standards = ComplianceStandard.objects.count()
            active_standards = ComplianceStandard.objects.filter(is_active=True).count()
            # logger.info(f"Standard stats: total={total_standards}, active={active_standards}")
        except Exception as standard_error:
            # logger.error(f"Error getting standard stats: {str(standard_error)}")
            total_standards = active_standards = 0
        
        # Get recent activities
        try:
            recent_audits = ComplianceAudit.objects.order_by('-created_at')[:5]
            recent_findings = AuditFinding.objects.order_by('-created_at')[:5]
            # logger.info(f"Recent activities: {recent_audits.count()} audits, {recent_findings.count()} findings")
        except Exception as recent_error:
            # logger.error(f"Error getting recent activities: {str(recent_error)}")
            recent_audits = []
            recent_findings = []
        
        # Get upcoming deadlines
        try:
            today = date.today()
            upcoming_date = today + timedelta(days=30)
            upcoming_findings = AuditFinding.objects.filter(
                target_completion_date__range=[today, upcoming_date],
                status__in=['open', 'in_progress']
            ).select_related('audit', 'assigned_to')[:10]
            # logger.info(f"Upcoming deadlines: {upcoming_findings.count()} findings")
        except Exception as upcoming_error:
            # logger.error(f"Error getting upcoming deadlines: {str(upcoming_error)}")
            upcoming_findings = []
        
        # Calculate compliance trends
        compliance_trends = []
        try:
            six_months_ago = today - timedelta(days=180)
            
            for i in range(6):
                try:
                    month_start = six_months_ago + timedelta(days=i*30)
                    month_end = month_start + timedelta(days=30)
                    
                    month_audits = ComplianceAudit.objects.filter(
                        actual_end_date__range=[month_start, month_end],
                        status='completed'
                    )
                    
                    if month_audits.exists():
                        avg_score = month_audits.aggregate(
                            avg_score=Avg('overall_score')
                        )['avg_score'] or 0
                    else:
                        avg_score = 0
                    
                    compliance_trends.append({
                        'month': month_start.strftime('%b %Y'),
                        'score': round(avg_score, 2),
                        'audits_count': month_audits.count()
                    })
                except Exception as month_error:
                    # logger.warning(f"Error calculating trend for month {i}: {str(month_error)}")
                    continue
            # logger.info(f"Compliance trends calculated: {len(compliance_trends)} months")
        except Exception as trend_error:
            logger.error(f"Error calculating compliance trends: {str(trend_error)}")
        
        dashboard_data = {
            # Overall Metrics
            'total_audits': total_audits,
            'completed_audits': completed_audits,
            'in_progress_audits': in_progress_audits,
            'incident_audits': incident_audits,
            
            # Finding Metrics
            'total_findings': total_findings,
            'open_findings': open_findings,
            'critical_findings': critical_findings,
            'overdue_findings': overdue_findings,
            
            # Control Metrics
            'total_controls_assessed': total_controls_assessed,
            'compliant_controls': compliant_controls,
            'compliance_rate': round(compliance_rate, 2),
            
            # Standard Metrics
            'total_standards': total_standards,
            'active_standards': active_standards,
            
            # Recent Activities
            'recent_audits': ComplianceAuditSerializer(recent_audits, many=True).data if recent_audits else [],
            'recent_findings': AuditFindingSerializer(recent_findings, many=True).data if recent_findings else [],
            
            # Upcoming Deadlines
            'upcoming_deadlines': [
                {
                    'id': f.id,
                    'title': f.title,
                    'due_date': f.target_completion_date.isoformat() if f.target_completion_date else None,
                    'days_remaining': (f.target_completion_date - today).days if f.target_completion_date else 0,
                    'audit': f.audit.audit_id,
                    'assigned_to': f.assigned_to.full_name if f.assigned_to else 'Unassigned'
                }
                for f in upcoming_findings
            ] if upcoming_findings else [],
            
            # Compliance Trends
            'compliance_trends': compliance_trends,
            
            # Quick Stats
            'quick_stats': {
                'audit_completion_rate': round((completed_audits / total_audits * 100), 2) if total_audits > 0 else 0,
                'finding_resolution_rate': round(((total_findings - open_findings) / total_findings * 100), 2) if total_findings > 0 else 0,
                'critical_findings_ratio': round((critical_findings / total_findings * 100), 2) if total_findings > 0 else 0,
                'incident_audit_ratio': round((incident_audits / total_audits * 100), 2) if total_audits > 0 else 0
            }
        }
        
        # logger.info("Dashboard data prepared successfully")
        return Response({
            'success': True,
            'dashboard': dashboard_data
        })
        
    except Exception as e:
        # logger.error(f"Error in compliance_dashboard: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to retrieve dashboard data',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@debug_request_response
def create_incident_based_audit(request):
    """Create an audit from incident(s)"""
    try:
        user = request.user
        # logger.info(f"Creating incident-based audit by user: {user.full_name}")
        
        if not (user.is_admin or user.role == 'compliance_officer'):
            # logger.warning(f"User {user.full_name} attempted to create incident-based audit without permission")
            return Response({
                'success': False,
                'error': 'Only admins and compliance officers can create incident-based audits'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Extract data
        data = request.data
        incident_ids = data.get('incident_ids', [])
        standard_id = data.get('standard_id')
        title = data.get('title')
        
        # logger.info(f"Creating audit for incidents: {incident_ids}, standard: {standard_id}")
        
        if not incident_ids:
            # logger.warning("No incidents provided for incident-based audit")
            return Response({
                'success': False,
                'error': 'At least one incident is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get incidents
        try:
            incidents = Incident.objects.filter(id__in=incident_ids)
            if not incidents.exists():
                # logger.warning(f"Incidents not found: {incident_ids}")
                return Response({
                    'success': False,
                    'error': 'Specified incidents not found'
                }, status=status.HTTP_404_NOT_FOUND)
            # logger.info(f"Found {incidents.count()} incidents")
        except Exception as incident_error:
            # logger.error(f"Error fetching incidents: {str(incident_error)}")
            return Response({
                'success': False,
                'error': 'Failed to fetch incidents',
                'details': str(incident_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Create audit data
        audit_data = {
            'title': title or f"Incident Response Audit - {incidents.first().incident_number}",
            'description': data.get('description', ''),
            'standard_id': standard_id,
            'audit_type': 'incident_response',
            'incident_ids': incident_ids,
            'planned_start_date': data.get('planned_start_date'),
            'planned_end_date': data.get('planned_end_date'),
            'lead_auditor_id': data.get('lead_auditor_id'),
            'priority': data.get('priority', 'high')
        }
        
        # logger.info(f"Audit data prepared: {audit_data}")
        
        serializer = ComplianceAuditSerializer(
            data=audit_data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            # logger.info(f"Incident-based audit data is valid: {serializer.validated_data}")
            
            # Create audit first without incidents
            validated_data = serializer.validated_data.copy()
            
            # Remove incident_ids for initial creation
            if 'incident_ids' in validated_data:
                validated_data.pop('incident_ids')
            
            # Set created_by
            validated_data['created_by'] = user
            
            # Create the audit
            audit = ComplianceAudit.objects.create(**validated_data)
            # logger.info(f"Audit created: {audit.audit_id}")
            
            # Add incidents
            audit.related_incidents.set(incidents)
            # logger.info(f"Added {incidents.count()} incidents to audit")
            
            # Calculate risk score
            risk_score = audit.calculate_risk_score()
            if risk_score:
                audit.risk_score_from_incident = risk_score
                audit.save(update_fields=['risk_score_from_incident'])
                logger.info(f"Set risk score: {risk_score}")
            
            # Update metrics
            audit.update_metrics()
            
            try:
                ActivityLogger.create_log(
                    user=user,
                    log_type='compliance',
                    activity='incident_audit_created',
                    description=f'Created incident-based audit {audit.audit_id} for {len(incidents)} incidents',
                    request=request,
                    response=None,
                    is_success=True
                )
            except Exception as log_error:
                logger.warning(f"Failed to create activity log: {str(log_error)}")
            
            # logger.info(f"Incident-based audit created successfully: {audit.audit_id}")
            return Response({
                'success': True,
                'message': 'Incident-based audit created successfully',
                'audit': ComplianceAuditSerializer(audit, context={'request': request}).data
            }, status=status.HTTP_201_CREATED)
        
        # logger.warning(f"Incident-based audit validation failed: {serializer.errors}")
        return Response({
            'success': False,
            'error': 'Validation failed',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error creating incident-based audit: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to create incident-based audit',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PERMISSION HELPER FUNCTIONS ====================

def can_access_audit(user, audit):
    """Check if user can access an audit"""
    try:
        if user.is_admin or user.role == 'compliance_officer':
            return True
        
        if audit.status == 'completed':
            return True
        
        if audit.lead_auditor == user or audit.created_by == user:
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking audit access: {str(e)}")
        return False


def can_update_audit(user, audit):
    """Check if user can update an audit"""
    try:
        if user.is_admin or user.role == 'compliance_officer':
            return True
        
        if audit.lead_auditor == user or audit.created_by == user:
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking audit update permission: {str(e)}")
        return False


def can_delete_audit(user, audit):
    """Check if user can delete an audit"""
    try:
        return user.is_admin or (user.role == 'compliance_officer' and audit.created_by == user)
    except Exception as e:
        logger.error(f"Error checking audit delete permission: {str(e)}")
        return False



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_incident_audits(request, incident_id):
    """Get all audits related to an incident"""
    try:
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            return Response({
                'success': False,
                'error': f'Incident with ID {incident_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            audits = ComplianceAudit.objects.filter(
                Q(related_incidents=incident) | Q(triggered_by_incident=incident)
            ).distinct().select_related('standard', 'lead_auditor')
        except Exception as audit_error:
            # logger.error(f"Error fetching audits: {str(audit_error)}")
            audits = ComplianceAudit.objects.none()
        
        serializer = ComplianceAuditSerializer(audits, many=True)
        
        return Response({
            'success': True,
            'incident': {
                'id': incident.id,
                'incident_number': incident.incident_number,
                'title': incident.title,
                'severity': incident.severity
            },
            'audits': serializer.data,
            'count': audits.count()
        })
        
    except Exception as e:
        # logger.error(f"Error getting incident audits: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to retrieve incident audits',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




# ==================== REPORT VIEWS ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_reports(request):
    """List all generated reports"""
    try:
        user = request.user
        
        if not (user.is_admin or user.role == 'compliance_officer'):
            return Response({
                'success': False,
                'error': 'Only admins and compliance officers can view reports'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Filter reports
        try:
            reports = ComplianceReport.objects.filter(generated_by=user)
            
            # Apply filters
            report_type = request.query_params.get('report_type')
            if report_type:
                reports = reports.filter(report_type=report_type)
            
            date_from = request.query_params.get('date_from')
            if date_from:
                reports = reports.filter(generated_at__date__gte=date_from)
            
            date_to = request.query_params.get('date_to')
            if date_to:
                reports = reports.filter(generated_at__date__lte=date_to)
            
            # Order by most recent
            reports = reports.order_by('-generated_at')
        except Exception as filter_error:
            # logger.error(f"Error filtering reports: {str(filter_error)}")
            reports = ComplianceReport.objects.none()
        
        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 20))
        result_page = paginator.paginate_queryset(reports, request)
        
        serializer = ComplianceReportSerializer(
            result_page,
            many=True,
            context={'request': request}
        )
        
        return paginator.get_paginated_response({
            'success': True,
            'reports': serializer.data
        })
        
    except ValueError as ve:
        # logger.error(f"ValueError in reports list: {str(ve)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Invalid parameter value',
            'details': str(ve)
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        # logger.error(f"Error listing reports: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to retrieve reports',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)











# complianceAuditApp/views.py - FIXED VERSION

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse, HttpResponse
from django.utils.timezone import now
from django.conf import settings
import os
import json
from pathlib import Path

from .models import ComplianceReport, ComplianceAudit
from .serializers import ComplianceReportSerializer
from userApp.utils import ActivityLogger


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """Generate compliance reports (audit reports only)"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.role == 'compliance_officer'):
            return Response({
                'success': False,
                'error': 'Only admins and compliance officers can generate reports'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data
        format_type = data.get('format', 'pdf')
        audit_ids = data.get('audit_ids', [])
        title = data.get('title', f'Audit Report - {now().strftime("%Y-%m-%d")}')
        
        # Validate input
        if not title:
            return Response({
                'success': False,
                'error': 'Report title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not audit_ids:
            return Response({
                'success': False,
                'error': 'Audit ID is required for report generation'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate report content
        report_content = None
        audit = None
        
        try:
            # Get the audit
            audit = ComplianceAudit.objects.get(id=audit_ids[0])
            print(f"✓ Found audit: {audit.audit_id} - {audit.title}")
            
            # Generate report content
            try:
                from complianceAuditApp.report_utils import ReportGenerator
                report_generator = ReportGenerator()
                
                print(f"✓ Generating {format_type} report for audit {audit.audit_id}")
                
                # Call the generator method
                report_content = report_generator.generate_audit_report(audit, format_type)
                
                if report_content:
                    print(f"✓ Report content generated successfully")
                    if hasattr(report_content, 'getvalue'):
                        size = len(report_content.getvalue())
                        print(f"✓ Content size: {size} bytes")
                else:
                    print(f"✗ Report generator returned None")
                    raise Exception("Report generator returned no content")
                    
            except ImportError as import_err:
                print(f"✗ Import error: {str(import_err)}")
                raise Exception(f"Failed to import ReportGenerator: {str(import_err)}")
            except AttributeError as attr_err:
                print(f"✗ Attribute error: {str(attr_err)}")
                raise Exception(f"ReportGenerator method missing: {str(attr_err)}")
            
        except ComplianceAudit.DoesNotExist:
            print(f"✗ Audit not found with ID: {audit_ids[0]}")
            return Response({
                'success': False,
                'error': 'Audit not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as gen_error:
            print(f"✗ Error generating report content: {str(gen_error)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'error': 'Failed to generate report content',
                'details': str(gen_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # ENSURE MEDIA DIRECTORIES EXIST
        try:
            # Create base media directory
            media_root = Path(settings.MEDIA_ROOT)
            media_root.mkdir(parents=True, exist_ok=True)
            
            # Create compliance_reports subdirectory
            reports_dir = media_root / 'compliance_reports'
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"✓ Media directories verified:")
            print(f"  Base: {media_root} (exists: {media_root.exists()})")
            print(f"  Reports: {reports_dir} (exists: {reports_dir.exists()})")
            
        except Exception as dir_error:
            print(f"✗ Error creating directories: {str(dir_error)}")
            return Response({
                'success': False,
                'error': 'Failed to create media directories',
                'details': str(dir_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Create report record first (without file)
        try:
            report = ComplianceReport.objects.create(
                title=title,
                report_type='audit_report',  # Fixed to audit_report only
                format=format_type,
                generated_by=user,
                parameters=json.dumps(data),
                audit=audit,
                standard=audit.standard if audit else None
            )
            print(f"✓ Report record created with ID: {report.report_id}")
        except Exception as create_error:
            print(f"✗ Error creating report record: {str(create_error)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'error': 'Failed to create report record',
                'details': str(create_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Save the generated file if content exists
        if report_content:
            try:
                from django.core.files.base import ContentFile
                
                # Create filename based on format
                file_extensions = {
                    'pdf': '.pdf',
                    'excel': '.xlsx',
                    'csv': '.csv',
                    'html': '.html'
                }
                extension = file_extensions.get(format_type, '.pdf')
                filename = f"audit_report_{audit.audit_id}_{now().strftime('%Y%m%d_%H%M%S')}{extension}"
                
                # Get the content from BytesIO object
                content_bytes = None
                if hasattr(report_content, 'getvalue'):
                    # It's a BytesIO object
                    content_bytes = report_content.getvalue()
                elif isinstance(report_content, bytes):
                    # It's already bytes
                    content_bytes = report_content
                elif isinstance(report_content, str):
                    # It's a string
                    content_bytes = report_content.encode('utf-8')
                else:
                    # Try to convert to bytes
                    content_bytes = str(report_content).encode('utf-8')
                
                if not content_bytes:
                    raise Exception("No content bytes to save")
                
                print(f"✓ Saving file: {filename}")
                print(f"✓ Content size: {len(content_bytes)} bytes")
                
                # Create ContentFile with the bytes
                content_file = ContentFile(content_bytes, name=filename)
                
                # Save the file using Django's file storage
                report.file_path.save(filename, content_file, save=True)
                
                # Refresh the report object to get updated file info
                report.refresh_from_db()
                
                # Get the absolute path for logging
                absolute_path = report.file_path.path
                relative_path = report.file_path.name
                file_size = report.file_path.size
                
                # Verify file was actually saved
                import os
                if not os.path.exists(absolute_path):
                    raise Exception(f"File not found after save: {absolute_path}")
                
                # Update the report with file info
                report.file_content = f"Audit report generated successfully. File: {relative_path}"
                report.save()
                
                # Log the save location
                print("\n" + "="*80)
                print(f"✓ AUDIT REPORT GENERATED AND SAVED SUCCESSFULLY")
                print("="*80)
                print(f"Audit ID:       {audit.audit_id}")
                print(f"Report ID:      {report.report_id}")
                print(f"Title:          {report.title}")
                print(f"Format:         {format_type}")
                print(f"Relative Path:  {relative_path}")
                print(f"Absolute Path:  {absolute_path}")
                print(f"File Size:      {file_size:,} bytes ({file_size/1024:.2f} KB)")
                print(f"File Exists:    {os.path.exists(absolute_path)}")
                print(f"Generated By:   {user.full_name} ({user.email})")
                print("="*80 + "\n")
                
            except Exception as file_error:
                print(f"\n{'='*80}")
                print(f"✗ ERROR SAVING REPORT FILE")
                print(f"{'='*80}")
                print(f"Error: {str(file_error)}")
                import traceback
                traceback.print_exc()
                print(f"{'='*80}\n")
                
                # Clean up the report record if file save failed
                report.delete()
                
                return Response({
                    'success': False,
                    'error': 'Failed to save report file',
                    'details': str(file_error)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            print(f"⚠ No report content generated for report {report.report_id}")
            # Don't delete the report, just return an error
            return Response({
                'success': False,
                'error': 'Report content was not generated',
                'report_id': report.report_id,
                'message': 'Report record created but file generation failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Log activity
        try:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity='report_generated',
                description=f'Generated audit report: {report.report_id} for audit {audit.audit_id}',
                request=request,
                response=None,
                is_success=True
            )
        except Exception as log_error:
            print(f"⚠ Failed to create activity log: {str(log_error)}")
        
        return Response({
            'success': True,
            'message': 'Audit report generated successfully',
            'report': ComplianceReportSerializer(report, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        print(f"✗ Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': 'Failed to generate report',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_report(request, report_id):
    """Download a generated report"""
    try:
        user = request.user
        
        print(f"\n{'='*80}")
        print(f"DOWNLOAD REQUEST RECEIVED")
        print(f"{'='*80}")
        print(f"User: {user.email}")
        print(f"Report ID: {report_id}")
        print(f"{'='*80}\n")
        
        # Get report
        try:
            report = ComplianceReport.objects.get(id=report_id)
            print(f"✓ Report found: {report.report_id}")
            print(f"✓ Report format: {report.format}")
            print(f"✓ File path: {report.file_path.name if report.file_path else 'No file'}")
        except ComplianceReport.DoesNotExist:
            print(f"✗ Report not found: {report_id}")
            return Response({
                'success': False,
                'error': f'Report with ID {report_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not (user.is_admin or user.role == 'compliance_officer' or report.generated_by == user):
            print(f"✗ Permission denied for user {user.email} to download report {report.report_id}")
            return Response({
                'success': False,
                'error': 'You do not have permission to download this report'
            }, status=status.HTTP_403_FORBIDDEN)
        
        print(f"✓ User has permission to download report")
        
        # Check if file exists
        if not report.file_path:
            print(f"✗ Report {report.report_id} has no file path")
            return Response({
                'success': False,
                'error': 'Report file not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get absolute path
        try:
            absolute_path = report.file_path.path
        except Exception as path_error:
            print(f"✗ Error getting file path: {str(path_error)}")
            return Response({
                'success': False,
                'error': 'Error accessing report file',
                'details': str(path_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if file actually exists
        if not os.path.exists(absolute_path):
            print(f"✗ File does not exist at path: {absolute_path}")
            return Response({
                'success': False,
                'error': 'Report file not found on server',
                'details': f'Expected path: {absolute_path}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get file size
        file_size = os.path.getsize(absolute_path)
        
        # Get filename from file path
        filename = os.path.basename(report.file_path.name)
        
        # Ensure filename has proper extension
        if not filename.lower().endswith(f'.{report.format}'):
            # If filename doesn't have proper extension, add it
            base_name, _ = os.path.splitext(filename)
            filename = f"{base_name}.{report.format}"
        
        print(f"✓ Serving file: {filename}")
        
        # Content type mapping - FIXED to use correct MIME types
        content_types = {
            'pdf': 'application/pdf',
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'csv': 'text/csv',
            'html': 'text/html',
            'json': 'application/json',
            'txt': 'text/plain'
        }
        
        # Determine correct content type
        content_type = content_types.get(report.format.lower(), 'application/octet-stream')
        
        # Increment download count
        try:
            report.download_count += 1
            report.save(update_fields=['download_count'])
        except Exception as update_error:
            print(f"⚠ Failed to update download count: {str(update_error)}")
        
        # Log the download
        print(f"\n{'='*80}")
        print(f"✓ SERVING REPORT FILE")
        print(f"{'='*80}")
        print(f"Report ID:       {report.report_id}")
        print(f"Title:           {report.title}")
        print(f"Format:          {report.format}")
        print(f"Content Type:    {content_type}")
        print(f"Filename:        {filename}")
        print(f"File Path:       {report.file_path.name}")
        print(f"Absolute Path:   {absolute_path}")
        print(f"File Size:       {file_size:,} bytes ({file_size/1024:.2f} KB)")
        print(f"Downloaded By:   {user.full_name} ({user.email})")
        print(f"Download Count:  {report.download_count}")
        print(f"{'='*80}\n")
        
        # Open and serve the file
        try:
            file_handle = open(absolute_path, 'rb')
            response = FileResponse(file_handle)
            
            # Set headers for proper file download
            response['Content-Type'] = content_type
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = file_size
            response['X-Report-Format'] = report.format
            response['X-Report-ID'] = report.report_id
            
            # Add caching headers to prevent browser caching issues
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            # Log activity
            try:
                ActivityLogger.create_log(
                    user=user,
                    log_type='compliance',
                    activity='report_downloaded',
                    description=f'Downloaded {report.format} report: {report.report_id}',
                    request=request,
                    is_success=True
                )
            except Exception as log_error:
                print(f"⚠ Failed to create activity log: {str(log_error)}")
            
            return response
            
        except Exception as file_error:
            print(f"\n{'='*80}")
            print(f"✗ ERROR SERVING REPORT FILE")
            print(f"{'='*80}")
            print(f"Report ID: {report.report_id}")
            print(f"Error: {str(file_error)}")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
            
            return Response({
                'success': False,
                'error': 'Failed to serve report file',
                'details': str(file_error)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        print(f"✗ Error downloading report: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': 'Failed to download report',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_report(request, report_id):
    """Delete a generated report"""
    try:
        user = request.user
        
        print(f"\n{'='*80}")
        print(f"DELETE REPORT REQUEST")
        print(f"{'='*80}")
        print(f"User: {user.email}")
        print(f"Report ID: {report_id}")
        
        # Get report
        try:
            report = ComplianceReport.objects.get(id=report_id)
            print(f"✓ Report found: {report.report_id}")
        except ComplianceReport.DoesNotExist:
            print(f"✗ Report not found: {report_id}")
            return Response({
                'success': False,
                'error': f'Report with ID {report_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions
        if not (user.is_admin or user.role == 'compliance_officer' or report.generated_by == user):
            print(f"✗ Permission denied for user {user.email} to delete report {report.report_id}")
            return Response({
                'success': False,
                'error': 'You do not have permission to delete this report'
            }, status=status.HTTP_403_FORBIDDEN)
        
        print(f"✓ User has permission to delete report")
        
        # Delete the file if it exists
        if report.file_path:
            try:
                absolute_path = report.file_path.path
                if os.path.exists(absolute_path):
                    os.remove(absolute_path)
                    print(f"✓ Deleted file: {absolute_path}")
            except Exception as file_error:
                print(f"⚠ Error deleting file: {str(file_error)}")
                # Continue with deletion even if file deletion fails
        
        # Store report info for logging
        report_info = {
            'report_id': report.report_id,
            'title': report.title,
            'format': report.format,
        }
        
        # Delete the report record
        report.delete()
        
        # Log activity
        try:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity='report_deleted',
                description=f'Deleted report: {report_info["report_id"]}',
                request=request,
                is_success=True
            )
        except Exception as log_error:
            print(f"⚠ Failed to create activity log: {str(log_error)}")
        
        print(f"\n{'='*80}")
        print(f"✓ REPORT DELETED SUCCESSFULLY")
        print(f"{'='*80}")
        print(f"Report ID:       {report_info['report_id']}")
        print(f"Title:           {report_info['title']}")
        print(f"Format:          {report_info['format']}")
        print(f"Deleted By:      {user.full_name} ({user.email})")
        print(f"{'='*80}\n")
        
        return Response({
            'success': True,
            'message': 'Report deleted successfully',
            'deleted_report': report_info
        })
        
    except Exception as e:
        print(f"✗ Error deleting report: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': 'Failed to delete report',
            'details': str(e),
            'error_type': type(e).__name__
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)