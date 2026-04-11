# serializers.py in trainingApp
from rest_framework import serializers
from .models import Training, Module, TrainingMaterial
from userApp.models import CustomUser as User
import logging
from base64 import b64encode, b64decode
import os
from departmentApp.models import Department
from userApp.models import CustomUser

logger = logging.getLogger(__name__)

class DepartmentSerializer(serializers.ModelSerializer):
    """Simple department serializer for nested representation"""
    class Meta:
        model = Department
        fields = ['id', 'name', 'status']


class CustomUserSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    departments_details = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'email', 'work_mail_address',
            'full_name', 'role', 'department', 'departments',
            'department_details', 'departments_details',
            'status', 'availability_status', 'created_at', 
            'created_by', 'created_by_name', 'is_admin'
        ]
        read_only_fields = ['work_mail_address', 'created_at', 'created_by']
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.full_name
        return None
    
    def get_department_details(self, obj):
        """Get department details for mentees"""
        if obj.role == 'mentee' and obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name,
                'status': obj.department.status
            }
        return None
    
    def get_departments_details(self, obj):
        """Get departments details for mentors"""
        if obj.role == 'mentor':
            return [
                {
                    'id': dept.id,
                    'name': dept.name,
                    'status': dept.status
                }
                for dept in obj.departments.all()
            ]
        return []



class TrainingMaterialSerializer(serializers.ModelSerializer):
    filename = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TrainingMaterial
        fields = ['id', 'file', 'filename', 'file_size', 'file_type', 'download_url', 'uploaded_at']

    def get_filename(self, obj):
        """Extract filename from file path"""
        if obj.file:
            return os.path.basename(obj.file.name)
        return None
    
    def get_file_size(self, obj):
        """Get file size in bytes"""
        try:
            if obj.file:
                return obj.file.size
        except:
            pass
        return None
    
    def get_file_type(self, obj):
        """Get file extension/type"""
        if obj.file:
            filename = os.path.basename(obj.file.name)
            return os.path.splitext(filename)[1].lower()
        return None
    
    def get_download_url(self, obj):
        """Get download URL for the file"""
        if obj.file:
            return obj.file.url
        return None


class ModuleSerializer(serializers.ModelSerializer):
    materials = TrainingMaterialSerializer(many=True, read_only=True)  # Nested materials
    materials_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Module
        fields = ['id', 'name', 'description', 'training', 'materials', 'materials_count', 'created_at']
    
    def get_materials_count(self, obj):
        """Get count of materials in this module"""
        return obj.materials.count()


class TrainingSerializer(serializers.ModelSerializer):
    created_by = CustomUserSerializer(read_only=True)
    modules = ModuleSerializer(many=True, read_only=True)  # Nested modules
    picture_data = serializers.SerializerMethodField()  # Add this as a method field
    modules_count = serializers.SerializerMethodField()
    total_materials_count = serializers.SerializerMethodField()

    class Meta:
        model = Training
        fields = ['id', 'created_by', 'name', 'description', 'modules', 'modules_count', 
                 'total_materials_count', 'picture_data', 'created_at']

    def to_representation(self, instance):
        logger.debug(f"Serializing training: {instance}")
        return super().to_representation(instance)
    
    def get_picture_data(self, obj):
        """Convert binary picture data to base64 string for frontend consumption"""
        if obj.picture_data:
            return b64encode(obj.picture_data).decode('utf-8')
        return None
    
    def get_modules_count(self, obj):
        """Get count of modules in this training"""
        return obj.modules.count()
    
    def get_total_materials_count(self, obj):
        """Get total count of all materials across all modules"""
        return sum(module.materials.count() for module in obj.modules.all())