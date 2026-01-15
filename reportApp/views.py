# reportApp/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q, Avg, Sum, F
from django.utils.timezone import now
from datetime import timedelta

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
    











# reportApp/views.py - Additional report endpoints

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Count, Sum, Avg
from django.utils.timezone import now
from datetime import timedelta, datetime
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import csv
import io
from django.http import HttpResponse
import pandas as pd

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    """Generate custom reports based on filters"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['admin', 'hr']):
            return Response({
                'success': False,
                'message': 'Permission denied. Admin or HR access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data
        report_type = data.get('report_type', 'users')
        filters = data.get('filters', {})
        
        start_date = filters.get('start_date')
        end_date = filters.get('end_date')
        role_filter = filters.get('role')
        status_filter = filters.get('status')
        department_filter = filters.get('department')
        
        report_data = None
        summary = {}
        
        # Build query filters
        query_filters = Q()
        
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query_filters &= Q(created_at__range=[start, end])
        
        if role_filter:
            query_filters &= Q(role=role_filter)
        
        if status_filter:
            query_filters &= Q(status=status_filter)
        
        if department_filter and report_type in ['users', 'mentorships']:
            query_filters &= Q(department__name=department_filter)
        
        if report_type == 'users':
            # Generate users report
            users = CustomUser.objects.filter(query_filters).select_related('department')
            
            report_data = []
            for user_obj in users:
                report_data.append({
                    'id': user_obj.id,
                    'full_name': user_obj.full_name,
                    'email': user_obj.email,
                    'phone_number': user_obj.phone_number,
                    'role': user_obj.role,
                    'status': user_obj.status,
                    'department': user_obj.department.name if user_obj.department else 'N/A',
                    'created_at': user_obj.created_at,
                    'is_active': user_obj.is_active
                })
            
            summary = {
                'total_users': users.count(),
                'by_role': users.values('role').annotate(count=Count('id')),
                'by_status': users.values('status').annotate(count=Count('id')),
                'by_department': users.values('department__name').annotate(count=Count('id')),
                'date_range': f"{start_date} to {end_date}" if start_date and end_date else "All time"
            }
        
        elif report_type == 'mentorships':
            # Generate mentorships report
            mentorships = Mentorship.objects.filter(query_filters).select_related(
                'mentor', 'mentee', 'department', 'current_program'
            )
            
            report_data = []
            for mentorship in mentorships:
                report_data.append({
                    'id': mentorship.id,
                    'mentor_name': mentorship.mentor.full_name,
                    'mentee_name': mentorship.mentee.full_name,
                    'department': mentorship.department.name,
                    'status': mentorship.status,
                    'start_date': mentorship.start_date,
                    'expected_end_date': mentorship.expected_end_date,
                    'actual_end_date': mentorship.actual_end_date,
                    'progress_percentage': mentorship.get_progress_percentage(),
                    'sessions_completed': mentorship.get_sessions_completed(),
                    'total_sessions': mentorship.get_total_sessions(),
                    'rating': mentorship.rating
                })
            
            summary = {
                'total_mentorships': mentorships.count(),
                'active': mentorships.filter(status='active').count(),
                'completed': mentorships.filter(status='completed').count(),
                'average_rating': mentorships.aggregate(avg=Avg('rating'))['avg'] or 0,
                'average_progress': mentorships.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
            }
        
        elif report_type == 'departments':
            # Generate departments report
            departments = Department.objects.filter(status='active')
            
            if department_filter:
                departments = departments.filter(name=department_filter)
            
            report_data = []
            for dept in departments:
                mentee_count = dept.users.filter(role='mentee').count()
                mentor_count = dept.mentors.filter(role='mentor').count()
                active_mentorships = Mentorship.objects.filter(
                    department=dept,
                    status='active'
                ).count()
                programs = dept.mentorship_programs.filter(status='active').count()
                
                report_data.append({
                    'id': dept.id,
                    'name': dept.name,
                    'description': dept.description,
                    'mentee_count': mentee_count,
                    'mentor_count': mentor_count,
                    'active_mentorships': active_mentorships,
                    'programs': programs,
                    'utilization_rate': round((mentee_count + mentor_count) / max(1, (mentee_count + mentor_count)) * 100, 2)
                })
            
            summary = {
                'total_departments': departments.count(),
                'total_mentees': sum(dept['mentee_count'] for dept in report_data),
                'total_mentors': sum(dept['mentor_count'] for dept in report_data),
                'total_active_mentorships': sum(dept['active_mentorships'] for dept in report_data),
                'average_utilization': round(sum(dept['utilization_rate'] for dept in report_data) / max(1, len(report_data)), 2)
            }
        
        elif report_type == 'onboarding':
            # Generate onboarding report
            progress_records = MenteeOnboardingProgress.objects.filter(
                query_filters
            ).select_related('mentee', 'module')
            
            report_data = []
            for progress in progress_records:
                report_data.append({
                    'id': progress.id,
                    'mentee_name': progress.mentee.full_name,
                    'module_title': progress.module.title,
                    'module_type': progress.module.module_type,
                    'status': progress.status,
                    'progress_percentage': progress.progress_percentage,
                    'started_at': progress.started_at,
                    'completed_at': progress.completed_at,
                    'due_date': progress.due_date,
                    'is_overdue': progress.is_overdue(),
                    'time_spent_minutes': progress.time_spent_minutes
                })
            
            summary = {
                'total_records': progress_records.count(),
                'completed': progress_records.filter(status='completed').count(),
                'in_progress': progress_records.filter(status='in_progress').count(),
                'not_started': progress_records.filter(status='not_started').count(),
                'overdue': progress_records.filter(due_date__lt=now(), status__in=['not_started', 'in_progress']).count(),
                'average_progress': progress_records.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
            }
        
        elif report_type == 'sessions':
            # Generate sessions report
            sessions = MentorshipSession.objects.filter(query_filters).select_related(
                'mentorship', 'mentorship__mentor', 'mentorship__mentee', 'program'
            )
            
            report_data = []
            for session in sessions:
                report_data.append({
                    'id': session.id,
                    'mentor_name': session.mentorship.mentor.full_name,
                    'mentee_name': session.mentorship.mentee.full_name,
                    'program_name': session.program.name if session.program else 'N/A',
                    'session_number': session.program_session_number,
                    'status': session.status,
                    'scheduled_date': session.scheduled_date,
                    'actual_date': session.actual_date,
                    'duration_minutes': session.duration_minutes,
                    'agenda': session.agenda,
                    'mentor_feedback': session.mentor_feedback,
                    'mentee_feedback': session.mentee_feedback
                })
            
            summary = {
                'total_sessions': sessions.count(),
                'completed': sessions.filter(status='completed').count(),
                'scheduled': sessions.filter(status='scheduled').count(),
                'cancelled': sessions.filter(status='cancelled').count(),
                'average_duration': sessions.aggregate(avg=Avg('duration_minutes'))['avg'] or 0,
                'completion_rate': round((sessions.filter(status='completed').count() / max(1, sessions.count())) * 100, 2)
            }
        
        result = {
            'success': True,
            'report_type': report_type,
            'filters': filters,
            'data': report_data,
            'summary': summary,
            'generated_at': now(),
            'generated_by': user.full_name,
            'organization': 'BigTech Solutions Ltd (BTSL)',
            'system': 'Digital Mentorship System'
        }
        
        print("\n" + "="*80)
        print(f"[REPORT LOG] ✅ Report Generated: {report_type}")
        print(f"Filters: {filters}")
        print(f"Records: {len(report_data) if report_data else 0}")
        print("="*80 + "\n")
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Report Generation Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error generating report: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_report(request):
    """Export report in various formats (PDF, Excel, CSV)"""
    try:
        user = request.user
        
        if not check_role_permission(user, ['admin', 'hr']):
            return Response({
                'success': False,
                'message': 'Permission denied. Admin or HR access required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data
        export_format = data.get('format', 'pdf')
        report_data = data.get('data', {})
        config = data.get('config', {})
        
        report_type = report_data.get('report_type', 'users')
        report_summary = report_data.get('summary', {})
        records = report_data.get('data', [])
        filters = report_data.get('filters', {})
        
        timestamp = now().strftime('%Y%m%d_%H%M%S')
        filename = f"BTSL_Mentorship_{report_type}_{timestamp}"
        
        if export_format == 'pdf':
            # Create PDF report
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
            
            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=6
            )
            
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
            
            # Report Summary
            story.append(Paragraph("Report Summary", styles['Heading2']))
            
            summary_text = f"""
            This report provides detailed analysis for the Digital Mentorship System at BigTech Solutions Ltd.
            Generated on: {now().strftime('%B %d, %Y at %I:%M %p')}
            Generated by: {user.full_name}
            Report Type: {report_type.title()}
            Date Range: {filters.get('start_date', 'All time')} to {filters.get('end_date', 'Present')}
            Total Records: {len(records)}
            """
            
            story.append(Paragraph(summary_text, normal_style))
            story.append(Spacer(1, 20))
            
            # Key Metrics
            if report_summary:
                story.append(Paragraph("Key Metrics", styles['Heading2']))
                
                metrics_data = []
                for key, value in report_summary.items():
                    if isinstance(value, (int, float, str)):
                        metrics_data.append([key.replace('_', ' ').title(), str(value)])
                
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
            
            # Data Table
            if records:
                story.append(Paragraph("Detailed Data", styles['Heading2']))
                
                # Create table data
                table_data = []
                
                # Add headers based on report type
                if report_type == 'users':
                    headers = ['Name', 'Email', 'Role', 'Status', 'Department', 'Created Date']
                    for record in records:
                        table_data.append([
                            record.get('full_name', ''),
                            record.get('email', ''),
                            record.get('role', '').title(),
                            record.get('status', '').title(),
                            record.get('department', ''),
                            record.get('created_at', '').strftime('%Y-%m-%d') if record.get('created_at') else ''
                        ])
                
                elif report_type == 'mentorships':
                    headers = ['Mentor', 'Mentee', 'Department', 'Status', 'Progress', 'Sessions']
                    for record in records:
                        table_data.append([
                            record.get('mentor_name', ''),
                            record.get('mentee_name', ''),
                            record.get('department', ''),
                            record.get('status', '').title(),
                            f"{record.get('progress_percentage', 0)}%",
                            f"{record.get('sessions_completed', 0)}/{record.get('total_sessions', 0)}"
                        ])
                
                elif report_type == 'departments':
                    headers = ['Department', 'Mentees', 'Mentors', 'Active Mentorships', 'Programs', 'Utilization']
                    for record in records:
                        table_data.append([
                            record.get('name', ''),
                            record.get('mentee_count', 0),
                            record.get('mentor_count', 0),
                            record.get('active_mentorships', 0),
                            record.get('programs', 0),
                            f"{record.get('utilization_rate', 0)}%"
                        ])
                
                else:
                    headers = ['ID', 'Details', 'Status', 'Date', 'Metrics']
                    for record in records:
                        table_data.append([
                            record.get('id', ''),
                            str(record)[:50],
                            record.get('status', '').title(),
                            record.get('created_at', '').strftime('%Y-%m-%d') if record.get('created_at') else '',
                            str(record.get('metrics', ''))
                        ])
                
                # Create table
                table_data.insert(0, headers)
                table = Table(table_data, colWidths=[100] * len(headers))
                
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                
                story.append(table)
            
            # Footer
            story.append(Spacer(1, 40))
            story.append(Paragraph("Confidential Information - BigTech Solutions Ltd", styles['Normal']))
            story.append(Paragraph(f"Generated on: {now().strftime('%B %d, %Y')}", styles['Normal']))
            story.append(Paragraph("Digital Mentorship System v2.0", styles['Normal']))
            
            # Build PDF
            doc.build(story)
            pdf = buffer.getvalue()
            buffer.close()
            
            response.write(pdf)
            return response
        
        elif export_format == 'excel':
            # Create Excel report
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            
            # Create DataFrame
            df = pd.DataFrame(records)
            
            # Write to Excel with multiple sheets
            with pd.ExcelWriter(response, engine='openpyxl') as writer:
                # Data sheet
                df.to_excel(writer, sheet_name='Data', index=False)
                
                # Summary sheet
                summary_df = pd.DataFrame([report_summary])
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Metadata sheet
                metadata = {
                    'Organization': 'BigTech Solutions Ltd (BTSL)',
                    'System': 'Digital Mentorship System',
                    'Report Type': report_type.title(),
                    'Generated By': user.full_name,
                    'Generated At': now().strftime('%Y-%m-%d %H:%M:%S'),
                    'Date Range': f"{filters.get('start_date', 'All time')} to {filters.get('end_date', 'Present')}",
                    'Total Records': len(records)
                }
                metadata_df = pd.DataFrame(list(metadata.items()), columns=['Field', 'Value'])
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
            
            return response
        
        elif export_format == 'csv':
            # Create CSV report
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
            
            writer = csv.writer(response)
            
            # Write metadata header
            writer.writerow(['BigTech Solutions Ltd (BTSL) - Digital Mentorship System'])
            writer.writerow(['Report Type:', report_type.title()])
            writer.writerow(['Generated By:', user.full_name])
            writer.writerow(['Generated At:', now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Date Range:', f"{filters.get('start_date', 'All time')} to {filters.get('end_date', 'Present')}"])
            writer.writerow([])
            
            # Write summary
            writer.writerow(['SUMMARY'])
            for key, value in report_summary.items():
                if isinstance(value, (int, float, str)):
                    writer.writerow([key.replace('_', ' ').title(), str(value)])
            
            writer.writerow([])
            writer.writerow(['DETAILED DATA'])
            
            # Write data headers
            if records:
                headers = list(records[0].keys())
                writer.writerow(headers)
                
                # Write data rows
                for record in records:
                    writer.writerow([record.get(key, '') for key in headers])
            
            return response
        
        else:
            return Response({
                'success': False,
                'message': 'Unsupported export format'
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        print(f"\n[REPORT ERROR] ❌ Export Error: {str(e)}\n")
        return Response({
            'success': False,
            'message': f'Error exporting report: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


