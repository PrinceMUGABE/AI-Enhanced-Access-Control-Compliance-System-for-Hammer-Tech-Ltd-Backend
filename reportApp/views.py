# reportApp/views.py - FINAL FIXED VERSION
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status  # Renamed to avoid conflict
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Q, Sum
from datetime import datetime, timedelta
from django.utils import timezone
import csv
import json
from io import StringIO, BytesIO
from django.http import HttpResponse
from django.db import connection
import logging


import csv
from io import StringIO, BytesIO
from datetime import datetime
from django.utils import timezone
from django.http import HttpResponse
import logging

# For PDF export - ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Import HTTP status constants
from rest_framework import status as http_status

# Import models
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department
from incidentApp.models import Incident
from complianceAuditApp.models import ComplianceAudit, ControlAssessment
from trainingApp.models import Training
from trainingCandidateApp.models import Candidate
from learningProgressApp.models import LearningProgress, ModuleCompletion
from complianceAuditApp.models import ComplianceStandard
from .serializers import ReportFilterSerializer

logger = logging.getLogger(__name__)


# ==================== BASE SERVICE ====================
class BaseDashboardService:
    """Base service class for dashboard data operations"""
    
    def __init__(self, user):
        self.user = user
        self.today = timezone.now()
    
    def get_date_range(self, timeframe='month', start_date=None, end_date=None):
        """Get date range based on timeframe or custom dates"""
        end_date = self.today
        
        if start_date and end_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            start_date = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        else:
            if timeframe == 'today':
                start_date = end_date - timedelta(days=1)
            elif timeframe == 'week':
                start_date = end_date - timedelta(weeks=1)
            elif timeframe == 'month':
                start_date = end_date - timedelta(days=30)
            elif timeframe == 'quarter':
                start_date = end_date - timedelta(days=90)
            elif timeframe == 'year':
                start_date = end_date - timedelta(days=365)
            else:  # Default to month
                start_date = end_date - timedelta(days=30)
        
        return start_date, end_date
    
    def get_department_filter_for_users(self, department_id=None):
        """Get department filter for users based on user role with debugging"""
        logger.info(f"get_department_filter_for_users - department_id: {department_id}, user_role: {self.user.role}")
        
        if department_id == '' or department_id is None:
            department_id = None
        
        # For users who can see all data
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            if department_id:
                filter_q = Q(department__id=department_id) | Q(departments__id=department_id)
                logger.info(f"  Admin/HR/Compliance with specific department: {department_id}")
                return filter_q
            logger.info(f"  Admin/HR/Compliance - No department filter (all data)")
            return Q()
        
        # For security analysts - only their assigned departments
        elif self.user.role == 'security_analyst':
            dept_ids = list(self.user.departments.values_list('id', flat=True))
            logger.info(f"  Security analyst - Assigned departments: {dept_ids}")
            
            if not dept_ids:
                logger.warning(f"  Security analyst has no departments assigned!")
                return Q(id__in=[])
            
            if department_id and department_id in dept_ids:
                filter_q = Q(department__id=department_id) | Q(departments__id=department_id)
                logger.info(f"  Filtering to specific department: {department_id}")
                return filter_q
            
            filter_q = Q(department__id__in=dept_ids) | Q(departments__id__in=dept_ids)
            logger.info(f"  Filtering to all assigned departments: {dept_ids}")
            return filter_q
        
        # For employees - only their own department
        elif self.user.role == 'employee':
            if self.user.department:
                if department_id and department_id == str(self.user.department.id):
                    filter_q = Q(department__id=self.user.department.id)
                    logger.info(f"  Employee - Own department: {self.user.department.id}")
                    return filter_q
                filter_q = Q(department__id=self.user.department.id)
                logger.info(f"  Employee - Own department (default): {self.user.department.id}")
                return filter_q
            else:
                logger.warning(f"  Employee has no department assigned!")
                return Q(id__in=[])
        
        logger.warning(f"  No filter for role: {self.user.role}")
        return Q()


    def get_department_filter_for_incidents(self, department_id=None):
        """Get department filter for incidents based on user role"""
        if department_id == '' or department_id is None:
            department_id = None
        
        # For users who can see all data
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            if department_id:
                return Q(department__id=department_id)
            return Q()
        
        # For security analysts - only their assigned departments
        elif self.user.role == 'security_analyst':
            dept_ids = list(self.user.departments.values_list('id', flat=True))
            if not dept_ids:
                return Q(id__in=[])
            
            if department_id and department_id in dept_ids:
                return Q(department__id=department_id)
            
            return Q(department__id__in=dept_ids)
        
        # For employees - only their own department
        elif self.user.role == 'employee':
            if self.user.department:
                if department_id and department_id == str(self.user.department.id):
                    return Q(department__id=self.user.department.id)
                return Q(department__id=self.user.department.id)
            else:
                return Q(id__in=[])
        
        return Q()
    
    def get_user_queryset(self, department_id=None):
        """Get filtered user queryset"""
        dept_filter = self.get_department_filter_for_users(department_id)
        
        qs = CustomUser.objects.filter(is_active=True)
        
        # Apply department filter
        if dept_filter:
            qs = qs.filter(dept_filter)
        
        return qs.distinct()
    
    def get_incident_queryset(self, start_date, end_date, department_id=None, incident_status=None, severity=None):
        """Get filtered incident queryset with debugging"""
        try:
            logger.info(f"get_incident_queryset - Start Date: {start_date}, End Date: {end_date}")
            
            dept_filter = self.get_department_filter_for_incidents(department_id)
            logger.info(f"Department filter: {dept_filter}")
            
            # Start with base queryset filtered by date
            qs = Incident.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            logger.info(f"After date filter: {qs.count()} incidents")
            
            # Log date range coverage
            if qs.exists():
                min_date = qs.earliest('created_at').created_at
                max_date = qs.latest('created_at').created_at
                logger.info(f"Date range coverage: {min_date} to {max_date}")
            else:
                # Check if there are any incidents outside the date range
                all_incidents = Incident.objects.count()
                if all_incidents > 0:
                    oldest = Incident.objects.earliest('created_at').created_at
                    newest = Incident.objects.latest('created_at').created_at
                    logger.warning(f"No incidents in date range {start_date} to {end_date}")
                    logger.info(f"But there are {all_incidents} incidents total, ranging from {oldest} to {newest}")
            
            # Apply department filter
            if dept_filter:
                before_count = qs.count()
                qs = qs.filter(dept_filter)
                after_count = qs.count()
                logger.info(f"After department filter: {after_count} incidents (was {before_count})")
            
            # Apply additional filters
            if incident_status:
                before_count = qs.count()
                qs = qs.filter(status=incident_status)
                after_count = qs.count()
                logger.info(f"After status filter ({incident_status}): {after_count} incidents (was {before_count})")
            
            if severity:
                before_count = qs.count()
                qs = qs.filter(severity=severity)
                after_count = qs.count()
                logger.info(f"After severity filter ({severity}): {after_count} incidents (was {before_count})")
            
            result = qs.distinct()
            logger.info(f"Final incident queryset count: {result.count()}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in get_incident_queryset: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return Incident.objects.none()
    
    
    
    def get_audit_queryset(self, start_date, end_date, department_id=None):
        """Get filtered audit queryset"""
        # For audits, check user's access to departments
        qs = ComplianceAudit.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        # Get accessible departments for user
        accessible_department_ids = self.get_accessible_department_ids(department_id)
        
        if accessible_department_ids:
            qs = qs.filter(departments__id__in=accessible_department_ids)
        else:
            # If no accessible departments, user can only see audits with no departments
            qs = qs.filter(departments__isnull=True)
        
        return qs.distinct()
    
    def get_accessible_department_ids(self, department_id=None):
        """Get list of department IDs that the user can access with debugging"""
        try:
            logger.info(f"get_accessible_department_ids called - department_id: {department_id}")
            logger.info(f"User role: {self.user.role}")
            
            if department_id and department_id != '':
                # Check if user can access this specific department
                can_access = self.can_access_department(department_id)
                logger.info(f"  Specific department {department_id} access: {can_access}")
                if can_access:
                    return [department_id]
                return []
            
            # Get all accessible departments
            if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
                dept_ids = list(Department.objects.filter(status='active').values_list('id', flat=True))
                logger.info(f"  Role {self.user.role} - All active departments: {dept_ids}")
                return dept_ids
                
            elif self.user.role == 'security_analyst':
                dept_ids = list(self.user.departments.filter(status='active').values_list('id', flat=True))
                logger.info(f"  Security analyst - Assigned departments: {dept_ids}")
                return dept_ids
                
            elif self.user.role == 'employee' and self.user.department:
                dept_ids = [self.user.department.id]
                logger.info(f"  Employee - Own department: {dept_ids}")
                return dept_ids
            
            logger.warning(f"  No accessible departments for role: {self.user.role}")
            return []
            
        except Exception as e:
            logger.error(f"Error in get_accessible_department_ids: {str(e)}")
            return []
    
    
    def can_access_department(self, department_id):
        """Check if user can access a specific department"""
        try:
            department = Department.objects.get(id=department_id, status='active')
            
            if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
                return True
            elif self.user.role == 'security_analyst':
                return self.user.departments.filter(id=department_id).exists()
            elif self.user.role == 'employee':
                return self.user.department and self.user.department.id == department_id
            
            return False
        except Department.DoesNotExist:
            return False


# ==================== DASHBOARD DATA SERVICE ====================
class DashboardDataService(BaseDashboardService):
    """Service for fetching real dashboard data from database"""
    
    def get_user_statistics(self, start_date, end_date, department_id=None):
        """Get user statistics from real database data"""
        user_qs = self.get_user_queryset(department_id)
        
        total_users = user_qs.count()
        active_users = user_qs.filter(availability_status='active').count()
        pending_users = user_qs.filter(status='pending').count()
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'pending_users': pending_users
        }
    
    def get_incident_statistics(self, start_date, end_date, department_id=None):
        """Get incident statistics from real database data"""
        incident_qs = self.get_incident_queryset(start_date, end_date, department_id)
        
        total_incidents = incident_qs.count()
        open_incidents = incident_qs.exclude(status__in=['resolved', 'closed']).count()
        critical_incidents = incident_qs.filter(severity__in=['critical', 'high']).count()
        
        return {
            'total_incidents': total_incidents,
            'open_incidents': open_incidents,
            'critical_incidents': critical_incidents
        }
    
    def get_audit_statistics(self, start_date, end_date, department_id=None):
        """Get audit statistics from real database data"""
        audit_qs = self.get_audit_queryset(start_date, end_date, department_id)
        
        total_audits = audit_qs.count()
        active_audits = audit_qs.filter(status='in_progress').count()
        
        # Calculate compliance score
        completed_audits = audit_qs.filter(status='completed', overall_score__isnull=False)
        if completed_audits.exists():
            avg_score = completed_audits.aggregate(Avg('overall_score'))['overall_score__avg'] or 100.0
        else:
            # Calculate from controls
            accessible_dept_ids = self.get_accessible_department_ids(department_id)
            if accessible_dept_ids:
                control_qs = ControlAssessment.objects.filter(
                    audit__departments__id__in=accessible_dept_ids,
                    audit__created_at__gte=start_date,
                    audit__created_at__lte=end_date
                )
            else:
                control_qs = ControlAssessment.objects.filter(
                    audit__departments__isnull=True,
                    audit__created_at__gte=start_date,
                    audit__created_at__lte=end_date
                )
            
            total_controls = control_qs.count()
            if total_controls > 0:
                compliant_controls = control_qs.filter(status='compliant').count()
                avg_score = (compliant_controls / total_controls) * 100
            else:
                avg_score = 100.0
        
        return {
            'total_audits': total_audits,
            'active_audits': active_audits,
            'completed_audits': audit_qs.filter(status='completed').count(),
            'compliance_score': round(avg_score, 2)
        }
    
    def get_training_statistics(self, department_id=None):
        """Get training statistics from real database data - FIXED VERSION"""
        user_qs = self.get_user_queryset(department_id)
        user_ids = user_qs.values_list('id', flat=True)
        
        # Get trainings for these users - Using correct relationship
        candidate_trainings = Candidate.objects.filter(
            learner__in=user_ids
        ).values_list('training_id', flat=True).distinct()
        
        trainings = Training.objects.filter(id__in=candidate_trainings)
        total_trainings = trainings.count()
        
        # Active candidates (candidates with pending status)
        active_candidates = Candidate.objects.filter(
            learner__in=user_ids,
            status='pending'
        ).count()
        
        return {
            'total_trainings': total_trainings,
            'active_candidates': active_candidates
        }
    
    def get_risk_score(self, start_date, end_date, department_id=None):
        """Calculate real risk score from incidents"""
        incident_qs = self.get_incident_queryset(start_date, end_date, department_id)
        
        severity_weights = {
            'critical': 1.0,
            'high': 0.75,
            'medium': 0.5,
            'low': 0.25
        }
        
        total_weight = 0
        incident_count = incident_qs.count()
        
        for incident in incident_qs:
            weight = severity_weights.get(incident.severity, 0.5)
            if incident.is_overdue:
                weight *= 1.5
            if incident.severity in ['critical', 'high'] and not incident.assigned_to:
                weight *= 1.3
            total_weight += weight
        
        if incident_count > 0:
            avg_weight = total_weight / incident_count
            risk_score = min(100, avg_weight * 100)
        else:
            risk_score = 0
        
        return round(risk_score, 2)
    
    def get_department_breakdown(self, start_date, end_date):
        """Get real department breakdown from database"""
        accessible_dept_ids = self.get_accessible_department_ids()
        departments = Department.objects.filter(id__in=accessible_dept_ids, status='active')
        
        breakdown = {}
        
        for dept in departments:
            # Get users in department
            dept_users = CustomUser.objects.filter(
                Q(department=dept) | Q(departments=dept),
                is_active=True
            ).distinct().count()
            
            # Get incidents for department
            dept_incidents = Incident.objects.filter(
                department=dept,
                created_at__gte=start_date,
                created_at__lte=end_date
            ).count()
            
            # Calculate department compliance score
            dept_audits = ComplianceAudit.objects.filter(
                departments=dept,
                status='completed'
            )
            
            if dept_audits.exists():
                dept_compliance = dept_audits.aggregate(
                    avg_score=Avg('overall_score')
                )['avg_score'] or 100.0
            else:
                dept_compliance = 100.0
            
            breakdown[dept.name] = {
                'user_count': dept_users,
                'incident_count': dept_incidents,
                'compliance_score': round(dept_compliance, 2)
            }
        
        return breakdown
    
    def get_access_trends(self, start_date, end_date, department_id=None, days=7, current_user=None):
        """Get real access trends from user logs with role-based filtering and detailed logging"""
        try:
            user_qs = self.get_user_queryset(department_id)
            user_ids = user_qs.values_list('id', flat=True)
            
            # Determine if the current user should only see their own logs
            only_self_logs = False
            if current_user and current_user.role in ['employee', 'compliance_officer']:
                only_self_logs = True
            
            # Build the query for authentication logs
            auth_logs = UserLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                user__in=user_ids,
                log_type='authentication'
            )
            
            # Apply role-based filtering
            if only_self_logs and current_user:
                auth_logs = auth_logs.filter(user=current_user)
            
            # Debug: Log the query counts
            logger.info(f"Total auth logs found: {auth_logs.count()}")
            logger.info(f"Login activities breakdown:")
            for activity in ['login', 'login_otp_verify', 'login_otp_request']:
                success_count = auth_logs.filter(activity=activity, is_success=True).count()
                fail_count = auth_logs.filter(activity=activity, is_success=False).count()
                logger.info(f"  {activity}: Success={success_count}, Failed={fail_count}")
            
            # Generate daily trends
            trends_data = []
            current_date = end_date - timedelta(days=days-1)
            
            while current_date <= end_date:
                date_start = timezone.make_aware(datetime.combine(current_date.date(), datetime.min.time()))
                date_end = timezone.make_aware(datetime.combine(current_date.date(), datetime.max.time()))
                
                date_logs = auth_logs.filter(
                    timestamp__gte=date_start,
                    timestamp__lte=date_end
                )
                
                # Detailed breakdown for each activity type
                login_verify_success = date_logs.filter(
                    activity='login_otp_verify',
                    is_success=True
                ).count()
                
                login_success = date_logs.filter(
                    activity='login',
                    is_success=True
                ).count()
                
                successful_logins = login_verify_success + login_success
                
                # Failed logins breakdown
                login_verify_failed = date_logs.filter(
                    activity='login_otp_verify',
                    is_success=False
                ).count()
                
                login_failed = date_logs.filter(
                    activity='login',
                    is_success=False
                ).count()
                
                otp_request_failed = date_logs.filter(
                    activity='login_otp_request',
                    is_success=False
                ).count()
                
                failed_logins = login_verify_failed + login_failed + otp_request_failed
                
                # Flagged activities (all unsuccessful)
                flagged_activities = date_logs.filter(is_success=False).count()
                
                # Optional: Add successful OTP requests
                successful_otp_requests = date_logs.filter(
                    activity='login_otp_request',
                    is_success=True
                ).count()
                
                trends_data.append({
                    'date': current_date.date(),
                    'successful_logins': successful_logins,
                    'failed_logins': failed_logins,
                    'flagged_activities': flagged_activities,
                    # Detailed breakdown for debugging
                    'breakdown': {
                        'login_verify_success': login_verify_success,
                        'login_success': login_success,
                        'login_verify_failed': login_verify_failed,
                        'login_failed': login_failed,
                        'otp_request_failed': otp_request_failed,
                        'successful_otp_requests': successful_otp_requests
                    }
                })
                
                current_date += timedelta(days=1)
            
            return trends_data
        except Exception as e:
            logger.error(f"Error getting access trends: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    
    def get_incident_trends(self, start_date, end_date, department_id=None, current_user=None, include_all_departments=False):
        """Get real incident trends with comprehensive role-based filtering and debugging"""
        try:
            # DEBUG: Log initial parameters
            logger.info("=" * 80)
            logger.info("INCIDENT TRENDS DEBUG - START")
            logger.info(f"Start Date: {start_date}")
            logger.info(f"End Date: {end_date}")
            logger.info(f"Department ID: {department_id}")
            logger.info(f"Current User: {current_user.email if current_user else 'None'}")
            logger.info(f"Current User Role: {current_user.role if current_user else 'None'}")
            logger.info(f"Include All Departments: {include_all_departments}")
            
            # Get base incident queryset
            incident_qs = self.get_incident_queryset(start_date, end_date, department_id)
            
            # DEBUG: Log base queryset count
            base_count = incident_qs.count()
            logger.info(f"Base incident queryset count (after date/department filter): {base_count}")
            
            # Log a few sample incidents from base queryset
            if base_count > 0:
                sample_incidents = incident_qs[:3]
                min_date = incident_qs.earliest('created_at').created_at.date()
                max_date = incident_qs.latest('created_at').created_at.date()
                logger.info(f"Incident date range in data: {min_date} to {max_date}")
                for idx, inc in enumerate(sample_incidents):
                    logger.info(f"Sample Incident {idx + 1}: ID={inc.id}, Number={inc.incident_number}, Created={inc.created_at.date()}")
            
            # Role-based filtering logic
            if current_user:
                logger.info(f"Applying role-based filtering for role: {current_user.role}")
                
                if current_user.role in ['employee', 'compliance_officer']:
                    before_count = incident_qs.count()
                    incident_qs = incident_qs.filter(
                        models.Q(created_by=current_user) | 
                        models.Q(assigned_to=current_user)
                    )
                    after_count = incident_qs.count()
                    logger.info(f"Employee/Compliance Officer filter: Before={before_count}, After={after_count}")
            
            # Final count after all filters
            final_count = incident_qs.count()
            logger.info(f"Final incident queryset count after all filters: {final_count}")
            
            # FIX: Calculate actual date range based on available data
            if final_count > 0:
                # Get the actual min and max dates from incidents
                actual_min_date = incident_qs.earliest('created_at').created_at.date()
                actual_max_date = incident_qs.latest('created_at').created_at.date()
                
                # Add padding before and after
                start_date_for_trends = actual_min_date - timedelta(days=2)
                end_date_for_trends = actual_max_date + timedelta(days=2)
                
                # Calculate days between
                days_between = (end_date_for_trends - start_date_for_trends).days
                days_count = min(15, max(7, days_between + 1))  # Between 7 and 15 days
                
                logger.info(f"Using dynamic date range based on incident data:")
                logger.info(f"  Actual min date: {actual_min_date}")
                logger.info(f"  Actual max date: {actual_max_date}")
                logger.info(f"  Trends start date: {start_date_for_trends}")
                logger.info(f"  Trends end date: {end_date_for_trends}")
                logger.info(f"  Days count: {days_count}")
            else:
                # Fallback to original date range if no incidents
                days_count = min(15, (end_date - start_date).days + 1)
                start_date_for_trends = start_date.date()
                end_date_for_trends = end_date.date()
                logger.warning(f"No incidents found, using fallback date range: {start_date_for_trends} to {end_date_for_trends}")
            
            # Generate daily trends
            trends_data = []
            current_date = start_date_for_trends
            
            while current_date <= end_date_for_trends:
                # Create datetime range for the day (with timezone)
                date_start = timezone.make_aware(datetime.combine(current_date, datetime.min.time()))
                date_end = timezone.make_aware(datetime.combine(current_date, datetime.max.time()))
                
                date_incidents = incident_qs.filter(
                    created_at__gte=date_start,
                    created_at__lte=date_end
                )
                
                total = date_incidents.count()
                
                # Log daily counts (only if > 0 to reduce noise)
                if total > 0:
                    logger.info(f"  Date {current_date}: {total} incidents found")
                    for inc in date_incidents:
                        logger.info(f"    - {inc.incident_number}: {inc.title[:50]} (Severity: {inc.severity})")
                
                # Status breakdown
                resolved_statuses = ['resolved', 'closed', 'completed', 'fixed', 'mitigated']
                in_progress_statuses = ['in_progress', 'investigating', 'analyzing', 'reviewing']
                pending_statuses = ['pending', 'open', 'new', 'reported', 'awaiting_response']
                
                resolved = date_incidents.filter(status__in=resolved_statuses).count()
                in_progress = date_incidents.filter(status__in=in_progress_statuses).count()
                pending = date_incidents.filter(status__in=pending_statuses).count()
                
                # Calculate average resolution time
                resolved_incidents = date_incidents.filter(
                    status__in=resolved_statuses,
                    resolved_at__isnull=False
                )
                
                avg_time = 0
                if resolved_incidents.exists():
                    from django.db.models import Avg, F, ExpressionWrapper, fields
                    
                    time_diff = ExpressionWrapper(
                        F('resolved_at') - F('created_at'),
                        output_field=fields.DurationField()
                    )
                    
                    avg_duration = resolved_incidents.annotate(
                        resolution_time=time_diff
                    ).aggregate(
                        avg_resolution=Avg('resolution_time')
                    )['avg_resolution']
                    
                    if avg_duration:
                        avg_time = avg_duration.total_seconds() / 3600  # Hours
                
                trends_data.append({
                    'date': current_date,
                    'total_incidents': total,
                    'resolved_incidents': resolved,
                    'in_progress_incidents': in_progress,
                    'pending_incidents': pending,
                    'average_resolution_time': round(avg_time, 2),
                    'resolution_rate': round((resolved / total * 100), 2) if total > 0 else 0,
                    'severity_breakdown': {
                        'high': date_incidents.filter(severity__in=['high', 'critical']).count(),
                        'medium': date_incidents.filter(severity='medium').count(),
                        'low': date_incidents.filter(severity='low').count()
                    }
                })
                
                current_date += timedelta(days=1)
            
            # Calculate non-zero entries for logging
            non_zero_entries = [d for d in trends_data if d['total_incidents'] > 0]
            logger.info(f"Generated {len(trends_data)} trend entries, {len(non_zero_entries)} have incidents")
            
            if non_zero_entries:
                logger.info(f"Dates with incidents: {[d['date'] for d in non_zero_entries]}")
            
            logger.info("INCIDENT TRENDS DEBUG - END")
            logger.info("=" * 80)
            
            return trends_data
            
        except Exception as e:
            logger.error(f"Error getting incident trends: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_department_performance(self, start_date, end_date):
        """Get real department performance metrics with debugging"""
        try:
            logger.info("=" * 80)
            logger.info("DEPARTMENT PERFORMANCE DEBUG - START")
            logger.info(f"Date Range: {start_date} to {end_date}")
            
            accessible_dept_ids = self.get_accessible_department_ids()
            logger.info(f"Accessible department IDs: {accessible_dept_ids}")
            
            departments = Department.objects.filter(id__in=accessible_dept_ids, status='active')
            logger.info(f"Found {departments.count()} active departments")
            
            # Log all departments for debugging
            for dept in departments:
                logger.info(f"  Department: ID={dept.id}, Name={dept.name}, Status={dept.status}")
            
            performance_data = []
            
            for dept in departments:
                logger.info(f"\n--- Processing Department: {dept.name} (ID: {dept.id}) ---")
                
                # Department users
                dept_users = CustomUser.objects.filter(
                    Q(department=dept) | Q(departments=dept),
                    is_active=True
                ).distinct()
                
                user_count = dept_users.count()
                logger.info(f"  Total users: {user_count}")
                
                # Log user details for debugging
                if user_count > 0:
                    user_emails = list(dept_users.values_list('email', flat=True)[:5])
                    logger.info(f"  Sample users: {user_emails}")
                
                # Department incidents
                dept_incidents = Incident.objects.filter(
                    department=dept,
                    created_at__gte=start_date,
                    created_at__lte=end_date
                )
                
                total_incidents = dept_incidents.count()
                active_incidents = dept_incidents.exclude(status__in=['resolved', 'closed']).count()
                logger.info(f"  Total incidents in date range: {total_incidents}")
                logger.info(f"  Active incidents: {active_incidents}")
                
                # Log incident details
                if total_incidents > 0:
                    for inc in dept_incidents[:3]:
                        logger.info(f"    Incident: {inc.incident_number}, Status={inc.status}, Severity={inc.severity}, Created={inc.created_at.date()}")
                
                # Department compliance score
                dept_audits = ComplianceAudit.objects.filter(
                    departments=dept,
                    status='completed'
                )
                
                dept_compliance = 100.0
                if dept_audits.exists():
                    audit_count = dept_audits.count()
                    avg_score = dept_audits.aggregate(avg_score=Avg('overall_score'))['avg_score']
                    if avg_score:
                        dept_compliance = avg_score
                    logger.info(f"  Audits found: {audit_count}, Average compliance score: {dept_compliance:.2f}%")
                else:
                    logger.info(f"  No completed audits found for this department, using default 100%")
                
                # Training completion rate
                user_ids = dept_users.values_list('id', flat=True)
                dept_candidates = Candidate.objects.filter(learner__in=user_ids)
                total_candidates = dept_candidates.count()
                
                completion_rate = 0
                if total_candidates > 0:
                    completed_candidates = dept_candidates.filter(status='completed').count()
                    completion_rate = (completed_candidates / total_candidates) * 100
                    logger.info(f"  Training stats: Total candidates={total_candidates}, Completed={completed_candidates}, Rate={completion_rate:.2f}%")
                else:
                    logger.info(f"  No training candidates found for this department")
                
                # Risk level based on incidents
                critical_incidents = dept_incidents.filter(severity='critical').count()
                high_incidents = dept_incidents.filter(severity='high').count()
                overdue_incidents = sum(1 for inc in dept_incidents if inc.is_overdue)
                
                if critical_incidents > 0 or overdue_incidents > 3:
                    risk_level = 'critical'
                elif high_incidents > 2 or overdue_incidents > 1:
                    risk_level = 'high'
                elif high_incidents > 0 or dept_incidents.count() > 5:
                    risk_level = 'medium'
                else:
                    risk_level = 'low'
                
                logger.info(f"  Risk assessment: Critical={critical_incidents}, High={high_incidents}, Overdue={overdue_incidents}, Risk Level={risk_level}")
                
                performance_entry = {
                    'department_id': dept.id,
                    'department_name': dept.name,
                    'total_users': user_count,
                    'active_incidents': active_incidents,
                    'compliance_score': round(dept_compliance, 2),
                    'training_completion_rate': round(completion_rate, 2),
                    'risk_level': risk_level
                }
                
                logger.info(f"  Final performance entry: {performance_entry}")
                performance_data.append(performance_entry)
            
            logger.info(f"\nTotal departments processed: {len(performance_data)}")
            logger.info("DEPARTMENT PERFORMANCE DEBUG - END")
            logger.info("=" * 80)
            
            return performance_data
            
        except Exception as e:
            logger.error(f"Error getting department performance: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    
    def get_recent_activities(self, start_date, end_date, department_id=None, limit=10, current_user=None):
        """Get real recent activities from user logs - with role-based filtering"""
        try:
            user_qs = self.get_user_queryset(department_id)
            user_ids = user_qs.values_list('id', flat=True)
            
            # Determine if the current user should only see their own logs
            only_self_logs = False
            if current_user and current_user.role in ['employee', 'compliance_officer']:
                only_self_logs = True
            
            # Build the query
            recent_logs_query = UserLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                user__in=user_ids
            )
            
            # Apply role-based filtering
            if only_self_logs and current_user:
                recent_logs_query = recent_logs_query.filter(user=current_user)
                logger.info(f"User {current_user.email} (role: {current_user.role}) viewing only their own logs")
            elif current_user:
                logger.info(f"User {current_user.email} (role: {current_user.role}) viewing all user logs")
            
            # Get the limited results
            recent_logs = recent_logs_query.order_by('-timestamp')[:limit]
            
            recent_activities = []
            
            for log in recent_logs:
                # Simple severity determination
                severity = 'low'
                if not log.is_success:
                    severity = 'high'
                elif 'fail' in log.activity or 'error' in log.activity:
                    severity = 'medium'
                
                description = log.description or ''
                if len(description) > 100:
                    description = description[:100] + '...'
                
                recent_activities.append({
                    'timestamp': log.timestamp,
                    'activity': log.get_activity_display() if hasattr(log, 'get_activity_display') else log.activity,
                    'description': description,
                    'user': log.user_email or 'System',
                    'severity': severity,
                    'category': log.get_log_type_display() if hasattr(log, 'get_log_type_display') else log.log_type
                })
            
            return recent_activities
        except Exception as e:
            logger.error(f"Error getting recent activities: {str(e)}")
            return []
    
    def get_system_health(self, start_date, end_date, current_user=None):
        """Get real system health metrics from database with role-based filtering"""
        try:
            # Determine if user should see limited system health data
            limited_access = False
            if current_user and current_user.role in ['employee', 'compliance_officer']:
                limited_access = True
            
            # 1. Authentication System Health
            auth_logs = UserLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                log_type='authentication'
            )
            
            # Apply role-based filtering for auth logs
            if limited_access and current_user:
                auth_logs = auth_logs.filter(user=current_user)
            
            total_auth = auth_logs.count()
            failed_auth = auth_logs.filter(is_success=False).count()
            auth_success_rate = ((total_auth - failed_auth) / total_auth * 100) if total_auth > 0 else 100
            
            # 2. Database Health
            db_status = 'Operational'
            db_latency = 0
            try:
                import time
                start_time = time.time()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    db_latency = (time.time() - start_time) * 1000  # Convert to milliseconds
                    db_status = 'Operational' if db_latency < 100 else 'Degraded'
            except Exception as e:
                db_status = 'Unavailable'
                logger.error(f"Database health check failed: {str(e)}")
            
            # 3. Incident Processing Health
            incident_qs = Incident.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            # Apply role-based filtering for incidents
            if limited_access and current_user:
                incident_qs = incident_qs.filter(
                    models.Q(created_by=current_user) | 
                    models.Q(assigned_to=current_user)
                )
            
            total_incidents = incident_qs.count()
            
            # Check for overdue incidents based on user role
            if limited_access:
                # For limited access users, only count their own overdue incidents
                overdue_incidents = incident_qs.filter(
                    status__in=['pending', 'investigating', 'assigned', 'in_progress'],
                    sla_due_date__lt=timezone.now()
                ).count()
            else:
                # For admin/HR/security analysts, count all overdue incidents
                overdue_incidents = Incident.objects.filter(
                    status__in=['pending', 'investigating', 'assigned', 'in_progress'],
                    sla_due_date__lt=timezone.now()
                ).count()
                
                # Also check critical overdue incidents (beyond SLA by more than 24 hours)
                critical_overdue = Incident.objects.filter(
                    status__in=['pending', 'investigating', 'assigned', 'in_progress'],
                    sla_due_date__lt=timezone.now() - timedelta(hours=24)
                ).count()
            
            # Determine incident status
            if limited_access:
                # For limited access users, show personal incident health
                if overdue_incidents > 2:
                    incident_status = 'Critical'
                elif overdue_incidents > 0:
                    incident_status = 'Warning'
                else:
                    incident_status = 'Healthy'
            else:
                # For full access users, show system-wide incident health
                if overdue_incidents > 5 or (total_incidents > 0 and overdue_incidents / total_incidents > 0.3):
                    incident_status = 'Critical'
                elif overdue_incidents > 2 or (total_incidents > 0 and overdue_incidents / total_incidents > 0.1):
                    incident_status = 'Warning'
                else:
                    incident_status = 'Healthy'
            
            # 4. API/Endpoint Health (optional)
            api_health = self._get_api_health(start_date, end_date, limited_access, current_user)
            
            # 5. User Activity Health
            user_activity_status = self._get_user_activity_health(start_date, end_date, limited_access, current_user)
            
            health_components = [
                {
                    'component': 'Authentication System',
                    'status': 'Operational' if auth_success_rate > 95 else 'Degraded' if auth_success_rate > 80 else 'Critical',
                    'uptime': round(auth_success_rate, 2),
                    'last_check': timezone.now(),
                    'issues': failed_auth,
                    'total_requests': total_auth,
                    'details': {
                        'success_rate': f"{auth_success_rate:.2f}%",
                        'failed_attempts': failed_auth,
                        'total_attempts': total_auth
                    }
                },
                {
                    'component': 'Database',
                    'status': db_status,
                    'uptime': 99.95 if db_status == 'Operational' else 99.5 if db_status == 'Degraded' else 95.0,
                    'last_check': timezone.now(),
                    'issues': 1 if db_status != 'Operational' else 0,
                    'details': {
                        'latency_ms': round(db_latency, 2),
                        'status': db_status
                    }
                },
                {
                    'component': 'Incident Management',
                    'status': incident_status,
                    'uptime': 100 - min(100, (overdue_incidents / max(total_incidents, 1) * 20)) if total_incidents > 0 else 100,
                    'last_check': timezone.now(),
                    'issues': overdue_incidents,
                    'details': {
                        'total_incidents': total_incidents,
                        'overdue_incidents': overdue_incidents,
                        'critical_overdue': critical_overdue if not limited_access else None,
                        'overdue_rate': round((overdue_incidents / max(total_incidents, 1)) * 100, 2) if total_incidents > 0 else 0
                    }
                }
            ]
            
            # Add API health if available
            if api_health:
                health_components.append(api_health)
            
            # Add user activity health
            if user_activity_status:
                health_components.append(user_activity_status)
            
            # Add overall system health summary for full access users
            if not limited_access:
                overall_status = self._calculate_overall_health(health_components)
                health_components.insert(0, overall_status)
            
            return health_components
        except Exception as e:
            logger.error(f"Error getting system health: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _get_api_health(self, start_date, end_date, limited_access=False, current_user=None):
        """Get API endpoint health metrics"""
        try:
            api_logs = UserLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date,
                endpoint__isnull=False
            )
            
            if limited_access and current_user:
                api_logs = api_logs.filter(user=current_user)
            
            total_api_calls = api_logs.count()
            failed_api_calls = api_logs.filter(status_code__gte=400).count() if total_api_calls > 0 else 0
            avg_response_time = api_logs.exclude(duration__isnull=True).aggregate(
                avg_duration=Avg('duration')
            )['avg_duration']
            
            api_success_rate = ((total_api_calls - failed_api_calls) / total_api_calls * 100) if total_api_calls > 0 else 100
            
            status = 'Operational'
            if api_success_rate < 90:
                status = 'Critical'
            elif api_success_rate < 95:
                status = 'Degraded'
            
            # Convert timedelta to milliseconds safely
            avg_response_time_ms = 0
            if avg_response_time:
                if hasattr(avg_response_time, 'total_seconds'):
                    # It's a timedelta object
                    avg_response_time_ms = avg_response_time.total_seconds() * 1000
                else:
                    # It's already a number (float/int)
                    avg_response_time_ms = float(avg_response_time) * 1000
            
            return {
                'component': 'API Endpoints',
                'status': status,
                'uptime': round(api_success_rate, 2),
                'last_check': timezone.now(),
                'issues': failed_api_calls,
                'details': {
                    'total_calls': total_api_calls,
                    'failed_calls': failed_api_calls,
                    'avg_response_time_ms': round(avg_response_time_ms, 2),
                    'success_rate': f"{api_success_rate:.2f}%"
                }
            }
        except Exception as e:
            logger.error(f"Error getting API health: {str(e)}")
            return None

    def _get_user_activity_health(self, start_date, end_date, limited_access=False, current_user=None):
        """Get user activity health metrics"""
        try:
            activity_logs = UserLog.objects.filter(
                timestamp__gte=start_date,
                timestamp__lte=end_date
            )
            
            if limited_access and current_user:
                activity_logs = activity_logs.filter(user=current_user)
            
            total_activities = activity_logs.count()
            
            # Calculate unique active users
            active_users = activity_logs.values('user').distinct().count() if not limited_access else 1
            
            # Calculate activity rate (activities per hour)
            hours = (end_date - start_date).total_seconds() / 3600
            activity_rate = total_activities / hours if hours > 0 else 0
            
            status = 'Healthy'
            if activity_rate < 1:  # Less than 1 activity per hour
                status = 'Low Activity'
            elif activity_rate > 100:  # More than 100 activities per hour
                status = 'High Activity'
            
            return {
                'component': 'User Activity',
                'status': status,
                'uptime': 99.9 if activity_rate > 0 else 95.0,
                'last_check': timezone.now(),
                'issues': 0 if activity_rate > 0 else 1,
                'details': {
                    'total_activities': total_activities,
                    'active_users': active_users,
                    'activity_rate_per_hour': round(activity_rate, 2),
                    'time_range': f"{start_date.date()} to {end_date.date()}"
                }
            }
        except Exception as e:
            logger.error(f"Error getting user activity health: {str(e)}")
            return None

    def _calculate_overall_health(self, health_components):
        """Calculate overall system health based on individual components"""
        try:
            if not health_components:
                return None
            
            # Define weights for each component
            weights = {
                'Authentication System': 0.3,
                'Database': 0.3,
                'Incident Management': 0.25,
                'API Endpoints': 0.1,
                'User Activity': 0.05
            }
            
            total_score = 0
            total_weight = 0
            
            for component in health_components:
                name = component['component']
                weight = weights.get(name, 0.1)
                
                # Convert status to score
                status_score = {
                    'Operational': 100,
                    'Healthy': 100,
                    'Degraded': 60,
                    'Warning': 50,
                    'Critical': 30,
                    'Unavailable': 0,
                    'Low Activity': 80,
                    'High Activity': 90
                }.get(component['status'], 50)
                
                total_score += (status_score * weight)
                total_weight += weight
            
            overall_score = total_score / total_weight if total_weight > 0 else 0
            
            # Determine overall status
            if overall_score >= 90:
                overall_status = 'Healthy'
            elif overall_score >= 70:
                overall_status = 'Degraded'
            elif overall_score >= 50:
                overall_status = 'Warning'
            else:
                overall_status = 'Critical'
            
            return {
                'component': 'Overall System Health',
                'status': overall_status,
                'uptime': round(overall_score, 2),
                'last_check': timezone.now(),
                'issues': sum(c.get('issues', 0) for c in health_components),
                'details': {
                    'component_count': len(health_components),
                    'average_score': round(overall_score, 2),
                    'component_breakdown': [
                        {
                            'name': c['component'],
                            'status': c['status'],
                            'score': c['uptime']
                        } for c in health_components
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Error calculating overall health: {str(e)}")
            return None
        
        
    def get_training_progress(self, department_id=None, current_user=None):
        """Get training progress data with role-based filtering and detailed analytics"""
        try:
            # Determine access level based on user role
            limited_access = False
            if current_user and current_user.role in ['employee', 'compliance_officer']:
                limited_access = True
            
            # Get base user queryset
            user_qs = self.get_user_queryset(department_id)
            user_ids = user_qs.values_list('id', flat=True)
            
            if limited_access:
                # For employees/compliance officers: get their own trainings
                candidates = Candidate.objects.filter(learner=current_user)
                trainings = Training.objects.filter(
                    id__in=candidates.values_list('training_id', flat=True)
                ).distinct()
                
                progress_data = []
                
                for training in trainings:
                    # Get the specific candidate for this training
                    candidate = candidates.filter(training=training).first()
                    if not candidate:
                        continue
                    
                    # Get learning progress
                    learning_progress = LearningProgress.objects.filter(
                        candidate=candidate,
                        training=training
                    ).first()
                    
                    if learning_progress:
                        total_modules = learning_progress.total_modules
                        completed_modules = learning_progress.completed_modules
                        progress_percentage = float(learning_progress.progress_percentage)
                        
                        # Get module completion details
                        module_completions = ModuleCompletion.objects.filter(
                            learning_progress=learning_progress
                        ).select_related('module')
                        
                        completed_modules_list = []
                        in_progress_modules_list = []
                        
                        for module_completion in module_completions:
                            module_data = {
                                'module_id': module_completion.module.id,
                                'module_name': module_completion.module.name,
                                'is_completed': module_completion.is_completed,
                                'completed_at': module_completion.completed_at,
                                'time_spent_minutes': module_completion.time_spent_minutes
                            }
                            
                            if module_completion.is_completed:
                                completed_modules_list.append(module_data)
                            else:
                                in_progress_modules_list.append(module_data)
                        
                        # Calculate average time per module
                        avg_time_per_module = 0
                        if completed_modules > 0:
                            total_time = sum(
                                mc.time_spent_minutes for mc in module_completions if mc.is_completed
                            )
                            avg_time_per_module = total_time / completed_modules
                        
                        # Determine status
                        if progress_percentage == 100:
                            status = 'completed'
                        elif progress_percentage > 0:
                            status = 'in_progress'
                        else:
                            status = 'not_started'
                        
                        progress_data.append({
                            'training_id': training.id,
                            'training_name': training.name,
                            'training_description': training.description,
                            'status': status,
                            'progress_percentage': progress_percentage,
                            'total_modules': total_modules,
                            'completed_modules': completed_modules,
                            'remaining_modules': total_modules - completed_modules,
                            'average_time_per_module_hours': round(avg_time_per_module / 60, 2),
                            'last_activity': learning_progress.last_activity,
                            'started_at': learning_progress.started_at,
                            'estimated_completion_date': learning_progress.estimated_completion_date,
                            'module_details': {
                                'completed': completed_modules_list,
                                'in_progress': in_progress_modules_list[:3]  # Show first 3 in-progress modules
                            }
                        })
                    else:
                        # No progress yet
                        progress_data.append({
                            'training_id': training.id,
                            'training_name': training.name,
                            'training_description': training.description,
                            'status': 'not_started',
                            'progress_percentage': 0,
                            'total_modules': training.modules.count(),
                            'completed_modules': 0,
                            'remaining_modules': training.modules.count(),
                            'average_time_per_module_hours': 0,
                            'last_activity': None,
                            'started_at': None,
                            'estimated_completion_date': None,
                            'module_details': {
                                'completed': [],
                                'in_progress': []
                            }
                        })
                
                # Calculate overall statistics for the user
                if progress_data:
                    overall_stats = {
                        'total_trainings': len(progress_data),
                        'completed_trainings': sum(1 for p in progress_data if p['status'] == 'completed'),
                        'in_progress_trainings': sum(1 for p in progress_data if p['status'] == 'in_progress'),
                        'not_started_trainings': sum(1 for p in progress_data if p['status'] == 'not_started'),
                        'average_progress': round(sum(p['progress_percentage'] for p in progress_data) / len(progress_data), 2),
                        'total_modules_completed': sum(p['completed_modules'] for p in progress_data),
                        'total_modules': sum(p['total_modules'] for p in progress_data)
                    }
                    
                    return {
                        'user_progress': progress_data,
                        'overall_stats': overall_stats
                    }
                
                return {
                    'user_progress': [],
                    'overall_stats': {
                        'total_trainings': 0,
                        'completed_trainings': 0,
                        'in_progress_trainings': 0,
                        'not_started_trainings': 0,
                        'average_progress': 0,
                        'total_modules_completed': 0,
                        'total_modules': 0
                    }
                }
            
            else:
                # For admin, HR managers, security analysts: get all trainings with candidate statistics
                # Get all trainings that have candidates from the filtered users
                candidate_trainings = Candidate.objects.filter(
                    learner__in=user_ids
                ).values_list('training_id', flat=True).distinct()
                
                trainings = Training.objects.filter(id__in=candidate_trainings).order_by('-created_at')
                
                progress_data = []
                
                for training in trainings:
                    # Get all candidates for this training
                    candidates = Candidate.objects.filter(training=training, learner__in=user_ids)
                    
                    total_candidates = candidates.count()
                    
                    if total_candidates == 0:
                        continue
                    
                    # Get learning progress for all candidates
                    learning_progresses = LearningProgress.objects.filter(
                        candidate__in=candidates,
                        training=training
                    ).select_related('candidate__learner')
                    
                    # Calculate statistics
                    completed_candidates = 0
                    in_progress_candidates = 0
                    not_started_candidates = 0
                    
                    progress_percentages = []
                    total_completed_modules = 0
                    total_modules_count = 0
                    
                    for candidate in candidates:
                        progress = learning_progresses.filter(candidate=candidate).first()
                        
                        if progress:
                            progress_percentage = float(progress.progress_percentage)
                            progress_percentages.append(progress_percentage)
                            
                            if progress_percentage == 100:
                                completed_candidates += 1
                            elif progress_percentage > 0:
                                in_progress_candidates += 1
                            else:
                                not_started_candidates += 1
                            
                            total_completed_modules += progress.completed_modules
                            total_modules_count += progress.total_modules
                        else:
                            not_started_candidates += 1
                            progress_percentages.append(0)
                    
                    # Calculate averages
                    average_progress = sum(progress_percentages) / total_candidates if total_candidates > 0 else 0
                    average_modules_completed = total_completed_modules / total_candidates if total_candidates > 0 else 0
                    
                    # Calculate completion rate
                    completion_rate = (completed_candidates / total_candidates * 100) if total_candidates > 0 else 0
                    
                    # Get top performers (candidates with highest progress)
                    top_performers = []
                    if learning_progresses.exists():
                        top_progress = learning_progresses.order_by('-progress_percentage')[:5]
                        for progress in top_progress:
                            top_performers.append({
                                'candidate_name': progress.candidate.learner.full_name,
                                'candidate_email': progress.candidate.learner.email,
                                'progress_percentage': float(progress.progress_percentage),
                                'completed_modules': progress.completed_modules,
                                'total_modules': progress.total_modules
                            })
                    
                    # Get at-risk candidates (low progress)
                    at_risk_candidates = []
                    at_risk_progress = learning_progresses.filter(
                        progress_percentage__lt=30,
                        progress_percentage__gt=0
                    ).order_by('progress_percentage')[:5]
                    
                    for progress in at_risk_progress:
                        at_risk_candidates.append({
                            'candidate_name': progress.candidate.learner.full_name,
                            'candidate_email': progress.candidate.learner.email,
                            'progress_percentage': float(progress.progress_percentage),
                            'completed_modules': progress.completed_modules,
                            'total_modules': progress.total_modules,
                            'last_activity': progress.last_activity
                        })
                    
                    progress_data.append({
                        'training_id': training.id,
                        'training_name': training.name,
                        'training_description': training.description,
                        'total_candidates': total_candidates,
                        'completed_candidates': completed_candidates,
                        'in_progress_candidates': in_progress_candidates,
                        'not_started_candidates': not_started_candidates,
                        'completion_rate': round(completion_rate, 2),
                        'average_progress': round(average_progress, 2),
                        'average_modules_completed': round(average_modules_completed, 2),
                        'total_modules_count': training.modules.count(),
                        'total_completed_modules_across_candidates': total_completed_modules,
                        'top_performers': top_performers,
                        'at_risk_candidates': at_risk_candidates,
                        'created_at': training.created_at
                    })
                
                # Calculate overall organizational statistics
                if progress_data:
                    overall_stats = {
                        'total_trainings': len(progress_data),
                        'total_candidates': sum(p['total_candidates'] for p in progress_data),
                        'total_completed_candidates': sum(p['completed_candidates'] for p in progress_data),
                        'total_in_progress_candidates': sum(p['in_progress_candidates'] for p in progress_data),
                        'overall_completion_rate': round(
                            sum(p['completed_candidates'] for p in progress_data) / 
                            sum(p['total_candidates'] for p in progress_data) * 100 
                            if sum(p['total_candidates'] for p in progress_data) > 0 else 0, 2
                        ),
                        'average_training_progress': round(
                            sum(p['average_progress'] for p in progress_data) / len(progress_data), 2
                        ),
                        'best_performing_training': max(progress_data, key=lambda x: x['completion_rate'])['training_name'] if progress_data else None,
                        'worst_performing_training': min(progress_data, key=lambda x: x['completion_rate'])['training_name'] if progress_data else None
                    }
                    
                    return {
                        'trainings_progress': progress_data,
                        'overall_stats': overall_stats
                    }
                
                return {
                    'trainings_progress': [],
                    'overall_stats': {
                        'total_trainings': 0,
                        'total_candidates': 0,
                        'total_completed_candidates': 0,
                        'total_in_progress_candidates': 0,
                        'overall_completion_rate': 0,
                        'average_training_progress': 0,
                        'best_performing_training': None,
                        'worst_performing_training': None
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting training progress: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'error': str(e),
                'trainings_progress': [],
                'overall_stats': {}
            } if not limited_access else {
                'error': str(e),
                'user_progress': [],
                'overall_stats': {}
            }
      
        
    def get_risk_distribution(self, start_date, end_date, department_id=None):
            """Get real risk distribution from incidents"""
            try:
                incident_qs = self.get_incident_queryset(start_date, end_date, department_id)
                
                severity_counts = incident_qs.values('severity').annotate(
                    count=Count('id')
                ).order_by('severity')
                
                total_incidents = incident_qs.count()
                
                risk_distribution = []
                
                for item in severity_counts:
                    percentage = (item['count'] / total_incidents * 100) if total_incidents > 0 else 0
                    
                    risk_distribution.append({
                        'risk_level': item['severity'],
                        'count': item['count'],
                        'percentage': round(percentage, 2),
                        'departments': []
                    })
                
                return risk_distribution
            except Exception as e:
                logger.error(f"Error getting risk distribution: {str(e)}")
                return []
        
    def get_user_activities(self, start_date, end_date, department_id=None):
            """Get real user activity data - SIMPLIFIED"""
            try:
                if self.user.role not in ['admin', 'hr_manager', 'security_analyst', 'compliance_officer']:
                    return []
                
                user_qs = self.get_user_queryset(department_id)
                
                user_activities = []
                
                for user in user_qs[:10]:  # Limit to 10 users
                    user_logs = UserLog.objects.filter(
                        user=user,
                        timestamp__gte=start_date,
                        timestamp__lte=end_date
                    )
                    
                    last_log = user_logs.order_by('-timestamp').first()
                    last_activity = last_log.timestamp if last_log else user.created_at
                    
                    user_activities.append({
                        'user_id': user.id,
                        'user_name': user.full_name,
                        'user_email': user.email,
                        'role': user.get_role_display() if hasattr(user, 'get_role_display') else user.role,
                        'last_activity': last_activity,
                        'total_activities': user_logs.count(),
                        'flagged_activities': user_logs.filter(is_success=False).count()
                    })
                
                # Sort by last activity
                return sorted(user_activities, key=lambda x: x['last_activity'], reverse=True)
            except Exception as e:
                logger.error(f"Error getting user activities: {str(e)}")
                return []


# ==================== API VIEWS ====================
class RoleBasedDashboardView(APIView):
    """
    Main dashboard endpoint with real data from database
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            filters = request.GET.dict()
            
            # DEBUG: Log request
            logger.info("=" * 80)
            logger.info("DASHBOARD API CALL")
            logger.info(f"User: {user.email} (Role: {user.role})")
            logger.info(f"Request filters: {filters}")
            
            # Parse filters
            timeframe = filters.get('timeframe', 'month')
            start_date_str = filters.get('start_date')
            end_date_str = filters.get('end_date')
            department_id = filters.get('department')
            incident_status = filters.get('status')
            severity = filters.get('severity')
            
            # Convert department_id
            if department_id and department_id.isdigit():
                department_id = int(department_id)
            elif department_id == '':
                department_id = None
            
            # Initialize data service
            data_service = DashboardDataService(user)
            
            # DEBUG: Check department data availability
            logger.info("=" * 40)
            logger.info("CHECKING DEPARTMENT DATA AVAILABILITY")
            all_depts = Department.objects.filter(status='active')
            logger.info(f"Total active departments in system: {all_depts.count()}")
            
            for dept in all_depts:
                logger.info(f"  Dept: {dept.name} (ID: {dept.id})")
                
                # Check users in department
                users_in_dept = CustomUser.objects.filter(
                    Q(department=dept) | Q(departments=dept),
                    is_active=True
                ).distinct().count()
                logger.info(f"    Users: {users_in_dept}")
                
                # Check incidents in department
                incidents_in_dept = Incident.objects.filter(department=dept).count()
                logger.info(f"    Incidents: {incidents_in_dept}")
                
                # Check if department has any audits
                audits_in_dept = ComplianceAudit.objects.filter(departments=dept).count()
                logger.info(f"    Audits: {audits_in_dept}")
                
                # Check training candidates in department
                user_ids = CustomUser.objects.filter(
                    Q(department=dept) | Q(departments=dept),
                    is_active=True
                ).values_list('id', flat=True).distinct()
                candidates_in_dept = Candidate.objects.filter(learner__in=user_ids).count()
                logger.info(f"    Training Candidates: {candidates_in_dept}")
            
            # Check user's accessible departments
            accessible_dept_ids = data_service.get_accessible_department_ids()
            logger.info(f"\nUser's accessible department IDs: {accessible_dept_ids}")
            
            # Check if there are any incidents at all in the system
            total_system_incidents = Incident.objects.count()
            logger.info(f"Total incidents in entire system: {total_system_incidents}")
            
            if total_system_incidents > 0:
                # Show date range of incidents
                oldest_incident = Incident.objects.earliest('created_at')
                newest_incident = Incident.objects.latest('created_at')
                logger.info(f"Incident date range: {oldest_incident.created_at.date()} to {newest_incident.created_at.date()}")
                
                # Show incidents by department
                logger.info("Incidents by department:")
                for dept in all_depts:
                    dept_incident_count = Incident.objects.filter(department=dept).count()
                    if dept_incident_count > 0:
                        logger.info(f"  {dept.name}: {dept_incident_count} incidents")
                    else:
                        logger.info(f"  {dept.name}: 0 incidents")
                
                # Show incidents without department
                no_dept_incidents = Incident.objects.filter(department__isnull=True).count()
                if no_dept_incidents > 0:
                    logger.info(f"  [No Department]: {no_dept_incidents} incidents")
            else:
                logger.warning("NO INCIDENTS FOUND IN THE ENTIRE SYSTEM!")
            
            logger.info("=" * 40)
            
            # Get date range
            start_date, end_date = data_service.get_date_range(
                timeframe=timeframe,
                start_date=start_date_str,
                end_date=end_date_str
            )
            
            logger.info(f"Computed date range for filters: {start_date} to {end_date}")
            
            # Fetch incident trends with debugging
            incident_trends = data_service.get_incident_trends(start_date, end_date, department_id, current_user=user)
            
            logger.info(f"Incident trends result: {len(incident_trends)} entries")
            if incident_trends:
                non_zero_trends = [t for t in incident_trends if t.get('total_incidents', 0) > 0]
                logger.info(f"Non-zero trend entries: {len(non_zero_trends)}")
                if non_zero_trends:
                    logger.info(f"First non-zero trend entry: {non_zero_trends[0] if non_zero_trends else 'None'}")
            
            # Fetch all other data
            user_stats = data_service.get_user_statistics(start_date, end_date, department_id)
            incident_stats = data_service.get_incident_statistics(start_date, end_date, department_id)
            audit_stats = data_service.get_audit_statistics(start_date, end_date, department_id)
            training_stats = data_service.get_training_statistics(department_id)
            risk_score = data_service.get_risk_score(start_date, end_date, department_id)
            department_breakdown = data_service.get_department_breakdown(start_date, end_date)
            
            # Fetch department performance with debugging
            department_performance = data_service.get_department_performance(start_date, end_date)
            logger.info(f"Department performance entries: {len(department_performance)}")
            
            # Compile main stats
            stats = {
                'total_users': user_stats['total_users'],
                'active_users': user_stats['active_users'],
                'pending_users': user_stats['pending_users'],
                'total_incidents': incident_stats['total_incidents'],
                'open_incidents': incident_stats['open_incidents'],
                'critical_incidents': incident_stats['critical_incidents'],
                'total_audits': audit_stats['total_audits'],
                'active_audits': audit_stats['active_audits'],
                'total_trainings': training_stats['total_trainings'],
                'ongoing_trainings': training_stats['active_candidates'],
                'compliance_score': audit_stats['compliance_score'],
                'risk_score': risk_score,
                'department_breakdown': department_breakdown
            }
            
            # Get all other data
            dashboard_data = {
                'stats': stats,
                'access_trends': data_service.get_access_trends(start_date, end_date, department_id, days=7, current_user=user),
                'incident_trends': incident_trends,
                'department_performance': department_performance,
                'recent_activities': data_service.get_recent_activities(start_date, end_date, department_id, limit=10, current_user=request.user),
                'system_health': data_service.get_system_health(start_date, end_date, current_user=user),
                'training_progress': data_service.get_training_progress(department_id, current_user=user),
                'risk_distribution': data_service.get_risk_distribution(start_date, end_date, department_id),
                'user_activities': data_service.get_user_activities(start_date, end_date, department_id),
                'generated_at': timezone.now(),
                'filters': {
                    'timeframe': timeframe,
                    'department': department_id,
                    'status': incident_status,
                    'severity': severity,
                    'start_date': start_date_str,
                    'end_date': end_date_str
                }
            }
            
            # DEBUG: Log response summary
            logger.info("\n" + "=" * 40)
            logger.info("RESPONSE SUMMARY")
            logger.info(f"Stats: Total Users={stats['total_users']}, Total Incidents={stats['total_incidents']}, Open Incidents={stats['open_incidents']}")
            logger.info(f"Incident trends in response: {len(dashboard_data['incident_trends'])}")
            logger.info(f"Department performance in response: {len(dashboard_data['department_performance'])}")
            logger.info(f"Access trends in response: {len(dashboard_data['access_trends'])}")
            logger.info(f"Recent activities in response: {len(dashboard_data['recent_activities'])}")
            logger.info(f"System health in response: {len(dashboard_data['system_health'])}")
            logger.info(f"Training progress in response: {dashboard_data['training_progress'] is not None}")
            logger.info(f"Risk distribution in response: {len(dashboard_data['risk_distribution'])}")
            logger.info("=" * 40)
            logger.info("DASHBOARD API CALL - END")
            logger.info("=" * 80)
            
            return Response(dashboard_data, status=http_status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Dashboard error: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to load dashboard data', 'details': str(e)},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DashboardFiltersView(APIView):
    """API endpoint to get available dashboard filters based on user role"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # Timeframes
            timeframes = [
                {'value': 'today', 'label': 'Today'},
                {'value': 'week', 'label': 'Last 7 Days'},
                {'value': 'month', 'label': 'Last 30 Days'},
                {'value': 'quarter', 'label': 'Last Quarter'},
                {'value': 'year', 'label': 'Last Year'},
                {'value': 'custom', 'label': 'Custom Range'}
            ]
            
            # Severities
            severities = [
                {'value': 'critical', 'label': 'Critical'},
                {'value': 'high', 'label': 'High'},
                {'value': 'medium', 'label': 'Medium'},
                {'value': 'low', 'label': 'Low'}
            ]
            
            # Statuses
            statuses = [
                {'value': 'pending', 'label': 'Pending'},
                {'value': 'investigating', 'label': 'Investigating'},
                {'value': 'assigned', 'label': 'Assigned'},
                {'value': 'in_progress', 'label': 'In Progress'},
                {'value': 'resolved', 'label': 'Resolved'},
                {'value': 'closed', 'label': 'Closed'}
            ]
            
            # Get departments based on user role
            departments_list = []
            try:
                if user.role in ['admin', 'hr_manager', 'compliance_officer']:
                    departments = Department.objects.filter(status='active')
                elif user.role == 'security_analyst':
                    departments = user.departments.filter(status='active')
                elif user.role == 'employee':
                    if user.department:
                        departments = Department.objects.filter(id=user.department.id, status='active')
                    else:
                        departments = Department.objects.none()
                else:
                    departments = Department.objects.none()
                
                departments_list = [
                    {'value': dept.id, 'label': dept.name}
                    for dept in departments
                ]
                
                # Add "All Departments" option for users who can see multiple departments
                if len(departments_list) > 1:
                    departments_list.insert(0, {'value': '', 'label': 'All Departments'})
            except Exception as e:
                logger.error(f"Error getting departments: {str(e)}")
            
            filters = {
                'timeframes': timeframes,
                'severities': severities,
                'statuses': statuses,
                'departments': departments_list
            }
            
            return Response(filters, status=http_status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error getting filters: {str(e)}")
            return Response(
                {'error': 'Failed to load filters'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ExportDashboardView(APIView):
    """API endpoint to export dashboard data in various formats"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            export_format = request.data.get('format')
            if not export_format or export_format not in ['json', 'csv', 'pdf']:
                return Response({'error': 'Invalid export format'}, status=http_status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            
            # Get dashboard data
            dashboard_view = RoleBasedDashboardView()
            dashboard_view.request = request
            
            response = dashboard_view.get(request)
            
            if response.status_code != 200:
                return response
            
            dashboard_data = response.data
            
            if export_format == 'json':
                return Response(dashboard_data, status=http_status.HTTP_200_OK)
            
            elif export_format == 'csv':
                return self.export_to_csv(dashboard_data, user)
            
            elif export_format == 'pdf':
                return self.export_to_pdf(dashboard_data, user)
                
        except Exception as e:
            logger.error(f"Export error: {str(e)}")
            return Response(
                {'error': f'Export failed: {str(e)}'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def export_to_csv(self, data, user):
        """Export dashboard data to CSV - SIMPLIFIED"""
        try:
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Security Dashboard Export'])
            writer.writerow(['Generated For:', user.full_name])
            writer.writerow(['Generated At:', str(timezone.now())])
            writer.writerow(['User Role:', user.role])
            writer.writerow([])
            
            # Write statistics
            writer.writerow(['OVERALL STATISTICS'])
            writer.writerow(['Metric', 'Value'])
            
            stats = data.get('stats', {})
            writer.writerow(['Total Users', stats.get('total_users', 0)])
            writer.writerow(['Active Users', stats.get('active_users', 0)])
            writer.writerow(['Pending Users', stats.get('pending_users', 0)])
            writer.writerow(['Total Incidents', stats.get('total_incidents', 0)])
            writer.writerow(['Open Incidents', stats.get('open_incidents', 0)])
            writer.writerow(['Critical Incidents', stats.get('critical_incidents', 0)])
            writer.writerow(['Total Audits', stats.get('total_audits', 0)])
            writer.writerow(['Active Audits', stats.get('active_audits', 0)])
            writer.writerow(['Total Trainings', stats.get('total_trainings', 0)])
            writer.writerow(['Active Candidates', stats.get('ongoing_trainings', 0)])
            writer.writerow(['Compliance Score', f"{stats.get('compliance_score', 0)}%"])
            writer.writerow(['Risk Score', f"{stats.get('risk_score', 0)}%"])
            writer.writerow([])
            
            # Write department breakdown if available
            if stats.get('department_breakdown'):
                writer.writerow(['DEPARTMENT BREAKDOWN'])
                writer.writerow(['Department', 'Users', 'Incidents', 'Compliance Score'])
                for dept_name, dept_data in stats['department_breakdown'].items():
                    writer.writerow([
                        dept_name,
                        dept_data.get('user_count', 0),
                        dept_data.get('incident_count', 0),
                        f"{dept_data.get('compliance_score', 0)}%"
                    ])
            
            # Prepare response
            csv_content = output.getvalue()
            response = HttpResponse(csv_content, content_type='text/csv')
            filename = f"dashboard_export_{user.email}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            logger.error(f"CSV export error: {str(e)}")
            return Response(
                {'error': 'Failed to generate CSV export'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def export_to_pdf(self, data, user):
        """Export dashboard data to PDF"""
        try:
            # Create buffer for PDF
            buffer = BytesIO()
            
            # Create PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontSize=18,
                spaceAfter=12
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                spaceBefore=12,
                spaceAfter=6
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=10
            )
            
            # Build content
            content = []
            
            # Title
            content.append(Paragraph('Security Dashboard Export Report', title_style))
            content.append(Paragraph(f'Generated For: {user.full_name}', normal_style))
            content.append(Paragraph(f'User Role: {user.get_role_display() if hasattr(user, "get_role_display") else user.role}', normal_style))
            content.append(Paragraph(f'Generated At: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}', normal_style))
            content.append(Spacer(1, 20))
            
            # Statistics Section
            content.append(Paragraph('Overall Statistics', heading_style))
            
            stats = data.get('stats', {})
            
            # Create statistics table
            stats_data = [
                ['Metric', 'Value'],
                ['Total Users', str(stats.get('total_users', 0))],
                ['Active Users', str(stats.get('active_users', 0))],
                ['Pending Users', str(stats.get('pending_users', 0))],
                ['Total Incidents', str(stats.get('total_incidents', 0))],
                ['Open Incidents', str(stats.get('open_incidents', 0))],
                ['Critical Incidents', str(stats.get('critical_incidents', 0))],
                ['Total Audits', str(stats.get('total_audits', 0))],
                ['Active Audits', str(stats.get('active_audits', 0))],
                ['Total Trainings', str(stats.get('total_trainings', 0))],
                ['Active Candidates', str(stats.get('ongoing_trainings', 0))],
                ['Compliance Score', f"{stats.get('compliance_score', 0)}%"],
                ['Risk Score', f"{stats.get('risk_score', 0)}%"]
            ]
            
            stats_table = Table(stats_data, colWidths=[250, 100])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ]))
            
            content.append(stats_table)
            content.append(Spacer(1, 20))
            
            # Department Breakdown Section
            if stats.get('department_breakdown'):
                content.append(Paragraph('Department Breakdown', heading_style))
                
                dept_data = [['Department', 'Users', 'Incidents', 'Compliance Score']]
                
                for dept_name, dept_stats in stats['department_breakdown'].items():
                    dept_data.append([
                        dept_name,
                        str(dept_stats.get('user_count', 0)),
                        str(dept_stats.get('incident_count', 0)),
                        f"{dept_stats.get('compliance_score', 0)}%"
                    ])
                
                dept_table = Table(dept_data, colWidths=[150, 70, 80, 100])
                dept_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
                ]))
                
                content.append(dept_table)
                content.append(Spacer(1, 20))
            
            # System Health Section (if available)
            if data.get('system_health'):
                content.append(Paragraph('System Health Status', heading_style))
                
                health_data = [['Component', 'Status', 'Uptime', 'Issues']]
                
                for component in data['system_health']:
                    health_data.append([
                        component.get('component', ''),
                        component.get('status', ''),
                        f"{component.get('uptime', 0)}%",
                        str(component.get('issues', 0))
                    ])
                
                health_table = Table(health_data, colWidths=[150, 80, 70, 60])
                health_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
                ]))
                
                content.append(health_table)
                content.append(Spacer(1, 20))
            
            # Recent Activities Section (if available, show first 10)
            if data.get('recent_activities'):
                content.append(Paragraph('Recent Activities (Last 10)', heading_style))
                
                activity_data = [['Time', 'Activity', 'User', 'Status']]
                
                for activity in data['recent_activities'][:10]:
                    # Format timestamp
                    timestamp = activity.get('timestamp', '')
                    if isinstance(timestamp, str):
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            time_str = dt.strftime('%Y-%m-%d %H:%M')
                        except:
                            time_str = timestamp[:16]
                    else:
                        time_str = str(timestamp)[:16]
                    
                    activity_data.append([
                        time_str,
                        activity.get('activity', '')[:30],
                        activity.get('user', '')[:20],
                        activity.get('severity', '').upper()
                    ])
                
                activity_table = Table(activity_data, colWidths=[80, 120, 100, 50])
                activity_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8e44ad')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
                ]))
                
                content.append(activity_table)
                content.append(Spacer(1, 20))
            
            # Footer
            content.append(Paragraph('--- End of Report ---', normal_style))
            content.append(Spacer(1, 10))
            content.append(Paragraph('Confidential - For internal use only', 
                                   ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray)))
            
            # Build PDF
            doc.build(content)
            buffer.seek(0)
            
            # Create response
            response = HttpResponse(buffer, content_type='application/pdf')
            filename = f"dashboard_export_{user.email}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except ImportError:
            logger.error("ReportLab not installed for PDF export")
            return Response(
                {'error': 'PDF export requires ReportLab library. Install with: pip install reportlab'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"PDF export error: {str(e)}", exc_info=True)
            
            # Fallback: try simple PDF generation
            try:
                return self.export_to_pdf_simple(data, user)
            except Exception as e2:
                logger.error(f"Simple PDF export also failed: {str(e2)}")
                return Response(
                    {'error': f'Failed to generate PDF: {str(e)}'},
                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    
    def export_to_pdf_simple(self, data, user):
        """Simple fallback PDF generation using canvas only"""
        try:
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            
            # Set up page
            width, height = letter
            
            # Title
            p.setFont("Helvetica-Bold", 16)
            p.drawString(100, height - 100, "Security Dashboard Export Report")
            
            p.setFont("Helvetica", 10)
            p.drawString(100, height - 130, f"Generated For: {user.full_name}")
            p.drawString(100, height - 150, f"User Role: {user.get_role_display() if hasattr(user, 'get_role_display') else user.role}")
            p.drawString(100, height - 170, f"Generated At: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            y = height - 200
            
            # Statistics
            p.setFont("Helvetica-Bold", 12)
            p.drawString(100, y, "Overall Statistics")
            y -= 20
            
            p.setFont("Helvetica", 10)
            stats = data.get('stats', {})
            
            stats_list = [
                f"Total Users: {stats.get('total_users', 0)}",
                f"Active Users: {stats.get('active_users', 0)}",
                f"Pending Users: {stats.get('pending_users', 0)}",
                f"Total Incidents: {stats.get('total_incidents', 0)}",
                f"Open Incidents: {stats.get('open_incidents', 0)}",
                f"Critical Incidents: {stats.get('critical_incidents', 0)}",
                f"Total Audits: {stats.get('total_audits', 0)}",
                f"Active Audits: {stats.get('active_audits', 0)}",
                f"Compliance Score: {stats.get('compliance_score', 0)}%",
                f"Risk Score: {stats.get('risk_score', 0)}%"
            ]
            
            for stat in stats_list:
                p.drawString(120, y, stat)
                y -= 15
                if y < 100:  # New page if needed
                    p.showPage()
                    y = height - 100
            
            # Department breakdown if available
            if stats.get('department_breakdown'):
                y -= 20
                p.setFont("Helvetica-Bold", 12)
                p.drawString(100, y, "Department Breakdown")
                y -= 20
                
                p.setFont("Helvetica", 10)
                for dept_name, dept_stats in stats['department_breakdown'].items():
                    dept_text = f"{dept_name}: Users={dept_stats.get('user_count', 0)}, "
                    dept_text += f"Incidents={dept_stats.get('incident_count', 0)}, "
                    dept_text += f"Compliance={dept_stats.get('compliance_score', 0)}%"
                    
                    p.drawString(120, y, dept_text[:80])  # Limit line length
                    y -= 15
                    if y < 100:
                        p.showPage()
                        y = height - 100
            
            # Footer
            p.setFont("Helvetica-Oblique", 8)
            p.drawString(100, 50, "Confidential - For internal use only")
            p.drawString(100, 40, f"Page 1 - Generated by {user.email}")
            
            p.save()
            buffer.seek(0)
            
            response = HttpResponse(buffer, content_type='application/pdf')
            filename = f"dashboard_simple_{user.email}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.error(f"Simple PDF export error: {str(e)}")
            raise
















# reportApp/views.py - ADD THESE VIEWS

# Add to existing imports
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from datetime import datetime, timedelta
from django.db.models import Count, Avg, Q, Sum, F, Min, Max
from django.db import models
import json
import logging

logger = logging.getLogger(__name__)



# ==================== REPORT GENERATION SERVICE ====================
class ReportGenerationService:
    """Service for generating reports based on user role and filters"""
    
    def __init__(self, user):
        self.user = user
        self.today = timezone.now()
    
    def get_date_range(self, start_date, end_date):
        """Get proper date range with timezone"""
        if not end_date:
            end_date = self.today.date()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        return start_datetime, end_datetime
    
    def get_user_queryset(self, filters):
        """Get filtered user queryset based on user role"""
        qs = CustomUser.objects.filter(is_active=True)
        
        # Apply date filter if provided
        if filters.get('start_date') and filters.get('end_date'):
            start_date, end_date = self.get_date_range(
                filters['start_date'], filters['end_date']
            )
            qs = qs.filter(created_at__range=[start_date, end_date])
        
        # Apply role filter
        if filters.get('role'):
            qs = qs.filter(role=filters['role'])
        
        # Apply status filter
        if filters.get('status'):
            qs = qs.filter(status=filters['status'])
        
        # Apply department filter based on user role
        if filters.get('department'):
            department_id = filters['department']
            qs = self.filter_by_department(qs, department_id)
        else:
            # Apply default department filtering based on user role
            qs = self.apply_role_based_filtering(qs)
        
        return qs.order_by('-created_at')
    
    def filter_by_department(self, queryset, department_id):
        """Filter queryset by department based on user role"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            # Admins can see all departments
            return queryset.filter(
                Q(department__id=department_id) | Q(departments__id=department_id)
            ).distinct()
        
        elif self.user.role == 'security_analyst':
            # Security analysts can only see their assigned departments
            if department_id and department_id in list(self.user.departments.values_list('id', flat=True)):
                return queryset.filter(
                    Q(department__id=department_id) | Q(departments__id=department_id)
                ).distinct()
            else:
                # Return empty queryset if trying to access unauthorized department
                return queryset.none()
        
        elif self.user.role == 'employee':
            # Employees can only see their own department
            if self.user.department and self.user.department.id == department_id:
                return queryset.filter(department__id=department_id)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def apply_role_based_filtering(self, queryset):
        """Apply default role-based filtering"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            # Can see all users
            return queryset
        
        elif self.user.role == 'security_analyst':
            # Can only see users in their assigned departments
            dept_ids = list(self.user.departments.values_list('id', flat=True))
            if dept_ids:
                return queryset.filter(
                    Q(department__id__in=dept_ids) | Q(departments__id__in=dept_ids)
                ).distinct()
            else:
                return queryset.none()
        
        elif self.user.role == 'employee':
            # Can only see users in same department
            if self.user.department:
                return queryset.filter(department=self.user.department)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def get_incident_queryset(self, filters):
        """Get filtered incident queryset based on user role"""
        qs = Incident.objects.all()
        
        # Apply date filter
        if filters.get('start_date') and filters.get('end_date'):
            start_date, end_date = self.get_date_range(
                filters['start_date'], filters['end_date']
            )
            qs = qs.filter(created_at__range=[start_date, end_date])
        
        # Apply severity filter
        if filters.get('severity'):
            qs = qs.filter(severity=filters['severity'])
        
        # Apply status filter
        status_filter = filters.get('incident_status') or filters.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        # Apply department filter
        if filters.get('department'):
            department_id = filters['department']
            qs = self.filter_incidents_by_department(qs, department_id)
        else:
            qs = self.apply_role_based_incident_filtering(qs)
        
        return qs.order_by('-created_at')
    
    def filter_incidents_by_department(self, queryset, department_id):
        """Filter incidents by department based on user role"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            return queryset.filter(department__id=department_id)
        
        elif self.user.role == 'security_analyst':
            if department_id and department_id in list(self.user.departments.values_list('id', flat=True)):
                return queryset.filter(department__id=department_id)
            else:
                return queryset.none()
        
        elif self.user.role == 'employee':
            if self.user.department and self.user.department.id == department_id:
                return queryset.filter(department__id=department_id)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def apply_role_based_incident_filtering(self, queryset):
        """Apply default role-based filtering for incidents"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            return queryset
        
        elif self.user.role == 'security_analyst':
            dept_ids = list(self.user.departments.values_list('id', flat=True))
            if dept_ids:
                return queryset.filter(department__id__in=dept_ids)
            else:
                return queryset.none()
        
        elif self.user.role == 'employee':
            if self.user.department:
                return queryset.filter(department=self.user.department)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def get_audit_queryset(self, filters):
        """Get filtered audit queryset based on user role"""
        qs = ComplianceAudit.objects.all()
        
        # Apply date filter
        if filters.get('start_date') and filters.get('end_date'):
            start_date, end_date = self.get_date_range(
                filters['start_date'], filters['end_date']
            )
            qs = qs.filter(created_at__range=[start_date, end_date])
        
        # Apply status filter
        status_filter = filters.get('audit_status') or filters.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        # Apply department filter
        if filters.get('department'):
            department_id = filters['department']
            qs = self.filter_audits_by_department(qs, department_id)
        else:
            qs = self.apply_role_based_audit_filtering(qs)
        
        # Apply compliance standard filter
        if filters.get('compliance_standard'):
            qs = qs.filter(standard__standard_type=filters['compliance_standard'])
        
        return qs.order_by('-created_at')
    
    def filter_audits_by_department(self, queryset, department_id):
        """Filter audits by department based on user role"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            return queryset.filter(departments__id=department_id)
        
        elif self.user.role == 'security_analyst':
            if department_id and department_id in list(self.user.departments.values_list('id', flat=True)):
                return queryset.filter(departments__id=department_id)
            else:
                return queryset.none()
        
        elif self.user.role == 'employee':
            if self.user.department and self.user.department.id == department_id:
                return queryset.filter(departments__id=department_id)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def apply_role_based_audit_filtering(self, queryset):
        """Apply default role-based filtering for audits"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            return queryset
        
        elif self.user.role == 'security_analyst':
            dept_ids = list(self.user.departments.values_list('id', flat=True))
            if dept_ids:
                return queryset.filter(departments__id__in=dept_ids)
            else:
                return queryset.none()
        
        elif self.user.role == 'employee':
            if self.user.department:
                return queryset.filter(departments__id=self.user.department.id)
            else:
                return queryset.none()
        
        return queryset.none()
    
    def get_training_queryset(self, filters):
        """Get filtered training queryset based on user role"""
        # Get accessible users first
        user_qs = self.get_user_queryset(filters)
        accessible_user_ids = list(user_qs.values_list('id', flat=True))
        
        # Get trainings for these users
        candidate_trainings = Candidate.objects.filter(
            learner__in=accessible_user_ids
        ).values_list('training_id', flat=True).distinct()
        
        qs = Training.objects.filter(id__in=candidate_trainings)
        
        # Apply status filter (through candidates)
        if filters.get('training_status') or filters.get('status'):
            status_filter = filters.get('training_status') or filters.get('status')
            # Filter trainings that have candidates with this status
            candidate_training_ids = Candidate.objects.filter(
                status=status_filter,
                learner__in=accessible_user_ids
            ).values_list('training_id', flat=True).distinct()
            qs = qs.filter(id__in=candidate_training_ids)
        
        return qs.order_by('-created_at')
    
    def get_department_queryset(self, filters):
        """Get filtered department queryset based on user role"""
        if self.user.role in ['admin', 'hr_manager', 'compliance_officer']:
            qs = Department.objects.all()
        elif self.user.role == 'security_analyst':
            qs = self.user.departments.all()
        elif self.user.role == 'employee':
            if self.user.department:
                qs = Department.objects.filter(id=self.user.department.id)
            else:
                qs = Department.objects.none()
        else:
            qs = Department.objects.none()
        
        # Apply status filter
        if filters.get('status'):
            qs = qs.filter(status=filters['status'])
        
        return qs.order_by('name')
    
    def get_activity_logs_queryset(self, filters):
        """Get filtered activity logs queryset based on user role"""
        # Get accessible users first
        user_qs = self.get_user_queryset(filters)
        accessible_user_ids = list(user_qs.values_list('id', flat=True))
        
        qs = UserLog.objects.filter(user__in=accessible_user_ids)
        
        # Apply date filter
        if filters.get('start_date') and filters.get('end_date'):
            start_date, end_date = self.get_date_range(
                filters['start_date'], filters['end_date']
            )
            qs = qs.filter(timestamp__range=[start_date, end_date])
        
        # Apply log type filter
        if filters.get('log_type'):
            qs = qs.filter(log_type=filters['log_type'])
        
        # Apply activity type filter
        if filters.get('activity'):
            qs = qs.filter(activity=filters['activity'])
        
        return qs.order_by('-timestamp')
    
    def get_user_training_progress_queryset(self, filters):
        """Get user training progress queryset based on user role"""
        # Get accessible users first
        user_qs = self.get_user_queryset(filters)
        accessible_user_ids = list(user_qs.values_list('id', flat=True))
        
        # Get candidates for these users
        candidates = Candidate.objects.filter(learner__in=accessible_user_ids)
        
        # Apply status filter
        if filters.get('training_status') or filters.get('status'):
            status_filter = filters.get('training_status') or filters.get('status')
            candidates = candidates.filter(status=status_filter)
        
        # Get learning progress for these candidates
        learning_progress = LearningProgress.objects.filter(
            candidate__in=candidates
        ).select_related('candidate', 'training')
        
        return learning_progress.order_by('-last_activity')
    
    def generate_users_report(self, filters):
        """Generate users report"""
        queryset = self.get_user_queryset(filters)
        
        # Apply pagination
        page = filters.get('page', 1)
        page_size = filters.get('page_size', 50)
        offset = (page - 1) * page_size
        total_records = queryset.count()
        
        paginated_qs = queryset[offset:offset + page_size]
        
        # Prepare data
        report_data = []
        for user in paginated_qs:
            report_data.append({
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'work_mail_address': user.work_mail_address,
                'phone_number': user.phone_number,
                'role': user.get_role_display() if hasattr(user, 'get_role_display') else user.role,
                'status': user.get_status_display() if hasattr(user, 'get_status_display') else user.status,
                'availability_status': user.get_availability_status_display() if hasattr(user, 'get_availability_status_display') else user.availability_status,
                'department': user.department.name if user.department else 'N/A',
                'departments': [dept.name for dept in user.departments.all()] if user.departments.exists() else [],
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never',
                'is_active': 'Yes' if user.is_active else 'No',
                'is_staff': 'Yes' if user.is_staff else 'No'
            })
        
        # Generate summary statistics
        summary_stats = {
            'total_users': total_records,
            'by_role': dict(queryset.values('role').annotate(count=Count('id')).values_list('role', 'count')),
            'by_status': dict(queryset.values('status').annotate(count=Count('id')).values_list('status', 'count')),
            'by_availability': dict(queryset.values('availability_status').annotate(count=Count('id')).values_list('availability_status', 'count')),
            'active_users': queryset.filter(availability_status='active').count(),
            'inactive_users': queryset.filter(availability_status='inactive').count(),
            'pending_users': queryset.filter(status='pending').count(),
            'average_users_per_day': self.calculate_average_per_day(queryset, 'created_at')
        }
        
        # Key metrics
        key_metrics = [
            f"Total Users: {summary_stats['total_users']}",
            f"Active Users: {summary_stats['active_users']}",
            f"Pending Approval: {summary_stats['pending_users']}",
            f"Average New Users Per Day: {summary_stats['average_users_per_day']:.2f}"
        ]
        
        return report_data, summary_stats, key_metrics, total_records
    
    def generate_incidents_report(self, filters):
        """Generate incidents report"""
        queryset = self.get_incident_queryset(filters)
        
        # Apply pagination
        page = filters.get('page', 1)
        page_size = filters.get('page_size', 50)
        offset = (page - 1) * page_size
        total_records = queryset.count()
        
        paginated_qs = queryset[offset:offset + page_size]
        
        # Prepare data
        report_data = []
        for incident in paginated_qs:
            report_data.append({
                'incident_number': incident.incident_number,
                'title': incident.title,
                'description': incident.description[:200] + '...' if len(incident.description) > 200 else incident.description,
                'status': incident.get_status_display() if hasattr(incident, 'get_status_display') else incident.status,
                'severity': incident.get_severity_display() if hasattr(incident, 'get_severity_display') else incident.severity,
                'priority': incident.get_priority_display() if hasattr(incident, 'get_priority_display') else incident.priority,
                'assigned_to': incident.assigned_to.full_name if incident.assigned_to else 'Unassigned',
                'department': incident.department.name if incident.department else 'N/A',
                'created_at': incident.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': incident.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                'resolved_at': incident.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if incident.resolved_at else 'Not resolved',
                'sla_due_date': incident.sla_due_date.strftime('%Y-%m-%d %H:%M:%S') if incident.sla_due_date else 'Not set',
                'sla_violated': 'Yes' if incident.sla_violated else 'No',
                'risk_score': incident.risk_score,
                'danger_zone': 'Yes' if incident.danger_zone else 'No',
                'is_overdue': 'Yes' if incident.is_overdue else 'No'
            })
        
        # Generate summary statistics
        resolved_incidents = queryset.filter(status__in=['resolved', 'closed'])
        avg_resolution_time = None
        if resolved_incidents.exists():
            total_hours = 0
            for incident in resolved_incidents:
                if incident.resolved_at and incident.created_at:
                    hours = (incident.resolved_at - incident.created_at).total_seconds() / 3600
                    total_hours += hours
            avg_resolution_time = total_hours / resolved_incidents.count()
        
        summary_stats = {
            'total_incidents': total_records,
            'open_incidents': queryset.exclude(status__in=['resolved', 'closed']).count(),
            'resolved_incidents': resolved_incidents.count(),
            'by_severity': dict(queryset.values('severity').annotate(count=Count('id')).values_list('severity', 'count')),
            'by_status': dict(queryset.values('status').annotate(count=Count('id')).values_list('status', 'count')),
            'by_priority': dict(queryset.values('priority').annotate(count=Count('id')).values_list('priority', 'count')),
            'sla_violations': queryset.filter(sla_violated=True).count(),
            'overdue_incidents': sum(1 for inc in queryset if inc.is_overdue),
            'average_resolution_time_hours': round(avg_resolution_time, 2) if avg_resolution_time else 0,
            'average_incidents_per_day': self.calculate_average_per_day(queryset, 'created_at')
        }
        
        # Key metrics
        key_metrics = [
            f"Total Incidents: {summary_stats['total_incidents']}",
            f"Open Incidents: {summary_stats['open_incidents']}",
            f"Resolved Incidents: {summary_stats['resolved_incidents']}",
            f"SLA Violations: {summary_stats['sla_violations']}",
            f"Average Resolution Time: {summary_stats['average_resolution_time_hours']} hours"
        ]
        
        return report_data, summary_stats, key_metrics, total_records
    
    def generate_audits_report(self, filters):
        """Generate audits report"""
        queryset = self.get_audit_queryset(filters)
        
        # Apply pagination
        page = filters.get('page', 1)
        page_size = filters.get('page_size', 50)
        offset = (page - 1) * page_size
        total_records = queryset.count()
        
        paginated_qs = queryset[offset:offset + page_size]
        
        # Prepare data
        report_data = []
        for audit in paginated_qs:
            report_data.append({
                'audit_id': audit.audit_id,
                'title': audit.title,
                'description': audit.description[:200] + '...' if len(audit.description) > 200 else audit.description,
                'standard': audit.standard.name if audit.standard else 'N/A',
                'audit_type': audit.get_audit_type_display() if hasattr(audit, 'get_audit_type_display') else audit.audit_type,
                'status': audit.get_status_display() if hasattr(audit, 'get_status_display') else audit.status,
                'priority': audit.get_priority_display() if hasattr(audit, 'get_priority_display') else audit.priority,
                'lead_auditor': audit.lead_auditor.full_name if audit.lead_auditor else 'Not assigned',
                'departments': [dept.name for dept in audit.departments.all()],
                'overall_score': f"{audit.overall_score}%" if audit.overall_score else 'Not assessed',
                'compliance_rate': f"{audit.compliance_rate}%" if audit.compliance_rate else 'Not calculated',
                'planned_start_date': audit.planned_start_date.strftime('%Y-%m-%d') if audit.planned_start_date else 'Not set',
                'planned_end_date': audit.planned_end_date.strftime('%Y-%m-%d') if audit.planned_end_date else 'Not set',
                'actual_start_date': audit.actual_start_date.strftime('%Y-%m-%d') if audit.actual_start_date else 'Not started',
                'actual_end_date': audit.actual_end_date.strftime('%Y-%m-%d') if audit.actual_end_date else 'Not completed',
                'total_findings': audit.total_findings,
                'open_findings': audit.open_findings,
                'critical_findings': audit.critical_findings,
                'created_at': audit.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Generate summary statistics
        completed_audits = queryset.filter(status='completed', overall_score__isnull=False)
        avg_compliance_score = 0
        if completed_audits.exists():
            avg_compliance_score = completed_audits.aggregate(avg=Avg('overall_score'))['avg'] or 0
        
        summary_stats = {
            'total_audits': total_records,
            'completed_audits': completed_audits.count(),
            'in_progress_audits': queryset.filter(status='in_progress').count(),
            'by_status': dict(queryset.values('status').annotate(count=Count('id')).values_list('status', 'count')),
            'by_type': dict(queryset.values('audit_type').annotate(count=Count('id')).values_list('audit_type', 'count')),
            'by_standard': dict(queryset.values('standard__name').annotate(count=Count('id')).values_list('standard__name', 'count')),
            'average_compliance_score': round(avg_compliance_score, 2),
            'total_findings': queryset.aggregate(total=Sum('total_findings'))['total'] or 0,
            'open_findings': queryset.aggregate(total=Sum('open_findings'))['total'] or 0,
            'critical_findings': queryset.aggregate(total=Sum('critical_findings'))['total'] or 0,
            'average_audits_per_month': self.calculate_average_per_month(queryset, 'created_at')
        }
        
        # Key metrics
        key_metrics = [
            f"Total Audits: {summary_stats['total_audits']}",
            f"Completed Audits: {summary_stats['completed_audits']}",
            f"In Progress Audits: {summary_stats['in_progress_audits']}",
            f"Average Compliance Score: {summary_stats['average_compliance_score']}%",
            f"Total Findings: {summary_stats['total_findings']} (Open: {summary_stats['open_findings']})"
        ]
        
        return report_data, summary_stats, key_metrics, total_records
    
    def generate_departments_report(self, filters):
        """Generate departments report"""
        queryset = self.get_department_queryset(filters)
        
        # Apply pagination
        page = filters.get('page', 1)
        page_size = filters.get('page_size', 50)
        offset = (page - 1) * page_size
        total_records = queryset.count()
        
        paginated_qs = queryset[offset:offset + page_size]
        
        # Prepare data with additional metrics
        report_data = []
        for dept in paginated_qs:
            # Get department metrics
            dept_users = CustomUser.objects.filter(
                Q(department=dept) | Q(departments=dept),
                is_active=True
            ).distinct()
            
            dept_incidents = Incident.objects.filter(department=dept)
            dept_audits = ComplianceAudit.objects.filter(departments=dept)
            
            # Calculate compliance score
            compliance_score = 0
            if dept_audits.filter(status='completed').exists():
                completed_audits = dept_audits.filter(status='completed', overall_score__isnull=False)
                if completed_audits.exists():
                    compliance_score = completed_audits.aggregate(avg=Avg('overall_score'))['avg'] or 0
            
            report_data.append({
                'id': dept.id,
                'name': dept.name,
                'description': dept.description[:200] + '...' if dept.description and len(dept.description) > 200 else dept.description or '',
                'status': dept.get_status_display() if hasattr(dept, 'get_status_display') else dept.status,
                'total_users': dept_users.count(),
                'total_incidents': dept_incidents.count(),
                'open_incidents': dept_incidents.exclude(status__in=['resolved', 'closed']).count(),
                'total_audits': dept_audits.count(),
                'compliance_score': f"{round(compliance_score, 2)}%",
                'created_at': dept.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': dept.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': dept.created_by.full_name if dept.created_by else 'System'
            })
        
        # Generate summary statistics
        summary_stats = {
            'total_departments': total_records,
            'active_departments': queryset.filter(status='active').count(),
            'inactive_departments': queryset.filter(status='inactive').count(),
            'by_status': dict(queryset.values('status').annotate(count=Count('id')).values_list('status', 'count')),
            'average_users_per_department': self.calculate_average_users_per_department(queryset),
            'departments_with_incidents': self.count_departments_with_incidents(queryset),
            'departments_with_audits': self.count_departments_with_audits(queryset)
        }
        
        # Key metrics
        key_metrics = [
            f"Total Departments: {summary_stats['total_departments']}",
            f"Active Departments: {summary_stats['active_departments']}",
            f"Inactive Departments: {summary_stats['inactive_departments']}",
            f"Average Users Per Department: {summary_stats['average_users_per_department']:.2f}",
            f"Departments with Incidents: {summary_stats['departments_with_incidents']}"
        ]
        
        return report_data, summary_stats, key_metrics, total_records
    
    def generate_trainings_report(self, filters):
        """Generate trainings report"""
        queryset = self.get_training_queryset(filters)
        
        # Apply pagination
        page = filters.get('page', 1)
        page_size = filters.get('page_size', 50)
        offset = (page - 1) * page_size
        total_records = queryset.count()
        
        paginated_qs = queryset[offset:offset + page_size]
        
        # Prepare data with metrics
        report_data = []
        for training in paginated_qs:
            # Get training metrics
            candidates = Candidate.objects.filter(training=training)
            total_candidates = candidates.count()
            completed_candidates = candidates.filter(status='completed').count()
            pending_candidates = candidates.filter(status='pending').count()
            
            completion_rate = 0
            if total_candidates > 0:
                completion_rate = (completed_candidates / total_candidates) * 100
            
            total_modules = training.modules.count()
            total_materials = training.get_total_materials_count()
            
            report_data.append({
                'id': training.id,
                'name': training.name,
                'description': training.description[:200] + '...' if training.description and len(training.description) > 200 else training.description or '',
                'total_candidates': total_candidates,
                'completed_candidates': completed_candidates,
                'pending_candidates': pending_candidates,
                'completion_rate': f"{round(completion_rate, 2)}%",
                'total_modules': total_modules,
                'total_materials': total_materials,
                'created_at': training.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': training.created_by.full_name if training.created_by else 'Unknown'
            })
        
        # Generate summary statistics
        summary_stats = {
            'total_trainings': total_records,
            'average_completion_rate': self.calculate_average_training_completion_rate(queryset),
            'total_candidates': self.calculate_total_candidates(queryset),
            'completed_candidates': self.calculate_completed_candidates(queryset),
            'by_candidate_status': self.get_candidate_status_distribution(queryset),
            'average_modules_per_training': self.calculate_average_modules_per_training(queryset),
            'average_materials_per_training': self.calculate_average_materials_per_training(queryset)
        }
        
        # Key metrics
        key_metrics = [
            f"Total Trainings: {summary_stats['total_trainings']}",
            f"Total Candidates: {summary_stats['total_candidates']}",
            f"Completed Candidates: {summary_stats['completed_candidates']}",
            f"Average Completion Rate: {summary_stats['average_completion_rate']:.2f}%",
            f"Average Modules Per Training: {summary_stats['average_modules_per_training']:.2f}"
        ]
        
        return report_data, summary_stats, key_metrics, total_records
    
    # Helper methods for statistics
    def calculate_average_per_day(self, queryset, date_field):
        """Calculate average records per day"""
        if not queryset.exists():
            return 0
        
        dates = queryset.values_list(date_field, flat=True)
        if not dates:
            return 0
        
        first_date = min(dates)
        last_date = max(dates)
        
        if first_date == last_date:
            return queryset.count()
        
        days_diff = (last_date - first_date).days + 1
        return queryset.count() / days_diff
    
    def calculate_average_per_month(self, queryset, date_field):
        """Calculate average records per month"""
        if not queryset.exists():
            return 0
        
        first_date = queryset.aggregate(min_date=Min(date_field))['min_date']
        last_date = queryset.aggregate(max_date=Max(date_field))['max_date']
        
        if not first_date or not last_date:
            return 0
        
        months_diff = ((last_date.year - first_date.year) * 12) + (last_date.month - first_date.month) + 1
        return queryset.count() / months_diff
    
    def calculate_average_users_per_department(self, departments_queryset):
        """Calculate average users per department"""
        if not departments_queryset.exists():
            return 0
        
        total_users = 0
        for dept in departments_queryset:
            dept_users = CustomUser.objects.filter(
                Q(department=dept) | Q(departments=dept),
                is_active=True
            ).distinct().count()
            total_users += dept_users
        
        return total_users / departments_queryset.count()
    
    def count_departments_with_incidents(self, departments_queryset):
        """Count departments that have incidents"""
        count = 0
        for dept in departments_queryset:
            if Incident.objects.filter(department=dept).exists():
                count += 1
        return count
    
    def count_departments_with_audits(self, departments_queryset):
        """Count departments that have audits"""
        count = 0
        for dept in departments_queryset:
            if ComplianceAudit.objects.filter(departments=dept).exists():
                count += 1
        return count
    
    def calculate_average_training_completion_rate(self, trainings_queryset):
        """Calculate average completion rate across trainings"""
        if not trainings_queryset.exists():
            return 0
        
        total_rate = 0
        count = 0
        
        for training in trainings_queryset:
            candidates = Candidate.objects.filter(training=training)
            total_candidates = candidates.count()
            completed_candidates = candidates.filter(status='completed').count()
            
            if total_candidates > 0:
                completion_rate = (completed_candidates / total_candidates) * 100
                total_rate += completion_rate
                count += 1
        
        return total_rate / count if count > 0 else 0
    
    def calculate_total_candidates(self, trainings_queryset):
        """Calculate total candidates across all trainings"""
        total = 0
        for training in trainings_queryset:
            total += Candidate.objects.filter(training=training).count()
        return total
    
    def calculate_completed_candidates(self, trainings_queryset):
        """Calculate completed candidates across all trainings"""
        total = 0
        for training in trainings_queryset:
            total += Candidate.objects.filter(training=training, status='completed').count()
        return total
    
    def get_candidate_status_distribution(self, trainings_queryset):
        """Get candidate status distribution"""
        distribution = {'completed': 0, 'pending': 0, 'failed': 0}
        
        for training in trainings_queryset:
            for status, count in Candidate.objects.filter(training=training).values('status').annotate(count=Count('id')).values_list('status', 'count'):
                if status in distribution:
                    distribution[status] += count
        
        return distribution
    
    def calculate_average_modules_per_training(self, trainings_queryset):
        """Calculate average modules per training"""
        if not trainings_queryset.exists():
            return 0
        
        total_modules = sum(training.modules.count() for training in trainings_queryset)
        return total_modules / trainings_queryset.count()
    
    def calculate_average_materials_per_training(self, trainings_queryset):
        """Calculate average materials per training"""
        if not trainings_queryset.exists():
            return 0
        
        total_materials = sum(training.get_total_materials_count() for training in trainings_queryset)
        return total_materials / trainings_queryset.count()


# ==================== REPORT GENERATION VIEW ====================
class ReportGenerationView(APIView):
    """
    API endpoint for generating detailed reports based on user role and filters
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Validate input
            serializer = ReportFilterSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {'error': 'Invalid filter parameters', 'details': serializer.errors},
                    status=http_status.HTTP_400_BAD_REQUEST
                )
            
            filters = serializer.validated_data
            report_type = filters['report_type']
            format_type = filters.get('format', 'json')
            
            # Initialize report service
            report_service = ReportGenerationService(request.user)
            
            # Generate report based on type
            if report_type == 'users':
                report_data, summary_stats, key_metrics, total_records = report_service.generate_users_report(filters)
                report_title = "Users Report"
                
            elif report_type == 'incidents':
                report_data, summary_stats, key_metrics, total_records = report_service.generate_incidents_report(filters)
                report_title = "Incidents Report"
                
            elif report_type == 'audits':
                report_data, summary_stats, key_metrics, total_records = report_service.generate_audits_report(filters)
                report_title = "Audits Report"
                
            elif report_type == 'departments':
                report_data, summary_stats, key_metrics, total_records = report_service.generate_departments_report(filters)
                report_title = "Departments Report"
                
            elif report_type == 'trainings':
                report_data, summary_stats, key_metrics, total_records = report_service.generate_trainings_report(filters)
                report_title = "Trainings Report"
                
            elif report_type == 'activity_logs':
                # This would be similar to other reports - implementing basic version
                report_data, summary_stats, key_metrics, total_records = [], {}, [], 0
                report_title = "Activity Logs Report"
                
            elif report_type == 'user_training_progress':
                # This would be similar to other reports - implementing basic version
                report_data, summary_stats, key_metrics, total_records = [], {}, [], 0
                report_title = "User Training Progress Report"
                
            else:
                return Response(
                    {'error': f'Unsupported report type: {report_type}'},
                    status=http_status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate pagination
            page = filters.get('page', 1)
            page_size = filters.get('page_size', 50)
            total_pages = (total_records + page_size - 1) // page_size
            
            # Prepare summary
            summary = {
                'report_type': report_title,
                'filters_applied': {
                    k: v for k, v in filters.items() 
                    if v not in [None, '', []] and k not in ['page', 'page_size', 'format']
                },
                'total_records': total_records,
                'date_range': {
                    'start_date': filters.get('start_date'),
                    'end_date': filters.get('end_date')
                },
                'generated_at': timezone.now(),
                'generated_by': request.user.full_name,
                'summary_stats': summary_stats,
                'key_metrics': key_metrics,
                'data_preview': report_data[:5] if report_data else [],  # First 5 records as preview
                'export_format': format_type,
                'total_pages': total_pages,
                'current_page': page
            }
            
            # Prepare response data
            response_data = {
                'summary': summary,
                'data': report_data,
                'pagination': {
                    'current_page': page,
                    'page_size': page_size,
                    'total_records': total_records,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                }
            }
            
            # Display on terminal if requested
            if format_type == 'terminal':
                self.display_report_on_terminal(summary, report_data)
            
            # Return response based on format
            if format_type == 'csv':
                return self.export_report_to_csv(response_data, report_title)
            else:  # JSON
                return Response(response_data, status=http_status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Report generation error: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to generate report', 'details': str(e)},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def display_report_on_terminal(self, summary, data):
        """Display report summary and data on terminal"""
        try:
            print("\n" + "="*80)
            print(f"REPORT: {summary['report_type']}")
            print("="*80)
            
            print(f"\nGENERATED BY: {summary['generated_by']}")
            print(f"GENERATED AT: {summary['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"TOTAL RECORDS: {summary['total_records']}")
            
            if summary['date_range']['start_date']:
                print(f"DATE RANGE: {summary['date_range']['start_date']} to {summary['date_range']['end_date']}")
            
            print("\n" + "-"*80)
            print("APPLIED FILTERS:")
            for key, value in summary['filters_applied'].items():
                print(f"  {key}: {value}")
            
            print("\n" + "-"*80)
            print("SUMMARY STATISTICS:")
            for key, value in summary['summary_stats'].items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    {sub_key}: {sub_value}")
                else:
                    print(f"  {key}: {value}")
            
            print("\n" + "-"*80)
            print("KEY METRICS:")
            for metric in summary['key_metrics']:
                print(f"  • {metric}")
            
            print("\n" + "-"*80)
            print(f"DATA PREVIEW (First {len(summary['data_preview'])} records):")
            if summary['data_preview']:
                # Display first record as sample
                first_record = summary['data_preview'][0]
                for key, value in first_record.items():
                    print(f"  {key}: {value}")
                print(f"\n  ... and {len(summary['data_preview'])-1} more records in preview")
            else:
                print("  No data to display")
            
            print("\n" + "-"*80)
            print(f"TOTAL DATA RECORDS: {len(data)}")
            
            if data:
                print("\nFIRST RECORD DETAILS:")
                first_data = data[0]
                for key, value in first_data.items():
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:97] + "..."
                    print(f"  {key}: {value_str}")
            
            print("\n" + "="*80 + "\n")
            
        except Exception as e:
            logger.error(f"Terminal display error: {str(e)}")
    
    def export_report_to_csv(self, response_data, report_title):
        """Export report to CSV format"""
        try:
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([report_title])
            writer.writerow(['Generated By:', response_data['summary']['generated_by']])
            writer.writerow(['Generated At:', response_data['summary']['generated_at'].strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Total Records:', response_data['summary']['total_records']])
            writer.writerow([])
            
            # Write summary statistics
            writer.writerow(['SUMMARY STATISTICS'])
            for key, value in response_data['summary']['summary_stats'].items():
                if isinstance(value, dict):
                    writer.writerow([f"{key}:"])
                    for sub_key, sub_value in value.items():
                        writer.writerow(['', sub_key, sub_value])
                else:
                    writer.writerow([key, value])
            writer.writerow([])
            
            # Write data headers if data exists
            if response_data['data']:
                writer.writerow(['DETAILED DATA'])
                # Get headers from first data item
                headers = list(response_data['data'][0].keys())
                writer.writerow(headers)
                
                # Write data rows
                for row in response_data['data']:
                    writer.writerow([row.get(header, '') for header in headers])
            
            # Prepare response
            csv_content = output.getvalue()
            response = HttpResponse(csv_content, content_type='text/csv')
            filename = f"{report_title.replace(' ', '_').lower()}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.error(f"CSV export error: {str(e)}")
            return Response(
                {'error': 'Failed to generate CSV export'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== ADDITIONAL REPORT ENDPOINTS ====================
class AvailableReportTypesView(APIView):
    """API endpoint to get available report types for the current user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # Base report types available to all users
            report_types = [
                {
                    'value': 'users',
                    'label': 'Users Report',
                    'description': 'Detailed report of users with filtering options',
                    'available': user.role in ['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
                },
                {
                    'value': 'incidents',
                    'label': 'Incidents Report',
                    'description': 'Comprehensive incident tracking and analysis report',
                    'available': user.role in ['admin', 'hr_manager', 'security_analyst', 'compliance_officer']
                },
                {
                    'value': 'audits',
                    'description': 'Compliance audit reports and findings',
                    'available': user.role in ['admin', 'compliance_officer', 'security_analyst']
                },
                {
                    'value': 'departments',
                    'label': 'Departments Report',
                    'description': 'Department-wise analysis and metrics',
                    'available': user.role in ['admin', 'hr_manager']
                },
                {
                    'value': 'trainings',
                    'label': 'Trainings Report',
                    'description': 'Training progress and completion reports',
                    'available': user.role in ['admin', 'hr_manager', 'security_analyst']
                },
                {
                    'value': 'activity_logs',
                    'label': 'Activity Logs Report',
                    'description': 'User activity and system logs report',
                    'available': user.role in ['admin', 'security_analyst', 'compliance_officer']
                },
                {
                    'value': 'user_training_progress',
                    'label': 'User Training Progress Report',
                    'description': 'Individual user training progress and performance',
                    'available': user.role in ['admin', 'hr_manager']
                }
            ]
            
            # Filter based on user role
            available_reports = [
                report for report in report_types 
                if report['available'] or user.role == 'admin'
            ]
            
            # Add filter options for each report type
            for report in available_reports:
                report['filters'] = self.get_available_filters_for_report(report['value'], user)
            
            return Response({'report_types': available_reports}, status=http_status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting report types: {str(e)}")
            return Response(
                {'error': 'Failed to get available report types'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_available_filters_for_report(self, report_type, user):
        """Get available filters for specific report type"""
        filters = []
        
        # Common filters
        if report_type in ['users', 'incidents', 'audits', 'activity_logs']:
            filters.append({
                'name': 'start_date',
                'type': 'date',
                'label': 'Start Date',
                'required': False
            })
            filters.append({
                'name': 'end_date',
                'type': 'date',
                'label': 'End Date',
                'required': False
            })
        
        # Report-specific filters
        if report_type == 'users':
            filters.append({
                'name': 'role',
                'type': 'select',
                'label': 'User Role',
                'options': [
                    {'value': role[0], 'label': role[1]} 
                    for role in CustomUser.ROLE_CHOICES
                ],
                'required': False
            })
            filters.append({
                'name': 'status',
                'type': 'select',
                'label': 'User Status',
                'options': [
                    {'value': status[0], 'label': status[1]} 
                    for status in CustomUser.STATUS_CHOICES
                ],
                'required': False
            })
            
            # Department filter based on user role
            if user.role in ['admin', 'hr_manager']:
                filters.append({
                    'name': 'department',
                    'type': 'select',
                    'label': 'Department',
                    'options': [
                        {'value': dept.id, 'label': dept.name}
                        for dept in Department.objects.filter(status='active')
                    ],
                    'required': False
                })
        
        elif report_type == 'incidents':
            filters.append({
                'name': 'severity',
                'type': 'select',
                'label': 'Severity Level',
                'options': [
                    {'value': 'critical', 'label': 'Critical'},
                    {'value': 'high', 'label': 'High'},
                    {'value': 'medium', 'label': 'Medium'},
                    {'value': 'low', 'label': 'Low'}
                ],
                'required': False
            })
            filters.append({
                'name': 'incident_status',
                'type': 'select',
                'label': 'Incident Status',
                'options': [
                    {'value': status[0], 'label': status[1]} 
                    for status in Incident.INCIDENT_STATUS_CHOICES
                ],
                'required': False
            })
        
        elif report_type == 'audits':
            filters.append({
                'name': 'audit_status',
                'type': 'select',
                'label': 'Audit Status',
                'options': [
                    {'value': status[0], 'label': status[1]} 
                    for status in ComplianceAudit.AUDIT_STATUS
                ],
                'required': False
            })
            filters.append({
                'name': 'compliance_standard',
                'type': 'select',
                'label': 'Compliance Standard',
                'options': [
                    {'value': std[0], 'label': std[1]} 
                    for std in ComplianceStandard.STANDARD_TYPES
                ],
                'required': False
            })
        
        return filters


class ReportHistoryView(APIView):
    """API endpoint to view report generation history"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # In a real implementation, you would store generated reports
            # For now, return a placeholder response
            return Response({
                'message': 'Report history endpoint',
                'note': 'Implement report storage and retrieval logic here'
            }, status=http_status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting report history: {str(e)}")
            return Response(
                {'error': 'Failed to get report history'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )