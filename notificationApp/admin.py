from django.contrib import admin
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'title', 'is_read', 'priority', 'created_at']
    list_filter = ['notification_type', 'is_read', 'priority', 'created_at']
    search_fields = ['title', 'message', 'user__email', 'user__full_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Notification Details', {
            'fields': ('notification_type', 'title', 'message', 'priority')
        }),
        ('Related Objects', {
            'fields': ('incident', 'audit')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Action', {
            'fields': ('action_link', 'action_text')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_notifications', 'in_app_notifications', 'email_frequency', 'updated_at']
    search_fields = ['user__email', 'user__full_name']
    readonly_fields = ['updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('General Preferences', {
            'fields': ('email_notifications', 'in_app_notifications', 'email_frequency')
        }),
        ('Notification Types', {
            'fields': (
                'incident_assigned', 'incident_updated', 'incident_resolved',
                'incident_escalated', 'sla_violation', 'audit_required',
                'audit_completed', 'finding_assigned', 'finding_due',
                'compliance_alert', 'system_alert'
            )
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        })
    )




    