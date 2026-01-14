# mentorshipApp/serializers.py
from rest_framework import serializers
from django.utils.timezone import now
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import (
    MentorshipReview, ProgramSessionTemplate, MentorshipProgram,
    Mentorship, MentorshipSession, MentorshipProgramProgress
)
from userApp.models import CustomUser
from departmentApp.models import Department
from onboarding.models import MenteeOnboardingProgress, OnboardingModule


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info"""
    department = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'full_name', 'email', 'phone_number', 
            'work_mail_address', 'role', 'department', 
            'status', 'availability_status'
        ]
        read_only_fields = fields
    
    def get_department(self, obj):
        if obj.department:
            return {
                'id': obj.department.id,
                'name': obj.department.name
            }
        return None


class DepartmentSerializer(serializers.ModelSerializer):
    """Department serializer"""
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'status']
        read_only_fields = fields


class ProgramSessionTemplateSerializer(serializers.ModelSerializer):
    """Session template serializer"""
    class Meta:
        model = ProgramSessionTemplate
        fields = [
            'id', 'title', 'session_type', 'description', 
            'objectives', 'requirements', 'duration_minutes',
            'order', 'is_required', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate(self, data):
        """Validate unique combination of title and order (case-insensitive)"""
        title = data.get('title')
        order = data.get('order')
        
        if title and order:
            # Check if this is an update or create
            instance = self.instance
            
            # For create operations - use case-insensitive comparison
            if not instance:
                if ProgramSessionTemplate.objects.filter(
                    title__iexact=title,  # Case-insensitive filter
                    order=order
                ).exists():
                    raise serializers.ValidationError({
                        'error': f'A session template with title "{title}" and order {order} already exists.'
                    })
            # For update operations
            else:
                if ProgramSessionTemplate.objects.filter(
                    title__iexact=title,  # Case-insensitive filter
                    order=order
                ).exclude(id=instance.id).exists():
                    raise serializers.ValidationError({
                        'error': f'A session template with title "{title}" and order {order} already exists.'
                    })
        
        return data




class MentorshipProgramSerializer(serializers.ModelSerializer):
    """Mentorship program serializer"""
    department = DepartmentSerializer(read_only=True)
    # Make department_id optional and add a new field to accept the object
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(status='active'),
        write_only=True,
        source='department',
        required=False
    )
    
    # Add a field to accept department object
    department_object = serializers.DictField(
        write_only=True,
        required=False
    )
    
    session_templates = ProgramSessionTemplateSerializer(many=True, read_only=True)
    session_template_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    
    created_by = UserBasicSerializer(read_only=True)
    
    # Calculated fields
    total_sessions = serializers.SerializerMethodField()
    total_duration_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipProgram
        fields = [
            'id', 'name', 'department', 'department_id', 'department_object',
            'description', 'status', 'session_templates', 'session_template_ids',
            'total_days', 'objectives', 'prerequisites', 'created_at',
            'updated_at', 'created_by', 'total_sessions', 'total_duration_hours'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_days']
    
    def get_total_sessions(self, obj):
        return obj.get_total_sessions()
    
    def get_total_duration_hours(self, obj):
        return obj.get_total_duration_hours()
    
    def to_internal_value(self, data):
        """Handle both department object and department_id"""
        # Handle department object
        if 'department' in data and isinstance(data['department'], dict):
            # Extract department_id from the object
            department_id = data['department'].get('id')
            if department_id:
                data['department_id'] = department_id
            # Remove the original department field to avoid conflict
            data.pop('department', None)
        
        # Handle session_templates array
        if 'session_templates' in data and isinstance(data['session_templates'], list):
            template_ids = []
            for template in data['session_templates']:
                if isinstance(template, dict) and 'id' in template:
                    template_ids.append(template['id'])
                elif isinstance(template, (int, str)):
                    template_ids.append(int(template))
            
            if template_ids:
                data['session_template_ids'] = template_ids
            # Remove the original session_templates field
            data.pop('session_templates', None)
        
        return super().to_internal_value(data)
    
    def create(self, validated_data):
        session_template_ids = validated_data.pop('session_template_ids', [])
        program = MentorshipProgram.objects.create(**validated_data)
        
        if session_template_ids:
            templates = ProgramSessionTemplate.objects.filter(
                id__in=session_template_ids, 
                is_active=True
            )
            program.session_templates.set(templates)
        
        return program



# ==================== MENTORSHIP SERIALIZERS ====================
class MentorshipCreateSerializer(serializers.Serializer):
    """Serializer for creating mentorships"""
    mentor_id = serializers.IntegerField()
    mentee_id = serializers.IntegerField()
    department_id = serializers.IntegerField()
    program_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=[]
    )
    start_date = serializers.DateField()
    goals = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=[]
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Validate mentorship creation"""
        # Check if mentor exists and is available
        try:
            mentor = CustomUser.objects.get(id=data['mentor_id'], role='mentor')
            if mentor.availability_status != 'active':
                raise serializers.ValidationError("Mentor is not available")
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Mentor not found")
        
        # Check if mentee exists and completed onboarding
        try:
            mentee = CustomUser.objects.get(id=data['mentee_id'], role='mentee')
            
            # Check onboarding completion
            from onboarding.models import OnboardingModule, MenteeOnboardingProgress
            
            required_modules = OnboardingModule.objects.filter(
                is_required=True, 
                is_active=True
            )
            
            for module in required_modules:
                progress = MenteeOnboardingProgress.objects.filter(
                    mentee=mentee,
                    module=module
                ).first()
                
                if not progress or progress.status != 'completed':
                    raise serializers.ValidationError(
                        f"Mentee must complete onboarding module: {module.title}"
                    )
                    
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Mentee not found")
        
        # Check department
        try:
            department = Department.objects.get(id=data['department_id'], status='active')
        except Department.DoesNotExist:
            raise serializers.ValidationError("Department not found or inactive")
        
        # Check if mentor has the selected department (among their departments - ManyToMany)
        if not mentor.departments.filter(id=department.id).exists():
            raise serializers.ValidationError(
                f"Mentor {mentor.full_name} is not in the {department.name} department"
            )
        
        # Check if mentee belongs to the selected department (ForeignKey - single department)
        if mentee.department != department:
            raise serializers.ValidationError(
                f"Mentee {mentee.full_name} does not belong to the {department.name} department. "
                f"Mentee's department is: {mentee.department.name if mentee.department else 'Not assigned'}"
            )
        
        # Check for existing active mentorship for this specific mentor-mentee-department combination
        if Mentorship.objects.filter(
            mentor=mentor,
            mentee=mentee,
            department=department,
            status__in=['pending', 'active']
        ).exists():
            raise serializers.ValidationError(
                f"Active mentorship already exists for this mentor-mentee pair in {department.name}"
            )
        
        # Validate programs if provided
        if data.get('program_ids'):
            programs = MentorshipProgram.objects.filter(
                id__in=data['program_ids'],
                department=department,
                status='active'
            )
            
            if len(programs) != len(data['program_ids']):
                raise serializers.ValidationError(
                    "One or more programs are invalid or not in the selected department"
                )
        
        return data

# ==================== MENTORSHIP VIEW SERIALIZERS ====================
class MentorshipSerializer(serializers.ModelSerializer):
    """Mentorship serializer for viewing"""
    mentor = UserBasicSerializer(read_only=True)
    mentee = UserBasicSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    current_program = MentorshipProgramSerializer(read_only=True)
    programs = MentorshipProgramSerializer(many=True, read_only=True)
    
    # Progress fields
    sessions_completed = serializers.SerializerMethodField()
    total_sessions = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    next_session = serializers.SerializerMethodField()
    
    class Meta:
        model = Mentorship
        fields = [
            'id', 'mentor', 'mentee', 'department',
            'current_program', 'programs', 'status',
            'start_date', 'expected_end_date', 'actual_end_date',
            'sessions_completed', 'total_sessions', 'progress_percentage',
            'next_session', 'rating', 'goals', 'achievements',
            'feedback', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = fields
    
    def get_sessions_completed(self, obj):
        return obj.get_sessions_completed()
    
    def get_total_sessions(self, obj):
        return obj.get_total_sessions()
    
    def get_progress_percentage(self, obj):
        return obj.get_progress_percentage()
    
    def get_next_session(self, obj):
        next_session = obj.sessions.filter(
            status='scheduled',
            scheduled_date__gte=now()
        ).order_by('scheduled_date').first()
        
        if next_session:
            return {
                'id': next_session.id,
                'scheduled_date': next_session.scheduled_date,
             
                'title': next_session.session_template.title if next_session.session_template else "Session"
            }
        return None
# ==================== USER MENTORSHIP SERIALIZER ====================
class UserMentorshipSerializer(serializers.ModelSerializer):
    """Simplified serializer for user views"""
    other_user = serializers.SerializerMethodField()
    department = DepartmentSerializer(read_only=True)
    current_program = serializers.SerializerMethodField()
    
    # Progress
    sessions_completed = serializers.SerializerMethodField()
    total_sessions = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Mentorship
        fields = [
            'id', 'other_user', 'department', 'current_program',
            'status', 'start_date', 'expected_end_date',
            'sessions_completed', 'total_sessions', 'progress_percentage',
            'rating', 'created_at'
        ]
        read_only_fields = fields
    
    def get_other_user(self, obj):
        """Get the other person in the mentorship"""
        request = self.context.get('request')
        if request and request.user:
            if request.user == obj.mentor:
                return {
                    'id': obj.mentee.id,
                    'full_name': obj.mentee.full_name,
                    'role': 'mentee',
                    'email': obj.mentee.email
                }
            else:
                return {
                    'id': obj.mentor.id,
                    'full_name': obj.mentor.full_name,
                    'role': 'mentor',
                    'email': obj.mentor.email
                }
        return None
    
    def get_current_program(self, obj):
        if obj.current_program:
            return {
                'id': obj.current_program.id,
                'name': obj.current_program.name
            }
        return None
    
    def get_sessions_completed(self, obj):
        return obj.get_sessions_completed()
    
    def get_total_sessions(self, obj):
        return obj.get_total_sessions()
    
    def get_progress_percentage(self, obj):
        return obj.get_progress_percentage()


# ==================== SESSION SERIALIZERS ====================
# In mentorshipApp/serializers.py

class MentorshipSessionSerializer(serializers.ModelSerializer):
    """Mentorship session serializer"""
    mentorship = MentorshipSerializer(read_only=True)
    session_template = ProgramSessionTemplateSerializer(read_only=True)

    # Derived fields
    session_type = serializers.SerializerMethodField()

    # ✅ Correct model fields
    program_session_number = serializers.IntegerField(read_only=True)
    overall_session_number = serializers.IntegerField(read_only=True)

    is_upcoming = serializers.SerializerMethodField()
    is_past_due = serializers.SerializerMethodField()

    class Meta:
        model = MentorshipSession
        fields = [
            'id',
            'mentorship',
            'session_template',

            # ✅ USE THESE — NOT session_number
            'program_session_number',
            'overall_session_number',

            'session_type',
            'status',
            'scheduled_date',
            'actual_date',
            'duration_minutes',
            'agenda',
            'objectives',
            'notes',
            'action_items',
            'mentor_rating',
            'mentor_feedback',
            'mentee_feedback',
            'meeting_link',
            'location',
            'completed_by',
            'created_at',
            'is_upcoming',
            'is_past_due',
        ]

        read_only_fields = [
            'id',
            'created_at',
            'completed_by',
            'program_session_number',
            'overall_session_number',
        ]

    def get_session_type(self, obj):
        return obj.session_template.session_type if obj.session_template else None

    def get_is_upcoming(self, obj):
        return obj.is_upcoming()

    def get_is_past_due(self, obj):
        return obj.is_past_due()

class SessionCreateSerializer(serializers.Serializer):
    """Serializer for creating sessions"""
    mentorship_id = serializers.IntegerField()
    session_template_id = serializers.IntegerField(required=False)
    program_session_number = serializers.IntegerField(required=False)  # Use correct field name
    
    # session_type is not needed here since it comes from the template
    scheduled_date = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(required=False)
    agenda = serializers.CharField(required=False, allow_blank=True)
    meeting_link = serializers.URLField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Validate session creation data"""
        mentorship = Mentorship.objects.get(id=data['mentorship_id'])
        
        # Get session number to use
        session_number = data.get('program_session_number')
        
        if session_number:
            # Check if session number doesn't exceed total sessions
            total_sessions = mentorship.current_program.get_total_sessions()
            
            if session_number > total_sessions:
                raise serializers.ValidationError(
                    f"Session number exceeds total sessions in program ({total_sessions})"
                )
            
            # Check for duplicate session number
            if MentorshipSession.objects.filter(
                mentorship=mentorship,
                program_session_number=session_number,
                program=mentorship.current_program
            ).exists():
                raise serializers.ValidationError(
                    f"Session number {session_number} already exists for this program"
                )
        
        return data
    

class SessionCompletionSerializer(serializers.Serializer):
    """Serializer for completing a session"""
    notes = serializers.CharField(required=False, allow_blank=True)
    mentor_feedback = serializers.CharField(required=False, allow_blank=True)
    mentee_feedback = serializers.CharField(required=False, allow_blank=True)
    action_items = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    mentor_rating = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=5
    )
    
    def validate(self, data):
        """Validate completion data"""
        # Check if user is authorized
        request = self.context.get('request')
        if not request or request.user.role == 'mentee':
            raise serializers.ValidationError("You are not authorized to mark sessions as completed")
        
        return data


class MentorshipReviewSerializer(serializers.ModelSerializer):
    """Serializer for mentorship reviews"""
    reviewer = UserBasicSerializer(read_only=True)
    reviewer_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        write_only=True,
        source='reviewer'
    )
    mentorship_id = serializers.PrimaryKeyRelatedField(
        queryset=Mentorship.objects.all(),
        write_only=True,
        source='mentorship'
    )
    mentorship = serializers.PrimaryKeyRelatedField(read_only=True)
    
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipReview
        fields = [
            'id', 'mentorship', 'mentorship_id', 'reviewer', 'reviewer_id', 
            'reviewer_type', 'rating', 'communication_rating', 
            'knowledge_rating', 'helpfulness_rating', 'review_text', 
            'would_recommend', 'created_at', 'updated_at', 'average_rating'
        ]
        read_only_fields = ['id', 'reviewer', 'mentorship', 'created_at', 'updated_at']
    
    def get_average_rating(self, obj):
        return obj.get_average_rating()
    
    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value
    
    def validate(self, data):
        for field in ['communication_rating', 'knowledge_rating', 'helpfulness_rating']:
            if field in data and (data[field] < 1 or data[field] > 5):
                raise serializers.ValidationError(f"{field} must be between 1 and 5")
        
        # Check reviewer type matches user role
        reviewer = data.get('reviewer')
        reviewer_type = data.get('reviewer_type')
        
        if reviewer and reviewer_type:
            if reviewer_type == 'mentee' and reviewer.role != 'mentee':
                raise serializers.ValidationError("Reviewer type must match user role")
            elif reviewer_type == 'mentor' and reviewer.role != 'mentor':
                raise serializers.ValidationError("Reviewer type must match user role")
        
        return data
    



class ProgramSessionsSerializer(serializers.Serializer):
    """Serializer for program session templates"""
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    session_type = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    order = serializers.IntegerField()
    is_required = serializers.BooleanField()
    status = serializers.SerializerMethodField()
    scheduled_date = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    
    def get_status(self, obj):
        """Get session status if scheduled/completed"""
        mentorship = self.context.get('mentorship')
        if not mentorship:
            return 'not_scheduled'
        
        session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            session_template=obj
        ).first()
        
        if session:
            return session.status
        return 'not_scheduled'
    
    def get_scheduled_date(self, obj):
        """Get scheduled date if session exists"""
        mentorship = self.context.get('mentorship')
        if not mentorship:
            return None
        
        session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            session_template=obj
        ).first()
        
        return session.scheduled_date if session else None
    
    def get_session_id(self, obj):
        """Get session ID if session exists"""
        mentorship = self.context.get('mentorship')
        if not mentorship:
            return None
        
        session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            session_template=obj
        ).first()
        
        return session.id if session else None


class ProgramWithSessionsSerializer(serializers.ModelSerializer):
    """Serializer for program with its sessions"""
    session_templates = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    sessions_completed = serializers.SerializerMethodField()
    total_sessions = serializers.SerializerMethodField()
    
    class Meta:
        model = MentorshipProgram
        fields = [
            'id', 'name', 'description', 'session_templates',
            'progress', 'sessions_completed', 'total_sessions',
            'total_duration_hours', 'total_days'
        ]
    
    def get_session_templates(self, obj):
        """Get all session templates with status"""
        mentorship = self.context.get('mentorship')
        templates = obj.session_templates.filter(is_active=True).order_by('order')
        
        return ProgramSessionsSerializer(
            templates, 
            many=True,
            context={'mentorship': mentorship}
        ).data
    
    def get_progress(self, obj):
        """Get program progress percentage"""
        mentorship = self.context.get('mentorship')
        if not mentorship:
            return 0
        
        progress = MentorshipProgramProgress.objects.filter(
            mentorship=mentorship,
            program=obj
        ).first()
        
        return progress.progress_percentage if progress else 0
    
    def get_sessions_completed(self, obj):
        """Get completed sessions count"""
        mentorship = self.context.get('mentorship')
        if not mentorship:
            return 0
        
        return MentorshipSession.objects.filter(
            mentorship=mentorship,
            program=obj,
            status='completed'
        ).count()
    
    def get_total_sessions(self, obj):
        """Get total sessions in program"""
        return obj.session_templates.filter(is_active=True).count()