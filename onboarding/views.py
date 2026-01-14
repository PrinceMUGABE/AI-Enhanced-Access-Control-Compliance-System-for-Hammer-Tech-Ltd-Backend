# onboarding/views.py
import email
import uuid
import logging
import traceback
from datetime import datetime

# Django & DRF imports
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count, Sum, F
from django.utils.timezone import now, timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from django.core.exceptions import ValidationError

# Models and Serializers
from .models import (
    OnboardingModule, 
    MenteeOnboardingProgress, 
    OnboardingChecklist,
    MenteeChecklistProgress,
    OnboardingNotification,
    OnboardingDeadline
)
from .serializers import (
    OnboardingModuleSerializer,
    OnboardingModuleCreateSerializer,
    MenteeOnboardingProgressSerializer,
    MenteeOnboardingProgressUpdateSerializer,
    MenteeSummarySerializer,
    MenteeChecklistProgressSerializer,
    DepartmentProgressSerializer,
    DepartmentModuleStatsSerializer,
    DepartmentSummarySerializer,
    SendReminderSerializer
)
from userApp.models import CustomUser
from departmentApp.models import Department
from .utils import FileUploadHandler
# Configure logging
logger = logging.getLogger(__name__)


# ================ HELPER FUNCTIONS ================

def calculate_overall_progress(mentee):
    """Calculate overall onboarding progress for a mentee"""
    try:
        progress_records = MenteeOnboardingProgress.objects.filter(mentee=mentee)
        
        if not progress_records:
            return {
                'total_modules': 0,
                'completed_modules': 0,
                'in_progress_modules': 0,
                'not_started_modules': 0,
                'overall_percentage': 0,
                'average_progress': 0,
                'total_time_spent': 0,
                'estimated_time_remaining': 0
            }
        
        total_modules = progress_records.count()
        completed_modules = progress_records.filter(status='completed').count()
        in_progress_modules = progress_records.filter(status='in_progress').count()
        not_started_modules = progress_records.filter(status='not_started').count()
        
        # Calculate average progress percentage
        average_progress = progress_records.aggregate(
            avg=Avg('progress_percentage')
        )['avg'] or 0
        
        # Calculate overall percentage (weighted by module duration)
        total_duration = sum([p.module.duration_minutes for p in progress_records])
        if total_duration > 0:
            weighted_sum = sum([
                p.progress_percentage * p.module.duration_minutes 
                for p in progress_records
            ])
            overall_percentage = round((weighted_sum / total_duration), 2)
        else:
            overall_percentage = round(average_progress, 2)
        
        # Calculate total time spent
        total_time_spent = progress_records.aggregate(
            total=Sum('time_spent_minutes')
        )['total'] or 0
        
        # Calculate estimated time remaining
        remaining_time = 0
        for progress in progress_records.filter(status__in=['not_started', 'in_progress']):
            remaining_percentage = 100 - progress.progress_percentage
            module_remaining = (remaining_percentage / 100) * progress.module.duration_minutes
            remaining_time += module_remaining
        
        return {
            'total_modules': total_modules,
            'completed_modules': completed_modules,
            'in_progress_modules': in_progress_modules,
            'not_started_modules': not_started_modules,
            'overall_percentage': overall_percentage,
            'average_progress': round(average_progress, 2),
            'total_time_spent': total_time_spent,
            'estimated_time_remaining': round(remaining_time, 0)
        }
    except Exception as e:
        logger.error(f"Error calculating overall progress for mentee {mentee.id}: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'total_modules': 0,
            'completed_modules': 0,
            'in_progress_modules': 0,
            'not_started_modules': 0,
            'overall_percentage': 0,
            'average_progress': 0,
            'total_time_spent': 0,
            'estimated_time_remaining': 0
        }


def send_onboarding_notification(recipient, notification_type, title, message, 
                                 related_module=None, related_progress=None):
    """Create and store an onboarding notification"""
    try:
        notification = OnboardingNotification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            related_module=related_module,
            related_progress=related_progress
        )
        
        # Also send email notification
        try:
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=True
            )
            logger.info(f"Email notification sent to {recipient.email}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
        
        return notification
    except Exception as e:
        logger.error(f"Error creating onboarding notification: {str(e)}")
        logger.error(traceback.format_exc())
        return None


def check_and_update_progress_status(progress):
    """Check and update progress status based on time and completion"""
    try:
        old_status = progress.status
        new_status = progress.calculate_auto_status()
        
        if old_status != new_status:
            progress.status = new_status
            progress.save()
            
            # Send notification for status change
            if new_status in ['needs_attention', 'off_track', 'overdue']:
                send_status_change_notification(progress, old_status, new_status)
            
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking and updating progress status: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def send_status_change_notification(progress, old_status, new_status):
    """Send notification when progress status changes"""
    try:
        mentee = progress.mentee
        module = progress.module
        
        # Status change mapping for email subjects
        status_titles = {
            'needs_attention': 'Needs Attention',
            'off_track': 'Off Track',
            'overdue': 'Overdue'
        }
        
        title = f"Onboarding Status Update: {module.title} - {status_titles.get(new_status, new_status)}"
        
        # Message to mentee
        mentee_message = f"""
        Hello {mentee.full_name},
        
        Your onboarding progress for "{module.title}" has been updated:
        
        Old Status: {old_status}
        New Status: {new_status}
        Current Progress: {progress.progress_percentage}%
        
        Please review your progress and take necessary action.
        
        Best regards,
        Mentorship Program Team
        """
        
        send_onboarding_notification(
            recipient=mentee,
            notification_type='status_changed',
            title=title,
            message=mentee_message,
            related_module=module,
            related_progress=progress
        )
        
        # Message to mentors in the department
        mentors = CustomUser.objects.filter(
            role='mentor',
            department=mentee.department,
            status='approved'
        )
        
        for mentor in mentors:
            mentor_title = f"Mentee Status Update: {mentee.full_name} - {module.title}"
            mentor_message = f"""
            Mentor Notification:
            
            Your mentee's onboarding status has changed:
            
            Mentee: {mentee.full_name}
            Module: {module.title}
            Old Status: {old_status}
            New Status: {new_status}
            Current Progress: {progress.progress_percentage}%
            
            Please provide guidance and support.
            
            Best regards,
            Mentorship Program Team
            """
            
            send_onboarding_notification(
                recipient=mentor,
                notification_type='status_changed',
                title=mentor_title,
                message=mentor_message,
                related_module=module,
                related_progress=progress
            )
        
        # Send to HR if progress is severely behind
        if progress.progress_percentage < 30 and new_status in ['overdue', 'off_track']:
            hr_users = CustomUser.objects.filter(role='hr', status='approved')
            for hr_user in hr_users:
                hr_title = f"Critical Onboarding Delay: {mentee.full_name}"
                hr_message = f"""
                HR Alert - Critical Onboarding Delay:
                
                Mentee: {mentee.full_name}
                Module: {module.title}
                Department: {mentee.department}
                Progress: {progress.progress_percentage}%
                Status: {new_status}
                
                This mentee is significantly behind schedule and may need intervention.
                
                Best regards,
                Mentorship Program System
                """
                
                send_onboarding_notification(
                    recipient=hr_user,
                    notification_type=new_status,
                    title=hr_title,
                    message=hr_message,
                    related_module=module,
                    related_progress=progress
                )
    except Exception as e:
        logger.error(f"Error sending status change notification: {str(e)}")
        logger.error(traceback.format_exc())


# ================ DEPARTMENT-FOCUSED VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_modules_summary(request, department_id=None):
    """Get summary of modules for a specific department or all departments"""
    try:
        if request.user.role not in ['admin', 'hr', 'mentor']:
            logger.warning(f"Unauthorized access attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins, HR, and mentors can view department summaries'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # If department_id is provided, get specific department
        if department_id:
            try:
                department = Department.objects.get(id=department_id, status='active')
                departments = [department]
            except Department.DoesNotExist:
                logger.error(f"Department {department_id} not found or inactive")
                return Response(
                    {'error': 'Department not found or inactive'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Get all active departments
            departments = Department.objects.filter(status='active')
        
        # If user is mentor, filter to their departments only
        if request.user.role == 'mentor':
            departments = departments.filter(id__in=request.user.departments.values_list('id', flat=True))
        
        department_summaries = []
        
        for department in departments:
            try:
                # Get all modules applicable to this department
                modules = OnboardingModule.objects.filter(
                    Q(module_type='core') | Q(departments=department),
                    is_active=True
                ).distinct()
                
                # Get mentees in this department
                mentees = CustomUser.objects.filter(
                    role='mentee',
                    department=department,
                    status='approved'
                )
                
                # Calculate statistics
                total_mentees = mentees.count()
                
                total_modules_assigned = MenteeOnboardingProgress.objects.filter(
                    mentee__department=department
                ).count()
                
                # Calculate completion statistics
                completed_modules = MenteeOnboardingProgress.objects.filter(
                    mentee__department=department,
                    status='completed'
                ).count()
                
                overall_completion_rate = 0
                if total_modules_assigned > 0:
                    overall_completion_rate = round((completed_modules / total_modules_assigned) * 100, 2)
                
                # Calculate average progress per mentee
                if total_mentees > 0:
                    avg_progress = MenteeOnboardingProgress.objects.filter(
                        mentee__department=department
                    ).aggregate(
                        avg=Avg('progress_percentage')
                    )['avg'] or 0
                else:
                    avg_progress = 0
                
                # Count mentees behind schedule
                mentees_behind_schedule = CustomUser.objects.filter(
                    role='mentee',
                    department=department,
                    status='approved',
                    onboarding_progress__status__in=['overdue', 'off_track', 'needs_attention']
                ).distinct().count()
                
                # Identify modules requiring attention
                problem_modules = OnboardingModule.objects.filter(
                    Q(module_type='core') | Q(departments=department),
                    is_active=True,
                    mentee_progress__status__in=['overdue', 'off_track'],
                    mentee_progress__mentee__department=department
                ).values_list('title', flat=True).distinct()[:5]
                
                department_summaries.append({
                    'department_id': department.id,
                    'department_name': department.name,
                    'total_mentees': total_mentees,
                    'total_modules_assigned': total_modules_assigned,
                    'completed_modules': completed_modules,
                    'overall_completion_rate': overall_completion_rate,
                    'average_progress_per_mentee': round(avg_progress, 2),
                    'mentees_behind_schedule': mentees_behind_schedule,
                    'modules_requiring_attention': list(problem_modules)
                })
            except Exception as e:
                logger.error(f"Error processing department {department.id}: {str(e)}")
                continue
        
        serializer = DepartmentSummarySerializer(department_summaries, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_department_modules_summary: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_progress_detail(request, department_id):
    """Get detailed progress for a specific department"""
    try:
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            logger.error(f"Department {department_id} not found")
            return Response(
                {'error': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role == 'mentor':
            # Check if mentor has access to this department
            if not request.user.departments.filter(id=department.id).exists():
                logger.warning(f"Mentor {request.user.id} unauthorized access to department {department_id}")
                return Response(
                    {'error': 'You can only view progress for your assigned departments'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get mentees in this department
        mentees = CustomUser.objects.filter(
            role='mentee',
            department=department,
            status='approved'
        )
        
        # Get all progress records for this department
        progress_records = MenteeOnboardingProgress.objects.filter(
            mentee__department=department
        ).select_related('mentee', 'module')
        
        # Group by mentee
        mentee_progress = {}
        for mentee in mentees:
            try:
                mentee_records = progress_records.filter(mentee=mentee)
                total_modules = mentee_records.count()
                completed_modules = mentee_records.filter(status='completed').count()
                avg_progress = mentee_records.aggregate(
                    avg=Avg('progress_percentage')
                )['avg'] or 0
                
                mentee_progress[mentee.id] = {
                    'mentee_id': mentee.id,
                    'mentee_name': mentee.full_name,
                    'mentee_email': mentee.email,
                    'total_modules': total_modules,
                    'completed_modules': completed_modules,
                    'in_progress_modules': mentee_records.filter(status='in_progress').count(),
                    'not_started_modules': mentee_records.filter(status='not_started').count(),
                    'average_progress': round(avg_progress, 2),
                    'is_behind_schedule': mentee_records.filter(
                        status__in=['overdue', 'off_track', 'needs_attention']
                    ).exists()
                }
            except Exception as e:
                logger.error(f"Error processing mentee {mentee.id}: {str(e)}")
                continue
        
        # Group by module
        modules = OnboardingModule.objects.filter(
            Q(module_type='core') | Q(departments=department),
            is_active=True
        ).distinct()
        
        module_stats = []
        for module in modules:
            try:
                module_progress = progress_records.filter(module=module)
                total_assigned = module_progress.count()
                completed = module_progress.filter(status='completed').count()
                
                completion_rate = 0
                if total_assigned > 0:
                    completion_rate = round((completed / total_assigned * 100), 2)
                
                module_stats.append({
                    'module_id': module.id,
                    'module_title': module.title,
                    'module_type': module.module_type,
                    'total_assigned': total_assigned,
                    'completed': completed,
                    'completion_rate': completion_rate,
                    'avg_time_spent': module_progress.aggregate(
                        avg=Avg('time_spent_minutes')
                    )['avg'] or 0,
                    'mentees_behind': module_progress.filter(
                        status__in=['overdue', 'off_track']
                    ).count()
                })
            except Exception as e:
                logger.error(f"Error processing module {module.id}: {str(e)}")
                continue
        
        # Calculate department-wide statistics
        total_mentees = mentees.count()
        total_progress_records = progress_records.count()
        total_completed = progress_records.filter(status='completed').count()
        
        overall_completion_rate = 0
        if total_progress_records > 0:
            overall_completion_rate = round((total_completed / total_progress_records * 100), 2)
        
        return Response({
            'department': {
                'id': department.id,
                'name': department.name,
                'description': department.description,
                'status': department.status
            },
            'summary': {
                'total_mentees': total_mentees,
                'total_modules_assigned': total_progress_records,
                'total_completed': total_completed,
                'overall_completion_rate': overall_completion_rate,
                'average_progress_percentage': progress_records.aggregate(
                    avg=Avg('progress_percentage')
                )['avg'] or 0,
                'mentees_behind_schedule': len([m for m in mentee_progress.values() if m['is_behind_schedule']])
            },
            'mentee_progress': list(mentee_progress.values()),
            'module_stats': module_stats
        })
        
    except Exception as e:
        logger.error(f"Error in get_department_progress_detail: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_modules_by_department(request):
    """Get modules filtered by department(s)"""
    try:
        user = request.user
        department_ids = request.query_params.getlist('department_ids[]')
        
        queryset = OnboardingModule.objects.filter(is_active=True)
        
        # Filter by specific departments if provided
        if department_ids:
            try:
                department_ids = [int(id) for id in department_ids]
                queryset = queryset.filter(
                    Q(module_type='core') | Q(departments__id__in=department_ids)
                ).distinct()
            except ValueError:
                logger.error(f"Invalid department IDs: {department_ids}")
                return Response(
                    {'error': 'Invalid department IDs'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # If no department filter, show appropriate modules based on role
            if user.role == 'mentee':
                # For mentees, show modules for their department
                if user.department:
                    queryset = queryset.filter(
                        Q(module_type='core') | Q(departments=user.department)
                    ).distinct()
            elif user.role == 'mentor':
                # For mentors, show modules for their departments
                mentor_dept_ids = user.departments.values_list('id', flat=True)
                queryset = queryset.filter(
                    Q(module_type='core') | Q(departments__id__in=mentor_dept_ids)
                ).distinct()
        
        # Apply additional filters
        module_type = request.query_params.get('module_type')
        if module_type:
            queryset = queryset.filter(module_type=module_type)
        
        serializer = OnboardingModuleSerializer(queryset, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_modules_by_department: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_module_to_department(request, pk):
    """Assign a module to all mentees in specific departments"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized assign attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can assign modules to departments'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk, is_active=True)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found or inactive")
            return Response(
                {'error': 'Module not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        department_ids = request.data.get('department_ids', [])
        
        if not department_ids:
            logger.error("No department IDs provided")
            return Response(
                {'error': 'No department IDs provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate department IDs
        try:
            department_ids = [int(id) for id in department_ids]
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid department IDs format: {str(e)}")
            return Response(
                {'error': 'Invalid department IDs. Must be integers.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        departments = Department.objects.filter(id__in=department_ids, status='active')
        if not departments.exists():
            logger.error(f"No active departments found with IDs: {department_ids}")
            return Response(
                {'error': 'No active departments found with the provided IDs'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        assigned_count = 0
        errors = []
        
        with transaction.atomic():
            for department in departments:
                try:
                    mentees = CustomUser.objects.filter(
                        role='mentee',
                        department=department,
                        status='approved'
                    )
                    
                    for mentee in mentees:
                        try:
                            # Check if already assigned
                            if MenteeOnboardingProgress.objects.filter(
                                mentee=mentee,
                                module=module
                            ).exists():
                                continue
                            
                            # Create progress record
                            progress = MenteeOnboardingProgress.objects.create(
                                mentee=mentee,
                                module=module,
                                status='not_started',
                                progress_percentage=0,
                                assigned_by=request.user
                            )
                            assigned_count += 1
                            
                            # Create deadline
                            due_date = now() + timedelta(days=14)
                            OnboardingDeadline.objects.create(
                                module=module,
                                mentee=mentee,
                                due_date=due_date,
                                original_due_date=due_date
                            )
                            
                            # Send notification
                            title = f"New Onboarding Module Assigned: {module.title}"
                            message = f"""
                            Hello {mentee.full_name},

                            A new onboarding module has been assigned to your department:

                            Module: {module.title}
                            Department: {department.name}
                            Description: {module.description[:200]}...

                            Please log in to start this module.

                            Best regards,
                            Mentorship Program Team
                            """
                            
                            send_onboarding_notification(
                                recipient=mentee,
                                notification_type='module_assigned',
                                title=title,
                                message=message,
                                related_module=module,
                                related_progress=progress
                            )
                            
                        except Exception as e:
                            error_msg = f'Error assigning to {mentee.full_name}: {str(e)}'
                            errors.append(error_msg)
                            logger.error(error_msg)
                            continue
                except Exception as e:
                    error_msg = f'Error processing department {department.id}: {str(e)}'
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
        
        return Response({
            'message': f'Module assigned to {assigned_count} mentees across {departments.count()} departments',
            'assigned_count': assigned_count,
            'departments_assigned': [dept.name for dept in departments],
            'errors': errors if errors else None
        })
        
    except Exception as e:
        logger.error(f"Error in assign_module_to_department: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_comparison(request):
    """Compare onboarding progress across departments"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized comparison attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can view department comparisons'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        departments = Department.objects.filter(status='active')
        comparison_data = []
        
        for department in departments:
            try:
                # Get mentees in department
                mentees = CustomUser.objects.filter(
                    role='mentee',
                    department=department,
                    status='approved'
                )
                
                # Get progress records
                progress_records = MenteeOnboardingProgress.objects.filter(
                    mentee__department=department
                )
                
                # Calculate statistics
                total_mentees = mentees.count()
                total_modules = progress_records.count()
                completed_modules = progress_records.filter(status='completed').count()
                
                # Calculate average progress
                avg_progress = progress_records.aggregate(
                    avg=Avg('progress_percentage')
                )['avg'] or 0
                
                # Calculate on-time completion rate
                on_time_rate = 0
                if completed_modules > 0:
                    on_time_completions = OnboardingDeadline.objects.filter(
                        mentee__department=department,
                        module__mentee_progress__status='completed'
                    ).filter(
                        due_date__gte=F('module__mentee_progress__completed_at')
                    ).count()
                    on_time_rate = round((on_time_completions / completed_modules * 100), 2)
                
                comparison_data.append({
                    'department_id': department.id,
                    'department_name': department.name,
                    'total_mentees': total_mentees,
                    'total_modules_assigned': total_modules,
                    'completed_modules': completed_modules,
                    'completion_rate': round((completed_modules / total_modules * 100), 2) if total_modules > 0 else 0,
                    'average_progress': round(avg_progress, 2),
                    'on_time_completion_rate': on_time_rate,
                    'mentees_behind_schedule': mentees.filter(
                        onboarding_progress__status__in=['overdue', 'off_track', 'needs_attention']
                    ).distinct().count()
                })
            except Exception as e:
                logger.error(f"Error processing department {department.id}: {str(e)}")
                continue
        
        # Sort by completion rate (descending)
        comparison_data.sort(key=lambda x: x['completion_rate'], reverse=True)
        
        summary_data = {
            'total_departments': len(comparison_data),
            'average_completion_rate': 0
        }
        
        if comparison_data:
            completion_rates = [d['completion_rate'] for d in comparison_data]
            summary_data.update({
                'highest_completion_rate': max(completion_rates),
                'lowest_completion_rate': min(completion_rates),
                'average_completion_rate': round(sum(completion_rates) / len(completion_rates), 2)
            })
        
        return Response({
            'comparison': comparison_data,
            'summary': summary_data
        })
        
    except Exception as e:
        logger.error(f"Error in get_department_comparison: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_module_performance(request, module_id):
    """Get performance of a specific module across departments"""
    try:
        try:
            module = OnboardingModule.objects.get(id=module_id)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {module_id} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.user.role not in ['admin', 'hr']:
            if request.user.role == 'mentor':
                # Mentors can only see their department
                departments = Department.objects.filter(
                    id=request.user.department.id,
                    status='active'
                )
            else:
                logger.warning(f"Unauthorized access attempt by user {request.user.id}")
                return Response(
                    {'error': 'You do not have permission to view this data'},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            # Admin/HR can see all departments
            departments = module.departments.all() if module.module_type == 'department' else Department.objects.filter(status='active')
        
        performance_data = []
        
        for department in departments:
            try:
                # Get progress for this module and department
                progress_records = MenteeOnboardingProgress.objects.filter(
                    module=module,
                    mentee__department=department
                )
                
                total_assigned = progress_records.count()
                completed = progress_records.filter(status='completed').count()
                
                # Calculate average time to complete
                completed_records = progress_records.filter(status='completed')
                avg_time = completed_records.aggregate(
                    avg=Avg('time_spent_minutes')
                )['avg'] if completed_records.exists() else None
                
                performance_data.append({
                    'department_id': department.id,
                    'department_name': department.name,
                    'total_assigned': total_assigned,
                    'completed': completed,
                    'completion_rate': round((completed / total_assigned * 100), 2) if total_assigned > 0 else 0,
                    'in_progress': progress_records.filter(status='in_progress').count(),
                    'not_started': progress_records.filter(status='not_started').count(),
                    'behind_schedule': progress_records.filter(
                        status__in=['overdue', 'off_track', 'needs_attention']
                    ).count(),
                    'average_time_minutes': round(avg_time, 1) if avg_time else None,
                    'fastest_completion': completed_records.order_by('time_spent_minutes').first().time_spent_minutes if completed_records.exists() else None,
                    'slowest_completion': completed_records.order_by('-time_spent_minutes').first().time_spent_minutes if completed_records.exists() else None
                })
            except Exception as e:
                logger.error(f"Error processing department {department.id} for module {module_id}: {str(e)}")
                continue
        
        # Sort by completion rate (descending)
        performance_data.sort(key=lambda x: x['completion_rate'], reverse=True)
        
        # Calculate overall stats
        overall_stats = {
            'total_departments': len(performance_data),
            'total_assigned': sum([d['total_assigned'] for d in performance_data]),
            'total_completed': sum([d['completed'] for d in performance_data]),
            'overall_completion_rate': 0
        }
        
        if overall_stats['total_assigned'] > 0:
            overall_stats['overall_completion_rate'] = round(
                overall_stats['total_completed'] / overall_stats['total_assigned'] * 100, 2
            )
        
        return Response({
            'module': {
                'id': module.id,
                'title': module.title,
                'type': module.module_type
            },
            'performance_by_department': performance_data,
            'overall_stats': overall_stats
        })
        
    except Exception as e:
        logger.error(f"Error in get_department_module_performance: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================ ONBOARDING MODULE VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_onboarding_modules(request):
    """Get all active onboarding modules with department support"""
    try:
        user = request.user
        queryset = OnboardingModule.objects.filter(is_active=True)
        
        # Filter by specific departments if provided (admin/HR use case)
        department_ids = request.query_params.getlist('department_ids[]')
        if department_ids:
            try:
                department_ids = [int(id) for id in department_ids]
                queryset = queryset.filter(
                    Q(module_type='core') | Q(departments__id__in=department_ids)
                ).distinct()
            except ValueError:
                logger.error(f"Invalid department IDs: {department_ids}")
                return Response(
                    {'error': 'Invalid department IDs'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Filter by module type if specified
        module_type = request.query_params.get('module_type')
        if module_type:
            queryset = queryset.filter(module_type=module_type)
        
        # Role-based filtering
        if user.role == 'mentor':
            # Mentors see modules for their departments
            mentor_dept_ids = user.departments.values_list('id', flat=True)
            queryset = queryset.filter(
                Q(module_type='core') | Q(departments__id__in=mentor_dept_ids)
            ).distinct()
        
        elif user.role == 'mentee':
            # Mentees see BOTH core modules AND their department modules
            if user.department:
                queryset = queryset.filter(
                    Q(module_type='core') | Q(departments=user.department)
                ).distinct()
            else:
                # If mentee has no department, show only core modules
                queryset = queryset.filter(module_type='core')
        
        # Admin/HR see all modules (no filtering needed)
        
        serializer = OnboardingModuleSerializer(queryset, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_onboarding_modules: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_onboarding_module_detail(request, pk):
    """Get details of a specific onboarding module"""
    try:
        try:
            module = OnboardingModule.objects.get(pk=pk, is_active=True)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found or inactive")
            return Response(
                {'error': 'Module not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user has access
        # Add your access control logic here
        
        serializer = OnboardingModuleSerializer(module)
        logger.info(f"Retrieved onboarding module details: {pk}")
        logger.info("\n\n\n")
        logger.info(serializer.data)
        logger.info("\n\n\n")
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_onboarding_module_detail: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_onboarding_module(request):
    """Create a new onboarding module (Admin/HR only)"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized create attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can create onboarding modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = OnboardingModuleCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            module = serializer.save(created_by=request.user)
            logger.info(f"Module created successfully: {module.id}")
            return Response(
                OnboardingModuleSerializer(module).data,
                status=status.HTTP_201_CREATED
            )
        
        logger.error(f"Module creation validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error in create_onboarding_module: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_onboarding_module(request, pk):
    """Update an onboarding module (Admin/HR only) - Files are optional"""
    try:
        logger.info(f"Module update request received for ID: {pk}")
        logger.info(f"Form data keys: {list(request.data.keys())}")
        logger.info(f"Files received: {list(request.FILES.keys())}")
        
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f'Unauthorized update attempt by user {request.user.id}')
            return Response(
                {'error': 'Only admins and HR can update onboarding modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse the incoming data
        update_data = {}
        
        # Handle regular form fields
        for key, value in request.data.items():
            if not key.startswith('files['):
                update_data[key] = value
        
        # Handle files separately (optional)
        files_data = []
        file_counter = 0
        
        # Check for files in the format files[0].file, files[1].file, etc.
        while True:
            file_key = f'files[{file_counter}].file'
            if file_key in request.FILES:
                file_obj = request.FILES[file_key]
                
                # Get additional file metadata if provided
                title_key = f'files[{file_counter}].title'
                description_key = f'files[{file_counter}].description'
                type_key = f'files[{file_counter}].type'
                
                file_data = {
                    'file': file_obj,
                    'title': request.data.get(title_key, file_obj.name),
                    'description': request.data.get(description_key, ''),
                    'type': request.data.get(type_key, '')
                }
                files_data.append(file_data)
                file_counter += 1
            else:
                break
        
        logger.info(f"Found {len(files_data)} files to process")
        
        # If there are files, add them to the update data
        if files_data:
            update_data['files'] = files_data
        else:
            # If no files are being uploaded, ensure we don't try to process files
            update_data['files'] = []
        
        # Handle department_ids - parse if it's a JSON string
        if 'department_ids' in update_data:
            dept_ids = update_data['department_ids']
            if isinstance(dept_ids, str):
                if dept_ids.startswith('[') and dept_ids.endswith(']'):
                    try:
                        import json
                        update_data['department_ids'] = json.loads(dept_ids)
                    except json.JSONDecodeError:
                        update_data['department_ids'] = []
                else:
                    # Handle comma-separated IDs
                    try:
                        update_data['department_ids'] = [int(id.strip()) for id in dept_ids.split(',') if id.strip()]
                    except ValueError:
                        update_data['department_ids'] = []
            elif dept_ids == '[]':
                update_data['department_ids'] = []
        
        # Handle boolean fields
        if 'is_required' in update_data:
            update_data['is_required'] = update_data['is_required'].lower() in ['true', '1', 'yes']
        
        if 'is_active' in update_data:
            update_data['is_active'] = update_data['is_active'].lower() in ['true', '1', 'yes']
        
        # Handle numeric fields
        if 'duration_minutes' in update_data:
            try:
                update_data['duration_minutes'] = int(update_data['duration_minutes'])
            except (ValueError, TypeError):
                pass
        
        if 'order' in update_data:
            try:
                update_data['order'] = int(update_data['order'])
            except (ValueError, TypeError):
                pass
        
        logger.info(f"Processed update data: {update_data}")
        
        # Create serializer with partial=True for PATCH
        serializer = OnboardingModuleCreateSerializer(
            module, 
            data=update_data, 
            partial=True if request.method == 'PATCH' else False,
            context={'request': request}
        )
        
        if serializer.is_valid():
            updated_module = serializer.save()
            logger.info(f"Module {pk} updated successfully")
            return Response(OnboardingModuleSerializer(updated_module).data)
        
        logger.error(f"Module update validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error in update_onboarding_module: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': f'An internal server error occurred: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_onboarding_module(request, pk):
    """Soft delete an onboarding module (Admin/HR only)"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized delete attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can delete onboarding modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        module.is_active = False
        module.save()
        logger.info(f"Module {pk} deactivated successfully")
        
        return Response(
            {'message': 'Module deactivated successfully'},
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error in delete_onboarding_module: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_onboarding_statistics(request):
    """Get overall onboarding statistics"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized statistics access by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can view statistics'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        total_modules = OnboardingModule.objects.filter(is_active=True).count()
        core_modules = OnboardingModule.objects.filter(
            is_active=True, 
            module_type='core'
        ).count()
        department_modules = OnboardingModule.objects.filter(
            is_active=True, 
            module_type='department'
        ).count()
        
        # Get completion statistics
        total_progress_records = MenteeOnboardingProgress.objects.count()
        completed_records = MenteeOnboardingProgress.objects.filter(
            status='completed'
        ).count()
        
        completion_rate = 0
        if total_progress_records > 0:
            completion_rate = round((completed_records / total_progress_records) * 100, 2)
        
        # Get mentee statistics
        total_mentees = CustomUser.objects.filter(role='mentee', status='approved').count()
        mentees_with_modules = CustomUser.objects.filter(
            role='mentee', 
            status='approved',
            onboarding_progress__isnull=False
        ).distinct().count()
        
        # Calculate average progress per mentee
        avg_progress = 0
        if mentees_with_modules > 0:
            avg_result = MenteeOnboardingProgress.objects.aggregate(
                avg_progress=Avg('progress_percentage')
            )
            avg_progress = avg_result['avg_progress'] or 0
        
        return Response({
            'total_modules': total_modules,
            'core_modules': core_modules,
            'department_modules': department_modules,
            'total_progress_records': total_progress_records,
            'completed_records': completed_records,
            'completion_rate': completion_rate,
            'total_mentees': total_mentees,
            'mentees_with_modules': mentees_with_modules,
            'average_mentee_progress': round(avg_progress, 2)
        })
        
    except Exception as e:
        logger.error(f"Error in get_onboarding_statistics: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_module_to_mentees(request, pk):
    """Assign a module to specific mentees"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"Unauthorized assignment attempt by user {request.user.id}")
            return Response(
                {'error': 'Only admins and HR can assign modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk, is_active=True)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found or inactive")
            return Response(
                {'error': 'Module not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        mentee_ids = request.data.get('mentee_ids', [])
        
        if not mentee_ids:
            logger.error("No mentee IDs provided")
            return Response(
                {'error': 'No mentee IDs provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        assigned_count = 0
        already_assigned = 0
        errors = []
        
        with transaction.atomic():
            for mentee_id in mentee_ids:
                try:
                    mentee = CustomUser.objects.get(id=mentee_id, role='mentee', status='approved')
                    
                    # Check if already assigned
                    if MenteeOnboardingProgress.objects.filter(
                        mentee=mentee, 
                        module=module
                    ).exists():
                        already_assigned += 1
                        continue
                    
                    # Create progress record
                    progress = MenteeOnboardingProgress.objects.create(
                        mentee=mentee,
                        module=module,
                        status='not_started',
                        progress_percentage=0,
                        assigned_by=request.user
                    )
                    assigned_count += 1
                    
                    # Create deadline record
                    if progress.started_at:
                        due_date = progress.started_at + timedelta(days=14)
                    else:
                        due_date = now() + timedelta(days=14)
                    
                    OnboardingDeadline.objects.create(
                        module=module,
                        mentee=mentee,
                        due_date=due_date,
                        original_due_date=due_date
                    )
                    
                    # Send notification to mentee
                    title = f"New Onboarding Module Assigned: {module.title}"
                    message = f"""
                    Hello {mentee.full_name},
                    
                    A new onboarding module has been assigned to you:
                    
                    Module: {module.title}
                    Type: {module.get_module_type_display()}
                    Description: {module.description[:200]}...
                    
                    Please log in to the mentorship portal to start this module.
                    
                    Best regards,
                    Mentorship Program Team
                    """
                    
                    send_onboarding_notification(
                        recipient=mentee,
                        notification_type='module_assigned',
                        title=title,
                        message=message,
                        related_module=module,
                        related_progress=progress
                    )
                    
                    # Send notification to mentors in the same department
                    mentors = CustomUser.objects.filter(
                        role='mentor',
                        department=mentee.department,
                        status='approved'
                    )
                    
                    for mentor in mentors:
                        mentor_title = f"New Module Assigned to Mentee: {mentee.full_name}"
                        mentor_message = f"""
                        Mentor Notification:
                        
                        A new onboarding module has been assigned to your mentee:
                        
                        Mentee: {mentee.full_name}
                        Module: {module.title}
                        Department: {mentee.department}
                        
                        Please check on their progress and provide support as needed.
                        
                        Best regards,
                        Mentorship Program Team
                        """
                        
                        send_onboarding_notification(
                            recipient=mentor,
                            notification_type='module_assigned',
                            title=mentor_title,
                            message=mentor_message,
                            related_module=module,
                            related_progress=progress
                        )
                    
                except CustomUser.DoesNotExist:
                    error_msg = f'Mentee with ID {mentee_id} not found or not approved'
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
                except Exception as e:
                    error_msg = f'Error assigning to mentee {mentee_id}: {str(e)}'
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
        
        return Response({
            'message': f'Module assigned to {assigned_count} mentees',
            'assigned_count': assigned_count,
            'already_assigned': already_assigned,
            'errors': errors if errors else None
        })
        
    except Exception as e:
        logger.error(f"Error in assign_module_to_mentees: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_module_mentee_progress(request, pk):
    """Get all mentees' progress for a specific module"""
    try:
        try:
            module = OnboardingModule.objects.get(pk=pk, is_active=True)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found or inactive")
            return Response(
                {'error': 'Module not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role == 'mentor' and module.module_type == 'department':
            if not module.departments.filter(id=request.user.department.id).exists():
                logger.warning(f"Mentor {request.user.id} unauthorized access to module {pk}")
                return Response(
                    {'error': 'You do not have permission to view this module progress'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Filter based on user role
        if request.user.role in ['admin', 'hr']:
            progress_records = MenteeOnboardingProgress.objects.filter(module=module)
        elif request.user.role == 'mentor':
            # Mentor can only see mentees in their department
            progress_records = MenteeOnboardingProgress.objects.filter(
                module=module,
                mentee__department=request.user.department
            )
        else:
            logger.warning(f"Unauthorized access attempt by user {request.user.id}")
            return Response(
                {'error': 'You do not have permission to view this data'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MenteeOnboardingProgressSerializer(progress_records, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_module_mentee_progress: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================ MENTEE PROGRESS VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentee_progress(request):
    """Get onboarding progress based on user role"""
    try:
        user = request.user
        
        if user.role in ['admin', 'hr']:
            # Admins and HR can see all progress
            queryset = MenteeOnboardingProgress.objects.all()
            
            # Apply filters if provided
            mentee_id = request.query_params.get('mentee_id')
            if mentee_id:
                queryset = queryset.filter(mentee_id=mentee_id)
        
        elif user.role == 'mentor':
            # Mentors can see progress of mentees in their departments
            mentor_dept_ids = user.departments.values_list('id', flat=True)
            queryset = MenteeOnboardingProgress.objects.filter(
                mentee__department__id__in=mentor_dept_ids
            )
            
            # Filter by specific mentee if provided
            mentee_id = request.query_params.get('mentee_id')
            if mentee_id:
                queryset = queryset.filter(mentee_id=mentee_id)
        
        elif user.role == 'mentee':
            # Mentees see their own progress on ALL assigned modules
            queryset = MenteeOnboardingProgress.objects.filter(mentee=user)
        
        else:
            logger.warning(f"Invalid user role: {user.role}")
            return Response(
                {'error': 'Invalid user role'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Apply additional filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        module_id = request.query_params.get('module_id')
        if module_id:
            queryset = queryset.filter(module_id=module_id)
        
        queryset = queryset.select_related('mentee', 'module')
        serializer = MenteeOnboardingProgressSerializer(queryset, many=True)
        
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_mentee_progress: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_mentee_progress_detail(request, pk):
    """Get detailed progress for a specific progress record"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr']:
            if request.user.role == 'mentor':
                if progress.mentee.department != request.user.department:
                    logger.warning(f"Mentor {request.user.id} unauthorized access to progress {pk}")
                    return Response(
                        {'error': 'You can only view progress of mentees in your department'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.role == 'mentee':
                if progress.mentee != request.user:
                    logger.warning(f"Mentee {request.user.id} unauthorized access to progress {pk}")
                    return Response(
                        {'error': 'You can only view your own progress'},
                        status=status.HTTP_403_FORBIDDEN
                    )
        
        serializer = MenteeOnboardingProgressSerializer(progress)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_mentee_progress_detail: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_onboarding_module(request, pk):
    """Mark an onboarding module as started"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr'] and progress.mentee != request.user:
            logger.warning(f"User {request.user.id} unauthorized to start module {pk}")
            return Response(
                {'error': 'You can only start your own modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        progress.mark_as_started()
        
        # Update deadline with actual start date
        try:
            deadline = OnboardingDeadline.objects.get(
                module=progress.module,
                mentee=progress.mentee
            )
            deadline.due_date = progress.started_at + timedelta(days=14)
            deadline.save()
        except OnboardingDeadline.DoesNotExist:
            # Create deadline if it doesn't exist
            OnboardingDeadline.objects.create(
                module=progress.module,
                mentee=progress.mentee,
                due_date=progress.started_at + timedelta(days=14),
                original_due_date=progress.started_at + timedelta(days=14)
            )
        
        # Send notification to mentors
        mentors = CustomUser.objects.filter(
            role='mentor',
            department=progress.mentee.department,
            status='approved'
        )
        
        title = f"Mentee Started Module: {progress.mentee.full_name}"
        message = f"""
        Mentor Notification:
        
        Your mentee has started a new onboarding module:
        
        Mentee: {progress.mentee.full_name}
        Module: {progress.module.title}
        Started: {progress.started_at.strftime('%Y-%m-%d %H:%M')}
        
        Please check in with them if they need any assistance.
        
        Best regards,
        Mentorship Program Team
        """
        
        for mentor in mentors:
            send_onboarding_notification(
                recipient=mentor,
                notification_type='module_started',
                title=title,
                message=message,
                related_module=progress.module,
                related_progress=progress
            )
        
        serializer = MenteeOnboardingProgressSerializer(progress)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in start_onboarding_module: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_onboarding_module(request, pk):
    """Mark an onboarding module as completed"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr'] and progress.mentee != request.user:
            logger.warning(f"User {request.user.id} unauthorized to complete module {pk}")
            return Response(
                {'error': 'You can only complete your own modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        progress.mark_as_completed()
        
        # Send notification to mentee
        title = f"Onboarding Module Completed: {progress.module.title}"
        message = f"""
        Congratulations {progress.mentee.full_name}!
        
        You have successfully completed the onboarding module: {progress.module.title}
        
        Great job on completing this module! You're one step closer to completing your onboarding process.
        
        Continue to the next module to keep progressing.
        
        Best regards,
        Mentorship Program Team
        """
        
        send_onboarding_notification(
            recipient=progress.mentee,
            notification_type='module_completed',
            title=title,
            message=message,
            related_module=progress.module,
            related_progress=progress
        )
        
        # Send notification to mentors
        mentors = CustomUser.objects.filter(
            role='mentor',
            department=progress.mentee.department,
            status='approved'
        )
        
        mentor_title = f"Mentee Completed Module: {progress.mentee.full_name}"
        mentor_message = f"""
        Mentor Notification:
        
        Your mentee has successfully completed an onboarding module:
        
        Mentee: {progress.mentee.full_name}
        Module: {progress.module.title}
        Completed: {progress.completed_at.strftime('%Y-%m-%d %H:%M')}
        
        Please acknowledge their achievement and encourage them to continue.
        
        Best regards,
        Mentorship Program Team
        """
        
        for mentor in mentors:
            send_onboarding_notification(
                recipient=mentor,
                notification_type='module_completed',
                title=mentor_title,
                message=mentor_message,
                related_module=progress.module,
                related_progress=progress
            )
        
        serializer = MenteeOnboardingProgressSerializer(progress)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in complete_onboarding_module: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_progress_percentage(request, pk):
    """Update progress percentage for a module"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr'] and progress.mentee != request.user:
            logger.warning(f"User {request.user.id} unauthorized to update progress {pk}")
            return Response(
                {'error': 'You can only update your own progress'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        percentage = request.data.get('progress_percentage')
        if percentage is None:
            logger.error("progress_percentage is required but not provided")
            return Response(
                {'error': 'progress_percentage is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            percentage = int(percentage)
            if not 0 <= percentage <= 100:
                logger.error(f"Invalid progress percentage: {percentage}")
                return Response(
                    {'error': 'Progress percentage must be between 0 and 100'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            time_spent = request.data.get('time_spent_minutes')
            if time_spent:
                try:
                    time_spent = int(time_spent)
                    if time_spent > 0:
                        progress.add_time_spent(time_spent)
                except ValueError:
                    logger.warning(f"Invalid time_spent value: {time_spent}")
            
            progress.update_progress(percentage)
            
            # Check and update status based on new progress
            check_and_update_progress_status(progress)
            
            serializer = MenteeOnboardingProgressSerializer(progress)
            return Response(serializer.data)
            
        except ValueError:
            logger.error(f"Invalid progress percentage format: {percentage}")
            return Response(
                {'error': 'Invalid progress percentage'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        logger.error(f"Error in update_progress_percentage: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_progress_details(request, pk):
    """Update progress details (notes, time spent, status)"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"User {request.user.id} unauthorized to update progress details {pk}")
            return Response(
                {'error': 'Only admins and HR can update progress details'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MenteeOnboardingProgressUpdateSerializer(
            progress, 
            data=request.data, 
            partial=True if request.method == 'PATCH' else False
        )
        
        if serializer.is_valid():
            old_status = progress.status
            serializer.save()
            
            # Send notification if status changed to 'needs_attention'
            new_status = progress.status
            if old_status != new_status and new_status in ['needs_attention', 'off_track', 'overdue']:
                send_status_change_notification(progress, old_status, new_status)
            
            return Response(MenteeOnboardingProgressSerializer(progress).data)
        
        logger.error(f"Progress update validation errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error in update_progress_details: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_checklist_item(request, pk):
    """Update checklist item completion status"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(pk=pk)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {pk} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr'] and progress.mentee != request.user:
            logger.warning(f"User {request.user.id} unauthorized to update checklist {pk}")
            return Response(
                {'error': 'You can only update your own checklist'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        checklist_item_id = request.data.get('checklist_item_id')
        is_completed = request.data.get('is_completed', True)
        
        if not checklist_item_id:
            logger.error("checklist_item_id is required but not provided")
            return Response(
                {'error': 'checklist_item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            checklist_item = OnboardingChecklist.objects.get(
                id=checklist_item_id,
                module=progress.module
            )
            
            # Get or create checklist progress
            checklist_progress, created = MenteeChecklistProgress.objects.get_or_create(
                mentee=progress.mentee,
                checklist_item=checklist_item
            )
            
            time_spent = request.data.get('time_spent_minutes')
            if time_spent:
                try:
                    time_spent = int(time_spent)
                    if time_spent > 0:
                        checklist_progress.add_time_spent(time_spent)
                except ValueError:
                    logger.warning(f"Invalid time_spent value: {time_spent}")
            
            if is_completed:
                checklist_progress.mark_completed()
            else:
                checklist_progress.mark_incomplete()
            
            # Update overall module progress based on checklist completion
            total_items = progress.module.checklist_items.count()
            if total_items > 0:
                completed_items = MenteeChecklistProgress.objects.filter(
                    mentee=progress.mentee,
                    checklist_item__module=progress.module,
                    is_completed=True
                ).count()
                
                new_percentage = round((completed_items / total_items) * 100)
                progress.update_progress(new_percentage)
                
                # Check if needs attention
                check_and_update_progress_status(progress)
            
            serializer = MenteeOnboardingProgressSerializer(progress)
            return Response(serializer.data)
            
        except OnboardingChecklist.DoesNotExist:
            logger.error(f"Checklist item {checklist_item_id} not found for module {progress.module.id}")
            return Response(
                {'error': 'Checklist item not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
    except Exception as e:
        logger.error(f"Error in update_checklist_item: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_progress_summary(request):
    """Get current user's onboarding progress summary"""
    try:
        if request.user.role != 'mentee':
            logger.warning(f"User {request.user.id} with role {request.user.role} attempted to access mentee progress")
            return Response(
                {'error': 'Only mentees have onboarding progress'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate overall progress
        overall_progress = calculate_overall_progress(request.user)
        
        # Get detailed progress
        progress_records = MenteeOnboardingProgress.objects.filter(
            mentee=request.user
        ).select_related('module')
        
        # Get upcoming deadlines
        deadlines = OnboardingDeadline.objects.filter(
            mentee=request.user
        ).select_related('module')
        
        upcoming_deadlines = []
        for deadline in deadlines:
            try:
                if deadline.is_overdue():
                    status = 'overdue'
                elif deadline.get_days_remaining() <= 3:
                    status = 'urgent'
                elif deadline.get_days_remaining() <= 7:
                    status = 'warning'
                else:
                    status = 'normal'
                
                # Get corresponding progress
                progress = progress_records.filter(module=deadline.module).first()
                
                upcoming_deadlines.append({
                    'module_id': deadline.module.id,
                    'module_title': deadline.module.title,
                    'due_date': deadline.due_date,
                    'days_remaining': deadline.get_days_remaining(),
                    'status': status,
                    'progress_percentage': progress.progress_percentage if progress else 0
                })
            except Exception as e:
                logger.error(f"Error processing deadline {deadline.id}: {str(e)}")
                continue
        
        # Sort by urgency (overdue first, then by days remaining)
        upcoming_deadlines.sort(key=lambda x: (
            0 if x['status'] == 'overdue' else 
            1 if x['status'] == 'urgent' else 
            2 if x['status'] == 'warning' else 3,
            x['days_remaining']
        ))
        
        serializer = MenteeSummarySerializer(request.user)
        response_data = serializer.data
        response_data.update(overall_progress)
        response_data['upcoming_deadlines'] = upcoming_deadlines[:5]  # Top 5 most urgent
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error in get_my_progress_summary: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_mentees_summary(request):
    """Get summary of all mentees' progress (admin/HR only)"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"User {request.user.id} unauthorized to view all mentees summary")
            return Response(
                {'error': 'Only admins and HR can view all mentees summary'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        mentees = CustomUser.objects.filter(role='mentee', status='approved')
        
        # Filter by department if specified
        department = request.query_params.get('department', None)
        if department:
            mentees = mentees.filter(department=department)
        
        # Get mentee IDs who are behind schedule
        behind_schedule_ids = []
        for mentee in mentees:
            try:
                progress_records = MenteeOnboardingProgress.objects.filter(
                    mentee=mentee,
                    status__in=['overdue', 'off_track', 'needs_attention']
                )
                if progress_records.exists():
                    behind_schedule_ids.append(mentee.id)
            except Exception as e:
                logger.error(f"Error checking progress for mentee {mentee.id}: {str(e)}")
                continue
        
        serializer = MenteeSummarySerializer(mentees, many=True)
        
        # Add additional statistics
        total_mentees = mentees.count()
        mentees_with_progress = mentees.filter(onboarding_progress__isnull=False).distinct().count()
        
        behind_schedule_percentage = 0
        if total_mentees > 0:
            behind_schedule_percentage = round((len(behind_schedule_ids) / total_mentees * 100), 2)
        
        return Response({
            'mentees': serializer.data,
            'statistics': {
                'total_mentees': total_mentees,
                'mentees_with_progress': mentees_with_progress,
                'mentees_behind_schedule': len(behind_schedule_ids),
                'behind_schedule_percentage': behind_schedule_percentage
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_all_mentees_summary: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auto_assign_modules(request):
    """Automatically assign appropriate modules to a mentee based on their department"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"User {request.user.id} unauthorized to auto-assign modules")
            return Response(
                {'error': 'Only admins and HR can auto-assign modules'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        mentee_id = request.data.get('mentee_id')
        if not mentee_id:
            logger.error("mentee_id is required but not provided")
            return Response(
                {'error': 'mentee_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            mentee = CustomUser.objects.get(id=mentee_id, role='mentee', status='approved')
        except CustomUser.DoesNotExist:
            logger.error(f"Mentee {mentee_id} not found or not approved")
            return Response(
                {'error': 'Mentee not found or not approved'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get BOTH core modules AND department-specific modules
        if mentee.department:
            modules = OnboardingModule.objects.filter(
                Q(module_type='core') | Q(departments=mentee.department),
                is_active=True
            ).distinct()
        else:
            # If no department, assign only core modules
            modules = OnboardingModule.objects.filter(
                module_type='core',
                is_active=True
            )
        
        assigned_count = 0
        assigned_modules = []
        
        with transaction.atomic():
            for module in modules:
                try:
                    # Check if already assigned
                    if not MenteeOnboardingProgress.objects.filter(
                        mentee=mentee,
                        module=module
                    ).exists():
                        progress = MenteeOnboardingProgress.objects.create(
                            mentee=mentee,
                            module=module,
                            status='not_started',
                            progress_percentage=0,
                            assigned_by=request.user
                        )
                        
                        # Create deadline
                        due_date = now() + timedelta(days=14)
                        OnboardingDeadline.objects.create(
                            module=module,
                            mentee=mentee,
                            due_date=due_date,
                            original_due_date=due_date
                        )
                        
                        assigned_count += 1
                        assigned_modules.append({
                            'id': module.id,
                            'title': module.title,
                            'type': module.module_type
                        })
                except Exception as e:
                    logger.error(f"Error assigning module {module.id} to mentee {mentee.id}: {str(e)}")
                    continue
        
        # Send notification
        if assigned_count > 0:
            title = "Onboarding Modules Assigned"
            module_list = "\n".join([f"- {module['title']} ({module['type']})" for module in assigned_modules])
            
            dept_name = mentee.department.name if mentee.department else "No Department"
            
            message = f"""
            Hello {mentee.full_name},

            {assigned_count} onboarding modules have been automatically assigned to you.

            Department: {dept_name}

            Assigned Modules:
            {module_list}

            These include both core modules (required for all mentees) and department-specific modules.

            Please log in to the mentorship portal to start your onboarding journey.

            Best regards,
            Mentorship Program Team
            """
            
            send_onboarding_notification(
                recipient=mentee,
                notification_type='module_assigned',
                title=title,
                message=message
            )
        
        return Response({
            'message': f'Auto-assigned {assigned_count} modules to {mentee.full_name}',
            'assigned_count': assigned_count,
            'assigned_modules': assigned_modules,
            'mentee': {
                'id': mentee.id,
                'name': mentee.full_name,
                'department': mentee.department.name if mentee.department else None
            }
        })
        
    except Exception as e:
        logger.error(f"Error in auto_assign_modules: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_upcoming_deadlines(request):
    """Get modules that are close to deadline"""
    try:
        user = request.user
        
        if user.role == 'mentee':
            # Get mentee's deadlines
            deadlines = OnboardingDeadline.objects.filter(mentee=user)
            
            upcoming_deadlines = []
            for deadline in deadlines:
                try:
                    days_remaining = deadline.get_days_remaining()
                    
                    if days_remaining <= 7:  # Show deadlines within 7 days
                        # Get progress for this module
                        progress = MenteeOnboardingProgress.objects.filter(
                            mentee=user,
                            module=deadline.module
                        ).first()
                        
                        status = 'overdue' if deadline.is_overdue() else 'urgent' if days_remaining <= 1 else 'warning'
                        
                        upcoming_deadlines.append({
                            'module_id': deadline.module.id,
                            'module_title': deadline.module.title,
                            'due_date': deadline.due_date,
                            'days_remaining': days_remaining,
                            'status': status,
                            'progress_percentage': progress.progress_percentage if progress else 0,
                            'is_extended': deadline.is_extended
                        })
                except Exception as e:
                    logger.error(f"Error processing deadline {deadline.id}: {str(e)}")
                    continue
            
            return Response(upcoming_deadlines)
        
        elif user.role == 'mentor':
            # Get deadlines for mentees in mentor's department
            mentees = CustomUser.objects.filter(
                role='mentee',
                department=user.department,
                status='approved'
            )
            
            upcoming_deadlines = []
            for mentee in mentees:
                try:
                    deadlines = OnboardingDeadline.objects.filter(mentee=mentee)
                    
                    for deadline in deadlines:
                        days_remaining = deadline.get_days_remaining()
                        
                        if days_remaining <= 7:
                            progress = MenteeOnboardingProgress.objects.filter(
                                mentee=mentee,
                                module=deadline.module
                            ).first()
                            
                            status = 'overdue' if deadline.is_overdue() else 'urgent' if days_remaining <= 1 else 'warning'
                            
                            upcoming_deadlines.append({
                                'mentee_id': mentee.id,
                                'mentee_name': mentee.full_name,
                                'module_id': deadline.module.id,
                                'module_title': deadline.module.title,
                                'due_date': deadline.due_date,
                                'days_remaining': days_remaining,
                                'status': status,
                                'progress_percentage': progress.progress_percentage if progress else 0,
                                'is_extended': deadline.is_extended
                            })
                except Exception as e:
                    logger.error(f"Error processing deadlines for mentee {mentee.id}: {str(e)}")
                    continue
            
            # Sort by urgency
            upcoming_deadlines.sort(key=lambda x: (
                0 if x['status'] == 'overdue' else 
                1 if x['status'] == 'urgent' else 
                2 if x['status'] == 'warning' else 3,
                x['days_remaining']
            ))
            
            return Response(upcoming_deadlines)
        
        elif user.role in ['admin', 'hr']:
            # Get all deadlines
            deadlines = OnboardingDeadline.objects.all()
            
            upcoming_deadlines = []
            for deadline in deadlines:
                try:
                    days_remaining = deadline.get_days_remaining()
                    
                    if days_remaining <= 7 or deadline.is_overdue():
                        progress = MenteeOnboardingProgress.objects.filter(
                            mentee=deadline.mentee,
                            module=deadline.module
                        ).first()
                        
                        status = 'overdue' if deadline.is_overdue() else 'urgent' if days_remaining <= 1 else 'warning'
                        
                        upcoming_deadlines.append({
                            'mentee_id': deadline.mentee.id,
                            'mentee_name': deadline.mentee.full_name,
                            'mentee_department': deadline.mentee.department.name if deadline.mentee.department else None,
                            'module_id': deadline.module.id,
                            'module_title': deadline.module.title,
                            'due_date': deadline.due_date,
                            'days_remaining': days_remaining,
                            'status': status,
                            'progress_percentage': progress.progress_percentage if progress else 0,
                            'is_extended': deadline.is_extended
                        })
                except Exception as e:
                    logger.error(f"Error processing deadline {deadline.id}: {str(e)}")
                    continue
            
            # Sort by urgency
            upcoming_deadlines.sort(key=lambda x: (
                0 if x['status'] == 'overdue' else 
                1 if x['status'] == 'urgent' else 
                2 if x['status'] == 'warning' else 3,
                x['days_remaining']
            ))
            
            return Response(upcoming_deadlines)
        
        return Response([])
        
    except Exception as e:
        logger.error(f"Error in get_upcoming_deadlines: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================ ADDITIONAL VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_notifications(request):
    """Get current user's onboarding notifications"""
    try:
        notifications = OnboardingNotification.objects.filter(
            recipient=request.user
        ).order_by('-sent_at')[:50]  # Last 50 notifications
        
        # Mark as read if specified
        mark_read = request.query_params.get('mark_read', 'false').lower() == 'true'
        if mark_read:
            unread_notifications = notifications.filter(is_read=False)
            updated_count = unread_notifications.update(is_read=True, read_at=now())
            logger.info(f"Marked {updated_count} notifications as read for user {request.user.id}")
        
        notification_data = []
        for notification in notifications:
            try:
                notification_data.append({
                    'id': notification.id,
                    'type': notification.notification_type,
                    'title': notification.title,
                    'message': notification.message,
                    'sent_at': notification.sent_at,
                    'is_read': notification.is_read,
                    'read_at': notification.read_at,
                    'module_id': notification.related_module.id if notification.related_module else None,
                    'module_title': notification.related_module.title if notification.related_module else None,
                    'progress_id': notification.related_progress.id if notification.related_progress else None
                })
            except Exception as e:
                logger.error(f"Error processing notification {notification.id}: {str(e)}")
                continue
        
        # Count unread notifications
        unread_count = OnboardingNotification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        
        return Response({
            'notifications': notification_data,
            'unread_count': unread_count,
            'total_count': notifications.count()
        })
        
    except Exception as e:
        logger.error(f"Error in get_my_notifications: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    """Mark a specific notification as read"""
    try:
        try:
            notification = OnboardingNotification.objects.get(id=notification_id, recipient=request.user)
        except OnboardingNotification.DoesNotExist:
            logger.error(f"Notification {notification_id} not found for user {request.user.id}")
            return Response(
                {'error': 'Notification not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not notification.is_read:
            notification.mark_as_read()
            logger.info(f"Marked notification {notification_id} as read for user {request.user.id}")
        
        return Response({
            'message': 'Notification marked as read',
            'notification_id': notification.id
        })
        
    except Exception as e:
        logger.error(f"Error in mark_notification_read: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all notifications as read for current user"""
    try:
        unread_notifications = OnboardingNotification.objects.filter(
            recipient=request.user,
            is_read=False
        )
        
        updated_count = unread_notifications.update(is_read=True, read_at=now())
        logger.info(f"Marked {updated_count} notifications as read for user {request.user.id}")
        
        return Response({
            'message': f'Marked {updated_count} notifications as read'
        })
        
    except Exception as e:
        logger.error(f"Error in mark_all_notifications_read: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def extend_deadline(request, progress_id):
    """Extend the deadline for a module (Admin/HR/Mentor only)"""
    try:
        try:
            progress = MenteeOnboardingProgress.objects.get(id=progress_id)
        except MenteeOnboardingProgress.DoesNotExist:
            logger.error(f"Progress record {progress_id} not found")
            return Response(
                {'error': 'Progress record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if request.user.role not in ['admin', 'hr', 'mentor']:
            logger.warning(f"User {request.user.id} unauthorized to extend deadline")
            return Response(
                {'error': 'You do not have permission to extend deadlines'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Mentors can only extend for mentees in their department
        if request.user.role == 'mentor' and progress.mentee.department != request.user.department:
            logger.warning(f"Mentor {request.user.id} unauthorized to extend deadline for mentee in different department")
            return Response(
                {'error': 'You can only extend deadlines for mentees in your department'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        new_due_date_str = request.data.get('new_due_date')
        reason = request.data.get('reason', '')
        
        if not new_due_date_str:
            logger.error("new_due_date is required but not provided")
            return Response(
                {'error': 'new_due_date is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            new_due_date = datetime.fromisoformat(new_due_date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date format: {new_due_date_str}, error: {str(e)}")
            return Response(
                {'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get or create deadline
        deadline, created = OnboardingDeadline.objects.get_or_create(
            module=progress.module,
            mentee=progress.mentee,
            defaults={
                'due_date': new_due_date,
                'original_due_date': new_due_date
            }
        )
        
        if not created:
            deadline.extend_deadline(new_due_date, reason, request.user)
        
        # Update progress due date
        progress.due_date = new_due_date
        progress.save()
        
        # Send notification
        title = f"Deadline Extended: {progress.module.title}"
        message = f"""
        Hello {progress.mentee.full_name},
        
        The deadline for your onboarding module "{progress.module.title}" has been extended.
        
        New Due Date: {new_due_date.strftime('%Y-%m-%d')}
        Reason: {reason if reason else 'No reason provided'}
        
        Please continue working on the module and aim to complete it by the new deadline.
        
        Best regards,
        Mentorship Program Team
        """
        
        send_onboarding_notification(
            recipient=progress.mentee,
            notification_type='deadline_approaching',
            title=title,
            message=message,
            related_module=progress.module,
            related_progress=progress
        )
        
        return Response({
            'message': 'Deadline extended successfully',
            'new_due_date': new_due_date,
            'reason': reason,
            'extended_by': request.user.full_name
        })
        
    except Exception as e:
        logger.error(f"Error in extend_deadline: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_progress_health(request):
    """Check the health of mentee's onboarding progress"""
    try:
        if request.user.role != 'mentee':
            logger.warning(f"User {request.user.id} with role {request.user.role} attempted to check progress health")
            return Response(
                {'error': 'Only mentees can check progress health'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        progress_records = MenteeOnboardingProgress.objects.filter(
            mentee=request.user
        ).select_related('module')
        
        warnings = []
        suggestions = []
        
        for progress in progress_records:
            try:
                # Check for overdue modules
                if progress.is_overdue():
                    warnings.append({
                        'type': 'overdue',
                        'module_id': progress.module.id,
                        'module_title': progress.module.title,
                        'message': f'Module "{progress.module.title}" is overdue. Please complete it as soon as possible.'
                    })
                
                # Check for slow progress
                speed = progress.get_progress_speed()
                if speed > 0 and speed < 10:  # Less than 10% per day
                    warnings.append({
                        'type': 'slow_progress',
                        'module_id': progress.module.id,
                        'module_title': progress.module.title,
                        'message': f'Progress on "{progress.module.title}" is slower than expected. Consider increasing your pace.'
                    })
                
                # Check for modules not started but assigned a while ago
                if progress.status == 'not_started':
                    assigned_days = (now() - progress.assigned_at).days
                    if assigned_days >= 3:
                        suggestions.append({
                            'type': 'not_started',
                            'module_id': progress.module.id,
                            'module_title': progress.module.title,
                            'message': f'Consider starting "{progress.module.title}" soon.'
                        })
            except Exception as e:
                logger.error(f"Error checking health for progress {progress.id}: {str(e)}")
                continue
        
        # Calculate overall progress
        overall_progress = calculate_overall_progress(request.user)
        
        # Generate overall suggestions
        if overall_progress['overall_percentage'] < 30 and len(warnings) > 2:
            suggestions.append({
                'type': 'overall_slow',
                'message': 'Your overall onboarding progress is slow. Consider focusing more time on onboarding.'
            })
        
        return Response({
            'warnings': warnings,
            'suggestions': suggestions,
            'overall_progress': overall_progress['overall_percentage'],
            'total_modules': overall_progress['total_modules'],
            'completed_modules': overall_progress['completed_modules']
        })
        
    except Exception as e:
        logger.error(f"Error in check_progress_health: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def send_reminder(request):
    """Send reminder email to mentee about onboarding progress."""
    try:
        logger.info("Received reminder request with data: %s", request.data)
        
        serializer = SendReminderSerializer(data=request.data)
        
        if serializer.is_valid():
            recipient_id = serializer.validated_data['recipient_id']
            notification_type = serializer.validated_data['notification_type']
            title = serializer.validated_data['title']
            message = serializer.validated_data['message']
            
            # Validate inputs
            if not recipient_id:
                logger.error("Recipient ID is empty.")
                return Response(
                    {"error": "Recipient ID field cannot be empty."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not notification_type.strip():
                logger.error("Notification type field is empty.")
                return Response(
                    {"error": "Notification type field cannot be empty."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not title.strip():
                logger.error("Title field is empty.")
                return Response(
                    {"error": "Title field cannot be empty."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not message.strip():
                logger.error("Message field is empty.")
                return Response(
                    {"error": "Message field cannot be empty."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get mentee directly from CustomUser
            try:
                mentee = CustomUser.objects.get(id=recipient_id, role='mentee')
                email = mentee.email
                logger.info(f"Found mentee: {mentee.full_name} ({email})")
            except CustomUser.DoesNotExist:
                logger.error("Mentee not found for recipient ID: %s", recipient_id)
                return Response(
                    {"error": "Mentee not found for the given recipient ID."}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Get mentee's progress summary for context
            try:
                progress_summary = MenteeOnboardingProgress.objects.filter(mentee=mentee)
                total_modules = progress_summary.count()
                completed_modules = progress_summary.filter(status='completed').count()
                in_progress_modules = progress_summary.filter(status='in_progress').count()
            except Exception as e:
                logger.warning(f"Could not fetch progress summary: {e}")
                total_modules = 0
                completed_modules = 0
                in_progress_modules = 0

            # Create onboarding notification record
            try:
                OnboardingNotification.objects.create(
                    recipient=mentee,
                    notification_type=notification_type,
                    title=title,
                    message=message
                )
                logger.info("Notification record created successfully")
            except Exception as e:
                logger.warning(f"Failed to create notification record: {e}")

            # Prepare and send email
            try:
                full_message = f"""
Hello {mentee.full_name},

{message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your Current Onboarding Progress:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Total Modules: {total_modules}
- Completed: {completed_modules}
- In Progress: {in_progress_modules}
- Not Started: {total_modules - completed_modules - in_progress_modules}
- Department: {mentee.department.name if mentee.department else 'Not assigned'}

Please log in to the mentorship portal to continue your onboarding journey.

Best regards,
Onboarding Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated message. Please do not reply to this email.
                """
                
                send_mail(
                    subject=title,
                    message=full_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                
                logger.info(f"Reminder email sent successfully to {email}")
                
                return Response({
                    "message": f"Reminder sent successfully to {mentee.full_name}",
                    "mentee_name": mentee.full_name,
                    "mentee_email": email,
                    "modules_completed": completed_modules,
                    "total_modules": total_modules
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                logger.exception(f"An error occurred while sending email: {e}")
                return Response({
                    "error": "Failed to send email. Please try again later.",
                    "details": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        logger.error(f"Invalid serializer data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error in send_reminder: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {"error": "An internal server error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_module_files(request, pk):
    """Upload files to an existing module"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"User {request.user.id} unauthorized to upload files")
            return Response(
                {'error': 'Only admins and HR can upload files'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        files = request.FILES.getlist('files')
        if not files:
            logger.error("No files provided for upload")
            return Response(
                {'error': 'No files provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_files = []
        errors = []
        
        for file in files:
            try:
                # Validate file size
                if file.size > settings.MAX_FILE_SIZE:
                    error_msg = f"File {file.name} exceeds size limit"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
                
                # Save file - assuming you have FileUploadHandler in utils
                # from .utils import FileUploadHandler
                file_handler = FileUploadHandler()
                file_metadata = file_handler.save_file(
                    file=file,
                    module_id=module.id,
                    user_id=request.user.id
                )
                
                # Add to module
                module.add_file(file_metadata)
                uploaded_files.append(file_metadata)
                logger.info(f"File {file.name} uploaded successfully for module {pk}")
                
            except Exception as e:
                error_msg = f"Error uploading {file.name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                continue
        
        return Response({
            'message': f'Successfully uploaded {len(uploaded_files)} files',
            'uploaded_files': uploaded_files,
            'errors': errors if errors else None
        })
        
    except Exception as e:
        logger.error(f"Error in upload_module_files: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_module_file(request, pk, file_id):
    """Delete a specific file from a module"""
    try:
        if request.user.role not in ['admin', 'hr']:
            logger.warning(f"User {request.user.id} unauthorized to delete files")
            return Response(
                {'error': 'Only admins and HR can delete files'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            module = OnboardingModule.objects.get(pk=pk)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find the file
        file_to_delete = None
        for file in module.multimedia_files:
            if file.get('id') == file_id:
                file_to_delete = file
                break
        
        if not file_to_delete:
            logger.error(f"File {file_id} not found in module {pk}")
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Delete from storage
            if 'path' in file_to_delete:
                # Assuming FileUploadHandler is available
                # from .utils import FileUploadHandler
                FileUploadHandler.delete_file(file_to_delete['path'])
            
            # Remove from module
            module.remove_file(file_id)
            logger.info(f"File {file_id} deleted successfully from module {pk}")
            
            return Response({
                'message': 'File deleted successfully',
                'file_id': file_id
            })
            
        except Exception as e:
            logger.error(f"Failed to delete file: {str(e)}")
            return Response(
                {'error': f'Failed to delete file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Exception as e:
        logger.error(f"Error in delete_module_file: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_module_file(request, pk, file_id):
    """Download a specific file from a module"""
    try:
        try:
            module = OnboardingModule.objects.get(pk=pk)
        except OnboardingModule.DoesNotExist:
            logger.error(f"Module {pk} not found")
            return Response(
                {'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user has access to this module
        if request.user.role == 'mentee':
            if module.module_type == 'department' and not module.departments.filter(id=request.user.department.id).exists():
                logger.warning(f"Mentee {request.user.id} unauthorized to access module {pk}")
                return Response(
                    {'error': 'You do not have access to this module'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Find the file
        file_data = None
        for file in module.multimedia_files:
            if file.get('id') == file_id:
                file_data = file
                break
        
        if not file_data or 'path' not in file_data:
            logger.error(f"File {file_id} not found or has no path in module {pk}")
            raise Http404("File not found")
        
        file_path = file_data['path']
        
        # Assuming you have os imported at the top
        import os
        if not os.path.exists(file_path):
            logger.error(f"File not found at path: {file_path}")
            raise Http404("File not found")
        
        # Determine content type
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Open and serve file
        try:
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type
            )
            
            # Set filename for download
            filename = file_data.get('original_filename', os.path.basename(file_path))
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"File {file_id} downloaded successfully from module {pk}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to serve file: {str(e)}")
            return Response(
                {'error': f'Failed to serve file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error in download_module_file: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ================ DEPARTMENT MODULES VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_modules(request):
    """Get modules for current user's department"""
    try:
        user = request.user
        
        if user.role == 'mentee':
            # For mentees, show BOTH core AND department modules
            if user.department:
                queryset = OnboardingModule.objects.filter(
                    Q(module_type='core') | Q(departments=user.department),
                    is_active=True
                ).distinct()
            else:
                # If no department, show only core modules
                queryset = OnboardingModule.objects.filter(
                    module_type='core',
                    is_active=True
                )
        
        elif user.role == 'mentor':
            # For mentors, show modules for their departments
            mentor_dept_ids = user.departments.values_list('id', flat=True)
            queryset = OnboardingModule.objects.filter(
                Q(module_type='core') | Q(departments__id__in=mentor_dept_ids),
                is_active=True
            ).distinct()
        
        else:
            # Admin/HR can specify department by ID
            department_id = request.query_params.get('department_id')
            if department_id:
                try:
                    department = Department.objects.get(id=int(department_id))
                    queryset = OnboardingModule.objects.filter(
                        Q(module_type='core') | Q(departments=department),
                        is_active=True
                    ).distinct()
                except (Department.DoesNotExist, ValueError) as e:
                    logger.error(f"Invalid department ID: {department_id}, error: {str(e)}")
                    return Response(
                        {'error': 'Invalid department ID'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Show all modules
                queryset = OnboardingModule.objects.filter(is_active=True)
        
        serializer = OnboardingModuleSerializer(queryset, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Error in get_department_modules: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            {'error': 'An internal server error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )