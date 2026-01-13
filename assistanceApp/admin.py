from django.contrib import admin
from .models import AssistanceChat, AssistanceMessage, FAQ, AIResponseLog, EmailResponse


class AssistanceMessageInline(admin.TabularInline):
    model = AssistanceMessage
    extra = 0
    readonly_fields = ['created_at']
    fields = ['message_type', 'content', 'sender', 'ai_model', 'created_at']


@admin.register(AssistanceChat)
class AssistanceChatAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'get_user_email', 'status', 'created_at', 'resolved_at']
    list_filter = ['status', 'created_at', 'resolved_at']
    search_fields = ['session_id', 'email', 'user__email', 'user__full_name']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    inlines = [AssistanceMessageInline]
    list_per_page = 20
    
    def get_user_email(self, obj):
        return obj.get_user_email()
    get_user_email.short_description = 'Email'
    
    fieldsets = (
        ('Session Information', {
            'fields': ('session_id', 'user', 'email', 'ip_address')
        }),
        ('Status', {
            'fields': ('status', 'is_active', 'escalated_to')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question_preview', 'category', 'times_asked', 'helpful_count', 'is_active']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['question', 'answer', 'keywords']
    readonly_fields = ['created_at', 'updated_at', 'times_asked']
    list_per_page = 20
    
    def question_preview(self, obj):
        return obj.question[:100] + "..." if len(obj.question) > 100 else obj.question
    question_preview.short_description = 'Question'
    
    fieldsets = (
        ('FAQ Content', {
            'fields': ('question', 'answer', 'category', 'keywords')
        }),
        ('Statistics', {
            'fields': ('times_asked', 'helpful_count', 'not_helpful_count')
        }),
        ('Metadata', {
            'fields': ('is_active', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(AIResponseLog)
class AIResponseLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_session_id', 'model_used', 'confidence_score', 'response_time', 'created_at']
    list_filter = ['model_used', 'created_at']
    search_fields = ['user_query', 'ai_response', 'chat__session_id']
    readonly_fields = ['created_at']
    list_per_page = 20
    
    def get_session_id(self, obj):
        return obj.chat.session_id
    get_session_id.short_description = 'Session ID'


@admin.register(EmailResponse)
class EmailResponseAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_session_id', 'sent_to', 'subject_preview', 'is_sent', 'sent_at']
    list_filter = ['is_sent', 'sent_at']
    search_fields = ['subject', 'sent_to', 'tracking_id', 'chat__session_id']
    readonly_fields = ['sent_at']
    list_per_page = 20
    
    def get_session_id(self, obj):
        return obj.chat.session_id
    get_session_id.short_description = 'Session ID'
    
    def subject_preview(self, obj):
        return obj.subject[:50] + "..." if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'