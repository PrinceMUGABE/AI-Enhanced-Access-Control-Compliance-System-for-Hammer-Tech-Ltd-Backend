from rest_framework import serializers
from .models import (
    ComplianceStandard, ComplianceAudit,
    ControlAssessment, AuditFinding, ComplianceReport
)
from userApp.serializers import CustomUserSerializer as UserSerializer
from incidentApp.serializers import IncidentSerializer
import json
from userApp.models import CustomUser
from incidentApp.models import Incident, IncidentAttachment, IncidentComment

        
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
        
        
        return representation



class ComplianceStandardSerializer(serializers.ModelSerializer):
    """Serializer for compliance standards"""
    
    created_by_details = serializers.SerializerMethodField()
    active_audits_count = serializers.SerializerMethodField()
    compliance_score = serializers.SerializerMethodField()
    
    class Meta:
        model = ComplianceStandard
        fields = [
            'id', 'name', 'standard_type', 'version', 'description',
            'is_active',
            'total_controls', 'mandatory_controls',
            'created_by', 'created_by_details',
            'created_at', 'updated_at',
            'active_audits_count', 'compliance_score'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']
    
    def get_created_by_details(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'full_name': obj.created_by.full_name,
                'email': obj.created_by.email
            }
        return None
    
    def get_active_audits_count(self, obj):
        return obj.active_audits_count
    
    def get_compliance_score(self, obj):
        return obj.compliance_score
    
    def validate(self, data):
        if data.get('mandatory_controls', 0) > data.get('total_controls', 0):
            raise serializers.ValidationError({
                'mandatory_controls': 'Mandatory controls cannot exceed total controls.'
            })
        
        return data


class AuditFindingSerializer(serializers.ModelSerializer):
    """Serializer for audit findings"""
    
    audit_details = serializers.SerializerMethodField()
    created_by_details = serializers.SerializerMethodField()
    assigned_to_details = serializers.SerializerMethodField()
    related_incident_details = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditFinding
        fields = [
            'id', 'audit', 'audit_details',
            'title', 'description', 'finding_type', 'risk_level',
            'status', 'target_completion_date', 'actual_completion_date',
            'evidence', 'remediation_plan',
            'related_incident', 'related_incident_details',
            'assigned_to', 'assigned_to_details',
            'created_by', 'created_by_details',
            'created_at', 'updated_at',
            'is_overdue'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']
    
    def get_audit_details(self, obj):
        if obj.audit:
            return {
                'id': obj.audit.id,
                'audit_id': obj.audit.audit_id,
                'title': obj.audit.title,
                'standard_name': obj.audit.standard.name if obj.audit.standard else None
            }
        return None
    
    def get_created_by_details(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'full_name': obj.created_by.full_name,
                'email': obj.created_by.email
            }
        return None
    
    def get_assigned_to_details(self, obj):
        if obj.assigned_to:
            return {
                'id': obj.assigned_to.id,
                'full_name': obj.assigned_to.full_name,
                'email': obj.assigned_to.email
            }
        return None
    
    def get_related_incident_details(self, obj):
        if obj.related_incident:
            return {
                'id': obj.related_incident.id,
                'incident_number': obj.related_incident.incident_number,
                'title': obj.related_incident.title,
                'severity': obj.related_incident.severity,
                'status': obj.related_incident.status
            }
        return None
    
    def get_is_overdue(self, obj):
        return obj.is_overdue


class ControlAssessmentSerializer(serializers.ModelSerializer):
    """Serializer for control assessments"""
    
    audit_details = serializers.SerializerMethodField()
    assessed_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ControlAssessment
        fields = [
            'id', 'audit', 'audit_details',
            'control_id', 'control_name', 'control_description',
            'status', 'assessment_date', 'assessed_by', 'assessed_by_details',
            'evidence', 'notes', 'attachments',
            'remediation_required', 'remediation_status',
            'remediation_deadline', 'remediation_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_audit_details(self, obj):
        if obj.audit:
            return {
                'id': obj.audit.id,
                'audit_id': obj.audit.audit_id,
                'title': obj.audit.title
            }
        return None
    
    def get_assessed_by_details(self, obj):
        if obj.assessed_by:
            return {
                'id': obj.assessed_by.id,
                'full_name': obj.assessed_by.full_name,
                'email': obj.assessed_by.email
            }
        return None


class ComplianceAuditSerializer(serializers.ModelSerializer):
    """Serializer for compliance audits"""
    
    # Write-only fields
    standard_id = serializers.PrimaryKeyRelatedField(
        queryset=ComplianceStandard.objects.filter(is_active=True),
        source='standard',
        write_only=True,
        required=True
    )
    lead_auditor_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(is_active=True),
        source='lead_auditor',
        write_only=True,
        required=False,
        allow_null=True
    )
    incident_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        default=list
    )
    
    # Read-only details
    standard_details = serializers.SerializerMethodField()
    lead_auditor_details = serializers.SerializerMethodField()
    created_by_details = serializers.SerializerMethodField()
    related_incidents_details = serializers.SerializerMethodField()
    
    # Calculated fields
    findings_count = serializers.SerializerMethodField()
    control_assessments_count = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = ComplianceAudit
        fields = [
            # IDs
            'id', 'audit_id',
            
            # Basic Information
            'title', 'description', 'audit_type', 'status', 'priority',
            
            # Relationships (write-only IDs)
            'standard_id', 'lead_auditor_id', 'incident_ids',
            
            # Schedule
            'planned_start_date', 'planned_end_date',
            'actual_start_date', 'actual_end_date',
            
            # Metrics
            'overall_score', 'compliance_rate',
            'controls_assessed', 'total_findings', 'open_findings', 'critical_findings',
            
            # Read-only details
            'standard', 'lead_auditor', 'created_by',
            'standard_details', 'lead_auditor_details', 'created_by_details',
            'related_incidents_details',
            
            # Calculated fields
            'findings_count', 'control_assessments_count', 'progress_percentage',
            
            # Timestamps
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'audit_id', 'created_at', 'updated_at',
            'created_by', 'standard', 'lead_auditor',
            'overall_score', 'compliance_rate',
            'controls_assessed', 'total_findings', 'open_findings', 'critical_findings'
        ]
    
    def get_standard_details(self, obj):
        if obj.standard:
            return {
                'id': obj.standard.id,
                'name': obj.standard.name,
                'standard_type': obj.standard.standard_type,
                'version': obj.standard.version
            }
        return None
    
    def get_lead_auditor_details(self, obj):
        if obj.lead_auditor:
            return UserSerializer(obj.lead_auditor).data
        return None
    
    def get_created_by_details(self, obj):
        if obj.created_by:
            return UserSerializer(obj.created_by).data
        return None
    
    def get_related_incidents_details(self, obj):
        incidents = obj.related_incidents.all()
        return IncidentSerializer(incidents, many=True).data
    
    def get_findings_count(self, obj):
        return obj.findings.count()
    
    def get_control_assessments_count(self, obj):
        return obj.control_assessments.count()
    
    def get_progress_percentage(self, obj):
        total_controls = obj.controls_assessed or 1
        assessed_controls = obj.control_assessments.filter(
            status__in=['compliant', 'non_compliant', 'partially_compliant']
        ).count()
        return round((assessed_controls / total_controls) * 100, 1)
    
    def create(self, validated_data):
        """Create audit with related incidents"""
        incident_ids = validated_data.pop('incident_ids', [])
        
        # Set created_by from request
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        
        # Create audit
        audit = super().create(validated_data)
        
        # Add incidents
        if incident_ids:
            from incidentApp.models import Incident
            incidents = Incident.objects.filter(id__in=incident_ids)
            audit.related_incidents.set(incidents)
            
            # Calculate risk score
            risk_score = audit.calculate_risk_score()
            if risk_score:
                audit.risk_score_from_incident = risk_score
                audit.save()
        
        return audit


class ComplianceReportSerializer(serializers.ModelSerializer):
    """Serializer for compliance reports"""
    
    generated_by_details = serializers.SerializerMethodField()
    audit_details = serializers.SerializerMethodField()
    standard_details = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ComplianceReport
        fields = [
            'id', 'report_id', 'title', 'report_type', 'format',
            'file_path', 'parameters',
            'audit', 'audit_details', 'standard', 'standard_details',
            'generated_by', 'generated_by_details',
            'generated_at', 'download_count',
            'download_url'
        ]
        read_only_fields = ['report_id', 'generated_at', 'download_count']
    
    def get_generated_by_details(self, obj):
        if obj.generated_by:
            return UserSerializer(obj.generated_by).data
        return None
    
    def get_audit_details(self, obj):
        if obj.audit:
            return {
                'id': obj.audit.id,
                'audit_id': obj.audit.audit_id,
                'title': obj.audit.title
            }
        return None
    
    def get_standard_details(self, obj):
        if obj.standard:
            return {
                'id': obj.standard.id,
                'name': obj.standard.name,
                'standard_type': obj.standard.standard_type
            }
        return None
    
    def get_download_url(self, obj):
        request = self.context.get('request')
        if request and obj.file_path:
            return request.build_absolute_uri(obj.file_path.url)
        return None


class DashboardStatisticsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    
    # Overall Metrics
    total_audits = serializers.IntegerField()
    completed_audits = serializers.IntegerField()
    in_progress_audits = serializers.IntegerField()
    incident_audits = serializers.IntegerField()
    
    # Finding Metrics
    total_findings = serializers.IntegerField()
    open_findings = serializers.IntegerField()
    critical_findings = serializers.IntegerField()
    overdue_findings = serializers.IntegerField()
    
    # Control Metrics
    total_controls_assessed = serializers.IntegerField()
    compliant_controls = serializers.IntegerField()
    compliance_rate = serializers.FloatField()
    
    # Standard Metrics
    total_standards = serializers.IntegerField()
    active_standards = serializers.IntegerField()
    
    # Recent Activities
    recent_audits = ComplianceAuditSerializer(many=True)
    recent_findings = AuditFindingSerializer(many=True)
    
    # Upcoming Deadlines
    upcoming_deadlines = serializers.ListField(child=serializers.DictField())
    
    # Compliance Trends
    compliance_trends = serializers.ListField(child=serializers.DictField())