import django_filters
from django.db.models import Q
from .models import ComplianceAudit, AuditFinding, ControlAssessment
from django.utils.timezone import now


class AuditFilter(django_filters.FilterSet):
    """Filter for compliance audits"""
    
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='exact'
    )
    
    standard = django_filters.NumberFilter(
        field_name='standard__id',
        lookup_expr='exact'
    )
    
    audit_type = django_filters.CharFilter(
        field_name='audit_type',
        lookup_expr='exact'
    )
    
    priority = django_filters.CharFilter(
        field_name='priority',
        lookup_expr='exact'
    )
    
    lead_auditor = django_filters.NumberFilter(
        field_name='lead_auditor__id',
        lookup_expr='exact'
    )
    
    created_by = django_filters.NumberFilter(
        field_name='created_by__id',
        lookup_expr='exact'
    )
    
    date_from = django_filters.DateFilter(
        field_name='planned_start_date',
        lookup_expr='gte'
    )
    
    date_to = django_filters.DateFilter(
        field_name='planned_end_date',
        lookup_expr='lte'
    )
    
    has_incidents = django_filters.BooleanFilter(
        method='filter_has_incidents'
    )
    
    min_score = django_filters.NumberFilter(
        field_name='overall_score',
        lookup_expr='gte'
    )
    
    max_score = django_filters.NumberFilter(
        field_name='overall_score',
        lookup_expr='lte'
    )
    
    class Meta:
        model = ComplianceAudit
        fields = [
            'status', 'standard', 'audit_type', 'priority',
            'lead_auditor', 'created_by', 'date_from', 'date_to',
            'has_incidents', 'min_score', 'max_score'
        ]
    
    def filter_has_incidents(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(related_incidents__isnull=False) |
                Q(triggered_by_incident__isnull=False)
            ).distinct()
        return queryset.filter(
            Q(related_incidents__isnull=True) &
            Q(triggered_by_incident__isnull=True)
        )


class FindingFilter(django_filters.FilterSet):
    """Filter for audit findings"""
    
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='exact'
    )
    
    risk_level = django_filters.CharFilter(
        field_name='risk_level',
        lookup_expr='exact'
    )
    
    finding_type = django_filters.CharFilter(
        field_name='finding_type',
        lookup_expr='exact'
    )
    
    audit = django_filters.NumberFilter(
        field_name='audit__id',
        lookup_expr='exact'
    )
    
    assigned_to = django_filters.NumberFilter(
        field_name='assigned_to__id',
        lookup_expr='exact'
    )
    
    created_by = django_filters.NumberFilter(
        field_name='created_by__id',
        lookup_expr='exact'
    )
    
    overdue = django_filters.BooleanFilter(
        method='filter_overdue'
    )
    
    date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__gte'
    )
    
    date_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date__lte'
    )
    
    class Meta:
        model = AuditFinding
        fields = [
            'status', 'risk_level', 'finding_type', 'audit',
            'assigned_to', 'created_by', 'overdue',
            'date_from', 'date_to'
        ]
    
    def filter_overdue(self, queryset, name, value):
        from datetime import date
        today = date.today()
        
        if value:
            return queryset.filter(
                target_completion_date__lt=today,
                status__in=['open', 'in_progress']
            )
        return queryset.filter(
            Q(target_completion_date__gte=today) |
            Q(target_completion_date__isnull=True) |
            Q(status__in=['resolved', 'closed'])
        )


class ControlAssessmentFilter(django_filters.FilterSet):
    """Filter for control assessments"""
    
    status = django_filters.CharFilter(
        field_name='status',
        lookup_expr='exact'
    )
    
    audit = django_filters.NumberFilter(
        field_name='audit__id',
        lookup_expr='exact'
    )
    
    remediation_required = django_filters.BooleanFilter(
        field_name='remediation_required',
        lookup_expr='exact'
    )
    
    remediation_status = django_filters.CharFilter(
        field_name='remediation_status',
        lookup_expr='exact'
    )
    
    assessed_by = django_filters.NumberFilter(
        field_name='assessed_by__id',
        lookup_expr='exact'
    )
    
    class Meta:
        model = ControlAssessment
        fields = [
            'status', 'audit', 'remediation_required',
            'remediation_status', 'assessed_by'
        ]