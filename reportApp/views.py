# reportApp/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q, Avg, Sum, F
from django.utils.timezone import now
from datetime import date, timedelta

from userApp.models import CustomUser
from departmentApp.models import Department
from onboarding.models import (
    OnboardingModule, MenteeOnboardingProgress,
    OnboardingChecklist, MenteeChecklistProgress
)
from mentorshipApp.models import (
    Mentorship, MentorshipSession, MentorshipProgram,
    MentorshipReview
)


# ==================== HELPER FUNCTIONS ====================
def check_role_permission(user, allowed_roles):
    """Check if user has permission based on role"""
    if user.role not in allowed_roles:
        return False
    return True


# ==================== ADMIN REPORTS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard_overview(request):
    """Admin dashboard with overall system statistics"""
    try:
        user = request.user
        
        # Check permission
        if not check_role_permission(user, ['admin']):
            return Response({
                'success': False,
                'message': 'Permission denied. Admin access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # User statistics
        total_users = CustomUser.objects.count()
        active_users = CustomUser.objects.filter(availability_status='active').count()
        pending_approvals = CustomUser.objects.filter(status='pending').count()
        
        users_by_role = CustomUser.objects.values('role').annotate(
            count=Count('id')
        )
        
        # Department statistics
        total_departments = Department.objects.filter(status='active').count()
        
        # Mentorship statistics
        total_mentorships = Mentorship.objects.count()
        active_mentorships = Mentorship.objects.filter(status='active').count()
        completed_mentorships = Mentorship.objects.filter(status='completed').count()
        
        # Onboarding statistics
        total_modules = OnboardingModule.objects.filter(is_active=True).count()
        total_progress = MenteeOnboardingProgress.objects.count()
        completed_progress = MenteeOnboardingProgress.objects.filter(status='completed').count()
        
        completion_rate = 0
        if total_progress > 0:
            completion_rate = round((completed_progress / total_progress) * 100, 2)
        
        # Session statistics
        total_sessions = MentorshipSession.objects.count()
        completed_sessions = MentorshipSession.objects.filter(status='completed').count()
        upcoming_sessions = MentorshipSession.objects.filter(
            status='scheduled',
            scheduled_date__gte=now()
        ).count()
        
        data = {
            'success': True,
            'users': {
                'total': total_users,
                'active': active_users,
                'pending_approvals': pending_approvals,
                'by_role': list(users_by_role)
            },
            'departments': {
                'total': total_departments
            },
            'mentorships': {
                'total': total_mentorships,
                'active': active_mentorships,
                'completed': completed_mentorships
            },
            'onboarding': {
                'total_modules': total_modules,
                'total_progress_records': total_progress,
                'completed': completed_progress,
                'completion_rate': completion_rate
            },
            'sessions': {
                'total': total_sessions,
                'completed': completed_sessions,
                'upcoming': upcoming_sessions
            },
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Admin Dashboard Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Admin Dashboard Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating admin dashboard: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_user_analytics(request):
    """Detailed user analytics for admin"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['admin']):
            return Response({
                'success': False,
                'message': 'Permission denied. Admin access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Users by department
        users_by_dept = Department.objects.filter(status='active').annotate(
            mentee_count=Count('users', filter=Q(users__role='mentee')),
            mentor_count=Count('mentors', filter=Q(mentors__role='mentor'))
        ).values('id', 'name', 'mentee_count', 'mentor_count')
        
        # Users by status
        users_by_status = CustomUser.objects.values('status').annotate(
            count=Count('id')
        )
        
        # Recent registrations (last 30 days)
        thirty_days_ago = now() - timedelta(days=30)
        recent_users = CustomUser.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()
        
        data = {
            'success': True,
            'users_by_department': list(users_by_dept),
            'users_by_status': list(users_by_status),
            'recent_registrations': recent_users,
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Admin User Analytics Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Admin User Analytics Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating user analytics: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_department_report(request):
    """Department-wise report for admin"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['admin']):
            return Response({
                'success': False,
                'message': 'Permission denied. Admin access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        departments = Department.objects.filter(status='active')
        
        dept_data = []
        for dept in departments:
            mentee_count = dept.users.filter(role='mentee').count()
            mentor_count = dept.mentors.filter(role='mentor').count()
            active_mentorships = Mentorship.objects.filter(
                department=dept,
                status='active'
            ).count()
            programs = dept.mentorship_programs.filter(status='active').count()
            
            dept_data.append({
                'department_id': dept.id,
                'department_name': dept.name,
                'mentee_count': mentee_count,
                'mentor_count': mentor_count,
                'active_mentorships': active_mentorships,
                'programs': programs
            })
        
        data = {
            'success': True,
            'departments': dept_data,
            'total_departments': len(dept_data),
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Admin Department Report Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Admin Department Report Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating department report: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== HR REPORTS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def hr_dashboard_overview(request):
    """HR dashboard with onboarding and user management stats"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['hr', 'admin']):
            return Response({
                'success': False,
                'message': 'Permission denied. HR or Admin access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Pending approvals
        pending_users = CustomUser.objects.filter(status='pending').count()
        
        # Onboarding stats
        total_modules = OnboardingModule.objects.filter(is_active=True).count()
        in_progress = MenteeOnboardingProgress.objects.filter(
            status='in_progress'
        ).count()
        overdue = MenteeOnboardingProgress.objects.filter(
            due_date__lt=now(),
            status__in=['not_started', 'in_progress']
        ).count()
        
        # Recent completions (last 7 days)
        week_ago = now() - timedelta(days=7)
        recent_completions = MenteeOnboardingProgress.objects.filter(
            status='completed',
            completed_at__gte=week_ago
        ).count()
        
        data = {
            'success': True,
            'pending_approvals': pending_users,
            'onboarding': {
                'total_modules': total_modules,
                'in_progress': in_progress,
                'overdue': overdue,
                'recent_completions': recent_completions
            },
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ HR Dashboard Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ HR Dashboard Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating HR dashboard: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def hr_onboarding_report(request):
    """Detailed onboarding report for HR"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['hr', 'admin']):
            return Response({
                'success': False,
                'message': 'Permission denied. HR or Admin access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all modules with completion stats
        modules = OnboardingModule.objects.filter(is_active=True)
        
        module_stats = []
        for module in modules:
            total_assigned = MenteeOnboardingProgress.objects.filter(
                module=module
            ).count()
            completed = MenteeOnboardingProgress.objects.filter(
                module=module,
                status='completed'
            ).count()
            in_progress = MenteeOnboardingProgress.objects.filter(
                module=module,
                status='in_progress'
            ).count()
            not_started = MenteeOnboardingProgress.objects.filter(
                module=module,
                status='not_started'
            ).count()
            
            completion_rate = 0
            if total_assigned > 0:
                completion_rate = round((completed / total_assigned) * 100, 2)
            
            module_stats.append({
                'module_id': module.id,
                'module_title': module.title,
                'module_type': module.module_type,
                'total_assigned': total_assigned,
                'completed': completed,
                'in_progress': in_progress,
                'not_started': not_started,
                'completion_rate': completion_rate
            })
        
        data = {
            'success': True,
            'modules': module_stats,
            'total_modules': len(module_stats),
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ HR Onboarding Report Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ HR Onboarding Report Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating onboarding report: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MENTOR REPORTS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mentor_dashboard_overview(request):
    """Mentor dashboard with their mentees and sessions"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['mentor']):
            return Response({
                'success': False,
                'message': 'Permission denied. Mentor access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get mentor's mentorships
        mentorships = Mentorship.objects.filter(mentor=user)
        
        total_mentees = mentorships.count()
        active_mentorships = mentorships.filter(status='active').count()
        
        # Session statistics
        total_sessions = MentorshipSession.objects.filter(
            mentorship__mentor=user
        ).count()
        completed_sessions = MentorshipSession.objects.filter(
            mentorship__mentor=user,
            status='completed'
        ).count()
        upcoming_sessions = MentorshipSession.objects.filter(
            mentorship__mentor=user,
            status='scheduled',
            scheduled_date__gte=now()
        ).count()
        
        # Average rating
        avg_rating = MentorshipReview.objects.filter(
            mentorship__mentor=user,
            reviewer_type='mentee'
        ).aggregate(avg=Avg('rating'))['avg'] or 0
        
        data = {
            'success': True,
            'mentor_name': user.full_name,
            'mentorships': {
                'total': total_mentees,
                'active': active_mentorships
            },
            'sessions': {
                'total': total_sessions,
                'completed': completed_sessions,
                'upcoming': upcoming_sessions
            },
            'average_rating': round(avg_rating, 2),
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Mentor Dashboard Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Mentor Dashboard Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating mentor dashboard: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mentor_mentee_progress(request):
    """Detailed progress report for mentor's mentees"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['mentor']):
            return Response({
                'success': False,
                'message': 'Permission denied. Mentor access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        mentorships = Mentorship.objects.filter(mentor=user, status='active')
        
        mentee_progress = []
        for mentorship in mentorships:
            mentee = mentorship.mentee
            
            # Onboarding progress
            onboarding_total = MenteeOnboardingProgress.objects.filter(
                mentee=mentee
            ).count()
            onboarding_completed = MenteeOnboardingProgress.objects.filter(
                mentee=mentee,
                status='completed'
            ).count()
            
            # Session progress
            sessions_completed = MentorshipSession.objects.filter(
                mentorship=mentorship,
                status='completed'
            ).count()
            total_sessions = mentorship.get_total_sessions()
            
            mentee_progress.append({
                'mentee_id': mentee.id,
                'mentee_name': mentee.full_name,
                'department': mentee.department.name if mentee.department else None,
                'mentorship_status': mentorship.status,
                'onboarding': {
                    'total': onboarding_total,
                    'completed': onboarding_completed,
                    'completion_rate': round((onboarding_completed / onboarding_total * 100), 2) if onboarding_total > 0 else 0
                },
                'sessions': {
                    'completed': sessions_completed,
                    'total': total_sessions,
                    'progress_percentage': mentorship.get_progress_percentage()
                }
            })
        
        data = {
            'success': True,
            'mentor_name': user.full_name,
            'mentees': mentee_progress,
            'total_mentees': len(mentee_progress),
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Mentor Mentee Progress Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Mentor Mentee Progress Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating mentee progress: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MENTEE REPORTS ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mentee_dashboard_overview(request):
    """Mentee dashboard with their progress and sessions"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['mentee']):
            return Response({
                'success': False,
                'message': 'Permission denied. Mentee access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Mentorship info
        try:
            mentorship = Mentorship.objects.get(mentee=user, status='active')
            has_mentorship = True
            mentor_name = mentorship.mentor.full_name
            mentorship_status = mentorship.status
        except Mentorship.DoesNotExist:
            has_mentorship = False
            mentor_name = None
            mentorship_status = None
        
        # Onboarding progress
        total_modules = MenteeOnboardingProgress.objects.filter(mentee=user).count()
        completed_modules = MenteeOnboardingProgress.objects.filter(
            mentee=user,
            status='completed'
        ).count()
        
        # Session statistics
        total_sessions = 0
        completed_sessions = 0
        upcoming_sessions = 0
        
        if has_mentorship:
            total_sessions = MentorshipSession.objects.filter(
                mentorship=mentorship
            ).count()
            completed_sessions = MentorshipSession.objects.filter(
                mentorship=mentorship,
                status='completed'
            ).count()
            upcoming_sessions = MentorshipSession.objects.filter(
                mentorship=mentorship,
                status='scheduled',
                scheduled_date__gte=now()
            ).count()
        
        data = {
            'success': True,
            'mentee_name': user.full_name,
            'department': user.department.name if user.department else None,
            'mentorship': {
                'has_mentor': has_mentorship,
                'mentor_name': mentor_name,
                'status': mentorship_status
            },
            'onboarding': {
                'total_modules': total_modules,
                'completed': completed_modules,
                'completion_rate': round((completed_modules / total_modules * 100), 2) if total_modules > 0 else 0
            },
            'sessions': {
                'total': total_sessions,
                'completed': completed_sessions,
                'upcoming': upcoming_sessions
            },
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Mentee Dashboard Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Mentee Dashboard Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating mentee dashboard: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mentee_onboarding_detail(request):
    """Detailed onboarding progress for mentee"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['mentee']):
            return Response({
                'success': False,
                'message': 'Permission denied. Mentee access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all onboarding progress
        progress_records = MenteeOnboardingProgress.objects.filter(
            mentee=user
        ).select_related('module')
        
        modules_data = []
        for progress in progress_records:
            # Get checklist progress
            total_checklist = OnboardingChecklist.objects.filter(
                module=progress.module
            ).count()
            completed_checklist = MenteeChecklistProgress.objects.filter(
                mentee=user,
                checklist_item__module=progress.module,
                is_completed=True
            ).count()
            
            modules_data.append({
                'module_id': progress.module.id,
                'module_title': progress.module.title,
                'module_type': progress.module.module_type,
                'description': progress.module.description,
                'status': progress.status,
                'progress_percentage': progress.progress_percentage,
                'started_at': progress.started_at,
                'completed_at': progress.completed_at,
                'due_date': progress.due_date,
                'is_overdue': progress.is_overdue(),
                'time_spent_minutes': progress.time_spent_minutes,
                'estimated_duration': progress.module.duration_minutes,
                'checklist': {
                    'total_items': total_checklist,
                    'completed_items': completed_checklist,
                    'completion_rate': round((completed_checklist / total_checklist * 100), 2) if total_checklist > 0 else 0
                }
            })
        
        data = {
            'success': True,
            'mentee_name': user.full_name,
            'department': user.department.name if user.department else None,
            'total_modules': len(modules_data),
            'modules': modules_data,
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Mentee Onboarding Detail Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Mentee Onboarding Detail Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating onboarding detail: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mentee_session_history(request):
    """Session history for mentee"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['mentee']):
            return Response({
                'success': False,
                'message': 'Permission denied. Mentee access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get mentorship - handle case where mentee has no active mentorship
        mentorship = None
        try:
            mentorship = Mentorship.objects.get(mentee=user, status='active')
        except Mentorship.DoesNotExist:
            # Return empty session history if no active mentorship
            print("\n" + "="*80)
            print("[REPORT LOG] ℹ️ Mentee has no active mentorship")
            print("="*80 + "\n")
            return Response({
                'success': True,
                'mentee_name': user.full_name,
                'has_mentorship': False,
                'mentor_name': None,
                'sessions': [],
                'total_sessions': 0,
                'completed_sessions': 0,
                'generated_at': now()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"\n[REPORT ERROR] ❌ Error fetching mentorship: {str(e)}\n")
            raise
        
        # Get all sessions for this mentorship
        sessions = MentorshipSession.objects.filter(
            mentorship=mentorship
        ).select_related('program', 'session_template').order_by('-scheduled_date')
        
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'session_id': session.id,
                'program_name': session.program.name if session.program else None,
                'session_number': session.program_session_number,
                'template_title': session.session_template.title if session.session_template else None,
                'status': session.status,
                'scheduled_date': session.scheduled_date,
                'actual_date': session.actual_date,
                'duration_minutes': session.duration_minutes,
                'agenda': session.agenda,
                'notes': session.notes,
                'mentor_feedback': session.mentor_feedback,
                'mentee_feedback': session.mentee_feedback,
                'meeting_link': session.meeting_link,
                'location': session.location
            })
        
        completed_count = sessions.filter(status='completed').count()
        
        data = {
            'success': True,
            'mentee_name': user.full_name,
            'has_mentorship': True,
            'mentor_name': mentorship.mentor.full_name,
            'sessions': sessions_data,
            'total_sessions': len(sessions_data),
            'completed_sessions': completed_count,
            'generated_at': now()
        }
        
        print("\n" + "="*80)
        print("[REPORT LOG] ✅ Mentee Session History Generated")
        print(f"Data: {data}")
        print("="*80 + "\n")
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Mentorship.DoesNotExist:
        # This should be caught above, but just in case
        return Response({
            'success': True,
            'mentee_name': user.full_name,
            'has_mentorship': False,
            'mentor_name': None,
            'sessions': [],
            'total_sessions': 0,
            'completed_sessions': 0,
            'generated_at': now()
        }, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print("\n" + "="*80)
        print(f"[REPORT LOG] ❌ ERROR: Error in mentee_session_history: {str(e)}")
        print(f"Traceback:\n{error_traceback}")
        print("="*80 + "\n")
        return Response({
            'success': False,
            'message': f'Error generating session history: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    






# reportApp/views.py - FIXED VERSION

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Count, Sum, Avg, F, Case, When, IntegerField
from django.utils.timezone import now
from datetime import timedelta, datetime, date
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import csv
import io
from django.http import HttpResponse
import pandas as pd
import traceback

from userApp.models import CustomUser
from departmentApp.models import Department
from onboarding.models import (
    OnboardingModule, MenteeOnboardingProgress,
    OnboardingChecklist, MenteeChecklistProgress
)
from mentorshipApp.models import (
    Mentorship, MentorshipSession, MentorshipProgram,
    MentorshipReview
)


# ==================== HELPER FUNCTIONS ====================
def check_role_permission(user, allowed_roles):
    """Check if user has required role permissions"""
    try:
        return user.role in allowed_roles if hasattr(user, 'role') else False
    except Exception as e:
        print(f"[PERMISSION ERROR] ❌ Role check failed: {str(e)}")
        return False


def log_report_generation(report_type, filters, record_count, user):
    """Log report generation details to terminal"""
    timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "="*100)
    print(f"[REPORT GENERATED] ✅")
    print(f"Timestamp: {timestamp}")
    print(f"Report Type: {report_type}")
    print(f"Generated By: {user.full_name} ({user.role})")
    print(f"Filters: {json.dumps(filters, indent=2, default=str)}")
    print(f"Records Found: {record_count}")
    print("="*100 + "\n")


def log_report_error(error_type, error_message, user=None, report_type=None):
    """Log report errors to terminal with detailed traceback"""
    timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "="*100)
    print(f"[{error_type}] ❌")
    print(f"Timestamp: {timestamp}")
    if user:
        print(f"User: {user.full_name} ({user.role})")
    if report_type:
        print(f"Report Type: {report_type}")
    print(f"Error: {error_message}")
    print("\nTraceback:")
    print("-"*50)
    traceback.print_exc()
    print("-"*50)
    print("="*100 + "\n")


def safe_date_format(date_value):
    """Safely format date/datetime to string"""
    if date_value is None:
        return ''
    if isinstance(date_value, str):
        return date_value
    if isinstance(date_value, (datetime, date)):
        return date_value.strftime('%Y-%m-%d')
    return str(date_value)


def safe_datetime_format(datetime_value):
    """Safely format datetime to string with time"""
    if datetime_value is None:
        return ''
    if isinstance(datetime_value, str):
        return datetime_value
    if isinstance(datetime_value, datetime):
        return datetime_value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(datetime_value, date):
        return datetime_value.strftime('%Y-%m-%d')
    return str(datetime_value)


def safe_float(value, default=0.0):
    """Safely convert value to float"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Safely convert value to int"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def validate_date_format(date_str, date_name):
    """Validate and parse date strings"""
    try:
        if not date_str:
            return None, None
        
        if isinstance(date_str, datetime):
            return date_str, None
        
        # Try multiple date formats
        date_formats = ['%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']
        
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, date_format)
                return parsed_date, None
            except ValueError:
                continue
        
        return None, f"Invalid {date_name} format: {date_str}. Use YYYY-MM-DD"
    
    except Exception as e:
        return None, f"Error parsing {date_name}: {str(e)}"


def validate_filters(filters, report_type):
    """Validate report filters"""
    validation_errors = []
    
    # Validate date filters
    start_date = filters.get('start_date')
    end_date = filters.get('end_date')
    
    if start_date or end_date:
        if start_date and not end_date:
            validation_errors.append("End date is required when start date is provided")
        elif end_date and not start_date:
            validation_errors.append("Start date is required when end date is provided")
        elif start_date and end_date:
            parsed_start, start_error = validate_date_format(start_date, 'start_date')
            parsed_end, end_error = validate_date_format(end_date, 'end_date')
            
            if start_error:
                validation_errors.append(start_error)
            if end_error:
                validation_errors.append(end_error)
            
            if parsed_start and parsed_end and parsed_start > parsed_end:
                validation_errors.append("Start date cannot be after end date")
    
    # Validate role filter
    role_filter = filters.get('role')
    valid_roles = ['admin', 'mentor', 'mentee', 'hr']
    if role_filter and role_filter not in valid_roles:
        validation_errors.append(f"Invalid role: {role_filter}. Valid roles: {', '.join(valid_roles)}")
    
    # Validate status filter
    status_filter = filters.get('status')
    if status_filter:
        if report_type == 'users':
            valid_statuses = ['pending', 'approved', 'rejected', 'active', 'inactive']
            if status_filter not in valid_statuses:
                validation_errors.append(f"Invalid user status: {status_filter}")
        elif report_type == 'mentorships':
            valid_statuses = ['pending', 'active', 'completed', 'paused', 'cancelled']
            if status_filter not in valid_statuses:
                validation_errors.append(f"Invalid mentorship status: {status_filter}")
    
    return validation_errors


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """Generate custom reports based on filters - FIXED VERSION"""
    try:
        user = request.user
        
        # Validate user permissions
        if not check_role_permission(user, ['admin', 'hr']):
            log_report_error("PERMISSION DENIED", 
                           f"User {user.full_name} does not have permission to generate reports", 
                           user)
            return Response({
                'success': False,
                'message': 'Permission denied. Admin or HR access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Validate request data
        if not request.data:
            log_report_error("INVALID REQUEST", "Request data is empty", user)
            return Response({
                'success': False,
                'message': 'Request data is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data
        report_type = data.get('report_type', 'users')
        filters = data.get('filters', {})
        
        # Validate report type
        valid_report_types = ['users', 'mentorships', 'departments', 'onboarding', 'sessions']
        if report_type not in valid_report_types:
            log_report_error("INVALID REPORT TYPE", 
                           f"Invalid report type: {report_type}", 
                           user, report_type)
            return Response({
                'success': False,
                'message': f'Invalid report type. Valid types: {", ".join(valid_report_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate filters
        filter_errors = validate_filters(filters, report_type)
        if filter_errors:
            log_report_error("FILTER VALIDATION ERROR", 
                           f"Filter validation failed: {filter_errors}", 
                           user, report_type)
            return Response({
                'success': False,
                'message': 'Filter validation errors',
                'errors': filter_errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse date filters
        start_date_str = filters.get('start_date')
        end_date_str = filters.get('end_date')
        start_date = None
        end_date = None
        
        if start_date_str:
            start_date, start_error = validate_date_format(start_date_str, 'start_date')
            if start_error:
                return Response({
                    'success': False,
                    'message': start_error
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if end_date_str:
            end_date, end_error = validate_date_format(end_date_str, 'end_date')
            if end_error:
                return Response({
                    'success': False,
                    'message': end_error
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if end_date:
                end_date = end_date.replace(hour=23, minute=59, second=59)
        
        # Initialize query filters
        query_filters = Q()
        
        # Apply date filters
        if start_date and end_date:
            query_filters &= Q(assigned_at__range=[start_date, end_date])
        elif start_date:
            query_filters &= Q(assigned_at__gte=start_date)
        elif end_date:
            query_filters &= Q(assigned_at__lte=end_date)
        
        # Apply role filter
        role_filter = filters.get('role')
        if role_filter:
            query_filters &= Q(role=role_filter)
        
        # Apply status filter
        status_filter = filters.get('status')
        if status_filter:
            if report_type == 'users':
                if status_filter in ['active', 'inactive']:
                    query_filters &= Q(availability_status=status_filter)
                else:
                    query_filters &= Q(status=status_filter)
            else:
                query_filters &= Q(status=status_filter)
        
        # Apply department filter
        department_filter = filters.get('department')
        if department_filter:
            if isinstance(department_filter, str):
                query_filters &= Q(department__name__icontains=department_filter)
            else:
                query_filters &= Q(department_id=department_filter)
        
        # Initialize report data and summary
        report_data = []
        summary = {}
        
        # Generate report based on type
        try:
            if report_type == 'users':
                users = CustomUser.objects.filter(query_filters).select_related('department')
                
                report_data = []
                for user_obj in users:
                    report_data.append({
                        'id': user_obj.id,
                        'full_name': user_obj.full_name or '',
                        'email': user_obj.email or '',
                        'phone_number': user_obj.phone_number or '',
                        'role': user_obj.role or '',
                        'status': user_obj.status or '',
                        'availability_status': user_obj.availability_status or '',
                        'department': user_obj.department.name if user_obj.department else 'N/A',
                        'work_mail_address': user_obj.work_mail_address or '',
                        'created_at': safe_datetime_format(user_obj.created_at),
                        'is_active': user_obj.is_active,
                        'is_staff': user_obj.is_staff
                    })
                
                summary = {
                    'total_users': users.count(),
                    'by_role': list(users.values('role').annotate(count=Count('id'))),
                    'by_status': list(users.values('status').annotate(count=Count('id'))),
                    'by_department': list(users.values('department__name').annotate(count=Count('id'))),
                    'active_count': users.filter(availability_status='active').count(),
                    'inactive_count': users.filter(availability_status='inactive').count(),
                    'staff_count': users.filter(is_staff=True).count()
                }
                
            elif report_type == 'mentorships':
                mentorships = Mentorship.objects.filter(query_filters).select_related(
                    'mentor', 'mentee', 'department', 'current_program'
                )
                
                report_data = []
                for mentorship in mentorships:
                    # Calculate progress safely
                    try:
                        progress_percentage = mentorship.get_progress_percentage()
                    except:
                        progress_percentage = 0
                    
                    try:
                        sessions_completed = mentorship.get_sessions_completed()
                    except:
                        sessions_completed = 0
                    
                    try:
                        total_sessions = mentorship.get_total_sessions()
                    except:
                        total_sessions = 0
                    
                    report_data.append({
                        'id': mentorship.id,
                        'mentor_name': mentorship.mentor.full_name or '',
                        'mentor_email': mentorship.mentor.email or '',
                        'mentee_name': mentorship.mentee.full_name or '',
                        'mentee_email': mentorship.mentee.email or '',
                        'department': mentorship.department.name or '',
                        'status': mentorship.status or '',
                        'start_date': safe_date_format(mentorship.start_date),
                        'expected_end_date': safe_date_format(mentorship.expected_end_date),
                        'actual_end_date': safe_date_format(mentorship.actual_end_date),
                        'progress_percentage': safe_float(progress_percentage),
                        'sessions_completed': safe_int(sessions_completed),
                        'total_sessions': safe_int(total_sessions),
                        'rating': safe_float(mentorship.rating),
                        'current_program': mentorship.current_program.name if mentorship.current_program else 'N/A',
                        'created_at': safe_datetime_format(mentorship.created_at)
                    })
                
                # Calculate average progress manually
                total_progress = 0
                progress_count = 0
                for m in mentorships:
                    try:
                        prog = m.get_progress_percentage()
                        if prog is not None:
                            total_progress += prog
                            progress_count += 1
                    except:
                        pass
                
                avg_progress = (total_progress / progress_count) if progress_count > 0 else 0
                
                summary = {
                    'total_mentorships': mentorships.count(),
                    'active': mentorships.filter(status='active').count(),
                    'completed': mentorships.filter(status='completed').count(),
                    'pending': mentorships.filter(status='pending').count(),
                    'cancelled': mentorships.filter(status='cancelled').count(),
                    'paused': mentorships.filter(status='paused').count(),
                    'average_rating': safe_float(mentorships.aggregate(avg=Avg('rating'))['avg']),
                    'average_progress': round(avg_progress, 2),
                    'by_department': list(mentorships.values('department__name').annotate(count=Count('id')))
                }
                
            elif report_type == 'departments':
                departments = Department.objects.filter(status='active')
                
                if department_filter:
                    if isinstance(department_filter, str):
                        departments = departments.filter(name__icontains=department_filter)
                    else:
                        departments = departments.filter(id=department_filter)
                
                report_data = []
                for dept in departments:
                    mentee_count = dept.users.filter(role='mentee').count()
                    mentor_count = dept.mentors.filter(role='mentor').count()
                    active_mentorships = Mentorship.objects.filter(
                        department=dept,
                        status='active'
                    ).count()
                    programs = dept.mentorship_programs.filter(status='active').count()
                    total_users = mentee_count + mentor_count
                    
                    report_data.append({
                        'id': dept.id,
                        'name': dept.name or '',
                        'description': dept.description or '',
                        'status': dept.status or '',
                        'mentee_count': mentee_count,
                        'mentor_count': mentor_count,
                        'total_users': total_users,
                        'active_mentorships': active_mentorships,
                        'programs': programs,
                        'utilization_rate': round((total_users / max(1, total_users)) * 100, 2) if total_users > 0 else 0,
                        'created_at': safe_datetime_format(dept.created_at),
                        'created_by': dept.created_by.full_name if dept.created_by else 'N/A'
                    })
                
                summary = {
                    'total_departments': departments.count(),
                    'total_mentees': sum(dept['mentee_count'] for dept in report_data),
                    'total_mentors': sum(dept['mentor_count'] for dept in report_data),
                    'total_active_mentorships': sum(dept['active_mentorships'] for dept in report_data),
                    'total_programs': sum(dept['programs'] for dept in report_data),
                    'average_utilization': round(sum(dept['utilization_rate'] for dept in report_data) / max(1, len(report_data)), 2)
                }
                
            elif report_type == 'onboarding':
                progress_records = MenteeOnboardingProgress.objects.filter(
                    query_filters
                ).select_related('mentee', 'module', 'assigned_by')
                
                report_data = []
                for progress in progress_records:
                    try:
                        is_overdue = progress.is_overdue()
                    except:
                        is_overdue = False
                    
                    report_data.append({
                        'id': progress.id,
                        'mentee_name': progress.mentee.full_name or '',
                        'mentee_email': progress.mentee.email or '',
                        'module_title': progress.module.title or '',
                        'module_type': progress.module.module_type or '',
                        'status': progress.status or '',
                        'progress_percentage': safe_int(progress.progress_percentage),
                        'started_at': safe_datetime_format(progress.started_at),
                        'completed_at': safe_datetime_format(progress.completed_at),
                        'due_date': safe_datetime_format(progress.due_date),
                        'is_overdue': is_overdue,
                        'time_spent_minutes': safe_int(progress.time_spent_minutes),
                        'assigned_by': progress.assigned_by.full_name if progress.assigned_by else 'N/A',
                        'assigned_at': safe_datetime_format(progress.assigned_at),
                        'last_updated': safe_datetime_format(progress.last_updated),
                        'notes': (progress.notes[:100] + '...') if progress.notes and len(progress.notes) > 100 else (progress.notes or '')
                    })
                
                summary = {
                    'total_records': progress_records.count(),
                    'completed': progress_records.filter(status='completed').count(),
                    'in_progress': progress_records.filter(status='in_progress').count(),
                    'not_started': progress_records.filter(status='not_started').count(),
                    'overdue': progress_records.filter(status='overdue').count(),
                    'needs_attention': progress_records.filter(status='needs_attention').count(),
                    'off_track': progress_records.filter(status='off_track').count(),
                    'paused': progress_records.filter(status='paused').count(),
                    'average_progress': safe_float(progress_records.aggregate(avg=Avg('progress_percentage'))['avg']),
                    'average_time_spent': safe_float(progress_records.aggregate(avg=Avg('time_spent_minutes'))['avg'])
                }
                
            elif report_type == 'sessions':
                sessions = MentorshipSession.objects.filter(query_filters).select_related(
                    'mentorship', 'mentorship__mentor', 'mentorship__mentee', 'program', 'session_template'
                )
                
                report_data = []
                for session in sessions:
                    report_data.append({
                        'id': session.id,
                        'mentor_name': session.mentorship.mentor.full_name or '',
                        'mentee_name': session.mentorship.mentee.full_name or '',
                        'program_name': session.program.name if session.program else 'N/A',
                        'session_template': session.session_template.title if session.session_template else 'N/A',
                        'session_number': safe_int(session.program_session_number),
                        'overall_session_number': safe_int(session.overall_session_number),
                        'status': session.status or '',
                        'scheduled_date': safe_datetime_format(session.scheduled_date),
                        'actual_date': safe_datetime_format(session.actual_date),
                        'duration_minutes': safe_int(session.duration_minutes),
                        'agenda': (session.agenda[:200] + '...') if session.agenda and len(session.agenda) > 200 else (session.agenda or ''),
                        'mentor_feedback': (session.mentor_feedback[:200] + '...') if session.mentor_feedback and len(session.mentor_feedback) > 200 else (session.mentor_feedback or ''),
                        'mentee_feedback': (session.mentee_feedback[:200] + '...') if session.mentee_feedback and len(session.mentee_feedback) > 200 else (session.mentee_feedback or ''),
                        'mentor_rating': safe_int(session.mentor_rating),
                        'meeting_link': session.meeting_link or '',
                        'location': session.location or '',
                        'created_at': safe_datetime_format(session.created_at)
                    })
                
                summary = {
                    'total_sessions': sessions.count(),
                    'completed': sessions.filter(status='completed').count(),
                    'scheduled': sessions.filter(status='scheduled').count(),
                    'cancelled': sessions.filter(status='cancelled').count(),
                    'rescheduled': sessions.filter(status='rescheduled').count(),
                    'no_show': sessions.filter(status='no_show').count(),
                    'average_duration': safe_float(sessions.aggregate(avg=Avg('duration_minutes'))['avg']),
                    'average_rating': safe_float(sessions.aggregate(avg=Avg('mentor_rating'))['avg']),
                    'completion_rate': round((sessions.filter(status='completed').count() / max(1, sessions.count())) * 100, 2),
                    'by_program': list(sessions.values('program__name').annotate(count=Count('id')))
                }
            
            # Prepare result
            result = {
                'success': True,
                'report_type': report_type,
                'filters': filters,
                'data': report_data,
                'summary': summary,
                'generated_at': safe_datetime_format(now()),
                'generated_by': user.full_name,
                'user_role': user.role,
                'records_count': len(report_data),
                'organization': 'BigTech Solutions Ltd (BTSL)',
                'system': 'Digital Mentorship System'
            }
            
            # Log successful generation
            log_report_generation(report_type, filters, len(report_data), user)
            
            # Print sample data to terminal
            if report_data:
                print("\n" + "="*80)
                print(f"SAMPLE DATA - First 3 records of {len(report_data)}:")
                print("="*80)
                for i, record in enumerate(report_data[:3]):
                    print(f"\nRecord {i+1}:")
                    for key, value in list(record.items())[:5]:
                        print(f"  {key}: {value}")
                if len(report_data) > 3:
                    print(f"\n... and {len(report_data) - 3} more records")
                print("="*80 + "\n")
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            log_report_error("DATA GENERATION ERROR", str(e), user, report_type)
            return Response({
                'success': False,
                'message': f'Error generating report data: {str(e)}',
                'report_type': report_type,
                'error_details': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        log_report_error("GENERAL REPORT ERROR", str(e), request.user if hasattr(request, 'user') else None)
        return Response({
            'success': False,
            'message': f'Unexpected error generating report: {str(e)}',
            'error_details': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_report(request):
    """Export report in various formats (PDF, Excel, CSV) - FIXED VERSION"""
    try:
        user = request.user
        
        # Validate user permissions
        if not check_role_permission(user, ['admin', 'hr']):
            log_report_error("EXPORT PERMISSION DENIED", 
                           f"User {user.full_name} does not have permission to export reports", 
                           user)
            return Response({
                'success': False,
                'message': 'Permission denied. Admin or HR access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Validate request data
        if not request.data:
            log_report_error("EXPORT INVALID REQUEST", "Export request data is empty", user)
            return Response({
                'success': False,
                'message': 'Export data is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data
        export_format = data.get('format', 'pdf')
        report_data = data.get('data', {})
        
        # Validate export format
        valid_formats = ['pdf', 'excel', 'csv']
        if export_format not in valid_formats:
            log_report_error("INVALID EXPORT FORMAT", 
                           f"Invalid export format: {export_format}", 
                           user)
            return Response({
                'success': False,
                'message': f'Invalid export format. Valid formats: {", ".join(valid_formats)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate report data structure
        if not report_data or not isinstance(report_data, dict):
            log_report_error("INVALID REPORT DATA", "Report data is missing or invalid", user)
            return Response({
                'success': False,
                'message': 'Invalid or missing report data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        report_type = report_data.get('report_type', 'users')
        report_summary = report_data.get('summary', {})
        records = report_data.get('data', [])
        filters = report_data.get('filters', {})
        
        if not isinstance(records, list):
            log_report_error("INVALID RECORDS DATA", "Records data must be a list", user, report_type)
            return Response({
                'success': False,
                'message': 'Invalid records data format'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log export attempt
        print("\n" + "="*80)
        print(f"[EXPORT STARTED] 📤")
        print(f"Format: {export_format.upper()}")
        print(f"Report Type: {report_type}")
        print(f"User: {user.full_name} ({user.role})")
        print(f"Records to export: {len(records)}")
        print("="*80 + "\n")
        
        timestamp = now().strftime('%Y%m%d_%H%M%S')
        filename = f"BTSL_Mentorship_{report_type}_{timestamp}"
        
        try:
            if export_format == 'pdf':
                return export_pdf_report(filename, report_type, report_summary, records, filters, user)
            elif export_format == 'excel':
                return export_excel_report(filename, report_type, report_summary, records, filters, user)
            elif export_format == 'csv':
                return export_csv_report(filename, report_type, report_summary, records, filters, user)
                
        except Exception as export_error:
            log_report_error("EXPORT PROCESSING ERROR", str(export_error), user, report_type)
            return Response({
                'success': False,
                'message': f'Error during export processing: {str(export_error)}',
                'error_details': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        log_report_error("EXPORT GENERAL ERROR", str(e), request.user if hasattr(request, 'user') else None)
        return Response({
            'success': False,
            'message': f'Unexpected error exporting report: {str(e)}',
            'error_details': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def export_pdf_report(filename, report_type, report_summary, records, filters, user):
    """Export report as PDF - FIXED VERSION"""
    try:
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        
        # Create styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            textColor=colors.HexColor('#1E40AF')
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=10,
            textColor=colors.HexColor('#4B5563')
        )
        
        normal_style = styles['Normal']
        
        # Build story
        story = []
        
        # Header
        story.append(Paragraph("BigTech Solutions Ltd (BTSL)", styles['Title']))
        story.append(Paragraph("Digital Mentorship System", subtitle_style))
        story.append(Paragraph("Confidential Report", subtitle_style))
        story.append(Spacer(1, 20))
        
        # Report Title
        title_map = {
            'users': 'User Registration Report',
            'mentorships': 'Mentorship Program Report',
            'departments': 'Department Activity Report',
            'onboarding': 'Onboarding Progress Report',
            'sessions': 'Session History Report'
        }
        
        story.append(Paragraph(title_map.get(report_type, 'System Report'), title_style))
        story.append(Spacer(1, 20))
        
        # Report Info
        info_text = f"""
        Generated on: {safe_datetime_format(now())}<br/>
        Generated by: {user.full_name}<br/>
        Report Type: {report_type.title()}<br/>
        Total Records: {len(records)}
        """
        story.append(Paragraph(info_text, normal_style))
        story.append(Spacer(1, 20))
        
        # Key Metrics
        if report_summary:
            story.append(Paragraph("Key Metrics", styles['Heading2']))
            
            metrics_data = []
            for key, value in report_summary.items():
                if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                    metrics_data.append([
                        key.replace('_', ' ').title(),
                        str(value)
                    ])
            
            if metrics_data:
                metrics_table = Table(metrics_data, colWidths=[200, 100])
                metrics_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey)
                ]))
                story.append(metrics_table)
                story.append(Spacer(1, 20))
        
        # Data Table (limited to first 100 records for PDF)
        if records:
            story.append(Paragraph(f"Detailed Data (First {min(100, len(records))} records)", styles['Heading2']))
            
            # Create table data with headers based on report type
            table_data = []
            
            if report_type == 'users':
                headers = ['Name', 'Email', 'Role', 'Status', 'Department']
                for record in records[:100]:  # Limit to 100 for PDF
                    table_data.append([
                        str(record.get('full_name', ''))[:20],
                        str(record.get('email', ''))[:30],
                        str(record.get('role', '')).title(),
                        str(record.get('status', '')).title(),
                        str(record.get('department', ''))[:20]
                    ])
            
            elif report_type == 'mentorships':
                headers = ['Mentor', 'Mentee', 'Department', 'Status', 'Progress']
                for record in records[:100]:
                    table_data.append([
                        str(record.get('mentor_name', ''))[:20],
                        str(record.get('mentee_name', ''))[:20],
                        str(record.get('department', ''))[:15],
                        str(record.get('status', '')).title(),
                        f"{record.get('progress_percentage', 0)}%"
                    ])
            
            elif report_type == 'departments':
                headers = ['Department', 'Mentees', 'Mentors', 'Mentorships', 'Programs']
                for record in records[:100]:
                    table_data.append([
                        str(record.get('name', ''))[:25],
                        str(record.get('mentee_count', 0)),
                        str(record.get('mentor_count', 0)),
                        str(record.get('active_mentorships', 0)),
                        str(record.get('programs', 0))
                    ])
            
            elif report_type == 'onboarding':
                headers = ['Mentee', 'Module', 'Status', 'Progress', 'Time Spent']
                for record in records[:100]:
                    table_data.append([
                        str(record.get('mentee_name', ''))[:20],
                        str(record.get('module_title', ''))[:20],
                        str(record.get('status', '')).title()[:10],
                        f"{record.get('progress_percentage', 0)}%",
                        f"{record.get('time_spent_minutes', 0)} min"
                    ])
            
            elif report_type == 'sessions':
                headers = ['Mentor', 'Mentee', 'Program', 'Status', 'Duration']
                for record in records[:100]:
                    table_data.append([
                        str(record.get('mentor_name', ''))[:20],
                        str(record.get('mentee_name', ''))[:20],
                        str(record.get('program_name', ''))[:15],
                        str(record.get('status', '')).title(),
                        f"{record.get('duration_minutes', 0)} min"
                    ])
            
            # Add headers to table data
            table_data.insert(0, headers)
            
            # Create table
            col_width = 500 / len(headers)
            table = Table(table_data, colWidths=[col_width] * len(headers))
            
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            
            story.append(table)
            
            if len(records) > 100:
                story.append(Spacer(1, 10))
                story.append(Paragraph(f"Note: Only first 100 of {len(records)} records shown. Download Excel/CSV for complete data.", normal_style))
        
        # Footer
        story.append(Spacer(1, 40))
        story.append(Paragraph("Confidential Information - BigTech Solutions Ltd", normal_style))
        story.append(Paragraph(f"Generated on: {safe_datetime_format(now())}", normal_style))
        
        # Build PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        
        response.write(pdf)
        
        print(f"[EXPORT SUCCESS] ✅ PDF exported: {filename}.pdf ({len(pdf)} bytes)")
        
        return response
        
    except Exception as e:
        log_report_error("PDF EXPORT ERROR", str(e), user, report_type)
        raise


def export_excel_report(filename, report_type, report_summary, records, filters, user):
    """Export report as Excel - FIXED VERSION"""
    try:
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
        
        # Convert records to DataFrame with safe handling
        df_records = []
        for record in records:
            clean_record = {}
            for key, value in record.items():
                # Handle different data types safely
                if isinstance(value, (datetime, date)):
                    clean_record[key] = safe_datetime_format(value)
                elif isinstance(value, bool):
                    clean_record[key] = 'Yes' if value else 'No'
                elif value is None:
                    clean_record[key] = ''
                else:
                    clean_record[key] = str(value)
            df_records.append(clean_record)
        
        df = pd.DataFrame(df_records)
        
        # Write to Excel with multiple sheets
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            # Data sheet
            if not df.empty:
                df.to_excel(writer, sheet_name='Data', index=False)
            
            # Summary sheet
            summary_data = []
            for key, value in report_summary.items():
                if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                    summary_data.append({
                        'Metric': key.replace('_', ' ').title(),
                        'Value': str(value)
                    })
            
            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Metadata sheet
            metadata = {
                'Organization': 'BigTech Solutions Ltd (BTSL)',
                'System': 'Digital Mentorship System',
                'Report Type': report_type.title(),
                'Generated By': user.full_name,
                'User Role': user.role,
                'Generated At': safe_datetime_format(now()),
                'Total Records': len(records),
                'Export Format': 'Excel'
            }
            metadata_df = pd.DataFrame(list(metadata.items()), columns=['Field', 'Value'])
            metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
        
        print(f"[EXPORT SUCCESS] ✅ Excel exported: {filename}.xlsx")
        
        return response
        
    except Exception as e:
        log_report_error("EXCEL EXPORT ERROR", str(e), user, report_type)
        raise


def export_csv_report(filename, report_type, report_summary, records, filters, user):
    """Export report as CSV - FIXED VERSION"""
    try:
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        # Add BOM for Excel compatibility
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Write metadata header
        writer.writerow(['BigTech Solutions Ltd (BTSL) - Digital Mentorship System'])
        writer.writerow(['Report Type:', report_type.title()])
        writer.writerow(['Generated By:', user.full_name])
        writer.writerow(['User Role:', user.role])
        writer.writerow(['Generated At:', safe_datetime_format(now())])
        writer.writerow(['Total Records:', len(records)])
        writer.writerow([])
        
        # Write summary
        writer.writerow(['SUMMARY'])
        for key, value in report_summary.items():
            if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                writer.writerow([key.replace('_', ' ').title(), str(value)])
        
        writer.writerow([])
        writer.writerow(['DETAILED DATA'])
        
        # Write data headers and rows
        if records:
            # Get all keys from first record
            headers = list(records[0].keys())
            writer.writerow(headers)
            
            # Write data rows
            for record in records:
                row = []
                for key in headers:
                    value = record.get(key, '')
                    # Convert values to string safely
                    if isinstance(value, (datetime, date)):
                        row.append(safe_datetime_format(value))
                    elif isinstance(value, bool):
                        row.append('Yes' if value else 'No')
                    elif value is None:
                        row.append('')
                    else:
                        # Remove commas and newlines for CSV
                        row.append(str(value).replace(',', ';').replace('\n', ' '))
                writer.writerow(row)
        
        print(f"[EXPORT SUCCESS] ✅ CSV exported: {filename}.csv")
        
        return response
        
    except Exception as e:
        log_report_error("CSV EXPORT ERROR", str(e), user, report_type)
        raise