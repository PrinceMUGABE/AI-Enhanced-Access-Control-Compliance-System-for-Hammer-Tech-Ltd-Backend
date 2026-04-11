# userApp/models.py - Fixed with Custom Email Field
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
import random
import string
import re

class WorkEmailValidator(EmailValidator):
    """Custom email validator that allows underscores in domain names"""
    message = "Enter a valid work email address."
    
    # Modified regex to allow underscores in domain
    domain_regex = r'((?:[A-Z0-9_](?:[A-Z0-9_-]{0,61}[A-Z0-9_])?\.)+)(?:[A-Z0-9_-]{2,63}(?<!-))$'
    
    def __call__(self, value):
        # Custom validation for work email
        if not value or '@' not in value:
            raise ValidationError(self.message, code=self.code)
        
        # Split into local and domain parts
        parts = value.rsplit('@', 1)
        if len(parts) != 2:
            raise ValidationError(self.message, code=self.code)
        
        local_part, domain_part = parts
        
        # Validate local part (before @)
        if not local_part or len(local_part) > 64:
            raise ValidationError(self.message, code=self.code)
        
        # Validate domain part (after @) - allow underscores
        if not domain_part:
            raise ValidationError(self.message, code=self.code)
        
        # Check for valid domain format (allowing underscores)
        domain_pattern = r'^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*\.[a-zA-Z]{2,}$'
        if not re.match(domain_pattern, domain_part):
            raise ValidationError(self.message, code=self.code)

from django.contrib.auth.models import BaseUserManager
import random
from departmentApp.models import Department

class CustomUserManager(BaseUserManager):

    def create_user(
        self,
        phone_number,
        email,
        full_name,
        password=None,
        role='employee',
        department=None,      # single department for employee
        departments=None,     # multiple departments for security analyst
        status='pending',
        availability_status='inactive',
        work_mail_address=None,
        created_by=None,
        **extra_fields
    ):
        """
        Create and save a user with the given phone number, email, full name, password, and role.
        Handles single department for employees and multiple departments for security analysts.
        Generates work email if not provided.
        """

        if not phone_number:
            raise ValueError("The phone number must be provided")
        if not email:
            raise ValueError("The email must be provided")
        if not full_name:
            raise ValueError("The full name must be provided")
        if role not in [choice[0] for choice in CustomUser.ROLE_CHOICES]:
            raise ValueError("Invalid role selected")

        email = self.normalize_email(email)

        # 🔹 Generate work email if not provided
        if not work_mail_address:
            work_mail_address = self.generate_work_mail(full_name, role)
        extra_fields['work_mail_address'] = work_mail_address

        # 🔹 Employee: assign single department
        if role == 'employee':
            if not department:
                raise ValueError("Employee users must have a department assigned.")
            try:
                dept_obj = Department.objects.get(id=department, status='active')
                extra_fields['department'] = dept_obj
            except Department.DoesNotExist:
                raise ValueError("Invalid or inactive department selected")

        # 🔹 Create user instance
        user = self.model(
            phone_number=phone_number,
            email=email,
            full_name=full_name,
            role=role,
            status=status,
            availability_status=availability_status,
            created_by=created_by,
            **extra_fields
        )

        if not password:
            raise ValueError("Password must be provided")
        user.set_password(password)
        user.save(using=self._db)

        # 🔹 Security analyst: assign multiple departments
        if role == 'security_analyst':
            if not departments or len(departments) == 0:
                raise ValueError("Security Analyst users must have at least one department assigned.")
            valid_depts = list(Department.objects.filter(id__in=departments, status='active'))
            if len(valid_depts) != len(departments):
                raise ValueError("One or more selected departments are invalid or inactive")
            user.departments.set(valid_depts)

        return user

    def create_superuser(
        self,
        phone_number,
        email,
        full_name,
        password=None,
        **extra_fields
    ):
        """
        Create and save a superuser with the given phone number, email, full name, and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(
            phone_number=phone_number,
            email=email,
            full_name=full_name,
            password=password,
            role='admin',
            status='approved',
            availability_status='active',
            **extra_fields
        )

    @staticmethod
    def generate_work_mail(full_name, role):
        """
        Generate a work email address from full name and role.
        Handles duplicates by appending random numbers.
        """
        full_name = full_name.strip()
        names = full_name.split()

        role_prefixes = {
            'admin': 'admin',
            'hr_manager': 'hr_manager',
            'compliance_officer': 'compliance_officer',
            'security_analyst': 'security_analyst',
            'employee': 'employee',
        }
        role_prefix = role_prefixes.get(role, 'user')

        if len(names) >= 2:
            first_initial = names[0][0].lower()
            last_name = names[-1].lower().replace(' ', '')
            base_mail = f"{first_initial}.{last_name}@{role_prefix}_hammer_tech_group.com"
        else:
            base_mail = f"{full_name.lower().replace(' ', '')}@{role_prefix}_hammer_tech_group.com"

        # Check for duplicates
        mail_exists = CustomUser.objects.filter(work_mail_address=base_mail).exists()
        if not mail_exists:
            return base_mail

        random_num = random.randint(100, 999)
        if len(names) >= 2:
            return f"{first_initial}.{last_name}{random_num}@{role_prefix}_hammer_tech_group.com"
        else:
            return f"{full_name.lower().replace(' ', '')}{random_num}@{role_prefix}_hammer_tech_group.com"
        
        
        
                    
class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('hr_manager', 'HR Manager'),
        ('compliance_officer', 'Compliance Officer'),
        ('security_analyst', 'Security Analyst'),
        ('employee', 'Employee'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    AVAILABILITY_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    phone_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(unique=True)
    
    # Use CharField instead of EmailField to avoid validation issues with custom domain
    work_mail_address = models.CharField(
        max_length=255,
        unique=True,
        validators=[WorkEmailValidator()],
        help_text="Work email address with custom domain format"
    )
    
    full_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    
    # Single department for mentee users (ForeignKey)
    department = models.ForeignKey(
        'departmentApp.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
    
    # Multiple departments for mentor users (ManyToManyField)
    departments = models.ManyToManyField(
        'departmentApp.Department',
        blank=True,
        related_name='security_analysts'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    availability_status = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='inactive')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_users')

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['email', 'full_name']

    objects = CustomUserManager()

    def __str__(self):
        return self.work_mail_address

    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_hr(self):
        return self.role == 'hr_manager'
    
    @property
    def is_mentor(self):
        return self.role == 'security_analyst'
    
    @property
    def is_mentee(self):
        return self.role == 'employee'
    
    def can_update_departments(self):
        """Check if user can update other users' departments"""
        return self.role in ['admin', 'hr_manager']
    
    def clean(self):
        """Validate department requirements based on role"""
        super().clean()
        
        # Employee require a single department
        if self.role == 'employee' and not self.department:
            raise ValidationError({'department': 'Employee users must have a department assigned.'})
        
        # Admin and HR don't require departments
        if self.role in ['admin', 'hr_manager']:
            self.department = None
    
    def save(self, *args, **kwargs):
        # Only validate if not bypassing validation
        if not kwargs.pop('skip_validation', False):
            self.full_clean()
        super().save(*args, **kwargs)
        
        # Post-save validation for security analysts
        if self.role == 'security_analyst' and self.departments.count() == 0:
            pass  # Allow save, validation happens in views/forms



class UserLog(models.Model):
    """Comprehensive user activity logging system"""
    
    # Activity type categories
    LOG_TYPE_CHOICES = [
        ('authentication', 'Authentication'),
        ('profile', 'Profile'),
        ('user_management', 'User Management'),
        ('department', 'Department Management'),
        ('system', 'System Activity'),
    ]
    
    ACTIVITY_CHOICES = [
        # Authentication activities
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('login_otp_request', 'Login OTP Request'),
        ('login_otp_verify', 'Login OTP Verification'),
        ('register', 'User Registration'),
        
        # Profile activities
        ('profile_update', 'Profile Update'),
        ('password_change', 'Password Change'),
        ('password_reset_request', 'Password Reset Request'),
        ('password_reset_complete', 'Password Reset Complete'),
        
        # User management activities
        ('user_create', 'Create User'),
        ('user_update', 'Update User'),
        ('user_delete', 'Delete User'),
        ('user_activate', 'Activate User'),
        ('user_deactivate', 'Deactivate User'),
        ('user_status_update', 'Update User Status'),
        
        # Department activities
        ('department_create', 'Create Department'),
        ('department_update', 'Update Department'),
        ('department_delete', 'Delete Department'),
        
        # System activities
        ('contact_us', 'Contact Form Submission'),
        ('token_refresh', 'Token Refresh'),
        ('token_verify', 'Token Verification'),
    ]
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        db_index=True
    )
    user_email = models.EmailField(max_length=255, db_index=True, help_text="User's email at time of activity")
    user_role = models.CharField(max_length=20, null=True, blank=True, help_text="User's role at time of activity")
    
    # Activity details
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, db_index=True)
    activity = models.CharField(max_length=50, choices=ACTIVITY_CHOICES, db_index=True)
    description = models.TextField(help_text="Detailed description of the activity")
    
    # Request/Response data (optional, for debugging)
    request_data = models.JSONField(null=True, blank=True, help_text="Request data snapshot")
    response_data = models.JSONField(null=True, blank=True, help_text="Response data snapshot")
    
    # Target information (for actions affecting other users/entities)
    target_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='targeted_activities',
        help_text="User affected by this activity"
    )
    target_department = models.ForeignKey(
        'departmentApp.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Department affected by this activity"
    )
    
    # Technical information
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(null=True, blank=True, help_text="Browser/device information")
    endpoint = models.CharField(max_length=500, null=True, blank=True, help_text="API endpoint accessed")
    http_method = models.CharField(max_length=10, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True, help_text="HTTP status code")
    
    # Status flags
    is_success = models.BooleanField(default=True, help_text="Whether the activity was successful")
    is_auto_generated = models.BooleanField(default=False, help_text="System-generated log")
    
    # Timing
    timestamp = models.DateTimeField(default=now, db_index=True)
    duration = models.DurationField(null=True, blank=True, help_text="Activity duration in seconds")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['activity', 'timestamp']),
            models.Index(fields=['log_type', 'timestamp']),
            models.Index(fields=['user_email', 'timestamp']),
        ]
        verbose_name = 'User Activity Log'
        verbose_name_plural = 'User Activity Logs'
    
    def __str__(self):
        return f"{self.user_email} - {self.activity} - {self.timestamp}"
    
    def save(self, *args, **kwargs):
        # Auto-fill user_email if user is provided
        if self.user and not self.user_email:
            self.user_email = self.user.email
        if self.user and not self.user_role:
            self.user_role = self.user.role
        super().save(*args, **kwargs)