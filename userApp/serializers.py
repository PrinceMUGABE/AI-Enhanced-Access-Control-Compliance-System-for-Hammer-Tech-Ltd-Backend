# serializers.py - Updated with Department Validation

from rest_framework import serializers
from .models import CustomUser, UserLog
from departmentApp.models import Department


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
        """Get department details for employees (who have a single department)"""
        # Changed from 'mentee' to 'employee' to match your actual role choices
        if obj.role == 'employee' and obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name,
                'status': obj.department.status
            }
        return None

    def get_departments_details(self, obj):
        """Get departments details for security analysts"""
        # Changed from 'mentor' to 'security_analyst' to match your actual role choices
        if obj.role == 'security_analyst':
            return [
                {
                    'id': dept.id,
                    'name': dept.name,
                    'status': dept.status
                }
                for dept in obj.departments.all()
            ]
        return []

# userApp/serializers.py - UserCreateSerializer update
class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating users with department validation"""
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(status='active'),
        required=False,
        allow_null=True
    )
    departments = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Department.objects.filter(status='active'),
        required=False
    )
    # REMOVE password and confirm_password fields - they are system-generated
    # password = serializers.CharField(write_only=True, required=False)  # REMOVE
    # confirm_password = serializers.CharField(write_only=True, required=False)  # REMOVE
    
    class Meta:
        model = CustomUser
        fields = [
            'phone_number', 'email', 'full_name', 'role',
            'department', 'departments'  # Remove password fields
        ]
    
    def validate(self, data):
        role = data.get('role', 'employee')  # Default to 'employee'
        department = data.get('department')
        departments = data.get('departments', [])
        
        # Validate department requirements based on role
        if role == 'employee':
            if not department:
                raise serializers.ValidationError({
                    'department': 'Employee users must have a department assigned.'
                })
        
        elif role == 'security_analyst':
            if not departments or len(departments) == 0:
                raise serializers.ValidationError({
                    'departments': 'Security Analyst users must have at least one department assigned.'
                })
        
        elif role in ['admin', 'hr_manager']:
            # Clear departments for admin/hr
            data['department'] = None
            data['departments'] = []
        
        # REMOVE password validation - passwords are system-generated
        return data
    
    def create(self, validated_data):
        departments = validated_data.pop('departments', [])
        
        # Generate system password
        password = CustomUser.objects.make_random_password(length=12)
        
        user = CustomUser.objects.create_user(
            password=password,  # System-generated password
            **validated_data
        )
        
        # Set multiple departments for security analysts
        if user.role == 'security_analyst' and departments:
            user.departments.set(departments)
        
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating users (admin/HR only)"""
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(status='active'),
        required=False,
        allow_null=True
    )
    departments = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Department.objects.filter(status='active'),
        required=False
    )
    
    class Meta:
        model = CustomUser
        fields = [
            'phone_number', 'email', 'full_name', 'role',
            'department', 'departments', 'status', 'availability_status'
        ]
        read_only_fields = ['work_mail_address']
    
    def validate(self, data):
        instance = self.instance
        role = data.get('role', instance.role if instance else None)
        department = data.get('department')
        departments = data.get('departments')
        
        # Check if user can update departments
        request = self.context.get('request')
        if request and ('department' in data or 'departments' in data):
            if not request.user.can_update_departments():
                raise serializers.ValidationError({
                    'detail': 'Only admin and HR users can update departments.'
                })
        
        # Validate department requirements
        if role == 'employee':
            if department is None and 'department' in data:
                raise serializers.ValidationError({
                    'department': 'Employee users must have a department assigned.'
                })
        
        elif role == 'security_analyst':
            if departments is not None and len(departments) == 0:
                raise serializers.ValidationError({
                    'departments': 'Security Analyst users must have at least one department assigned.'
                })
        
        elif role in ['admin', 'hr_manager']:
            data['department'] = None
        
        return data
    
    def update(self, instance, validated_data):
        departments = validated_data.pop('departments', None)
        
        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Update departments for security analysts
        if instance.role == 'security_analyst' and departments is not None:
            instance.departments.set(departments)
            instance.department = None  # Clear FK
        elif instance.role == 'employee':
            instance.departments.clear()  # Clear M2M
        elif instance.role in ['admin', 'hr_manager']:
            instance.departments.clear()
            instance.department = None
        
        return instance


class RegisterSerializer(serializers.Serializer):
    """Serializer for self-registration (mentees only)"""
    phone_number = serializers.CharField(max_length=15, required=True)
    email = serializers.EmailField(required=True)
    full_name = serializers.CharField(max_length=100, required=True)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(status='active'),
        required=True
    )
    password = serializers.CharField(write_only=True, required=True)
    confirm_password = serializers.CharField(write_only=True, required=True)
    
    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match.'
            })
        return data


class LoginSerializer(serializers.Serializer):
    """Serializer for login"""
    work_mail_address = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Serializer for users updating their own profile (no department changes)"""
    class Meta:
        model = CustomUser
        fields = ['phone_number', 'email', 'full_name', 'availability_status']
    
    def validate(self, data):
        # Prevent department changes in profile updates
        if 'department' in data or 'departments' in data:
            raise serializers.ValidationError({
                'detail': 'You cannot change your department(s). Please contact admin or HR.'
            })
        return data


class ContactUsSerializer(serializers.Serializer):
    """Serializer for contact form"""
    names = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(required=True)
    subject = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(required=True)


class UpdateDepartmentSerializer(serializers.Serializer):
    """Serializer for updating user departments (admin/HR only)"""
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(status='active'),
        required=False,
        allow_null=True
    )
    departments = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Department.objects.filter(status='active'),
        required=False
    )
    
    def validate(self, data):
        user = self.context.get('user')
        if not user:
            raise serializers.ValidationError('User context is required.')
        
        department = data.get('department')
        departments = data.get('departments', [])
        
        if user.role == 'employee':
            if not department and department is not None:
                raise serializers.ValidationError({
                    'department': 'Employee users must have a department assigned.'
                })
        elif user.role == 'security_analyst':
            if not departments:
                raise serializers.ValidationError({
                    'departments': 'Security Analyst users must have at least one department assigned.'
                })
        
        return data
    




class CreatedByUserSerializer(serializers.ModelSerializer):
    """Serializer for the user who created the department"""
    class Meta:
        model = CustomUser
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






class LoginOTPRequestSerializer(serializers.Serializer):
    """Serializer for OTP login request"""
    email = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True)

class LoginOTPVerifySerializer(serializers.Serializer):
    """Serializer for OTP verification"""
    email = serializers.CharField(required=True, write_only=True)
    otp = serializers.CharField(required=True, write_only=True, max_length=6, min_length=6)





class UserLogSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField()
    target_user_details = serializers.SerializerMethodField()
    target_department_details = serializers.SerializerMethodField()
    
    class Meta:
        model = UserLog
        fields = [
            'id',
            'user',
            'user_details',
            'user_email',
            'user_role',
            'log_type',
            'activity',
            'description',
            'target_user',
            'target_user_details',
            'target_department',
            'target_department_details',
            'ip_address',
            'user_agent',
            'endpoint',
            'http_method',
            'status_code',
            'is_success',
            'is_auto_generated',
            'timestamp',
            'duration',
            'created_at',
            'request_data',
            'response_data'
        ]
        read_only_fields = fields
    
    def get_user_details(self, obj):
        if obj.user:
            return {
                'id': obj.user.id,
                'full_name': obj.user.full_name,
                'work_mail_address': obj.user.work_mail_address
            }
        return None
    
    def get_target_user_details(self, obj):
        if obj.target_user:
            return {
                'id': obj.target_user.id,
                'full_name': obj.target_user.full_name,
                'email': obj.target_user.email
            }
        return None
    
    def get_target_department_details(self, obj):
        if obj.target_department:
            return {
                'id': obj.target_department.id,
                'name': obj.target_department.name
            }
        return None