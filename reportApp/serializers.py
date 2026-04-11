from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from django.db.models import Count, Avg, Q, Sum, F
from django.db.models.functions import TruncDate
from datetime import datetime, timedelta
from django.utils import timezone
import csv
import json
from io import StringIO, BytesIO
from django.http import HttpResponse
from django.db import connection
import logging

# Import models
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department
from incidentApp.models import Incident
from complianceAuditApp.models import ComplianceAudit, ComplianceStandard, ControlAssessment
from trainingApp.models import Training
from trainingCandidateApp.models import Candidate
from learningProgressApp.models import LearningProgress

logger = logging.getLogger(__name__)


# Serializers
class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics"""
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    pending_users = serializers.IntegerField()
    total_incidents = serializers.IntegerField()
    open_incidents = serializers.IntegerField()
    critical_incidents = serializers.IntegerField()
    total_audits = serializers.IntegerField()
    active_audits = serializers.IntegerField()
    total_trainings = serializers.IntegerField()
    ongoing_trainings = serializers.IntegerField()
    compliance_score = serializers.FloatField()
    risk_score = serializers.FloatField()
    department_breakdown = serializers.JSONField()


class AccessTrendSerializer(serializers.Serializer):
    """Serializer for access trends data"""
    date = serializers.DateField()
    successful_logins = serializers.IntegerField()
    failed_logins = serializers.IntegerField()
    flagged_activities = serializers.IntegerField()


class IncidentTrendSerializer(serializers.Serializer):
    """Serializer for incident trends"""
    date = serializers.DateField()
    total_incidents = serializers.IntegerField()
    resolved_incidents = serializers.IntegerField()
    average_resolution_time = serializers.FloatField()


class DepartmentPerformanceSerializer(serializers.Serializer):
    """Serializer for department performance metrics"""
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    total_users = serializers.IntegerField()
    active_incidents = serializers.IntegerField()
    compliance_score = serializers.FloatField()
    training_completion_rate = serializers.FloatField()
    risk_level = serializers.CharField()


class UserActivitySerializer(serializers.Serializer):
    """Serializer for user activity logs"""
    user_id = serializers.IntegerField()
    user_name = serializers.CharField()
    user_email = serializers.EmailField()
    role = serializers.CharField()
    last_activity = serializers.DateTimeField()
    total_activities = serializers.IntegerField()
    flagged_activities = serializers.IntegerField()


class RecentActivitySerializer(serializers.Serializer):
    """Serializer for recent activities"""
    timestamp = serializers.DateTimeField()
    activity = serializers.CharField()
    description = serializers.CharField()
    user = serializers.CharField()
    severity = serializers.CharField(required=False)
    category = serializers.CharField()


class SystemHealthSerializer(serializers.Serializer):
    """Serializer for system health metrics"""
    component = serializers.CharField()
    status = serializers.CharField()
    uptime = serializers.FloatField()
    last_check = serializers.DateTimeField()
    issues = serializers.IntegerField()


class TrainingProgressSerializer(serializers.Serializer):
    """Serializer for training progress"""
    training_id = serializers.IntegerField()
    training_name = serializers.CharField()
    total_candidates = serializers.IntegerField()
    completed_candidates = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_time = serializers.FloatField()


class RiskDistributionSerializer(serializers.Serializer):
    """Serializer for risk distribution"""
    risk_level = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()
    departments = serializers.JSONField()


class FilterSerializer(serializers.Serializer):
    """Serializer for dashboard filters"""
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    department = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField(required=False)
    severity = serializers.CharField(required=False)
    timeframe = serializers.ChoiceField(
        choices=['today', 'week', 'month', 'quarter', 'year', 'custom'],
        default='month'
    )


class ExportRequestSerializer(serializers.Serializer):
    """Serializer for export requests"""
    format = serializers.ChoiceField(choices=['json', 'csv', 'pdf'])
    filters = FilterSerializer(required=False)


class ReportDataSerializer(serializers.Serializer):
    """Main report data serializer"""
    stats = DashboardStatsSerializer()
    access_trends = AccessTrendSerializer(many=True)
    incident_trends = IncidentTrendSerializer(many=True)
    department_performance = DepartmentPerformanceSerializer(many=True)
    recent_activities = RecentActivitySerializer(many=True)
    system_health = SystemHealthSerializer(many=True)
    training_progress = TrainingProgressSerializer(many=True)
    risk_distribution = RiskDistributionSerializer(many=True)
    user_activities = UserActivitySerializer(many=True)
    generated_at = serializers.DateTimeField()
    filters = FilterSerializer(required=False)







# ==================== SERIALIZERS ====================
class ReportFilterSerializer(serializers.Serializer):
    """Serializer for report filters"""
    report_type = serializers.ChoiceField(
        choices=[
            ('users', 'Users Report'),
            ('incidents', 'Incidents Report'),
            ('audits', 'Audits Report'),
            ('departments', 'Departments Report'),
            ('trainings', 'Trainings Report'),
            ('compliance', 'Compliance Report'),
            ('activity_logs', 'Activity Logs Report'),
            ('user_training_progress', 'User Training Progress Report'),
        ],
        required=True
    )
    
    # Date filters
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    
    # Common filters
    status = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    severity = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    department = serializers.IntegerField(required=False, allow_null=True)
    role = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    # Pagination
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=50, min_value=10, max_value=1000)
    
    # Format
    format = serializers.ChoiceField(
        choices=['json', 'csv', 'terminal'],
        default='json'
    )
    
    # Specific filters for different report types
    incident_status = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    audit_status = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    training_status = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    compliance_standard = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    def validate(self, data):
        # Validate date range
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError({
                    'start_date': 'Start date cannot be after end date'
                })
        
        # Set end_date to today if not provided
        if not data.get('end_date'):
            data['end_date'] = datetime.now().date()
        
        # Set start_date to 30 days before end_date if not provided
        if not data.get('start_date'):
            data['start_date'] = data['end_date'] - timedelta(days=30)
        
        return data


class ReportSummarySerializer(serializers.Serializer):
    """Serializer for report summary"""
    report_type = serializers.CharField()
    filters_applied = serializers.DictField()
    total_records = serializers.IntegerField()
    date_range = serializers.DictField()
    generated_at = serializers.DateTimeField()
    generated_by = serializers.CharField()
    
    # Summary statistics
    summary_stats = serializers.DictField()
    
    # Key metrics
    key_metrics = serializers.ListField()
    
    # Data preview
    data_preview = serializers.ListField()
    
    # Export info
    export_format = serializers.CharField()
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()


class ReportDataSerializer(serializers.Serializer):
    """Main report data serializer"""
    summary = ReportSummarySerializer()
    data = serializers.ListField()
    pagination = serializers.DictField()
