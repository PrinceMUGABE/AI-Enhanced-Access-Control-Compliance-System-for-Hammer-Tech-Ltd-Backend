from django.contrib import admin
from .models import (
    ComplianceStandard, ComplianceAudit,
    AuditFinding, ControlAssessment, ComplianceReport
)


@admin.register(ComplianceStandard)
class ComplianceStandardAdmin(admin.ModelAdmin):
    list_display = ('name', 'standard_type', 'version', 'is_active', 'total_controls', 'created_at')
    list_filter = ('standard_type', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'standard_type', 'version', 'description')
        }),

        ('Control Metrics', {
            'fields': ('total_controls', 'mandatory_controls')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        })
    )


@admin.register(ComplianceAudit)
class ComplianceAuditAdmin(admin.ModelAdmin):
    list_display = ('audit_id', 'title', 'standard', 'status', 'audit_type', 'overall_score', 'created_at')
    list_filter = ('status', 'audit_type', 'standard', 'created_at')
    search_fields = ('audit_id', 'title', 'description')
    readonly_fields = ('audit_id', 'created_at', 'updated_at')
    filter_horizontal = ('related_incidents', 'departments')
    fieldsets = (
        ('Identification', {
            'fields': ('audit_id', 'title', 'description')
        }),
        ('Relationships', {
            'fields': ('standard', 'related_incidents', 'triggered_by_incident', 'departments')
        }),
        ('Audit Details', {
            'fields': ('audit_type', 'status', 'priority')
        }),
        ('Schedule', {
            'fields': ('planned_start_date', 'planned_end_date', 'actual_start_date', 'actual_end_date')
        }),
        ('Team', {
            'fields': ('lead_auditor', 'created_by')
        }),
        ('Metrics', {
            'fields': ('overall_score', 'compliance_rate', 'controls_assessed',
                      'total_findings', 'open_findings', 'critical_findings')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        })
    )


@admin.register(AuditFinding)
class AuditFindingAdmin(admin.ModelAdmin):
    list_display = ('audit', 'title', 'risk_level', 'status', 'assigned_to', 'created_at')
    list_filter = ('risk_level', 'status', 'finding_type', 'created_at')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ControlAssessment)
class ControlAssessmentAdmin(admin.ModelAdmin):
    list_display = ('control_id', 'control_name', 'audit', 'status', 'remediation_required', 'created_at')
    list_filter = ('status', 'remediation_required', 'remediation_status', 'created_at')
    search_fields = ('control_id', 'control_name', 'control_description')


@admin.register(ComplianceReport)
class ComplianceReportAdmin(admin.ModelAdmin):
    list_display = ('report_id', 'title', 'report_type', 'format', 'generated_by', 'generated_at')
    list_filter = ('report_type', 'format', 'generated_at')
    search_fields = ('report_id', 'title', 'generated_by__username')
    readonly_fields = ('report_id', 'generated_at')