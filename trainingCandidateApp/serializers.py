# serializers.py
from rest_framework import serializers
from .models import Candidate
from trainingApp.models import Training, TrainingMaterial
from userApp.models import CustomUser as User
from userApp.models import CustomUser
from base64 import b64encode, b64decode
import logging
from trainingApp.models import Module
from departmentApp.models import Department

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
    class Meta:
        model = TrainingMaterial
        fields = ['id', 'file', 'uploaded_at']

class ModuleSerializer(serializers.ModelSerializer):
    materials = TrainingMaterialSerializer(many=True, read_only=True)  # Nested materials
    

    class Meta:
        model = Module
        fields = ['id', 'name', 'description', 'training', 'materials', 'created_at']

class TrainingSerializer(serializers.ModelSerializer):
    created_by = CustomUserSerializer(read_only=True)
    modules = ModuleSerializer(many=True, read_only=True)  # Nested modules

    class Meta:
        model = Training
        fields = ['id', 'created_by', 'picture_data',  'name', 'modules', 'created_at']

    def to_representation(self, instance):
        logger.debug(f"Serializing training: {instance}")
        return super().to_representation(instance)
    
    def get_picture_data(self, obj):
        """Convert binary picture data to base64 string for frontend consumption"""
        if obj.picture_data:
            return b64encode(obj.picture_data).decode('utf-8')
        return None
    
      
 

class CandidateSerializer(serializers.ModelSerializer):
    learner = CustomUserSerializer(read_only=True)
    training = TrainingSerializer(read_only=True)

    class Meta:
        model = Candidate
        fields = ['id', 'learner', 'training', 'status', 'created_at']