# onboarding/serializers.py - Fixed version
import logging
import uuid
from django.conf import settings
from rest_framework import serializers
from .models import (
    OnboardingModule, 
    MenteeOnboardingProgress, 
    OnboardingChecklist,
    MenteeChecklistProgress,
    OnboardingDeadline
)
from userApp.models import CustomUser
from departmentApp.models import Department
from .utils import FileUploadHandler

logger = logging.getLogger(__name__)

class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model"""
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'status']


class OnboardingChecklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingChecklist
        fields = [
            'id', 
            'title', 
            'description', 
            'order', 
            'is_required',
            'estimated_minutes'
        ]


class FileUploadSerializer(serializers.Serializer):
    """Serializer for optional file upload"""
    file = serializers.FileField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate(self, data):
        """Custom validation - file is optional"""
        # No validation needed since file is optional
        return data


class OnboardingModuleCreateSerializer(serializers.ModelSerializer):
    checklist_items = OnboardingChecklistSerializer(many=True, required=False)
    departments = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=Department.objects.filter(status='active'),
        required=False,
        write_only=True
    )
    files = FileUploadSerializer(many=True, required=False, write_only=True)
    
    class Meta:
        model = OnboardingModule
        fields = [
            'title',
            'description',
            'module_type',
            'departments',
            'order',
            'is_required',
            'duration_minutes',
            'content',
            'resources',
            'is_active',
            'checklist_items',
            'files'
        ]
    
    def validate(self, data):
        """Validate file uploads - files are optional"""
        files = data.get('files', [])
        
        for file_data in files:
            file = file_data.get('file')
            if file:  # Only validate if file exists
                # Check file size
                if file.size > settings.MAX_FILE_SIZE:
                    raise serializers.ValidationError(
                        f"File {file.name} exceeds maximum size of {settings.MAX_FILE_SIZE / (1024*1024)}MB"
                    )
                
                # Check file type
                ext = file.name.split('.')[-1].lower()
                allowed = False
                for allowed_exts in settings.ALLOWED_FILE_TYPES.values():
                    if ext in allowed_exts:
                        allowed = True
                        break
                
                if not allowed:
                    raise serializers.ValidationError(
                        f"File type {ext} is not allowed"
                    )
        
        return data
    
    def create(self, validated_data):
        files_data = validated_data.pop('files', [])
        checklist_items_data = validated_data.pop('checklist_items', [])
        departments_data = validated_data.pop('departments', [])
        
        # Create module
        module = OnboardingModule.objects.create(**validated_data)
        
        # Add departments
        if departments_data:
            module.departments.set(departments_data)
        
        # Handle file uploads - files are optional
        multimedia_files = []
        for file_data in files_data:
            file = file_data.get('file')
            if not file:
                continue  # Skip if no file
                
            title = file_data.get('title', '')
            description = file_data.get('description', '')
            file_type = file_data.get('type', '')
            
            try:
                # Save file and get metadata
                file_handler = FileUploadHandler()
                file_metadata = file_handler.save_file(
                    file=file,
                    module_id=module.id,
                    user_id=self.context['request'].user.id
                )
                
                # Add custom metadata
                file_metadata['title'] = title or file.name
                file_metadata['description'] = description
                if file_type:
                    file_metadata['type'] = file_type
                
                multimedia_files.append(file_metadata)
                
            except Exception as e:
                logger.error(f"Error saving file {file.name}: {str(e)}")
                continue
        
        # Save files to module if any were uploaded
        if multimedia_files:
            module.multimedia_files = multimedia_files
            module.save()
        
        # Create checklist items
        for item_data in checklist_items_data:
            OnboardingChecklist.objects.create(module=module, **item_data)
        
        return module
    
    def update(self, instance, validated_data):
        files_data = validated_data.pop('files', [])  # Get files, default to empty list
        checklist_items_data = validated_data.pop('checklist_items', None)
        departments_data = validated_data.pop('departments', None)
        
        # Update module fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update departments if provided
        if departments_data is not None:
            instance.departments.set(departments_data)
        
        # Handle file updates - append new files to existing ones
        if files_data:
            multimedia_files = instance.multimedia_files or []
            
            for file_data in files_data:
                file = file_data.get('file')
                if not file:
                    continue  # Skip if no file
                    
                title = file_data.get('title', '')
                description = file_data.get('description', '')
                file_type = file_data.get('type', '')
                
                try:
                    file_handler = FileUploadHandler()
                    file_metadata = file_handler.save_file(
                        file=file,
                        module_id=instance.id,
                        user_id=self.context['request'].user.id
                    )
                    
                    file_metadata['title'] = title or file.name
                    file_metadata['description'] = description
                    if file_type:
                        file_metadata['type'] = file_type
                    
                    multimedia_files.append(file_metadata)
                    
                except Exception as e:
                    logger.error(f"Error saving file {file.name}: {str(e)}")
                    continue
            
            instance.multimedia_files = multimedia_files
        
        # Update checklist items if provided
        if checklist_items_data is not None:
            instance.checklist_items.all().delete()
            for item_data in checklist_items_data:
                OnboardingChecklist.objects.create(module=instance, **item_data)
        
        instance.save()
        return instance

class OnboardingModuleSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    applicable_departments = serializers.SerializerMethodField()
    departments = DepartmentSerializer(many=True, read_only=True)
    department_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    checklist_items = OnboardingChecklistSerializer(many=True, read_only=True)
    total_mentees_assigned = serializers.SerializerMethodField()
    total_completed = serializers.SerializerMethodField()
    department_stats = serializers.SerializerMethodField()
    multimedia_files = serializers.SerializerMethodField()
    
    class Meta:
        model = OnboardingModule
        fields = [
            'id',
            'title',
            'description',
            'module_type',
            'departments',
            'department_ids',
            'order',
            'is_required',
            'duration_minutes',
            'content',
            'resources',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
            'applicable_departments',
            'checklist_items',
            'total_mentees_assigned',
            'total_completed',
            'department_stats',
            'multimedia_files',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_multimedia_files(self, obj):
        """Serialize multimedia files with proper URL formatting"""
        files = obj.multimedia_files or []
        processed_files = []
        
        for file in files:
            # Normalize path - replace backslashes with forward slashes
            url = file.get('url', '')
            if url:
                url = url.replace('\\', '/')
                # Remove any leading slash and ensure it starts with media/
                url = url.lstrip('/')
                if not url.startswith('media/'):
                    url = 'media/' + url
            
            processed_file = {
                'id': file.get('id', str(uuid.uuid4())),
                'url': url,  # Use normalized URL
                'type': file.get('type', ''),
                'title': file.get('title', ''),
                'description': file.get('description', ''),
                'size': file.get('size', 0),
                'duration': file.get('duration', 0),
                'thumbnail': file.get('thumbnail', ''),
                'extension': file.get('extension', ''),
                'uploaded_at': file.get('uploaded_at', ''),
                'uploaded_by': file.get('uploaded_by', '')
            }
            processed_files.append(processed_file)
        
        return processed_files
    def get_applicable_departments(self, obj):
        return obj.get_applicable_departments()
    
    def get_total_mentees_assigned(self, obj):
        return obj.mentee_progress.count()
    
    def get_total_completed(self, obj):
        return obj.mentee_progress.filter(status='completed').count()
    
    def get_department_stats(self, obj):
        return obj.get_department_stats()
    
    def validate(self, data):
        """Validate module data"""
        module_type = data.get('module_type')
        department_ids = data.get('department_ids', [])
        
        # Clear departments for core modules
        if module_type == 'core':
            data['department_ids'] = []
        # For department modules, validate department IDs
        elif module_type == 'department' and department_ids:
            existing_dept_ids = Department.objects.filter(
                id__in=department_ids,
                status='active'
            ).values_list('id', flat=True)
            
            invalid_ids = set(department_ids) - set(existing_dept_ids)
            if invalid_ids:
                raise serializers.ValidationError({
                    'department_ids': f'Invalid department IDs: {invalid_ids}'
                })
        
        return data
    
    def create(self, validated_data):
        department_ids = validated_data.pop('department_ids', [])
        checklist_items_data = validated_data.pop('checklist_items', [])
        
        module = OnboardingModule.objects.create(**validated_data)
        
        # Add departments if provided (only for department modules)
        if department_ids and module.module_type == 'department':
            departments = Department.objects.filter(id__in=department_ids)
            module.departments.set(departments)
        
        # Create checklist items
        for item_data in checklist_items_data:
            OnboardingChecklist.objects.create(module=module, **item_data)
        
        return module
    
    def update(self, instance, validated_data):
        department_ids = validated_data.pop('department_ids', None)
        checklist_items_data = validated_data.pop('checklist_items', None)
        
        # Update module fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update departments if provided
        if department_ids is not None:
            if department_ids and instance.module_type == 'department':
                departments = Department.objects.filter(id__in=department_ids)
                instance.departments.set(departments)
            else:
                instance.departments.clear()
        
        # Update checklist items if provided
        if checklist_items_data is not None:
            instance.checklist_items.all().delete()
            for item_data in checklist_items_data:
                OnboardingChecklist.objects.create(module=instance, **item_data)
        
        return instance
class MenteeOnboardingProgressSerializer(serializers.ModelSerializer):
    mentee_name = serializers.CharField(source='mentee.full_name', read_only=True)
    mentee_email = serializers.CharField(source='mentee.email', read_only=True)
    mentee_department = serializers.SerializerMethodField()
    module_title = serializers.CharField(source='module.title', read_only=True)
    module_description = serializers.CharField(source='module.description', read_only=True)
    module_type = serializers.CharField(source='module.module_type', read_only=True)
    module_duration = serializers.IntegerField(source='module.duration_minutes', read_only=True)
    module_content = serializers.JSONField(source='module.content', read_only=True)
    module_resources = serializers.JSONField(source='module.resources', read_only=True)
    checklist_progress = serializers.SerializerMethodField()
    
    class Meta:
        model = MenteeOnboardingProgress
        fields = [
            'id',
            'mentee',
            'mentee_name',
            'mentee_email',
            'mentee_department',
            'module',
            'module_title',
            'module_description',
            'module_type',
            'module_duration',
            'module_content',
            'module_resources',
            'status',
            'progress_percentage',
            'started_at',
            'completed_at',
            'due_date',
            'notes',
            'time_spent_minutes',
            'checklist_progress'
        ]
        read_only_fields = ['started_at', 'completed_at']
    
    def get_mentee_department(self, obj):
        """Get mentee's department name - Fixed for ForeignKey"""
        if obj.mentee.department:
            return obj.mentee.department.name
        return None
    
    def get_checklist_progress(self, obj):
        """Get checklist progress for this module"""
        checklist_items = obj.module.checklist_items.all()
        progress_items = MenteeChecklistProgress.objects.filter(
            mentee=obj.mentee,
            checklist_item__module=obj.module
        )
        
        result = []
        for item in checklist_items:
            progress = progress_items.filter(checklist_item=item).first()
            result.append({
                'id': item.id,
                'title': item.title,
                'description': item.description,
                'is_required': item.is_required,
                'estimated_minutes': item.estimated_minutes,
                'is_completed': progress.is_completed if progress else False,
                'completed_at': progress.completed_at if progress else None,
                'time_spent_minutes': progress.time_spent_minutes if progress else 0
            })
        
        return result


class MenteeOnboardingProgressUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenteeOnboardingProgress
        fields = [
            'status',
            'progress_percentage',
            'notes',
            'time_spent_minutes'
        ]
    
    def validate_progress_percentage(self, value):
        if not 0 <= value <= 100:
            raise serializers.ValidationError("Progress percentage must be between 0 and 100")
        return value


class MenteeSummarySerializer(serializers.ModelSerializer):
    """Summary of mentee's overall onboarding progress"""
    department_name = serializers.SerializerMethodField()
    total_modules = serializers.SerializerMethodField()
    completed_modules = serializers.SerializerMethodField()
    in_progress_modules = serializers.SerializerMethodField()
    not_started_modules = serializers.SerializerMethodField()
    overall_progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id',
            'full_name',
            'email',
            'department',
            'department_name',
            'total_modules',
            'completed_modules',
            'in_progress_modules',
            'not_started_modules',
            'overall_progress_percentage'
        ]
    
    def get_department_name(self, obj):
        """Get department name - Fixed for ForeignKey"""
        if obj.department:
            return obj.department.name
        return None
    
    def get_total_modules(self, obj):
        return obj.onboarding_progress.count()
    
    def get_completed_modules(self, obj):
        return obj.onboarding_progress.filter(status='completed').count()
    
    def get_in_progress_modules(self, obj):
        return obj.onboarding_progress.filter(status='in_progress').count()
    
    def get_not_started_modules(self, obj):
        return obj.onboarding_progress.filter(status='not_started').count()
    
    def get_overall_progress_percentage(self, obj):
        progress_records = obj.onboarding_progress.all()
        if not progress_records:
            return 0
        
        total_progress = sum(p.progress_percentage for p in progress_records)
        return round(total_progress / progress_records.count(), 2)


class MenteeChecklistProgressSerializer(serializers.ModelSerializer):
    checklist_item_title = serializers.CharField(source='checklist_item.title', read_only=True)
    checklist_item_description = serializers.CharField(source='checklist_item.description', read_only=True)
    
    class Meta:
        model = MenteeChecklistProgress
        fields = [
            'id',
            'checklist_item',
            'checklist_item_title',
            'checklist_item_description',
            'is_completed',
            'completed_at',
            'time_spent_minutes',
            'notes'
        ]


class DepartmentProgressSerializer(serializers.Serializer):
    """Serializer for department-wise progress summary"""
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    total_modules = serializers.IntegerField()
    completed_modules = serializers.IntegerField()
    in_progress_modules = serializers.IntegerField()
    not_started_modules = serializers.IntegerField()
    overall_progress_percentage = serializers.FloatField()
    total_mentees = serializers.IntegerField()
    mentees_completed_all = serializers.IntegerField()
    avg_completion_rate = serializers.FloatField()


class DepartmentModuleStatsSerializer(serializers.Serializer):
    """Serializer for module statistics by department"""
    module_id = serializers.IntegerField()
    module_title = serializers.CharField()
    total_assigned = serializers.IntegerField()
    total_completed = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    avg_time_spent = serializers.FloatField()


class DepartmentSummarySerializer(serializers.Serializer):
    """Summary of onboarding progress for a department"""
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    total_mentees = serializers.IntegerField()
    total_modules_assigned = serializers.IntegerField()
    completed_modules = serializers.IntegerField()
    overall_completion_rate = serializers.FloatField()
    average_progress_per_mentee = serializers.FloatField()
    mentees_behind_schedule = serializers.IntegerField()
    modules_requiring_attention = serializers.ListField(child=serializers.CharField())


class SendReminderSerializer(serializers.Serializer):
    recipient_id = serializers.IntegerField(required=True)
    notification_type = serializers.CharField(max_length=100, required=True)
    title = serializers.CharField(max_length=255, required=True)
    message = serializers.CharField(required=True)