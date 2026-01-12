from django.forms import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg
from django.utils.timezone import now
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta
from notificationApp.models import ChatNotification
from chatApp.models import ChatRoom
from departmentApp.models import Department
from django.db import transaction

from .models import (
    MentorshipProgram, Mentorship, MentorshipProgramProgress, MentorshipSession,
    MentorshipMessage, MentorshipReview,
    ProgramSessionTemplate
)
from .serializers import (
     DepartmentSerializer, MentorshipProgramSerializer, MentorshipSerializer,
    MentorshipSessionSerializer,
    SessionCreateSerializer,
    MentorshipReviewSerializer, ProgramSessionTemplateSerializer,
      SessionCompletionSerializer, MentorshipSessionSerializer, MentorshipCreateSerializer, UserMentorshipSerializer
    
)
from userApp.models import CustomUser
from departmentApp.models import Department
from rest_framework import serializers
from django.db.models import Count, Q, F, Sum, Max, Min
from django.utils import timezone

from .utils import (
    send_session_scheduled_notification,
    send_session_completed_notification,
    send_session_cancelled_notification,
    send_session_rescheduled_notification,
    send_program_completed_notification,
    send_mentorship_completed_notification
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_departments(request):
    """Get all active departments"""
    try:
        departments = Department.objects.filter(status='active').order_by('name')
        serializer = DepartmentSerializer(departments, many=True)
        return Response({
            'success': True,
            'departments': serializer.data
        })
    except Exception as e:
        return Response({
            'error': 'Failed to fetch departments',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_programs(request, department_id):
    """Get programs for a specific department"""
    try:
        department = get_object_or_404(Department, id=department_id, status='active')
        programs = MentorshipProgram.objects.filter(
            department=department,
            status='active'
        )
        serializer = MentorshipProgramSerializer(programs, many=True)
        return Response({
            'success': True,
            'department': DepartmentSerializer(department).data,
            'programs': serializer.data
        })
    except Exception as e:
        return Response({
            'error': 'Failed to fetch department programs',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_available_mentors(request):
    """Get available mentors for a department"""
    print("submitted data: ", request.query_params)
    try:
        department_name = request.query_params.get('department')
        if not department_name:
            print("Department is not provided in request")
            return Response({
                'error': 'Department is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        department = get_object_or_404(Department, name=department_name, status='active')
        print("Fetching mentors for department: ", department.name)
        
        # Get mentors in department
        mentors = CustomUser.objects.filter(
            role='mentor',
            departments=department,  # ManyToMany field
            status='approved',
            availability_status='active'
        )

        if not mentors.exists():
            print("No mentors found in department")
            print(f"Users in {department.name} department: ", CustomUser.objects.filter(departments=department, role='mentor').count())

        print(f"Total mentors found: {mentors.count()}")
        
        # Check workload
        mentors_data = []
        for mentor in mentors:
            active_mentorships = Mentorship.objects.filter(
                mentor=mentor,
                status='active'
            ).count()
            
            # Get all departments for this mentor
            mentor_departments = [dept.name for dept in mentor.departments.all()]
            
            mentors_data.append({
                'id': mentor.id,
                'full_name': mentor.full_name,
                'email': mentor.email,
                'departments': mentor_departments,  # List of department names
                'active_mentorships': active_mentorships,
                'is_available': active_mentorships < 5  # Max 5 mentees
            })
        
        print(f"Available mentors data prepared: {len(mentors_data)} mentors")
        
        return Response({
            'success': True,
            'department': department.name,
            'mentors': mentors_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Error in get_available_mentors: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Failed to fetch available mentors',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ready_mentees(request):
    """Get mentees ready for mentorship in a department"""
    print("submitted data: ", request.query_params)
    try:
        department_name = request.query_params.get('department')
        if not department_name:
            print("Department not provided in request")
            return Response({
                'error': 'Department is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        department = get_object_or_404(Department, name=department_name, status='active')
        print("Fetching ready mentees for department: ", department.name)
        
        # Get mentees in department
        mentees = CustomUser.objects.filter(
            role='mentee',
            department=department,
            status='approved'
        )
        
        print(f"Total mentees found: {mentees.count()}")
        
        from onboarding.models import MenteeOnboardingProgress, OnboardingModule
        
        ready_mentees = []
        for mentee in mentees:
            print(f"Checking mentee: {mentee.full_name}")
            
            # Check onboarding completion
            required_modules = OnboardingModule.objects.filter(
                is_required=True,
                is_active=True
            )
            
            completed_all = True
            for module in required_modules:
                progress = MenteeOnboardingProgress.objects.filter(
                    mentee=mentee,
                    module=module
                ).first()
                
                if not progress or progress.status != 'completed':
                    completed_all = False
                    print(f"  - Module {module.title} not completed")
                    break
            
            # Check for existing mentorship
            has_active_mentorship = Mentorship.objects.filter(
                mentee=mentee,
                department=department,
                status__in=['pending', 'active']
            ).exists()
            
            if completed_all and not has_active_mentorship:
                print(f"  ✓ Mentee {mentee.full_name} is ready for mentorship")
                ready_mentees.append({
                    'id': mentee.id,
                    'full_name': mentee.full_name,
                    'email': mentee.email,
                    'department': department.name,  # Just return the name string
                    'is_ready': True
                })
            else:
                print(f"  ✗ Mentee {mentee.full_name} is NOT ready (completed_all: {completed_all}, has_active: {has_active_mentorship})")
        
        print(f"Total ready mentees: {len(ready_mentees)}")
        
        return Response({
            'success': True,
            'department': department.name,
            'ready_mentees': ready_mentees,
            'count': len(ready_mentees)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Error in get_ready_mentees: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Failed to fetch ready mentees',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentees_ready_for_mentorship(request):
    """Get mentees who have completed onboarding and are ready for mentorship"""
    print("submitted data: ", request.query_params)
    try:
        department = request.query_params.get('department')
        
        if not department:
            print("Department parameter is missing")
            return Response({
                'error': 'Department parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from onboarding.models import OnboardingModule, MenteeOnboardingProgress
        
        # Get all mentees in the department
        mentees = CustomUser.objects.filter(
            role='mentee',
            department=department,
            status='approved'
        )
        
        ready_mentees = []
        for mentee in mentees:
            # Check if mentee has completed all required core modules
            required_core_modules = OnboardingModule.objects.filter(
                module_type='core',
                is_required=True,
                is_active=True
            )
            
            completed_all = True
            for module in required_core_modules:
                progress = MenteeOnboardingProgress.objects.filter(
                    mentee=mentee,
                    module=module
                ).first()
                
                if not progress or progress.status != 'completed':
                    completed_all = False
                    break
            
            if completed_all:
                # Check if mentee already has active mentorship
                has_active_mentorship = Mentorship.objects.filter(
                    mentee=mentee,
                    status__in=['pending', 'active']
                ).exists()
                
                ready_mentees.append({
                    'id': mentee.id,
                    'full_name': mentee.full_name,
                    'email': mentee.email,
                    'department': mentee.department,
                    'onboarding_completed': completed_all,
                    'has_active_mentorship': has_active_mentorship,
                    'last_active': mentee.last_login
                })
        
        return Response({
            'success': True,
            'department': department,
            'mentees': ready_mentees,
            'count': len(ready_mentees)
        }, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error in get_mentees_ready_for_mentorship: {str(e)}")
        return Response({
            'error': 'Failed to fetch mentees ready for mentorship',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_mentorship(request):
    """Create a new mentorship (Admin/HR only)"""
    try:
        if request.user.role not in ['admin', 'hr']:
            print("Permission denied for user: ", request.user.full_name)
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        print("Received data:", request.data)
        
        serializer = MentorshipCreateSerializer(data=request.data)
        if not serializer.is_valid():
            print("Validation errors: ", serializer.errors)
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        print("Validated data:", data)
        
        with transaction.atomic():
            # Get objects
            mentor = CustomUser.objects.get(id=data['mentor_id'])
            mentee = CustomUser.objects.get(id=data['mentee_id'])
            department = Department.objects.get(id=data['department_id'])
            
            print(f"Creating mentorship:")
            print(f"  Mentor: {mentor.full_name} (departments: {[d.name for d in mentor.departments.all()]})")
            print(f"  Mentee: {mentee.full_name} (department: {mentee.department.name if mentee.department else 'None'})")
            print(f"  Department: {department.name}")
            
            # Create mentorship
            mentorship = Mentorship.objects.create(
                mentor=mentor,
                mentee=mentee,
                department=department,
                start_date=data['start_date'],
                goals=data.get('goals', []),
                notes=data.get('notes', ''),
                status='active',
                created_by=request.user
            )
            
            # Add programs if specified
            if data.get('program_ids'):
                programs = MentorshipProgram.objects.filter(
                    id__in=data['program_ids'],
                    department=department
                )
                mentorship.programs.set(programs)
                
                # Set first program as current
                if programs.exists():
                    mentorship.current_program = programs.first()
                    mentorship.save()
                    
                    # Create program progress records
                    for program in programs:
                        MentorshipProgramProgress.objects.create(
                            mentorship=mentorship,
                            program=program,
                            total_sessions=program.get_total_sessions()
                        )
        
        print(f"✓ Mentorship created successfully: ID {mentorship.id}")
        
        return Response({
            'success': True,
            'message': 'Mentorship created successfully',
            'mentorship': MentorshipSerializer(mentorship).data
        }, status=status.HTTP_201_CREATED)
        
    except serializers.ValidationError as e:
        # Handle DRF validation errors properly
        print(f"Validation error: {e.detail}")
        error_message = str(e.detail[0]) if isinstance(e.detail, list) else str(e.detail)
        return Response({
            'error': 'Validation failed',
            'detail': error_message
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        print(f"Error in create_mentorship: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Failed to create mentorship',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_mentorship_program(request):
    """Create a new mentorship program (Admin/HR only)"""
    print("Received data for creating program: ", request.data)
   
    try:
        if request.user.role not in ['admin', 'hr']:
            print("Permission denied for user: ", request.user.full_name)
            return Response({
                'error': 'Permission denied. Only Admin and HR can create programs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = MentorshipProgramSerializer(data=request.data)
        
        if not serializer.is_valid():
            print("Validation errors: ", serializer.errors)
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        program = serializer.save(created_by=request.user)
        
        return Response({
            'success': True,
            'message': 'Mentorship program created successfully',
            'program': MentorshipProgramSerializer(program).data
        }, status=status.HTTP_201_CREATED)
    
    except ValidationError as e:
        print(f"Validation error: {str(e)}")
        return Response({
            'error': 'Validation failed',
            'detail': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in create_mentorship_program: {str(e)}")
        return Response({
            'error': 'Failed to create program',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_session_templates(request):
    """List all session templates"""
    try:
        templates = ProgramSessionTemplate.objects.filter(is_active=True)
        serializer = ProgramSessionTemplateSerializer(templates, many=True)
        return Response({
            'success': True,
            'count': templates.count(),
            'templates': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Failed to fetch session templates',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_session_template(request, template_id):
    """Get single session template details"""
    try:
        template = get_object_or_404(ProgramSessionTemplate, id=template_id, is_active=True)
        serializer = ProgramSessionTemplateSerializer(template)
        return Response({
            'success': True,
            'template': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Session template not found',
            'detail': str(e)
        }, status=status.HTTP_404_NOT_FOUND)
    



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session(request):

    """Create a session for the current program in mentorship"""
    try:
        serializer = SessionCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        mentorship = get_object_or_404(Mentorship, id=data['mentorship_id'])
        
        # Check if mentorship has a current program
        if not mentorship.current_program:
            return Response({
                'error': 'No current program assigned to this mentorship'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create session for current program
        program_progress = mentorship.program_progress.filter(
            program=mentorship.current_program
        ).first()
        
        if not program_progress:
            return Response({
                'error': 'Program progress not found'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get next session number for this program
        last_session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            program=mentorship.current_program
        ).order_by('-program_session_number').first()
        
        program_session_number = (last_session.program_session_number + 1) if last_session else 1
        
        # Create session
        session = MentorshipSession.objects.create(
            mentorship=mentorship,
            program=mentorship.current_program,
            program_progress=program_progress,
            session_template_id=data.get('session_template_id'),
            program_session_number=program_session_number,
            session_type=data.get('session_type', 'video'),
            scheduled_date=data['scheduled_date'],
            duration_minutes=data.get('duration_minutes', 60),
            agenda=data.get('agenda', ''),
            meeting_link=data.get('meeting_link', ''),
            location=data.get('location', ''),
            status='scheduled'
        )
        
        return Response({
            'success': True,
            'message': 'Session created successfully',
            'session': MentorshipSessionSerializer(session).data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'error': 'Failed to create session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_session_completed(request, session_id):
    """Mark a session as completed"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        user = request.user
        
        # Check permission
        mentorship = session.mentorship
        if user not in [mentorship.mentor, mentorship.mentee]:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Mark as completed
        mentor_feedback = request.data.get('mentor_feedback', '')
        mentee_feedback = request.data.get('mentee_feedback', '')
        notes = request.data.get('notes', '')
        
        session.mark_completed(
            user=user,
            notes=notes,
            mentor_feedback=mentor_feedback,
            mentee_feedback=mentee_feedback
        )
        
        return Response({
            'success': True,
            'message': 'Session marked as completed',
            'session': MentorshipSessionSerializer(session).data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to mark session as completed',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_programs(request):
    """Get all mentorship programs"""
    try:
        programs = MentorshipProgram.objects.filter(status='active')
        serializer = MentorshipProgramSerializer(programs, many=True)
        return Response({
            'success': True,
            'programs': serializer.data
        })
    except Exception as e:
        return Response({
            'error': 'Failed to fetch programs',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_program_sessions(request, program_id):
    """Get all session templates for a program"""
    try:
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        # Check permissions based on user role
        user = request.user
        if user.role == 'mentee':
            # Mentees can only see programs in their department
            if user.department != program.department:
                return Response({
                    'error': 'Permission denied. You can only view programs in your department'
                }, status=status.HTTP_403_FORBIDDEN)
        
        session_templates = program.session_templates.filter(is_active=True).order_by('order')
        serializer = ProgramSessionTemplateSerializer(session_templates, many=True)
        
        program_data = {
            'id': program.id,
            'name': program.name,
            'department': program.department.name,
            'total_sessions': program.get_total_sessions(),
            'total_duration_hours': program.get_total_duration_hours(),
            'total_days': program.total_days,
            'sessions': serializer.data
        }
        
        return Response({
            'success': True,
            'program': program_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to fetch program sessions',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session_template(request):
    """Create a new session template (Admin/HR only)"""
    print("Received data for session template creation: ", request.data)
    try:
        if request.user.role not in ['admin', 'hr']:
            print("Permission denied for user: ", request.user.full_name)
            return Response({
                'error': 'Permission denied. Only Admin and HR can create session templates'
            }, status=status.HTTP_403_FORBIDDEN)
               
        
        serializer = ProgramSessionTemplateSerializer(data=request.data)
        
        if not serializer.is_valid():
            print("Validation errors: ", serializer.errors)
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session_template = serializer.save()
        print(f"✓ Session template created successfully: ID {session_template.id}")
        
        return Response({
            'success': True,
            'message': 'Session template created successfully',
            'session_template': ProgramSessionTemplateSerializer(session_template).data
        }, status=status.HTTP_201_CREATED)
    
    except ValidationError as e:
        print(f"Validation error: {str(e)}")
        return Response({
            'error': 'Validation failed',
            'detail': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f"Error in create_session_template: {str(e)}")
        return Response({
            'error': 'Failed to create session template',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentorship_progress(request, mentorship_id):
    """Get detailed progress of a mentorship"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        user = request.user
        
        # Check permissions
        if user.role == 'mentor' and mentorship.mentor != user:
            return Response({
                'error': 'Permission denied. You can only view your own mentorships'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if user.role == 'mentee' and mentorship.mentee != user:
            return Response({
                'error': 'Permission denied. You can only view your own mentorships'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all session templates for the program
        session_templates = mentorship.program.session_templates.filter(is_active=True).order_by('order')
        
        # Get completed sessions
        completed_sessions = mentorship.sessions.filter(status='completed')
        completed_session_numbers = [s.session_number for s in completed_sessions]
        
        progress_data = []
        for template in session_templates:
            session = mentorship.sessions.filter(session_template=template).first()
            
            progress_data.append({
                'session_number': template.order,
                'template_id': template.id,
                'title': template.title,
                'description': template.description,
                'objectives': template.objectives,
                'requirements': template.requirements,
                'duration_minutes': template.duration_minutes,
                'is_required': template.is_required,
                'status': 'completed' if template.order in completed_session_numbers else 'pending',
                'scheduled_date': session.scheduled_date if session else None,
                'completed_date': session.actual_date if session and session.status == 'completed' else None,
                'completed_by': {
                    'id': session.completed_by.id,
                    'name': session.completed_by.full_name
                } if session and session.completed_by else None
            })
        
        return Response({
            'success': True,
            'mentorship': {
                'id': mentorship.id,
                'program': mentorship.program.name,
                'mentor': mentorship.mentor.full_name,
                'mentee': mentorship.mentee.full_name,
                'status': mentorship.status,
                'progress_percentage': mentorship.get_progress_percentage(),
                'sessions_completed': mentorship.sessions_completed,
                'total_sessions': mentorship.program.get_total_sessions(),
                'remaining_sessions': mentorship.get_remaining_sessions(),
                'start_date': mentorship.start_date,
                'expected_end_date': mentorship.expected_end_date,
                'actual_end_date': mentorship.actual_end_date,
                'is_overdue': mentorship.is_overdue(),
                'can_schedule': mentorship.can_schedule_session()
            },
            'sessions': progress_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to fetch mentorship progress',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_mentorship_programs(request):
    """List all mentorship programs"""
    try:
        status_filter = request.query_params.get('status', None)
        
        programs = MentorshipProgram.objects.all()
        
        if status_filter:
            if status_filter not in ['active', 'inactive', 'archived']:
                print(f"Invalid status filter received: {status_filter}")
                return Response({
                    'error': 'Invalid status filter. Must be: active, inactive, or archived'
                }, status=status.HTTP_400_BAD_REQUEST)
            programs = programs.filter(status=status_filter)
        
        # Admin and HR see all, others see only active
        if request.user.role not in ['admin', 'hr']:
            programs = programs.filter(status='active')
        
        serializer = MentorshipProgramSerializer(programs, many=True)
        print(f"Programs fetched: {programs.count()}")
        return Response({
            'success': True,
            'count': programs.count(),
            'programs': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        print(f"Error in list_mentorship_programs: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching programs',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentorship_program(request, program_id):
    """Get single mentorship program details"""
    try:
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        serializer = MentorshipProgramSerializer(program)
        return Response({
            'success': True,
            'program': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Program not found',
            'detail': str(e)
        }, status=status.HTTP_404_NOT_FOUND)



@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_mentorship_program(request, program_id):
    """Update mentorship program (Admin/HR only)"""
    try:
        if request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied. Only Admin and HR can update programs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        partial = request.method == 'PATCH'
        serializer = MentorshipProgramSerializer(
            program, data=request.data, partial=partial
        )
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        program = serializer.save()
        
        return Response({
            'success': True,
            'message': 'Program updated successfully',
            'program': MentorshipProgramSerializer(program).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to update program',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_mentorship_program(request, program_id):
    """Archive mentorship program (Admin only)"""
    try:
        if request.user.role != 'admin':
            return Response({
                'error': 'Permission denied. Only Admin can archive programs'
            }, status=status.HTTP_403_FORBIDDEN)
        
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        # Check if program has active mentorships
        if program.mentorships.filter(status='active').exists():
            return Response({
                'error': 'Cannot archive program with active mentorships',
                'message': 'Please complete or cancel all active mentorships first'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        program.status = 'archived'
        program.save()
        
        return Response({
            'success': True,
            'message': 'Program archived successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to archive program',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MENTORSHIP VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_mentorships(request):
    """List mentorships based on user role"""
    try:
        user = request.user
        status_filter = request.query_params.get('status', None)
        program_filter = request.query_params.get('program', None)
        department_filter = request.query_params.get('department', None)
        
        # Base queryset based on role
        if user.role == 'mentor':
            mentorships = Mentorship.objects.filter(mentor=user)
        elif user.role == 'mentee':
            mentorships = Mentorship.objects.filter(mentee=user)
        elif user.role in ['admin', 'hr']:
            mentorships = Mentorship.objects.all()
        else:
            return Response({
                'error': 'Invalid user role'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Apply filters - ONLY basic filters, heavy filtering will be done in frontend
        if status_filter:
            if status_filter not in dict(Mentorship.STATUS_CHOICES).keys():
                return Response({
                    'error': f'Invalid status. Must be one of: {", ".join(dict(Mentorship.STATUS_CHOICES).keys())}'
                }, status=status.HTTP_400_BAD_REQUEST)
            mentorships = mentorships.filter(status=status_filter)
        
        # Department filter - simple filtering for better performance
        if department_filter:
            # First try to get department by ID
            if department_filter.isdigit():
                try:
                    department = Department.objects.get(id=int(department_filter))
                    mentorships = mentorships.filter(department=department)
                except Department.DoesNotExist:
                    return Response({
                        'error': f'Department with ID {department_filter} not found'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Try to get by name
                try:
                    department = Department.objects.get(name=department_filter)
                    mentorships = mentorships.filter(department=department)
                except Department.DoesNotExist:
                    # If department name not found, filter by department name string
                    mentorships = mentorships.filter(department__name=department_filter)
        
        # Program filter - using current_program instead of program
        if program_filter:
            try:
                mentorships = mentorships.filter(current_program_id=int(program_filter))
            except (ValueError, TypeError):
                return Response({
                    'error': 'Invalid program ID'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # FIXED: Use correct related field names
        mentorships = mentorships.select_related(
            'mentor', 
            'mentee', 
            'department', 
            'current_program',  # Changed from 'program' to 'current_program'
            'created_by'
        ).prefetch_related(
            'programs',  # ManyToMany field
            'completed_programs'  # ManyToMany field
        )
        
        # Get the data with serialization
        mentorships_data = []
        for mentorship in mentorships:
            # Get serialized data
            serializer = MentorshipSerializer(mentorship)
            mentorship_data = serializer.data
            
            # Add progress information if needed
            if hasattr(mentorship, 'get_progress_percentage'):
                mentorship_data['progress_percentage'] = mentorship.get_progress_percentage()
            
            # Calculate remaining sessions if possible
            if mentorship.current_program:
                try:
                    total_sessions = mentorship.current_program.get_total_sessions()
                    completed_sessions = mentorship.sessions.filter(
                        status='completed',
                        program=mentorship.current_program
                    ).count()
                    mentorship_data['sessions_completed'] = completed_sessions
                    mentorship_data['total_sessions'] = total_sessions
                    if total_sessions > 0:
                        mentorship_data['progress_percentage'] = round((completed_sessions / total_sessions) * 100, 2)
                except Exception:
                    mentorship_data['sessions_completed'] = 0
                    mentorship_data['total_sessions'] = 0
                    mentorship_data['progress_percentage'] = 0
            
            mentorships_data.append(mentorship_data)
        
        return Response({
            'success': True,
            'count': len(mentorships_data),
            'mentorships': mentorships_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        print(f"Error in list_mentorships: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        
        return Response({
            'error': 'An error occurred while fetching mentorships',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentorship(request, mentorship_id):
    """Get single mentorship details"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        user = request.user
        
        # Check permissions
        if user.role == 'mentor' and mentorship.mentor != user:
            return Response({
                'error': 'Permission denied. You can only view your own mentorships'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if user.role == 'mentee' and mentorship.mentee != user:
            return Response({
                'error': 'Permission denied. You can only view your own mentorships'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if user.role not in ['admin', 'hr', 'mentor', 'mentee']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = MentorshipSerializer(mentorship)
        return Response({
            'success': True,
            'mentorship': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Mentorship not found',
            'detail': str(e)
        }, status=status.HTTP_404_NOT_FOUND)




@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_mentorship_status(request, mentorship_id):
    """Update mentorship status"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        user = request.user
        
        # Check permissions
        if user.role not in ['admin', 'hr'] and mentorship.mentor != user:
            return Response({
                'error': 'Permission denied. Only Admin, HR, or assigned mentor can update status'
            }, status=status.HTTP_403_FORBIDDEN)
        
        new_status = request.data.get('status')
        if not new_status:
            return Response({
                'error': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_status not in dict(Mentorship.STATUS_CHOICES).keys():
            return Response({
                'error': f'Invalid status. Must be one of: {", ".join(dict(Mentorship.STATUS_CHOICES).keys())}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        old_status = mentorship.status
        mentorship.status = new_status
        
        if new_status == 'active' and old_status == 'pending':
            mentorship.start_date = now().date()
        
        if new_status == 'completed':
            mentorship.end_date = now().date()
        
        mentorship.save()
        
        # Send notification
        if hasattr(mentorship, 'chat_room'):
            status_display = dict(Mentorship.STATUS_CHOICES).get(new_status, new_status)
            ChatNotification.objects.create(
                recipient=mentorship.mentee,
                chat_room=mentorship.chat_room,
                notification_type='case_status_changed',
                title='Mentorship Status Updated',
                message=f'Your mentorship status has been changed to: {status_display}'
            )
        
        return Response({
            'success': True,
            'message': 'Status updated successfully',
            'mentorship': MentorshipSerializer(mentorship).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to update status',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def add_mentorship_goals(request, mentorship_id):
    """Add or update mentorship goals"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        user = request.user
        
        # Only mentor, mentee, admin, or HR can update goals
        if user not in [mentorship.mentor, mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        goals = request.data.get('goals')
        if not goals or not isinstance(goals, list):
            return Response({
                'error': 'Goals must be provided as a list'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        mentorship.goals = goals
        mentorship.save()
        
        return Response({
            'success': True,
            'message': 'Goals updated successfully',
            'goals': mentorship.goals
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to update goals',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== SESSION VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_sessions(request):
    """List sessions based on filters"""
    try:
        user = request.user
        mentorship_id = request.query_params.get('mentorship')
        status_filter = request.query_params.get('status')
        
        # Base queryset based on role
        if user.role == 'mentor':
            sessions = MentorshipSession.objects.filter(mentorship__mentor=user)
        elif user.role == 'mentee':
            sessions = MentorshipSession.objects.filter(mentorship__mentee=user)
        elif user.role in ['admin', 'hr']:
            sessions = MentorshipSession.objects.all()
        else:
            return Response({
                'error': 'Invalid user role'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Apply filters
        if mentorship_id:
            try:
                sessions = sessions.filter(mentorship_id=int(mentorship_id))
            except (ValueError, TypeError):
                return Response({
                    'error': 'Invalid mentorship ID'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if status_filter:
            if status_filter not in dict(MentorshipSession.SESSION_STATUS).keys():
                print(f"Invalid status filter received: {status_filter}")
                return Response({
                    'error': f'Invalid status. Must be one of: {", ".join(dict(MentorshipSession.SESSION_STATUS).keys())}'
                }, status=status.HTTP_400_BAD_REQUEST)
            sessions = sessions.filter(status=status_filter)
        
        sessions = sessions.select_related('mentorship__mentor', 'mentorship__mentee', 'mentorship__current_program')
        serializer = MentorshipSessionSerializer(sessions, many=True)
        
        return Response({
            'success': True,
            'count': sessions.count(),
            'sessions': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        print(f"Error in list_sessions: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching sessions',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_session(request, session_id):
    """Get single session details"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        user = request.user
        
        # Check permissions
        if user.role == 'mentor' and session.mentorship.mentor != user:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if user.role == 'mentee' and session.mentorship.mentee != user:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if user.role not in ['admin', 'hr', 'mentor', 'mentee']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = MentorshipSessionSerializer(session)
        return Response({
            'success': True,
            'session': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Session not found',
            'detail': str(e)
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session(request):
    """Create a new session"""
    try:
        serializer = SessionCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        mentorship = get_object_or_404(Mentorship, id=data['mentorship_id'])
        user = request.user
        
        # Check permissions
        if user not in [mentorship.mentor, mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied. Only participants, Admin, or HR can schedule sessions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get next session number
        last_session = mentorship.sessions.order_by('-session_number').first()
        session_number = (last_session.session_number + 1) if last_session else 1
        
        # Check for scheduling conflicts
        conflicts = MentorshipSession.objects.filter(
            Q(mentorship__mentor=mentorship.mentor) | Q(mentorship__mentee=mentorship.mentee),
            status='scheduled',
            scheduled_date__date=data['scheduled_date'].date()
        )
        
        for conflict in conflicts:
            time_diff = abs((conflict.scheduled_date - data['scheduled_date']).total_seconds() / 3600)
            if time_diff < 1:
                return Response({
                    'error': 'Scheduling conflict detected',
                    'message': f'There is another session scheduled at {conflict.scheduled_date}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create session
        session = MentorshipSession.objects.create(
            mentorship=mentorship,
            session_number=session_number,
            session_type=data['session_type'],
            scheduled_date=data['scheduled_date'],
            duration_minutes=data['duration_minutes'],
            agenda=data.get('agenda', ''),
            meeting_link=data.get('meeting_link', ''),
            location=data.get('location', ''),
            status='scheduled'
        )
        
        # Send notifications
        if hasattr(mentorship, 'chat_room'):
            ChatNotification.objects.create(
                recipient=mentorship.mentee,
                chat_room=mentorship.chat_room,
                notification_type='module_assigned',
                title='New Session Scheduled',
                message=f'Session {session_number} has been scheduled for {data["scheduled_date"].strftime("%Y-%m-%d %H:%M")}'
            )
            
            ChatNotification.objects.create(
                recipient=mentorship.mentor,
                chat_room=mentorship.chat_room,
                notification_type='module_assigned',
                title='New Session Scheduled',
                message=f'Session {session_number} has been scheduled for {data["scheduled_date"].strftime("%Y-%m-%d %H:%M")}'
            )
        
        return Response({
            'success': True,
            'message': 'Session created successfully',
            'session': MentorshipSessionSerializer(session).data
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'error': 'Failed to create session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_session_completed(request, session_id):
    """Mark a session as completed"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        user = request.user
        
        # Check permissions
        if user not in [session.mentorship.mentor, session.mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if session.status == 'completed':
            return Response({
                'error': 'Session is already marked as completed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        notes = request.data.get('notes', '')
        mentor_feedback = request.data.get('mentor_feedback', '')
        mentee_feedback = request.data.get('mentee_feedback', '')
        action_items = request.data.get('action_items', [])
        
        session.mark_completed(notes, mentor_feedback, mentee_feedback)
        
        if action_items:
            session.action_items = action_items
            session.save()
        
        return Response({
            'success': True,
            'message': 'Session marked as completed',
            'session': MentorshipSessionSerializer(session).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to mark session as completed',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def reschedule_session(request, session_id):
    """Reschedule a session"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        user = request.user
        
        # Check permissions
        if user not in [session.mentorship.mentor, session.mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if session.status != 'scheduled':
            return Response({
                'error': 'Can only reschedule sessions with scheduled status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        new_date = request.data.get('new_date')
        if not new_date:
            return Response({
                'error': 'New date is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from datetime import datetime
        try:
            new_date = datetime.fromisoformat(new_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return Response({
                'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_date < now():
            return Response({
                'error': 'Cannot reschedule to a past date'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session.reschedule(new_date)
        
        # Send notifications
        if hasattr(session.mentorship, 'chat_room'):
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=session.mentorship.chat_room,
                notification_type='status_changed',
                title='Session Rescheduled',
                message=f'Session {session.session_number} has been rescheduled to {new_date.strftime("%Y-%m-%d %H:%M")}'
            )
            
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=session.mentorship.chat_room,
                notification_type='status_changed',
                title='Session Rescheduled',
                message=f'Session {session.session_number} has been rescheduled to {new_date.strftime("%Y-%m-%d %H:%M")}'
            )
        
        return Response({
            'success': True,
            'message': 'Session rescheduled successfully',
            'session': MentorshipSessionSerializer(session).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to reschedule session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def cancel_session(request, session_id):
    """Cancel a session"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        user = request.user
        
        # Check permissions
        if user not in [session.mentorship.mentor, session.mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if session.status == 'completed':
            return Response({
                'error': 'Cannot cancel a completed session'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reason = request.data.get('reason', 'No reason provided')
        session.mark_cancelled(reason)
        
        # Send notifications
        if hasattr(session.mentorship, 'chat_room'):
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=session.mentorship.chat_room,
                notification_type='status_changed',
                title='Session Cancelled',
                message=f'Session {session.session_number} has been cancelled. Reason: {reason}'
            )
            
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=session.mentorship.chat_room,
                notification_type='status_changed',
                title='Session Cancelled',
                message=f'Session {session.session_number} has been cancelled. Reason: {reason}'
            )
        
        return Response({
            'success': True,
            'message': 'Session cancelled successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to cancel session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_mentorship_actions(request):
    """Handle bulk actions on multiple mentorships"""
    try:
        if request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied. Only Admin and HR can perform bulk actions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        mentorship_ids = request.data.get('mentorshipIds', [])
        action = request.data.get('action')
        
        if not mentorship_ids:
            return Response({
                'error': 'No mentorships selected'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not action:
            return Response({
                'error': 'Action is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_actions = ['activate', 'complete', 'pause', 'cancel', 'delete']
        if action not in valid_actions:
            return Response({
                'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the mentorships
        mentorships = Mentorship.objects.filter(id__in=mentorship_ids)
        
        if mentorships.count() != len(mentorship_ids):
            return Response({
                'error': 'Some mentorships were not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for mentorship in mentorships:
                try:
                    if action == 'activate':
                        if mentorship.status != 'active':
                            mentorship.status = 'active'
                            if not mentorship.start_date:
                                mentorship.start_date = now().date()
                            mentorship.save()
                            updated_count += 1
                            
                    elif action == 'complete':
                        if mentorship.status != 'completed':
                            mentorship.status = 'completed'
                            mentorship.actual_end_date = now().date()
                            mentorship.save()
                            updated_count += 1
                            
                    elif action == 'pause':
                        if mentorship.status == 'active':
                            mentorship.status = 'paused'
                            mentorship.save()
                            updated_count += 1
                            
                    elif action == 'cancel':
                        if mentorship.status not in ['completed', 'cancelled']:
                            mentorship.status = 'cancelled'
                            mentorship.save()
                            updated_count += 1
                            
                    elif action == 'delete':
                        # Check if mentorship can be deleted
                        if mentorship.status in ['completed', 'cancelled']:
                            mentorship.delete()
                            updated_count += 1
                        else:
                            errors.append(f'Mentorship {mentorship.id} cannot be deleted because it is {mentorship.status}')
                    
                except Exception as e:
                    errors.append(f'Error processing mentorship {mentorship.id}: {str(e)}')
                    continue
        
        response_data = {
            'success': True,
            'message': f'Bulk action completed. Processed {updated_count} mentorships.',
            'updated_count': updated_count,
            'total_selected': len(mentorship_ids)
        }
        
        if errors:
            response_data['errors'] = errors
            response_data['has_errors'] = True
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to perform bulk action',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    






@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_current_program(request, mentorship_id, program_id):
    """Switch to a different program within the department"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        new_program = get_object_or_404(MentorshipProgram, id=program_id)
        
        # Check if program belongs to mentorship's department
        if new_program.department != mentorship.department.name:
            return Response({
                'error': 'Program does not belong to mentorship department'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if program is in mentorship's programs list
        if not mentorship.programs.filter(id=program_id).exists():
            return Response({
                'error': 'Program not assigned to this mentorship'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Switch current program
        mentorship.current_program = new_program
        mentorship.save()
        
        return Response({
            'success': True,
            'message': f'Switched to program: {new_program.name}',
            'current_program': MentorshipProgramSerializer(new_program).data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Failed to switch program',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_sessions(request):
    """Get sessions for the logged-in user"""
    try:
        user = request.user
        
        if user.role == 'mentor':
            mentorships = Mentorship.objects.filter(mentor=user)
        elif user.role == 'mentee':
            mentorships = Mentorship.objects.filter(mentee=user)
        else:
            return Response({
                'success': True,
                'sessions': []
            })
        
        sessions = MentorshipSession.objects.filter(
            mentorship__in=mentorships
        ).select_related(
            'mentorship',
            'session_template'
        ).order_by('-scheduled_date')
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            sessions = sessions.filter(status=status_filter)
        
        mentorship_filter = request.query_params.get('mentorship')
        if mentorship_filter:
            sessions = sessions.filter(mentorship_id=mentorship_filter)
        
        serializer = MentorshipSessionSerializer(sessions, many=True)
        
        return Response({
            'success': True,
            'sessions': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch sessions',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_dashboard(request):
    """Get dashboard data for the logged-in user"""
    try:
        user = request.user
        
        if user.role not in ['mentor', 'mentee']:
            return Response({
                'success': True,
                'message': 'Dashboard only for mentors and mentees'
            })
        
        # Get user's mentorships
        if user.role == 'mentor':
            all_mentorships = Mentorship.objects.filter(mentor=user)
        else:
            all_mentorships = Mentorship.objects.filter(mentee=user)
        
        active_mentorships = all_mentorships.filter(status='active')
        
        # Calculate statistics
        stats = {
            'total_mentorships': all_mentorships.count(),
            'active_mentorships': active_mentorships.count(),
            'completed_mentorships': all_mentorships.filter(status='completed').count(),
            'pending_mentorships': all_mentorships.filter(status='pending').count(),
        }
        
        # Get upcoming sessions (next 7 days)
        upcoming_sessions = MentorshipSession.objects.filter(
            mentorship__in=active_mentorships,
            status='scheduled',
            scheduled_date__gte=now(),
            scheduled_date__lte=now() + timedelta(days=7)
        ).order_by('scheduled_date')[:5]
        
        # Get recent sessions (last 7 days)
        recent_sessions = MentorshipSession.objects.filter(
            mentorship__in=all_mentorships,
            status='completed',
            actual_date__gte=now() - timedelta(days=7)
        ).order_by('-actual_date')[:5]
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'role': user.role
            },
            'statistics': stats,
            'upcoming_sessions': MentorshipSessionSerializer(upcoming_sessions, many=True).data,
            'recent_sessions': MentorshipSessionSerializer(recent_sessions, many=True).data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch dashboard data',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_upcoming_sessions(request):
    """Get upcoming sessions for the logged-in user"""
    try:
        user = request.user
        
        # Get user's mentorships
        if user.role == 'mentor':
            mentorships = Mentorship.objects.filter(mentor=user, status='active')
        elif user.role == 'mentee':
            mentorships = Mentorship.objects.filter(mentee=user, status='active')
        else:
            return Response({
                'success': True,
                'upcoming_sessions': []
            })
        
        # Get upcoming sessions
        upcoming_sessions = MentorshipSession.objects.filter(
            mentorship__in=mentorships,
            status='scheduled',
            scheduled_date__gte=now()
        ).select_related(
            'mentorship',
            'mentorship__mentor',
            'mentorship__mentee',
            'session_template'
        ).order_by('scheduled_date')
        
        serializer = MentorshipSessionSerializer(upcoming_sessions, many=True)
        
        return Response({
            'success': True,
            'upcoming_sessions': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch upcoming sessions',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_mentorship_detail(request, mentorship_id):
    """Get detailed view of a specific mentorship"""
    try:
        user = request.user
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permission
        if user not in [mentorship.mentor, mentorship.mentee] and user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get mentorship data
        serializer = MentorshipSerializer(mentorship)
        
        # Get sessions
        sessions = MentorshipSession.objects.filter(
            mentorship=mentorship
        ).order_by('scheduled_date')
        
        session_serializer = MentorshipSessionSerializer(sessions, many=True)
        
        # Get upcoming sessions
        upcoming_sessions = sessions.filter(
            status='scheduled',
            scheduled_date__gte=now()
        ).order_by('scheduled_date')
        
        # Get program progress
        program_progress = []
        for program in mentorship.programs.all():
            progress = MentorshipProgramProgress.objects.filter(
                mentorship=mentorship,
                program=program
            ).first()
            
            if progress:
                program_progress.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'progress_percentage': progress.progress_percentage,
                    'sessions_completed': progress.sessions_completed,
                    'total_sessions': progress.total_sessions,
                    'status': progress.status
                })
        
        return Response({
            'success': True,
            'mentorship': serializer.data,
            'sessions': session_serializer.data,
            'upcoming_sessions': MentorshipSessionSerializer(upcoming_sessions, many=True).data,
            'program_progress': program_progress
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch mentorship details',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_active_mentorships(request):
    """Get active mentorships for the logged-in user"""
    try:
        user = request.user
        
        if user.role == 'mentor':
            mentorships = Mentorship.objects.filter(mentor=user, status='active')
        elif user.role == 'mentee':
            mentorships = Mentorship.objects.filter(mentee=user, status='active')
        else:
            return Response({
                'success': True,
                'active_mentorships': []
            })
        
        serializer = UserMentorshipSerializer(
            mentorships, 
            many=True,
            context={'request': request}
        )
        print(serializer.data)
        
        return Response({
            'success': True,
            'active_mentorships': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch active mentorships',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_mentorships(request):
    """Get all mentorships for the logged-in user"""
    try:
        user = request.user
        
        if user.role == 'mentor':
            mentorships = Mentorship.objects.filter(mentor=user)
        elif user.role == 'mentee':
            mentorships = Mentorship.objects.filter(mentee=user)
        else:
            print("Admin user trying to access my mentorships")
            return Response({
                'success': True,
                'message': 'Admin users should use admin endpoints',
                'mentorships': []
            })
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            mentorships = mentorships.filter(status=status_filter)
        
        department_filter = request.query_params.get('department')
        if department_filter:
            mentorships = mentorships.filter(department_id=department_filter)
        
        mentorships = mentorships.order_by('-created_at')
        serializer = UserMentorshipSerializer(
            mentorships, 
            many=True,
            context={'request': request}
        )
        print("\n My mentorships: ",serializer.data, "\n")
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'role': user.role
            },
            'mentorships': serializer.data
        })
        
    except Exception as e:
        print(f"Error in get_my_mentorships: {str(e)}")
        return Response({
            'error': 'Failed to fetch your mentorships',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_mentorships(request):
    """Get all mentorships (Admin/HR only)"""
    if request.user.role not in ['admin', 'hr']:
        return Response({
            'error': 'Permission denied'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        mentorships = Mentorship.objects.all().select_related(
            'mentor', 'mentee', 'department', 'current_program'
        ).order_by('-created_at')
        
        serializer = MentorshipSerializer(mentorships, many=True)
        
        return Response({
            'success': True,
            'mentorships': serializer.data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch mentorships',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_mentorship_status(request, mentorship_id):
    """Update mentorship status (Admin/HR only)"""
    if request.user.role not in ['admin', 'hr']:
        return Response({
            'error': 'Permission denied'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({
                'error': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if new_status not in dict(Mentorship.STATUS_CHOICES).keys():
            return Response({
                'error': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        mentorship.status = new_status
        mentorship.save()
        
        return Response({
            'success': True,
            'message': 'Status updated successfully',
            'mentorship': MentorshipSerializer(mentorship).data
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to update status',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




# mentorshipApp/views.py - Add these imports
from .serializers import MentorshipReviewSerializer
from .models import MentorshipReview

# mentorshipApp/views.py - Add this endpoint

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_can_review_mentorship(request, mentorship_id):
    """Check if user can review a mentorship"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        user = request.user
        
        # Check if user is part of this mentorship
        if user not in [mentorship.mentor, mentorship.mentee]:
            return Response({
                'can_review': False,
                'reason': 'You are not a participant in this mentorship'
            })
        
        # Check if mentorship is completed
        if mentorship.status != 'completed':
            return Response({
                'can_review': False,
                'reason': 'Can only review completed mentorships'
            })
        
        # Check if review already exists
        reviewer_type = 'mentee' if user == mentorship.mentee else 'mentor'
        has_reviewed = MentorshipReview.objects.filter(
            mentorship=mentorship,
            reviewer=user,
            reviewer_type=reviewer_type
        ).exists()
        
        if has_reviewed:
            return Response({
                'can_review': False,
                'reason': 'You have already reviewed this mentorship',
                'has_reviewed': True
            })
        
        return Response({
            'can_review': True,
            'mentorship': {
                'id': mentorship.id,
                'mentor': mentorship.mentor.full_name,
                'mentee': mentorship.mentee.full_name,
                'department': mentorship.department.name if mentorship.department else None,
                'start_date': mentorship.start_date,
                'end_date': mentorship.actual_end_date
            },
            'reviewer_type': reviewer_type
        })
        
    except Exception as e:
        return Response({
            'can_review': False,
            'reason': 'Error checking review eligibility',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_mentorship_review(request):
    """Create a review for a completed mentorship"""
    print('Create mentorship review with these data:', request.data)
    try:
        # Only mentees and mentors can review
        if request.user.role not in ['mentee', 'mentor']:
            print('User role:', request.user.role, 'is not allowed to submit reviews')
            return Response({
                'error': 'Only mentees and mentors can submit reviews'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get mentorship
        mentorship_id = request.data.get('mentorship')
        if not mentorship_id:
            print('Mentorship ID not provided in request data')
            return Response({
                'error': 'Mentorship ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check if mentorship is completed
        if mentorship.status != 'completed':
            print('Mentorship status:', mentorship.status, 'is not completed')
            return Response({
                'error': 'Can only review completed mentorships'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is part of this mentorship
        if request.user not in [mentorship.mentor, mentorship.mentee]:
            print('User is not a participant in this mentorship')
            return Response({
                'error': 'You can only review mentorships you participated in'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if review already exists
        reviewer_type = 'mentee' if request.user == mentorship.mentee else 'mentor'
        if MentorshipReview.objects.filter(
            mentorship=mentorship,
            reviewer=request.user,
            reviewer_type=reviewer_type
        ).exists():
            print('User has already submitted a review for this mentorship')
            return Response({
                'error': 'You have already reviewed this mentorship'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prepare data for serializer
        review_data = {
            'mentorship_id': mentorship.id,
            'reviewer_id': request.user.id,  # Pass user ID, serializer will get the user object
            'reviewer_type': reviewer_type,
            'rating': request.data.get('rating'),
            'communication_rating': request.data.get('communication_rating'),
            'knowledge_rating': request.data.get('knowledge_rating'),
            'helpfulness_rating': request.data.get('helpfulness_rating'),
            'review_text': request.data.get('review_text', ''),
            'would_recommend': request.data.get('would_recommend', True)
        }
        
        print('Review data prepared for serializer:', review_data)
        
        # Validate and create review
        serializer = MentorshipReviewSerializer(data=review_data)
        
        if not serializer.is_valid():
            print('Review serializer errors:', serializer.errors)
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        review = serializer.save()
        
        print(f'Review created successfully with ID: {review.id}')
        
        return Response({
            'success': True,
            'message': 'Review submitted successfully',
            'review': MentorshipReviewSerializer(review).data
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print('Exception occurred while submitting review:', str(e))
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        return Response({
            'error': 'Failed to submit review',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentorship_reviews(request, mentorship_id):
    """Get all reviews for a specific mentorship"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permissions - admin/HR can see all, others only their own
        user = request.user
        if user.role not in ['admin', 'hr'] and user not in [mentorship.mentor, mentorship.mentee]:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        reviews = MentorshipReview.objects.filter(mentorship=mentorship).select_related('reviewer')
        
        # Get detailed review data
        reviews_data = []
        for review in reviews:
            review_dict = {
                'id': review.id,
                'reviewer': {
                    'id': review.reviewer.id,
                    'full_name': review.reviewer.full_name,
                    'email': review.reviewer.email,
                    'role': review.reviewer.role
                },
                'reviewer_type': review.reviewer_type,
                'rating': review.rating,
                'communication_rating': review.communication_rating,
                'knowledge_rating': review.knowledge_rating,
                'helpfulness_rating': review.helpfulness_rating,
                'review_text': review.review_text,
                'would_recommend': review.would_recommend,
                'created_at': review.created_at,
                'updated_at': review.updated_at,
                'average_rating': review.get_average_rating()
            }
            reviews_data.append(review_dict)
        
        return Response({
            'success': True,
            'mentorship': {
                'id': mentorship.id,
                'mentor': mentorship.mentor.full_name,
                'mentee': mentorship.mentee.full_name,
                'status': mentorship.status
            },
            'reviews': reviews_data,
            'count': len(reviews_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch reviews',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentor_performance(request):
    """Get mentor's performance metrics and reviews"""
    try:
        if request.user.role != 'mentor':
            print('User role:', request.user.role, 'is not mentor')
            return Response({
                'error': 'This endpoint is for mentors only'
            }, status=status.HTTP_403_FORBIDDEN)
        
        mentor = request.user
        
        # Get all completed mentorships for this mentor
        completed_mentorships = Mentorship.objects.filter(
            mentor=mentor,
            status='completed'
        )
        
        # Get all reviews for this mentor
        reviews = MentorshipReview.objects.filter(
            mentorship__mentor=mentor
        ).select_related('mentorship', 'reviewer')
        
        # Calculate average rating
        avg_rating = reviews.aggregate(
            avg_rating=Avg('rating')
        )['avg_rating'] or 0
        
        # Calculate category averages
        category_ratings = {
            'communication': reviews.aggregate(avg=Avg('communication_rating'))['avg'] or 0,
            'knowledge': reviews.aggregate(avg=Avg('knowledge_rating'))['avg'] or 0,
            'helpfulness': reviews.aggregate(avg=Avg('helpfulness_rating'))['avg'] or 0,
            'overall': avg_rating
        }
        
        # Calculate completion rate
        total_mentorships = Mentorship.objects.filter(mentor=mentor).count()
        completion_rate = 0
        if total_mentorships > 0:
            completion_rate = round((completed_mentorships.count() / total_mentorships) * 100)
        
        # Get performance metrics
        metrics = [
            {
                'name': 'Mentorship Completion Rate',
                'value': f'{completion_rate}%',
                'percentage': completion_rate
            },
            {
                'name': 'Average Session Rating',
                'value': f'{avg_rating:.1f}/5',
                'percentage': (avg_rating / 5) * 100
            },
            {
                'name': 'Mentee Satisfaction',
                'value': f'{reviews.filter(would_recommend=True).count()}/{reviews.count()}',
                'percentage': reviews.filter(would_recommend=True).count() / max(reviews.count(), 1) * 100
            }
        ]
        
        # Analyze strengths from reviews
        strengths = []
        positive_reviews = reviews.filter(rating__gte=4)
        
        if positive_reviews.exists():
            # Common positive phrases (simplified analysis)
            positive_phrases = [
                'great communicator', 'knowledgeable', 'helpful', 
                'patient', 'supportive', 'professional', 'organized'
            ]
            
            for phrase in positive_phrases:
                # FIXED: Only search in review_text field (mentor_feedback doesn't exist)
                count = positive_reviews.filter(
                    review_text__icontains=phrase
                ).count()
                if count >= 2:  # At least 2 mentions
                    strengths.append(phrase.title())
        
        # Get recent reviews with mentee info
        recent_reviews = []
        for review in reviews.order_by('-created_at')[:5]:
            recent_reviews.append({
                'id': review.id,
                'rating': review.rating,
                'review_text': review.review_text,
                'created_at': review.created_at,
                'mentee_name': review.mentorship.mentee.full_name,
                'mentee_email': review.mentorship.mentee.email
            })
        
        return Response({
            'success': True,
            'mentor': {
                'id': mentor.id,
                'full_name': mentor.full_name,
                'email': mentor.email
            },
            'average_rating': round(avg_rating, 2),
            'total_reviews': reviews.count(),
            'category_ratings': category_ratings,
            'metrics': metrics,
            'strengths': strengths[:3],  # Top 3 strengths
            'recent_reviews': recent_reviews,
            'completion_rate': completion_rate
        })
        
    except Exception as e:
        print('Exception occurred while fetching mentor performance:', str(e))
        return Response({
            'error': 'Failed to fetch mentor performance',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentor_reviews(request):
    """Get all reviews for the logged-in mentor"""
    try:
        if request.user.role != 'mentor':
            return Response({
                'error': 'This endpoint is for mentors only'
            }, status=status.HTTP_403_FORBIDDEN)
        
        reviews = MentorshipReview.objects.filter(
            mentorship__mentor=request.user
        ).select_related('mentorship', 'mentorship__mentee').order_by('-created_at')
        
        reviews_data = []
        for review in reviews:
            reviews_data.append({
                'id': review.id,
                'rating': review.rating,
                'communication_rating': review.communication_rating,
                'knowledge_rating': review.knowledge_rating,
                'helpfulness_rating': review.helpfulness_rating,
                'review_text': review.review_text,
                'would_recommend': review.would_recommend,
                'created_at': review.created_at,
                'mentee_name': review.mentorship.mentee.full_name,
                'mentee_email': review.mentorship.mentee.email,
                'mentorship_id': review.mentorship.id
            })
        
        return Response({
            'success': True,
            'reviews': reviews_data,
            'count': len(reviews_data)
        })
        
    except Exception as e:
        return Response({
            'error': 'Failed to fetch reviews',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentorship_program_sessions(request, mentorship_id, program_id):
    """Get all session templates for a specific program in a mentorship"""
    try:
        # Get mentorship
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permission
        if request.user not in [mentorship.mentor, mentorship.mentee] and request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get program
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        # Check if program belongs to mentorship
        if not mentorship.programs.filter(id=program.id).exists():
            return Response({
                'error': 'Program not assigned to this mentorship'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get program progress
        progress = MentorshipProgramProgress.objects.filter(
            mentorship=mentorship,
            program=program
        ).first()
        
        # Get all session templates
        session_templates = program.session_templates.filter(is_active=True).order_by('order')
        
        # Get existing sessions for this program
        existing_sessions = MentorshipSession.objects.filter(
            mentorship=mentorship,
            program=program
        )
        
        # Prepare session data
        sessions_data = []
        for template in session_templates:
            # Find if session already exists for this template
            session = existing_sessions.filter(session_template=template).first()
            
            session_data = {
                'template_id': template.id,
                'session_id': session.id if session else None,
                'title': template.title,
                'description': template.description,
                'session_type': template.session_type,
                'duration_minutes': template.duration_minutes,
                'order': template.order,
                'is_required': template.is_required,
                'objectives': template.objectives,
                'requirements': template.requirements,
                'status': session.status if session else 'not_scheduled',
                'scheduled_date': session.scheduled_date if session else None,
                'actual_date': session.actual_date if session else None,
                'notes': session.notes if session else '',
                'can_schedule': not session or session.status in ['cancelled', 'rescheduled']
            }
            sessions_data.append(session_data)
        
        # Get next available session number
        last_session = existing_sessions.order_by('-program_session_number').first()
        next_session_number = (last_session.program_session_number + 1) if last_session else 1
        
        # Check which sessions can be scheduled
        # Rule: Can only schedule sessions in order, but can skip completed sessions
        scheduled_sessions = existing_sessions.filter(status='scheduled').count()
        completed_sessions = existing_sessions.filter(status='completed').count()
        
        return Response({
            'success': True,
            'program': {
                'id': program.id,
                'name': program.name,
                'description': program.description,
                'total_sessions': session_templates.count(),
                'sessions_completed': completed_sessions,
                'sessions_scheduled': scheduled_sessions,
                'progress_percentage': progress.progress_percentage if progress else 0,
                'status': progress.status if progress else 'not_started',
                'is_current': mentorship.current_program == program
            },
            'sessions': sessions_data,
            'next_session_number': next_session_number,
            'can_schedule_next': completed_sessions + scheduled_sessions < session_templates.count(),
            'available_dates': get_available_dates(mentorship.mentor, mentorship.mentee)
        })
        
    except Exception as e:
        print(f"Error getting program sessions: {str(e)}")
        return Response({
            'error': 'Failed to fetch program sessions',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_available_dates(mentor, mentee):
    """Get available dates for scheduling sessions"""
    # Get next 30 days
    start_date = timezone.now()
    end_date = start_date + timedelta(days=30)
    
    # Get busy dates for mentor and mentee
    mentor_busy_dates = get_user_busy_dates(mentor)
    mentee_busy_dates = get_user_busy_dates(mentee)
    
    # Combine busy dates
    busy_dates = set(mentor_busy_dates) | set(mentee_busy_dates)
    
    # Generate available dates (weekdays only)
    available_dates = []
    current_date = start_date
    
    while current_date <= end_date:
        # Check if weekday and not busy
        if current_date.weekday() < 5 and current_date.date() not in busy_dates:
            available_dates.append(current_date.date())
        
        current_date += timedelta(days=1)
    
    return available_dates[:10]  # Return next 10 available dates


def get_user_busy_dates(user):
    """Get dates when user has scheduled sessions"""
    # Get user's scheduled sessions
    if user.role == 'mentor':
        sessions = MentorshipSession.objects.filter(
            mentorship__mentor=user,
            status='scheduled',
            scheduled_date__gte=timezone.now()
        )
    else:
        sessions = MentorshipSession.objects.filter(
            mentorship__mentee=user,
            status='scheduled',
            scheduled_date__gte=timezone.now()
        )
    
    # Extract dates
    busy_dates = []
    for session in sessions:
        busy_dates.append(session.scheduled_date.date())
    
    return busy_dates


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def schedule_program_session(request, mentorship_id, program_id):
    """Schedule a session for a specific program in mentorship"""
    try:
        # Get mentorship
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permission - only mentor can schedule sessions
        if request.user != mentorship.mentor:
            return Response({
                'error': 'Only the mentor can schedule sessions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get program
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        # Check if program belongs to mentorship
        if not mentorship.programs.filter(id=program.id).exists():
            return Response({
                'error': 'Program not assigned to this mentorship'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate request data
        template_id = request.data.get('template_id')
        scheduled_date = request.data.get('scheduled_date')
        session_type = request.data.get('session_type', 'video')
        duration_minutes = request.data.get('duration_minutes', 60)
        agenda = request.data.get('agenda', '')
        meeting_link = request.data.get('meeting_link', '')
        location = request.data.get('location', '')
        
        if not template_id:
            return Response({
                'error': 'Template ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not scheduled_date:
            return Response({
                'error': 'Scheduled date is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get session template
        template = get_object_or_404(ProgramSessionTemplate, id=template_id)
        
        # Check if template belongs to program
        if not program.session_templates.filter(id=template.id).exists():
            return Response({
                'error': 'Session template does not belong to this program'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if session already exists for this template
        existing_session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            program=program,
            session_template=template
        ).first()
        
        if existing_session and existing_session.status == 'scheduled':
            return Response({
                'error': 'Session already scheduled for this template'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse scheduled date
        try:
            scheduled_datetime = timezone.make_aware(
                timezone.datetime.fromisoformat(scheduled_date.replace('Z', '+00:00'))
            )
        except (ValueError, AttributeError):
            return Response({
                'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if date is in the future
        if scheduled_datetime < timezone.now():
            return Response({
                'error': 'Cannot schedule session in the past'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for scheduling conflicts
        conflicts = check_scheduling_conflicts(mentorship, scheduled_datetime, duration_minutes)
        if conflicts:
            return Response({
                'error': 'Scheduling conflict detected',
                'conflicts': conflicts
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get next session number
        last_session = MentorshipSession.objects.filter(
            mentorship=mentorship,
            program=program
        ).order_by('-program_session_number').first()
        
        program_session_number = (last_session.program_session_number + 1) if last_session else 1
        
        # Get overall session number
        last_overall_session = MentorshipSession.objects.filter(
            mentorship=mentorship
        ).order_by('-overall_session_number').first()
        
        overall_session_number = (last_overall_session.overall_session_number + 1) if last_overall_session else 1
        
        # Get or create program progress
        program_progress, created = MentorshipProgramProgress.objects.get_or_create(
            mentorship=mentorship,
            program=program,
            defaults={
                'status': 'in_progress',
                'started_at': timezone.now(),
                'total_sessions': program.session_templates.filter(is_active=True).count()
            }
        )
        
        # Create session
        session = MentorshipSession.objects.create(
            mentorship=mentorship,
            program=program,
            program_progress=program_progress,
            session_template=template,
            program_session_number=program_session_number,
            overall_session_number=overall_session_number,
            session_type=session_type,
            scheduled_date=scheduled_datetime,
            duration_minutes=duration_minutes,
            agenda=agenda,
            meeting_link=meeting_link,
            location=location,
            status='scheduled',
            objectives=template.objectives
        )

        # Send notification
        send_session_scheduled_notification(session)
        
        # Update mentorship's current program if not set
        if not mentorship.current_program:
            mentorship.current_program = program
            mentorship.save()
        
        # Send notification to mentee
        send_session_scheduled_notification(session)
        
        return Response({
            'success': True,
            'message': 'Session scheduled successfully',
            'session': MentorshipSessionSerializer(session).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        print(f"Error scheduling session: {str(e)}")
        return Response({
            'error': 'Failed to schedule session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def check_scheduling_conflicts(mentorship, scheduled_datetime, duration_minutes):
    """Check for scheduling conflicts"""
    conflicts = []
    
    # Calculate session end time
    session_end = scheduled_datetime + timedelta(minutes=duration_minutes)
    
    # Check mentor's schedule
    mentor_sessions = MentorshipSession.objects.filter(
        mentorship__mentor=mentorship.mentor,
        status='scheduled',
        scheduled_date__date=scheduled_datetime.date()
    ).exclude(mentorship=mentorship)
    
    for other_session in mentor_sessions:
        other_end = other_session.scheduled_date + timedelta(minutes=other_session.duration_minutes)
        
        # Check for overlap
        if (scheduled_datetime < other_end and session_end > other_session.scheduled_date):
            conflicts.append({
                'user': 'mentor',
                'conflict_with': f"Session with {other_session.mentorship.mentee.full_name}",
                'time': other_session.scheduled_date.strftime('%H:%M'),
                'duration': other_session.duration_minutes
            })
    
    # Check mentee's schedule
    mentee_sessions = MentorshipSession.objects.filter(
        mentorship__mentee=mentorship.mentee,
        status='scheduled',
        scheduled_date__date=scheduled_datetime.date()
    ).exclude(mentorship=mentorship)
    
    for other_session in mentee_sessions:
        other_end = other_session.scheduled_date + timedelta(minutes=other_session.duration_minutes)
        
        # Check for overlap
        if (scheduled_datetime < other_end and session_end > other_session.scheduled_date):
            conflicts.append({
                'user': 'mentee',
                'conflict_with': f"Session with {other_session.mentorship.mentor.full_name}",
                'time': other_session.scheduled_date.strftime('%H:%M'),
                'duration': other_session.duration_minutes
            })
    
    return conflicts


def send_session_scheduled_notification(session):
    """Send notification about scheduled session"""
    try:
        # Create chat notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=session.mentorship.chat_room if hasattr(session.mentorship, 'chat_room') else None,
            notification_type='session_scheduled',
            title='New Session Scheduled',
            message=f'Session {session.program_session_number}: {session.session_template.title} scheduled for {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
            metadata={
                'session_id': session.id,
                'mentorship_id': session.mentorship.id,
                'scheduled_date': session.scheduled_date.isoformat()
            }
        )
    except Exception as e:
        print(f"Error sending notification: {str(e)}")


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_session_progress(request, session_id):
    """Update session status (complete, cancel, reschedule)"""
    try:
        session = get_object_or_404(MentorshipSession, id=session_id)
        
        # Check permission
        if request.user not in [session.mentorship.mentor, session.mentorship.mentee] and request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        action = request.data.get('action')
        
        if not action:
            return Response({
                'error': 'Action is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if action == 'complete':
            return complete_session(session, request)
        elif action == 'cancel':
            return cancel_session(session, request)
        elif action == 'reschedule':
            return reschedule_session(session, request)
        else:
            return Response({
                'error': 'Invalid action. Must be: complete, cancel, or reschedule'
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        print(f"Error updating session: {str(e)}")
        return Response({
            'error': 'Failed to update session',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#complete_session function
def complete_session(session, request):
    """Mark session as completed"""
    if session.status == 'completed':
        return Response({
            'error': 'Session is already completed'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get completion data
    notes = request.data.get('notes', '')
    mentor_feedback = request.data.get('mentor_feedback', '')
    mentee_feedback = request.data.get('mentee_feedback', '')
    action_items = request.data.get('action_items', [])
    
    # Update session
    session.status = 'completed'
    session.actual_date = timezone.now()
    session.notes = notes
    session.mentor_feedback = mentor_feedback
    session.mentee_feedback = mentee_feedback
    session.action_items = action_items
    session.completed_by = request.user
    session.save()
    
    # Update program progress
    if session.program_progress:
        session.program_progress.update_progress()
        
        # Check if program is now completed
        if session.program_progress.status == 'completed':
            send_program_completed_notification(session.mentorship, session.program)
    
    # Update mentorship progress
    update_mentorship_progress(session.mentorship)
    
    # Send notification
    send_session_completed_notification(session)
    
    return Response({
        'success': True,
        'message': 'Session marked as completed',
        'session': MentorshipSessionSerializer(session).data,
        'program_progress': get_program_progress_data(session.program)
    })

#cancel_session function
def cancel_session(session, request):
    """Cancel a scheduled session"""
    if session.status != 'scheduled':
        return Response({
            'error': 'Only scheduled sessions can be cancelled'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    reason = request.data.get('reason', 'No reason provided')
    
    session.status = 'cancelled'
    session.notes = f"Cancelled: {reason}"
    session.save()
    
    # Send notification
    send_session_cancelled_notification(session, reason)
    
    return Response({
        'success': True,
        'message': 'Session cancelled',
        'session': MentorshipSessionSerializer(session).data
    })

# reschedule_session function
def reschedule_session(session, request):
    """Reschedule a session"""
    if session.status != 'scheduled':
        return Response({
            'error': 'Only scheduled sessions can be rescheduled'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    new_date = request.data.get('new_date')
    reason = request.data.get('reason', '')
    
    if not new_date:
        return Response({
            'error': 'New date is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        new_datetime = timezone.make_aware(
            timezone.datetime.fromisoformat(new_date.replace('Z', '+00:00'))
        )
    except (ValueError, AttributeError):
        return Response({
            'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check for conflicts
    conflicts = check_scheduling_conflicts(session.mentorship, new_datetime, session.duration_minutes)
    if conflicts:
        return Response({
            'error': 'Scheduling conflict detected',
            'conflicts': conflicts
        }, status=status.HTTP_400_BAD_REQUEST)
    
    old_date = session.scheduled_date
    session.status = 'rescheduled'
    session.scheduled_date = new_datetime
    if reason:
        session.notes = f"Rescheduled from {old_date}: {reason}"
    session.save()
    
    # Send notification
    send_session_rescheduled_notification(session, old_date)
    
    return Response({
        'success': True,
        'message': 'Session rescheduled',
        'session': MentorshipSessionSerializer(session).data
    })

# update_mentorship_progress function
def update_mentorship_progress(mentorship):
    """Update overall mentorship progress"""
    # Get all programs in mentorship
    programs = mentorship.programs.all()
    total_programs = programs.count()
    
    if total_programs == 0:
        return
    
    # Calculate overall progress
    total_progress = 0
    completed_programs = 0
    
    for program in programs:
        progress = MentorshipProgramProgress.objects.filter(
            mentorship=mentorship,
            program=program
        ).first()
        
        if progress:
            total_progress += progress.progress_percentage
            
            if progress.status == 'completed':
                completed_programs += 1
    
    # Update mentorship if all programs are completed
    if completed_programs == total_programs:
        mentorship.status = 'completed'
        mentorship.actual_end_date = timezone.now().date()
        mentorship.save()
        
        # Send mentorship completed notification
        send_mentorship_completed_notification(mentorship)

def get_program_progress_data(program):
    """Get detailed program progress data"""
    progress = MentorshipProgramProgress.objects.filter(program=program).first()
    
    if not progress:
        return None
    
    return {
        'program_id': program.id,
        'program_name': program.name,
        'progress_percentage': progress.progress_percentage,
        'sessions_completed': progress.sessions_completed,
        'total_sessions': progress.total_sessions,
        'status': progress.status,
        'started_at': progress.started_at,
        'completed_at': progress.completed_at
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentor_program_overview(request, mentorship_id):
    """Get overview of all programs in a mentorship for mentor"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permission
        if request.user != mentorship.mentor:
            return Response({
                'error': 'Only the mentor can view this'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all programs in mentorship
        programs = mentorship.programs.all()
        
        program_data = []
        for program in programs:
            # Get program progress
            progress = MentorshipProgramProgress.objects.filter(
                mentorship=mentorship,
                program=program
            ).first()
            
            # Get session statistics
            total_sessions = program.session_templates.filter(is_active=True).count()
            completed_sessions = MentorshipSession.objects.filter(
                mentorship=mentorship,
                program=program,
                status='completed'
            ).count()
            
            scheduled_sessions = MentorshipSession.objects.filter(
                mentorship=mentorship,
                program=program,
                status='scheduled'
            ).count()
            
            program_data.append({
                'id': program.id,
                'name': program.name,
                'description': program.description,
                'is_current': mentorship.current_program == program,
                'total_sessions': total_sessions,
                'completed_sessions': completed_sessions,
                'scheduled_sessions': scheduled_sessions,
                'remaining_sessions': total_sessions - completed_sessions - scheduled_sessions,
                'progress_percentage': progress.progress_percentage if progress else 0,
                'status': progress.status if progress else 'not_started',
                'can_schedule': completed_sessions + scheduled_sessions < total_sessions,
                'next_session_number': (completed_sessions + scheduled_sessions) + 1
            })
        
        # Calculate overall mentorship progress
        overall_progress = 0
        if program_data:
            total_progress = sum(p['progress_percentage'] for p in program_data)
            overall_progress = total_progress / len(program_data)
        
        return Response({
            'success': True,
            'mentorship': {
                'id': mentorship.id,
                'mentee': {
                    'id': mentorship.mentee.id,
                    'name': mentorship.mentee.full_name,
                    'email': mentorship.mentee.email
                },
                'start_date': mentorship.start_date,
                'status': mentorship.status,
                'overall_progress': round(overall_progress, 2)
            },
            'programs': program_data,
            'total_programs': len(program_data),
            'completed_programs': len([p for p in program_data if p['status'] == 'completed']),
            'in_progress_programs': len([p for p in program_data if p['status'] == 'in_progress'])
        })
        
    except Exception as e:
        print(f"Error getting program overview: {str(e)}")
        return Response({
            'error': 'Failed to fetch program overview',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_statistics(request):
    """Get comprehensive statistics for all departments"""
    try:
        if request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        departments = Department.objects.filter(status='active')
        
        department_stats = []
        for dept in departments:
            # Get programs in this department
            dept_programs = MentorshipProgram.objects.filter(
                Q(department__name=dept.name) | Q(department=dept)
            )
            
            # Get mentorships in this department
            dept_mentorships = Mentorship.objects.filter(
                Q(department__name=dept.name) | Q(department=dept)
            )
            
            # Calculate completion rate
            completed_mentorships = dept_mentorships.filter(status='completed')
            completion_rate = 0
            if dept_mentorships.count() > 0:
                completion_rate = round((completed_mentorships.count() / dept_mentorships.count()) * 100)
            
            # Get average rating for completed mentorships
            avg_rating = 0
            if completed_mentorships.exists():
                avg_rating = completed_mentorships.aggregate(
                    avg_rating=Avg('rating')
                )['avg_rating'] or 0
            
            # Get top mentors in this department
            top_mentors = CustomUser.objects.filter(
                mentorships_as_mentor__in=dept_mentorships,
                role='mentor'
            ).annotate(
                avg_rating=Avg('mentorships_as_mentor__rating'),
                completed_count=Count('mentorships_as_mentor', filter=Q(mentorships_as_mentor__status='completed')),
                total_count=Count('mentorships_as_mentor')
            ).filter(avg_rating__isnull=False).order_by('-avg_rating')[:3]
            
            top_mentors_data = []
            for mentor in top_mentors:
                top_mentors_data.append({
                    'id': mentor.id,
                    'name': mentor.full_name,
                    'rating': round(mentor.avg_rating, 1),
                    'completed_mentorships': mentor.completed_count,
                    'total_mentorships': mentor.total_count,
                    'email': mentor.email
                })
            
            department_stats.append({
                'id': dept.id,
                'name': dept.name,
                'description': dept.description,
                'program_count': dept_programs.count(),
                'mentorship_count': dept_mentorships.count(),
                'active_mentorships': dept_mentorships.filter(status='active').count(),
                'completion_rate': completion_rate,
                'average_rating': round(avg_rating, 1),
                'top_mentors': top_mentors_data
            })
        
        # Get overall statistics
        all_mentorships = Mentorship.objects.all()
        all_completed = all_mentorships.filter(status='completed')
        
        overall_stats = {
            'total_mentorships': all_mentorships.count(),
            'active_mentorships': all_mentorships.filter(status='active').count(),
            'completed_mentorships': all_completed.count(),
            'overall_completion_rate': round((all_completed.count() / all_mentorships.count() * 100)) if all_mentorships.count() > 0 else 0,
            'average_rating': round(all_completed.aggregate(avg=Avg('rating'))['avg'] or 0, 1)
        }
        
        return Response({
            'success': True,
            'overall': overall_stats,
            'departments': department_stats,
            'count': len(department_stats)
        })
        
    except Exception as e:
        print(f"Error fetching department statistics: {str(e)}")
        return Response({
            'error': 'Failed to fetch department statistics',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_program_stats(request, department_id):
    """Get detailed statistics for programs in a department"""
    try:
        if request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        department = get_object_or_404(Department, id=department_id)
        
        # Get programs in this department
        programs = MentorshipProgram.objects.filter(
            Q(department__name=department.name) | Q(department=department)
        )
        
        program_stats = []
        for program in programs:
            program_mentorships = program.mentorships.all()
            completed_mentorships = program_mentorships.filter(status='completed')
            
            # Calculate completion rate
            completion_rate = 0
            if program_mentorships.count() > 0:
                completion_rate = round((completed_mentorships.count() / program_mentorships.count()) * 100)
            
            # Calculate average duration for completed mentorships
            avg_duration = 0
            if completed_mentorships.exists():
                durations = []
                for mentorship in completed_mentorships:
                    if mentorship.start_date and mentorship.actual_end_date:
                        duration = (mentorship.actual_end_date - mentorship.start_date).days
                        durations.append(duration)
                
                if durations:
                    avg_duration = round(sum(durations) / len(durations))
            
            # Calculate average rating
            avg_rating = completed_mentorships.aggregate(
                avg_rating=Avg('rating')
            )['avg_rating'] or 0
            
            # Calculate satisfaction rate (would_recommend percentage)
            satisfaction_rate = 0
            reviews = MentorshipReview.objects.filter(mentorship__in=completed_mentorships)
            if reviews.exists():
                would_recommend = reviews.filter(would_recommend=True).count()
                satisfaction_rate = round((would_recommend / reviews.count()) * 100)
            
            # Get session completion data
            total_sessions = program.get_total_sessions()
            completed_sessions = 0
            for mentorship in program_mentorships:
                completed_sessions += mentorship.sessions.filter(status='completed').count()
            
            session_completion_rate = 0
            if total_sessions > 0 and program_mentorships.count() > 0:
                session_completion_rate = round((completed_sessions / (total_sessions * program_mentorships.count())) * 100)
            
            program_stats.append({
                'id': program.id,
                'name': program.name,
                'description': program.description,
                'total_mentorships': program_mentorships.count(),
                'active_mentorships': program_mentorships.filter(status='active').count(),
                'completion_rate': completion_rate,
                'average_duration': avg_duration,
                'average_rating': round(avg_rating, 1),
                'satisfaction_rate': satisfaction_rate,
                'session_completion_rate': session_completion_rate,
                'total_sessions': total_sessions,
                'sessions_completed': completed_sessions
            })
        
        return Response({
            'success': True,
            'department': {
                'id': department.id,
                'name': department.name,
                'description': department.description
            },
            'programs': program_stats,
            'total_programs': len(program_stats)
        })
        
    except Exception as e:
        print(f"Error fetching department program stats: {str(e)}")
        return Response({
            'error': 'Failed to fetch program statistics',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.db.models import F, ExpressionWrapper, DurationField
from django.db.models.functions import Coalesce
from datetime import timedelta

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_top_performing_mentors(request):
    """Get top performing mentors based on ratings and completion rates"""
    try:
        if request.user.role not in ['admin', 'hr']:
            print("User does not have permission to access this endpoint.")
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get mentors with completed mentorships
        mentors = CustomUser.objects.filter(
            role='mentor',
            status='approved'
        ).annotate(
            total_mentorships=Count('mentorships_as_mentor', distinct=True),
            completed_mentorships=Count(
                'mentorships_as_mentor',
                filter=Q(mentorships_as_mentor__status='completed'),
                distinct=True
            ),
            avg_rating=Avg('mentorships_as_mentor__rating'),
            avg_session_rating=Avg('mentorships_as_mentor__sessions__mentor_rating'),
            # Calculate average response time (difference between actual and scheduled dates)
            avg_response_time=Avg(
                ExpressionWrapper(
                    F('mentorships_as_mentor__sessions__actual_date') - F('mentorships_as_mentor__sessions__scheduled_date'),
                    output_field=DurationField()
                ),
                filter=Q(mentorships_as_mentor__sessions__status='completed')
            )
        ).filter(
            total_mentorships__gt=0  # Only mentors with at least one mentorship
        ).order_by('-avg_rating', '-completed_mentorships')[:10]
        
        mentor_stats = []
        for mentor in mentors:
            # Calculate completion rate
            completion_rate = 0
            if mentor.total_mentorships > 0:
                completion_rate = round((mentor.completed_mentorships / mentor.total_mentorships) * 100)
            
            # Get departments they mentor in
            departments = mentor.departments.all()
            
            # Get recent reviews
            recent_reviews = MentorshipReview.objects.filter(
                mentorship__mentor=mentor,
                reviewer_type='mentee'
            ).select_related('mentorship__mentee').order_by('-created_at')[:3]
            
            recent_reviews_data = []
            for review in recent_reviews:
                recent_reviews_data.append({
                    'rating': review.rating,
                    'review_text': review.review_text[:200] + '...' if len(review.review_text) > 200 else review.review_text,
                    'mentee_name': review.mentorship.mentee.full_name,
                    'date': review.created_at.strftime('%Y-%m-%d')
                })
            
            # Convert response time to hours if available
            avg_response_hours = None
            if mentor.avg_response_time:
                avg_response_hours = round(mentor.avg_response_time.total_seconds() / 3600, 1)
            
            # Calculate performance score
            performance_score = calculate_performance_score(
                mentor.avg_rating or 0,
                completion_rate,
                mentor.total_mentorships
            )
            
            mentor_stats.append({
                'id': mentor.id,
                'name': mentor.full_name,
                'email': mentor.email,
                'profile_picture': mentor.profile_picture.url if mentor.profile_picture else None,
                'total_mentorships': mentor.total_mentorships,
                'completed_mentorships': mentor.completed_mentorships,
                'active_mentorships': mentor.total_mentorships - mentor.completed_mentorships,
                'completion_rate': completion_rate,
                'average_rating': round(mentor.avg_rating, 1) if mentor.avg_rating else 0,
                'average_session_rating': round(mentor.avg_session_rating, 1) if mentor.avg_session_rating else 0,
                'avg_response_time_hours': avg_response_hours,
                'departments': [dept.name for dept in departments],
                'recent_reviews': recent_reviews_data,
                'performance_score': performance_score
            })
        
        return Response({
            'success': True,
            'mentors': mentor_stats,
            'count': len(mentor_stats)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Error fetching top performing mentors: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Failed to fetch mentor statistics',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def calculate_performance_score(avg_rating, completion_rate, total_mentorships):
    """
    Calculate a performance score based on:
    - Average rating (40% weight)
    - Completion rate (30% weight)
    - Total mentorships (30% weight, with diminishing returns)
    """
    # Normalize rating to 0-100 scale (assuming max rating is 5)
    rating_score = (avg_rating / 5.0) * 100 if avg_rating else 0
    
    # Completion rate is already 0-100
    completion_score = completion_rate
    
    # Normalize total mentorships (cap at 20 for scoring purposes)
    mentorship_score = min(total_mentorships / 20.0, 1.0) * 100
    
    # Calculate weighted average
    performance_score = (
        (rating_score * 0.4) +
        (completion_score * 0.3) +
        (mentorship_score * 0.3)
    )
    
    return round(performance_score, 1)

def calculate_performance_score(mentor):
    """Calculate a performance score for a mentor (0-100)"""
    score = 50  # Base score
    
    # Rating component (0-30 points)
    if mentor.avg_rating:
        score += (mentor.avg_rating - 3) * 10  # 3 rating = base, 5 rating = +20
    
    # Completion rate component (0-20 points)
    if mentor.total_mentorships > 0:
        completion_rate = mentor.completed_mentorships / mentor.total_mentorships
        score += completion_rate * 20
    
    # Session rating component (0-20 points)
    if mentor.avg_session_rating:
        score += (mentor.avg_session_rating - 3) * 10
    
    # Response time component (-10 to +10 points)
    if hasattr(mentor, 'response_time') and mentor.response_time:
        avg_response_hours = mentor.response_time.total_seconds() / 3600
        if avg_response_hours < 24:
            score += 10
        elif avg_response_hours < 48:
            score += 5
        elif avg_response_hours > 72:
            score -= 10
    
    return min(max(round(score), 0), 100)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_activity(request):
    """Get recent system activity"""
    try:
        if request.user.role not in ['admin', 'hr']:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        recent_activity = []
        
        # Get recent mentorships
        recent_mentorships = Mentorship.objects.all().order_by('-created_at')[:10]
        for mentorship in recent_mentorships:
            recent_activity.append({
                'type': 'mentorship_created',
                'title': f'New Mentorship Created',
                'description': f'{mentorship.mentor.full_name} → {mentorship.mentee.full_name}',
                'timestamp': mentorship.created_at,
                'department': mentorship.department.name if mentorship.department else 'Unknown',
                'user': mentorship.created_by.full_name if mentorship.created_by else 'System'
            })
        
        # Get recent program creations
        recent_programs = MentorshipProgram.objects.all().order_by('-created_at')[:10]
        for program in recent_programs:
            recent_activity.append({
                'type': 'program_created',
                'title': f'New Program Created',
                'description': program.name,
                'timestamp': program.created_at,
                'department': program.department.name if program.department else 'Unknown',
                'user': program.created_by.full_name if program.created_by else 'System'
            })
        
        # Get recent session completions
        recent_sessions = MentorshipSession.objects.filter(
            status='completed'
        ).order_by('-actual_date')[:10]
        for session in recent_sessions:
            recent_activity.append({
                'type': 'session_completed',
                'title': f'Session Completed',
                'description': f'Session {session.program_session_number}: {session.session_template.title if session.session_template else "Unknown"}',
                'timestamp': session.actual_date,
                'department': session.mentorship.department.name if session.mentorship.department else 'Unknown',
                'user': session.completed_by.full_name if session.completed_by else 'System'
            })
        
        # Get recent reviews
        recent_reviews = MentorshipReview.objects.all().order_by('-created_at')[:10]
        for review in recent_reviews:
            recent_activity.append({
                'type': 'review_submitted',
                'title': f'New Review Submitted',
                'description': f'{review.rating}/5 - {review.reviewer.full_name}',
                'timestamp': review.created_at,
                'department': review.mentorship.department.name if review.mentorship.department else 'Unknown',
                'user': review.reviewer.full_name
            })
        
        # Sort by timestamp and limit to 20 items
        recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)
        recent_activity = recent_activity[:20]
        
        # Format timestamps
        for activity in recent_activity:
            activity['timestamp'] = activity['timestamp'].isoformat()
        
        return Response({
            'success': True,
            'activities': recent_activity,
            'count': len(recent_activity)
        })
        
    except Exception as e:
        print(f"Error fetching recent activity: {str(e)}")
        return Response({
            'error': 'Failed to fetch recent activity',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_program_statistics(request, program_id):
    """Get detailed statistics for a specific program"""
    try:
        program = get_object_or_404(MentorshipProgram, id=program_id)
        
        if request.user.role not in ['admin', 'hr']:
            # Check if user is mentor or mentee in this program
            user_mentorships = Mentorship.objects.filter(
                Q(mentor=request.user) | Q(mentee=request.user),
                programs=program
            )
            if not user_mentorships.exists():
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)
        
        program_mentorships = program.mentorships.all()
        completed_mentorships = program_mentorships.filter(status='completed')
        
        # Basic statistics
        stats = {
            'id': program.id,
            'name': program.name,
            'description': program.description,
            'total_mentorships': program_mentorships.count(),
            'active_mentorships': program_mentorships.filter(status='active').count(),
            'pending_mentorships': program_mentorships.filter(status='pending').count(),
            'completed_mentorships': completed_mentorships.count(),
            'completion_rate': round((completed_mentorships.count() / program_mentorships.count() * 100)) if program_mentorships.count() > 0 else 0,
        }
        
        # Rating statistics
        if completed_mentorships.exists():
            rating_stats = completed_mentorships.aggregate(
                avg_rating=Avg('rating'),
                min_rating=Min('rating'),
                max_rating=Max('rating'),
                rating_count=Count('rating')
            )
            stats['rating_stats'] = rating_stats
        
        # Session statistics
        total_sessions = program.get_total_sessions()
        completed_sessions = 0
        for mentorship in program_mentorships:
            completed_sessions += mentorship.sessions.filter(status='completed').count()
        
        stats['session_stats'] = {
            'total_sessions': total_sessions,
            'completed_sessions': completed_sessions,
            'session_completion_rate': round((completed_sessions / (total_sessions * program_mentorships.count())) * 100) if total_sessions > 0 and program_mentorships.count() > 0 else 0
        }
        
        # Duration statistics
        durations = []
        for mentorship in completed_mentorships:
            if mentorship.start_date and mentorship.actual_end_date:
                duration = (mentorship.actual_end_date - mentorship.start_date).days
                durations.append(duration)
        
        if durations:
            stats['duration_stats'] = {
                'average_duration': round(sum(durations) / len(durations)),
                'min_duration': min(durations),
                'max_duration': max(durations),
                'total_duration': sum(durations)
            }
        
        # Department distribution
        departments = {}
        for mentorship in program_mentorships:
            dept_name = mentorship.department.name if mentorship.department else 'Unknown'
            if dept_name not in departments:
                departments[dept_name] = 0
            departments[dept_name] += 1
        
        stats['department_distribution'] = [
            {'name': dept, 'count': count}
            for dept, count in departments.items()
        ]
        
        return Response({
            'success': True,
            'program': stats
        })
        
    except Exception as e:
        print(f"Error fetching program statistics: {str(e)}")
        return Response({
            'error': 'Failed to fetch program statistics',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_detailed_mentorship(request, mentorship_id):
    """Get detailed information for a specific mentorship"""
    try:
        mentorship = get_object_or_404(Mentorship, id=mentorship_id)
        
        # Check permissions
        user = request.user
        if user.role not in ['admin', 'hr'] and user not in [mentorship.mentor, mentorship.mentee]:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get detailed mentorship data
        serializer = MentorshipSerializer(mentorship)
        mentorship_data = serializer.data
        
        # Get sessions
        sessions = MentorshipSession.objects.filter(
            mentorship=mentorship
        ).order_by('scheduled_date')
        
        session_serializer = MentorshipSessionSerializer(sessions, many=True)
        
        # Get reviews
        reviews = MentorshipReview.objects.filter(mentorship=mentorship)
        review_serializer = MentorshipReviewSerializer(reviews, many=True)
        
        # Get program progress
        program_progress = []
        for program in mentorship.programs.all():
            progress = MentorshipProgramProgress.objects.filter(
                mentorship=mentorship,
                program=program
            ).first()
            
            if progress:
                program_progress.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'progress_percentage': progress.progress_percentage,
                    'sessions_completed': progress.sessions_completed,
                    'total_sessions': progress.total_sessions,
                    'status': progress.status,
                    'started_at': progress.started_at,
                    'completed_at': progress.completed_at
                })
        
        # Calculate statistics
        total_sessions = sessions.count()
        completed_sessions = sessions.filter(status='completed').count()
        scheduled_sessions = sessions.filter(status='scheduled').count()
        
        # Calculate average session rating
        session_ratings = sessions.exclude(mentor_rating__isnull=True).values_list('mentor_rating', flat=True)
        avg_session_rating = 0
        if session_ratings:
            avg_session_rating = sum(session_ratings) / len(session_ratings)
        
        return Response({
            'success': True,
            'mentorship': mentorship_data,
            'sessions': session_serializer.data,
            'reviews': review_serializer.data,
            'program_progress': program_progress,
            'statistics': {
                'total_sessions': total_sessions,
                'completed_sessions': completed_sessions,
                'scheduled_sessions': scheduled_sessions,
                'completion_rate': round((completed_sessions / total_sessions * 100)) if total_sessions > 0 else 0,
                'average_session_rating': round(avg_session_rating, 1),
                'days_active': (timezone.now().date() - mentorship.start_date).days if mentorship.start_date else 0,
                'days_remaining': (mentorship.expected_end_date - timezone.now().date()).days if mentorship.expected_end_date else None
            }
        })
        
    except Exception as e:
        print(f"Error fetching detailed mentorship: {str(e)}")
        return Response({
            'error': 'Failed to fetch mentorship details',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)