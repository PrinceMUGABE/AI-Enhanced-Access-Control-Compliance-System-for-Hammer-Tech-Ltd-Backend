from rest_framework import serializers
from .models import Incident, IncidentComment, IncidentAttachment, Report, ReportSchedule
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department
from userApp.serializers import DepartmentSerializer, UserLogSerializer
from django.utils.timezone import now
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, generics, filters
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, F


class CustomUserSerializer(serializers.ModelSerializer):
    """Serializer for CustomUser model with consistent output"""
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'full_name', 'role', 'work_mail_address',
            'is_active', 'status', 'availability_status', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def to_representation(self, instance):
        """Ensure consistent output format"""
        representation = super().to_representation(instance)
        
        # Ensure all fields have default values
        for field in self.Meta.fields:
            if field not in representation:
                representation[field] = ''
            elif representation[field] is None:
                representation[field] = ''
        
        return representation



class IncidentListCreateAPIView(generics.ListCreateAPIView):
    """List and create incidents without Django pagination"""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'severity', 'priority', 'danger_zone', 'department']
    search_fields = ['incident_number', 'title', 'description', 'log__user_email']
    ordering_fields = ['created_at', 'updated_at', 'severity', 'priority']
    ordering = ['-created_at']
    pagination_class = None  # Disable Django REST Framework pagination
    
    def get_serializer_class(self):
        """Use different serializers for list vs create"""
        if self.request.method == 'GET':
            return IncidentListSerializer
        return IncidentSerializer
    
    def get_queryset(self):
        """Get incidents based on user role"""
        user = self.request.user
        
        # Build base queryset with select_related for performance
        queryset = Incident.objects.select_related(
            'log', 'assigned_to', 'created_by', 'department'
        )
        
        # Apply role-based filtering
        if user.is_admin:
            # Admin can see all incidents
            return queryset
        
        elif user.is_hr:
            # HR can see all incidents except those marked as internal/confidential
            return queryset
        
        elif user.role == 'security_analyst':
            # Security analysts can see incidents in their departments
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
            # Compliance officers can see incidents related to compliance
            return queryset.filter(
                Q(assigned_to=user) |
                Q(created_by=user) |
                Q(severity__in=['high', 'critical'])
            )
        
        elif user.role == 'employee':
            # Employees can only see incidents related to them
            return queryset.filter(
                Q(log__user_email=user.email) |
                Q(assigned_to=user) |
                Q(created_by=user)
            )
        
        else:
            # Default: only own incidents
            return queryset.filter(
                Q(assigned_to=user) |
                Q(created_by=user)
            )
    
    def list(self, request, *args, **kwargs):
        """Custom list response with manual pagination for frontend"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get pagination parameters from frontend
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        # Calculate slice for pagination
        total_count = queryset.count()
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_queryset = queryset[start_index:end_index]
        
        serializer = self.get_serializer(paginated_queryset, many=True)
        
        return Response({
            'success': True,
            'incidents': serializer.data,
            'pagination': {
                'current_page': page,
                'page_size': page_size,
                'total_items': total_count,
                'total_pages': (total_count + page_size - 1) // page_size if page_size > 0 else 1,
                'has_next': end_index < total_count,
                'has_previous': start_index > 0
            }
        })

        
class IncidentCommentSerializer(serializers.ModelSerializer):
    """Serializer for incident comments"""
    user_details = serializers.SerializerMethodField()
    
    class Meta:
        model = IncidentComment
        fields = [
            'id', 'incident', 'user', 'user_details',
            'comment', 'is_internal', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'user']
    
    def get_user_details(self, obj):
        return {
            'id': obj.user.id,
            'full_name': obj.user.full_name,
            'email': obj.user.email,
            'role': obj.user.role
        }
    
    def create(self, validated_data):
        # Set the current user as comment author
        request = self.context.get('request')
        if request and request.user:
            validated_data['user'] = request.user
        return super().create(validated_data)


class IncidentAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for incident attachments"""
    uploaded_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = IncidentAttachment
        fields = [
            'id', 'incident', 'file', 'file_name', 'file_type',
            'file_size', 'uploaded_by', 'uploaded_by_details',
            'uploaded_at', 'description'
        ]
        read_only_fields = [
            'id', 'file_name', 'file_type', 'file_size',
            'uploaded_by', 'uploaded_at'
        ]
    
    def get_uploaded_by_details(self, obj):
        if obj.uploaded_by:
            return {
                'id': obj.uploaded_by.id,
                'full_name': obj.uploaded_by.full_name,
                'email': obj.uploaded_by.email
            }
        return None
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user:
            validated_data['uploaded_by'] = request.user
        
        # Extract file metadata
        file = validated_data.get('file')
        if file:
            validated_data['file_name'] = file.name
            validated_data['file_type'] = file.name.split('.')[-1] if '.' in file.name else 'unknown'
            validated_data['file_size'] = file.size
        
        return super().create(validated_data)


class IncidentSerializer(serializers.ModelSerializer):
    """Serializer for incidents with consistent data structure"""
    log_details = serializers.SerializerMethodField()
    assigned_to_details = serializers.SerializerMethodField()
    created_by_details = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    comments = IncidentCommentSerializer(many=True, read_only=True)
    attachments = IncidentAttachmentSerializer(many=True, read_only=True)
    time_to_resolution = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    
    # Add these fields to ensure consistent response
    assigned_to_id = serializers.SerializerMethodField()
    created_by_id = serializers.SerializerMethodField()
    department_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Incident
        fields = [
            'id', 'incident_number', 'log', 'log_details',
            'assigned_to', 'assigned_to_id', 'assigned_to_details',
            'created_by', 'created_by_id', 'created_by_details',
            'title', 'description', 'status', 'severity', 'priority',
            'risk_score', 'danger_zone', 'created_at', 'updated_at',
            'assigned_at', 'resolved_at', 'resolution_notes',
            'department', 'department_id', 'department_details',
            'sla_due_date', 'sla_violated', 'comments', 'attachments',
            'time_to_resolution', 'is_overdue'
        ]
        read_only_fields = [
            'id', 'incident_number', 'created_at', 'updated_at',
            'assigned_at', 'resolved_at', 'sla_violated'
        ]
    
    def get_assigned_to_id(self, obj):
        """Always return assigned_to ID, even if assigned_to is an object"""
        if obj.assigned_to:
            return obj.assigned_to.id
        return None
    
    def get_created_by_id(self, obj):
        """Always return created_by ID"""
        if obj.created_by:
            return obj.created_by.id
        return None
    
    def get_department_id(self, obj):
        """Always return department ID"""
        if obj.department:
            return obj.department.id
        return None
    
    def get_assigned_to_details(self, obj):
        """Consistent user details structure"""
        if obj.assigned_to:
            return self.get_user_details(obj.assigned_to)
        return None
    
    def get_created_by_details(self, obj):
        """Consistent user details structure"""
        if obj.created_by:
            return self.get_user_details(obj.created_by)
        return None
    
    def get_user_details(self, user):
        """Helper method to return consistent user structure"""
        if not user:
            return None
        
        return {
            'id': user.id,
            'full_name': user.full_name or '',
            'email': user.email or '',
            'role': user.role or '',
            'work_mail_address': user.work_mail_address or '',
            'is_active': user.is_active,
            'status': user.status or ''
        }
    
    def get_department_details(self, obj):
        """Consistent department details structure"""
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name or '',
                'status': obj.department.status or ''
            }
        return None
    
    def get_log_details(self, obj):
        """Consistent log details structure"""
        if obj.log:
            return {
                'id': obj.log.id,
                'activity': obj.log.activity or '',
                'description': obj.log.description or '',
                'user_email': obj.log.user_email or '',
                'timestamp': obj.log.timestamp,
                'is_success': obj.log.is_success,
                'ip_address': obj.log.ip_address or '',
                'endpoint': obj.log.endpoint or ''
            }
        return None
    
    def get_time_to_resolution(self, obj):
        """Format time to resolution consistently"""
        if obj.time_to_resolution:
            total_seconds = obj.time_to_resolution.total_seconds()
            days = int(total_seconds // 86400)
            hours = int((total_seconds % 86400) // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            if days > 0:
                return f"{days}d {hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        return None
    
    # Override to_human_representation method to ensure consistent output
    def to_representation(self, instance):
        """Override to ensure consistent data structure"""
        representation = super().to_representation(instance)
        
        # Ensure assigned_to is always an ID (not an object)
        if 'assigned_to' in representation and representation['assigned_to']:
            if isinstance(representation['assigned_to'], dict):
                # If it's already a dict, extract the ID
                representation['assigned_to'] = representation['assigned_to'].get('id', None)
        
        # Ensure created_by is always an ID
        if 'created_by' in representation and representation['created_by']:
            if isinstance(representation['created_by'], dict):
                representation['created_by'] = representation['created_by'].get('id', None)
        
        # Ensure department is always an ID
        if 'department' in representation and representation['department']:
            if isinstance(representation['department'], dict):
                representation['department'] = representation['department'].get('id', None)
        
        # Add calculated fields for frontend convenience
        representation['is_overdue'] = instance.is_overdue
        if instance.sla_due_date and instance.is_overdue:
            from django.utils.timezone import now
            overdue_hours = (now() - instance.sla_due_date).total_seconds() / 3600
            representation['overdue_hours'] = round(overdue_hours, 1)
        else:
            representation['overdue_hours'] = 0
        
        return representation



class CreateIncidentFromLogSerializer(serializers.Serializer):
    """Serializer for creating incidents from logs"""
    log_id = serializers.IntegerField(required=True)
    title = serializers.CharField(max_length=200, required=True)
    description = serializers.CharField(required=True)
    severity = serializers.ChoiceField(choices=Incident.SEVERITY_CHOICES, default='medium')
    priority = serializers.ChoiceField(choices=Incident.PRIORITY_CHOICES, default='medium')
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
        ),
        required=False,
        allow_null=True
    )
    
    def validate_log_id(self, value):
        """Validate that log exists and is suitable for incident creation"""
        try:
            log = UserLog.objects.get(id=value)
            
            # Check if log already has incidents
            if log.incidents.exists():
                raise serializers.ValidationError('This log already has associated incidents.')
            
            # EXPANDED: Consider more activities as security incidents
            security_incident_activities = [
                # Login/Access related
                'login_failed',
                'access_denied', 
                'unauthorized_access',
                'multiple_failed_logins',
                'brute_force_attempt',
                
                # Assessment and scanning
                'vulnerability_assessment_view',
                'vulnerability_scan',
                'risk_assessment_view',
                'risk_assessment_executed',
                'risk_assessment_created',
                'risk_assessment_updated',
                'security_audit_view',
                'security_scan',
                'penetration_test',
                
                # Security incidents
                'sensitive_data_access',
                'privilege_escalation',
                'suspicious_activity',
                'data_breach_detected',
                'system_breach',
                
                # Compliance
                'policy_violation',
                'compliance_violation',
                'audit_failure',
                
                # User management incidents
                'mass_user_create',
                'mass_user_update',
                'user_deactivate',
                'role_change',
                
                # System incidents
                'system_failure',
                'service_down',
                'database_error',
                'api_error'
            ]
            
            # Check if activity is in security incident list OR has high risk score
            is_security_incident = (
                log.activity in security_incident_activities or
                (hasattr(log, 'risk_score') and log.risk_score >= 40) or  # Lowered threshold
                (hasattr(log, 'danger_zone') and log.danger_zone is True) or
                (log.is_success is False)  # Failed actions are suspicious
            )
            
            if not is_security_incident:
                raise serializers.ValidationError(
                    f'This log (activity: {log.activity}) does not indicate a security incident. '
                    f'Only security-related activities can create incidents.'
                )
            
            return value
        except UserLog.DoesNotExist:
            raise serializers.ValidationError('Log not found.')
    
    def calculate_risk_score(self, log):
        """Calculate risk score based on log attributes"""
        risk_score = 0
        
        # Base risk by activity type
        activity_risk_map = {
            # Critical risk (90-100)
            'data_breach_detected': 95,
            'system_breach': 100,
            'privilege_escalation': 90,
            
            # High risk (70-89)
            'unauthorized_access': 85,
            'brute_force_attempt': 80,
            
            # Medium-high risk (60-69)
            'risk_assessment_executed': 65,
            'risk_assessment_view': 60,
            'risk_assessment_created': 60,
            'risk_assessment_updated': 55,
            'vulnerability_assessment_view': 65,
            'vulnerability_scan': 60,
            'security_audit_view': 60,
            'multiple_failed_logins': 70,
            
            # Medium risk (40-59)
            'sensitive_data_access': 65,
            'access_denied': 60,
            'login_failed': 55,
            'suspicious_activity': 65,
            'compliance_violation': 60,
            'policy_violation': 55,
            'audit_failure': 60,
            
            # Lower risk (20-39)
            'view_user_logs': 40,
            'user_create': 35,
            'user_update': 30,
            'user_deactivate': 45,
            'role_change': 50,
            
            # Low risk (0-19)
            'profile_update': 25,
            'password_change': 30,
            'login': 15,
            'logout': 10,
        }
        
        # Get base risk from activity
        base_risk = activity_risk_map.get(log.activity, 25)
        risk_score += base_risk
        
        # Adjust based on success/failure (failed actions are riskier)
        if not log.is_success:
            risk_score += 20
        
        # Adjust based on endpoint sensitivity
        sensitive_endpoints = [
            '/admin/', '/api/admin/', '/user-management/', 
            '/security/', '/compliance/', '/audit/',
            '/risk-assessment/', '/vulnerabilities/',
            '/user-delete/', '/mass-update/'
        ]
        
        if log.endpoint:
            for endpoint in sensitive_endpoints:
                if endpoint in log.endpoint:
                    risk_score += 15
                    break
        
        # Adjust based on recent activity (multiple similar actions)
        from datetime import timedelta
        from django.utils.timezone import now
        
        # Count recent similar activities from same user/IP
        recent_similar = UserLog.objects.filter(
            Q(user_email=log.user_email) | Q(ip_address=log.ip_address),
            activity=log.activity,
            timestamp__gte=now() - timedelta(minutes=30)
        ).count()
        
        if recent_similar > 5:
            risk_score += 20
        elif recent_similar > 3:
            risk_score += 10
        elif recent_similar > 1:
            risk_score += 5
        
        # Cap at 100
        return min(risk_score, 100)
    
    def create(self, validated_data):
        log_id = validated_data.pop('log_id')
        log = UserLog.objects.get(id=log_id)
        
        # Calculate risk score based on log (override if frontend provided)
        risk_score = validated_data.pop('risk_score', None)
        if risk_score is None:
            risk_score = self.calculate_risk_score(log)
        
        # Determine if in danger zone (risk > 70)
        danger_zone = risk_score > 70
        
        incident = Incident.objects.create(
            log=log,
            risk_score=risk_score,
            danger_zone=danger_zone,
            **validated_data
        )
        
        return incident

class ReportSerializer(serializers.ModelSerializer):
    """Serializer for reports"""
    generated_by_details = serializers.SerializerMethodField()
    shared_with_details = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Report
        fields = [
            'id', 'report_number', 'title', 'description',
            'report_type', 'format', 'file_path', 'file_url',
            'file_size', 'generated_by', 'generated_by_details',
            'generated_at', 'parameters', 'is_scheduled',
            'schedule_id', 'is_public', 'shared_with',
            'shared_with_details', 'download_count',
            'last_downloaded_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'report_number', 'generated_at', 'download_count',
            'last_downloaded_at', 'file_size', 'metadata'
        ]
    
    def get_generated_by_details(self, obj):
        if obj.generated_by:
            return {
                'id': obj.generated_by.id,
                'full_name': obj.generated_by.full_name,
                'email': obj.generated_by.email,
                'role': obj.generated_by.role
            }
        return None
    
    def get_shared_with_details(self, obj):
        return [
            {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email
            }
            for user in obj.shared_with.all()
        ]
    
    def get_file_url(self, obj):
        """Get the file URL for downloading"""
        if obj.file_path:
            # Construct full URL
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(f'/incidents/reports/{obj.id}/file/')
        return None
    
    def validate(self, data):
        request = self.context.get('request')
        
        # Check permissions for public reports
        if 'is_public' in data and data['is_public']:
            if not request.user.is_admin and not request.user.is_hr:
                raise serializers.ValidationError({
                    'is_public': 'Only admin or HR can create public reports.'
                })
        
        return data
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user:
            validated_data['generated_by'] = request.user
        
        # Remove shared_with from validated_data to handle after creation
        shared_with_users = validated_data.pop('shared_with', [])
        
        report = super().create(validated_data)
        
        # Add shared_with users
        if shared_with_users:
            report.shared_with.set(shared_with_users)
        
        return report  


class ReportScheduleSerializer(serializers.ModelSerializer):
    """Serializer for report schedules"""
    created_by_details = serializers.SerializerMethodField()
    recipients_details = serializers.SerializerMethodField()
    next_run_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ReportSchedule
        fields = [
            'id', 'name', 'description', 'report_type',
            'frequency', 'cron_expression', 'start_date',
            'end_date', 'next_run', 'next_run_display',
            'last_run', 'parameters', 'format', 'recipients',
            'recipients_details', 'additional_emails',
            'is_active', 'created_by', 'created_by_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_run']
    
    def get_created_by_details(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'full_name': obj.created_by.full_name,
                'email': obj.created_by.email
            }
        return None
    
    def get_recipients_details(self, obj):
        return [
            {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email
            }
            for user in obj.recipients.all()
        ]
    
    def get_next_run_display(self, obj):
        if obj.next_run:
            return obj.next_run.strftime('%Y-%m-%d %H:%M:%S')
        return None
    
    def validate(self, data):
        request = self.context.get('request')
        
        # Validate start and end dates
        if 'start_date' in data and 'end_date' in data:
            if data['end_date'] and data['start_date'] >= data['end_date']:
                raise serializers.ValidationError({
                    'end_date': 'End date must be after start date.'
                })
        
        # Check permissions for recipients
        if 'recipients' in data:
            if not request.user.is_admin and not request.user.is_hr:
                raise serializers.ValidationError({
                    'recipients': 'Only admin or HR can set recipients for scheduled reports.'
                })
        
        return data
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


class GenerateReportSerializer(serializers.Serializer):
    """Serializer for report generation request"""
    report_type = serializers.ChoiceField(choices=Report.REPORT_TYPE_CHOICES)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    format = serializers.ChoiceField(choices=Report.FORMAT_CHOICES, default='pdf')
    
    # Filter parameters - allow null values
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    severity = serializers.ChoiceField(
        choices=Incident.SEVERITY_CHOICES,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    status = serializers.ChoiceField(
        choices=Incident.INCIDENT_STATUS_CHOICES,
        required=False,
        allow_null=True,
        allow_blank=True
    )
    department_id = serializers.IntegerField(required=False, allow_null=True)
    user_id = serializers.IntegerField(required=False, allow_null=True)
    
    # Access control
    is_public = serializers.BooleanField(default=False)
    shared_with = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )

    send_email = serializers.BooleanField(default=True)
    email_recipients = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Comma-separated list of additional email recipients"
    )
    
    def validate(self, data):
        # Validate date range only if both dates are provided and not null
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if date_from and date_to:
            if date_from > date_to:
                raise serializers.ValidationError({
                    'date_from': 'Start date must be before end date.'
                })
        
        return data
    



class ManualIncidentAssignmentSerializer(serializers.Serializer):
    """Serializer for manual incident assignment"""
    incident_id = serializers.IntegerField(required=True)
    assigned_to_id = serializers.IntegerField(required=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=Incident.PRIORITY_CHOICES, required=False)
    update_status = serializers.BooleanField(default=True, help_text="Whether to update incident status to 'assigned'")
    
    def validate(self, data):
        incident_id = data.get('incident_id')
        assigned_to_id = data.get('assigned_to_id')
        
        # Validate incident exists
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise serializers.ValidationError({"incident_id": "Incident not found."})
        
        # Validate user exists and can be assigned
        try:
            user = CustomUser.objects.get(id=assigned_to_id, is_active=True)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"assigned_to_id": "User not found or inactive."})
        
        # Check if user can handle incidents
        if user.role not in ['admin', 'hr_manager', 'security_analyst', 'compliance_officer']:
            raise serializers.ValidationError({
                "assigned_to_id": "This user cannot be assigned incidents."
            })
        
        # Store objects for later use
        data['incident'] = incident
        data['user'] = user
        
        return data
    
    def create(self, validated_data):
        incident = validated_data['incident']
        user = validated_data['user']
        due_date = validated_data.get('due_date')
        priority = validated_data.get('priority')
        update_status = validated_data.get('update_status', True)
        
        # Store old assigned user
        old_assigned_to = incident.assigned_to
        
        # Assign user
        incident.assigned_to = user
        incident.assigned_at = now()
        
        # Only update status if requested and incident is not already assigned
        if update_status and incident.status != 'assigned':
            incident.status = 'assigned'
        
        # Set SLA due date if provided
        if due_date:
            incident.sla_due_date = due_date
        elif not incident.sla_due_date:
            # Set default SLA (e.g., based on severity)
            incident.set_sla_due_date()
        
        # Update priority if provided
        if priority:
            incident.priority = priority
        
        # Save the incident
        incident.save()
        
        # Send notification
        from .utils import NotificationUtils
        NotificationUtils.send_incident_assignment_notification(incident)
        
        # Store the old assigned user info for the response
        incident._old_assigned_to = old_assigned_to
        
        return incident


class IncidentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing incidents"""
    assigned_to_details = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    overdue_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = Incident
        fields = [
            'id', 'incident_number', 'title', 'description',
            'status', 'severity', 'priority', 'risk_score',
            'created_at', 'assigned_at', 'sla_due_date',
            'assigned_to', 'assigned_to_details', 'department',
            'department_name', 'is_overdue', 'overdue_hours',
            'danger_zone'
        ]
    
    def get_assigned_to_details(self, obj):
        """Return minimal user info for lists"""
        if obj.assigned_to:
            return {
                'id': obj.assigned_to.id,
                'full_name': obj.assigned_to.full_name or '',
                'email': obj.assigned_to.email or ''
            }
        return None
    
    def get_department_name(self, obj):
        """Return department name"""
        if obj.department:
            return obj.department.name
        return ''
    
    def get_overdue_hours(self, obj):
        """Calculate overdue hours if SLA is violated"""
        if obj.sla_due_date and obj.is_overdue:
            from django.utils.timezone import now
            overdue_hours = (now() - obj.sla_due_date).total_seconds() / 3600
            return round(overdue_hours, 1)
        return 0


class IncidentSLAUpdateSerializer(serializers.Serializer):
    """Serializer for updating incident SLA"""
    incident_id = serializers.IntegerField(required=True)
    sla_due_date = serializers.DateTimeField(required=True)
    
    def validate(self, data):
        incident_id = data.get('incident_id')
        
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise serializers.ValidationError({"incident_id": "Incident not found."})
        
        # Validate due date is in future
        if data['sla_due_date'] <= now():
            raise serializers.ValidationError({
                "sla_due_date": "SLA due date must be in the future."
            })
        
        data['incident'] = incident
        return data
    
    def create(self, validated_data):
        incident = validated_data['incident']
        sla_due_date = validated_data['sla_due_date']
        
        incident.sla_due_date = sla_due_date
        incident.sla_violated = False  # Reset violation status
        incident.save()
        
        return incident
    




class HasAssignedIncidentsSerializer(serializers.Serializer):
    """Serializer for checking if user has assigned incidents"""
    has_assigned_incidents = serializers.BooleanField(read_only=True)
    assigned_count = serializers.IntegerField(read_only=True)
    pending_count = serializers.IntegerField(read_only=True)
    in_progress_count = serializers.IntegerField(read_only=True)

class UpdateAssignedIncidentStatusSerializer(serializers.Serializer):
    """Serializer for updating status of assigned incidents"""
    incident_id = serializers.IntegerField(required=True)
    new_status = serializers.ChoiceField(
        choices=Incident.INCIDENT_STATUS_CHOICES,
        required=True
    )
    resolution_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Required when changing status to 'resolved' or 'closed'"
    )
    
    def validate(self, data):
        incident_id = data.get('incident_id')
        new_status = data.get('new_status')
        resolution_notes = data.get('resolution_notes', '')
        
        # Validate incident exists and is assigned to current user
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            raise serializers.ValidationError({"incident_id": "Incident not found."})
        
        # Check if incident is assigned to current user
        request = self.context.get('request')
        if request and request.user:
            if incident.assigned_to != request.user:
                raise serializers.ValidationError({
                    "incident_id": "This incident is not assigned to you."
                })
        
        # Validate status transitions
        current_status = incident.status
        if current_status != new_status:
            allowed_transitions = {
                'pending': ['investigating', 'assigned'],
                'investigating': ['assigned', 'in_progress', 'pending'],
                'assigned': ['in_progress', 'escalated', 'investigating'],
                'in_progress': ['resolved', 'escalated', 'assigned'],
                'resolved': ['closed', 'in_progress'],
                'escalated': ['assigned', 'in_progress'],
                'closed': []  # No transitions from closed
            }
            
            if current_status in allowed_transitions:
                if new_status not in allowed_transitions[current_status]:
                    raise serializers.ValidationError({
                        "new_status": f"Cannot change status from {current_status} to {new_status}."
                    })
        
        # Validate resolution notes for resolved/closed status
        if new_status in ['resolved', 'closed'] and not resolution_notes:
            raise serializers.ValidationError({
                "resolution_notes": "Resolution notes are required when resolving or closing an incident."
            })
        
        # Store incident for later use
        data['incident'] = incident
        
        return data