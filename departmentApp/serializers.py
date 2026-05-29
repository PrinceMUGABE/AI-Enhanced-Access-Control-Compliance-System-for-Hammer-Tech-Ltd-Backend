# departmentApp/serializers.py

from rest_framework import serializers
from .models import Department
from userApp.models import CustomUser as User


class CreatedByUserSerializer(serializers.ModelSerializer):
    """Serializer for the user who created the department"""
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'email', 'work_mail_address', 'full_name', 'role', 'department']


class DepartmentSerializer(serializers.ModelSerializer):
    created_by_details = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'status', 'created_at', 'updated_at', 'created_by', 'created_by_details']
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'created_by_details']
    
    def get_created_by_details(self, obj):
        """Get full details of the user who created the department"""
        if obj.created_by:
            return CreatedByUserSerializer(obj.created_by).data
        return None
    
    def validate_name(self, value):
        """Validate department name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Department name cannot be empty.")
        
        # Check for duplicate names (case-insensitive)
        name = value.strip().title()
        department_id = self.instance.id if self.instance else None
        
        if Department.objects.filter(name__iexact=name).exclude(id=department_id).exists():
            raise serializers.ValidationError("A department with this name already exists.")
        
        if len(name) < 2:
            raise serializers.ValidationError("Department name must be at least 2 characters long.")
        
        if len(name) > 100:
            raise serializers.ValidationError("Department name cannot exceed 100 characters.")
        
        return name
    
    def validate_status(self, value):
        """Validate status"""
        valid_statuses = ['active', 'inactive']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
        return value


class DepartmentCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for creating departments"""
    class Meta:
        model = Department
        fields = ['name', 'description', 'status']
    
    def validate_name(self, value):
        """Validate department name"""
        if not value or not value.strip():
            raise serializers.ValidationError("Department name cannot be empty.")
        
        name = value.strip().title()
        
        if Department.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError("A department with this name already exists.")
        
        if len(name) < 2:
            raise serializers.ValidationError("Department name must be at least 2 characters long.")
        
        if len(name) > 100:
            raise serializers.ValidationError("Department name cannot exceed 100 characters.")
        
        return name
    
    def validate_status(self, value):
        """Validate status"""
        valid_statuses = ['active', 'inactive']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
        return value


class DepartmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating departments"""
    class Meta:
        model = Department
        fields = ['name', 'description', 'status']
    
    def validate_name(self, value):
        """Validate department name on update"""
        if not value or not value.strip():
            raise serializers.ValidationError("Department name cannot be empty.")
        
        name = value.strip().title()
        department_id = self.instance.id if self.instance else None
        
        if Department.objects.filter(name__iexact=name).exclude(id=department_id).exists():
            raise serializers.ValidationError("A department with this name already exists.")
        
        if len(name) < 2:
            raise serializers.ValidationError("Department name must be at least 2 characters long.")
        
        if len(name) > 100:
            raise serializers.ValidationError("Department name cannot exceed 100 characters.")
        
        return name
    
    def validate_status(self, value):
        """Validate status"""
        valid_statuses = ['active', 'inactive']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
        return value