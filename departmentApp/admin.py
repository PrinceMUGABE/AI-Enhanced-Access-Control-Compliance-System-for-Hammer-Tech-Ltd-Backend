# departmentApp/admin.py

from django.contrib import admin
from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'created_by', 'created_at', 'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Department Information', {
            'fields': ('name', 'description', 'status')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new department
            obj.created_by = request.user
        super().save_model(request, obj, form, change)