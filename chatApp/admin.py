# chatApp/admin.py

from django.contrib import admin
from .models import ChatRoom, ChatParticipant, Message
from notificationApp.models import ChatNotification


class ChatParticipantInline(admin.TabularInline):
    """Inline for viewing participants in ChatRoom admin"""
    model = ChatParticipant
    extra = 0
    readonly_fields = ['joined_at']
    fields = ['user', 'role', 'joined_at', 'last_read_at', 'is_muted']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'chat_type', 'mentorship', 'department', 'is_active', 'created_by', 'created_at', 'participant_count']
    list_filter = ['chat_type', 'is_active', 'created_at', 'updated_at', 'department']
    search_fields = [
        'name',
        'mentorship__mentor__full_name',
        'mentorship__mentee__full_name',
        'department__name',
        'participants__full_name'
    ]
    readonly_fields = ['created_at', 'updated_at', 'participant_count_display']
    inlines = [ChatParticipantInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'mentorship',
            'department',
            'created_by',
            'mentorship__mentor',
            'mentorship__mentee'
        ).prefetch_related('participants')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'chat_type')
        }),
        ('Relationships', {
            'fields': ('mentorship', 'department')
        }),
        ('Creator', {
            'fields': ('created_by',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Statistics', {
            'fields': ('participant_count_display',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def participant_count(self, obj):
        """Display participant count in list view"""
        return obj.participants.count()
    participant_count.short_description = 'Participants'
    
    def participant_count_display(self, obj):
        """Display participant count in detail view"""
        return obj.participants.count()
    participant_count_display.short_description = 'Total Participants'


@admin.register(ChatParticipant)
class ChatParticipantAdmin(admin.ModelAdmin):
    list_display = ['user', 'chat_room', 'role', 'joined_at', 'last_read_at', 'is_muted']
    list_filter = ['role', 'is_muted', 'joined_at', 'chat_room__chat_type']
    search_fields = ['user__full_name', 'chat_room__name', 'user__email']
    list_select_related = ['user', 'chat_room']
    readonly_fields = ['joined_at']
    
    fieldsets = (
        ('Participant Information', {
            'fields': ('user', 'chat_room', 'role')
        }),
        ('Settings', {
            'fields': ('is_muted',)
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'last_read_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'chat_room')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'chat_room', 'sender', 'message_type', 'content_preview', 'is_deleted', 'created_at']
    list_filter = ['message_type', 'is_deleted', 'created_at', 'chat_room__chat_type']
    search_fields = ['content', 'sender__full_name', 'sender__email', 'chat_room__name']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    
    def content_preview(self, obj):
        """Show preview of message content"""
        if obj.is_deleted:
            return "[DELETED]"
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content Preview'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('chat_room', 'sender')
    
    fieldsets = (
        ('Message Information', {
            'fields': ('sender', 'chat_room', 'message_type', 'content')
        }),
        ('Attachments', {
            'fields': ('attachment',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_deleted', 'deleted_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ChatNotification)
class ChatNotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'recipient', 'sender', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'recipient__full_name', 'sender__full_name']
    readonly_fields = ['created_at', 'read_at', 'archived_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'recipient', 
            'sender', 
            'chat_room',
            'group_chat_room'
        )
    
    fieldsets = (
        ('Notification Information', {
            'fields': ('notification_type', 'title', 'message')
        }),
        ('Users', {
            'fields': ('recipient', 'sender')
        }),
        ('Related Chat', {
            'fields': ('chat_room', 'group_chat_room'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_read', 'is_archived', 'read_at', 'archived_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )