# riskAssessmentApp/utils.py - COMPLETE FIXED VERSION

from django.db.models import Count, Avg, Q, F, Sum, ExpressionWrapper, FloatField
from django.utils.timezone import now
from datetime import timedelta, datetime
from decimal import Decimal
import math
import logging
from incidentApp.models import Incident
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department

logger = logging.getLogger(__name__)


class RiskCalculator:
    """Utility class for calculating risk scores - UPDATED with real data"""
    
    # Risk factor weights (adjust based on importance)
    RISK_WEIGHTS = {
        'incident_frequency': 0.35,
        'incident_severity': 0.35,
        'user_behavior': 0.15,
        'resolution_time': 0.10,
        'compliance_violations': 0.05
    }
    
    # Severity to numeric mapping
    SEVERITY_SCORES = {
        'critical': 100,
        'high': 75,
        'medium': 50,
        'low': 25,
        'info': 10
    }
    
    @staticmethod
    def calculate_department_risk(department, timeframe_days=90):
        """Calculate comprehensive risk score for a department"""
        
        # Get department incidents
        incidents = Incident.objects.filter(
            department=department,
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).select_related('assigned_to', 'log')
        
        # Get department users (users in this department)
        department_users = CustomUser.objects.filter(
            Q(department=department) | Q(departments=department),
            is_active=True
        ).distinct()
        
        # Calculate risk factors
        risk_factors = []
        total_score = 0
        
        incident_count = incidents.count()
        user_count = department_users.count()
        
        # Log for debugging
        logger.info(f"Calculating risk for {department.name}: {incident_count} incidents, {user_count} users")
        
        # 1. Incident Frequency Factor (0-100)
        incidents_per_user = 0
        if user_count > 0:
            incidents_per_user = incident_count / user_count
            freq_score = min(100, (incidents_per_user / 5) * 100)
        else:
            freq_score = 0
        
        risk_factors.append({
            'name': 'Incident Frequency',
            'score': round(freq_score, 1),
            'weight': RiskCalculator.RISK_WEIGHTS['incident_frequency'],
            'description': f'{incident_count} incidents across {user_count} users ({incidents_per_user:.2f} per user)'
        })
        total_score += freq_score * RiskCalculator.RISK_WEIGHTS['incident_frequency']
        
        # 2. Incident Severity Factor
        severity_score = 0  # Initialize with default value
        if incident_count > 0:
            severity_sum = 0
            for incident in incidents:
                severity_sum += RiskCalculator.SEVERITY_SCORES.get(incident.severity, 25)
            avg_severity = severity_sum / incident_count
            severity_score = avg_severity
        else:
            severity_score = 0
        
        risk_factors.append({
            'name': 'Incident Severity',
            'score': round(severity_score, 1),
            'weight': RiskCalculator.RISK_WEIGHTS['incident_severity'],
            'description': f'Average severity: {severity_score:.1f} from {incident_count} incidents'
        })
        total_score += severity_score * RiskCalculator.RISK_WEIGHTS['incident_severity']
        
        # 3. User Behavior Factor
        behavior_score = 0  # Initialize with default value
        avg_failed = 0  # Initialize with default value
        if user_count > 0:
            total_failed = 0
            for user in department_users:
                failed_count = UserLog.objects.filter(
                    user=user,
                    is_success=False,
                    timestamp__gte=now() - timedelta(days=30)
                ).count()
                total_failed += min(failed_count, 20)
            
            avg_failed = total_failed / user_count if user_count > 0 else 0
            behavior_score = min(100, avg_failed * 10)
        else:
            behavior_score = 0
        
        risk_factors.append({
            'name': 'User Behavior',
            'score': round(behavior_score, 1),
            'weight': RiskCalculator.RISK_WEIGHTS['user_behavior'],
            'description': f'Average {avg_failed:.1f} failed activities per user'
        })
        total_score += behavior_score * RiskCalculator.RISK_WEIGHTS['user_behavior']
        
        # 4. Resolution Time Factor
        resolution_score = 0  # Initialize with default value
        avg_resolution = 0  # Initialize with default value
        resolved_incidents = incidents.filter(status__in=['resolved', 'closed'], resolved_at__isnull=False)
        if resolved_incidents.exists():
            resolution_hours = []
            for incident in resolved_incidents:
                if incident.resolved_at and incident.created_at:
                    delta = incident.resolved_at - incident.created_at
                    hours = delta.total_seconds() / 3600
                    resolution_hours.append(hours)
            
            if resolution_hours:
                avg_resolution = sum(resolution_hours) / len(resolution_hours)
                resolution_score = min(100, max(0, (avg_resolution - 24) / 48 * 100))
            else:
                resolution_score = 0
        else:
            resolution_score = 0
        
        risk_factors.append({
            'name': 'Resolution Time',
            'score': round(resolution_score, 1),
            'weight': RiskCalculator.RISK_WEIGHTS['resolution_time'],
            'description': f'Average resolution time: {avg_resolution:.1f} hours' if resolved_incidents.exists() else 'No resolved incidents'
        })
        total_score += resolution_score * RiskCalculator.RISK_WEIGHTS['resolution_time']
        
        # 5. Compliance Violations Factor
        compliance_incidents = incidents.filter(
            Q(title__icontains='policy') |
            Q(title__icontains='compliance') |
            Q(description__icontains='violation') |
            Q(severity__in=['critical', 'high'])
        ).count()
        
        compliance_score = min(100, compliance_incidents * 20)
        risk_factors.append({
            'name': 'Compliance Violations',
            'score': round(compliance_score, 1),
            'weight': RiskCalculator.RISK_WEIGHTS['compliance_violations'],
            'description': f'{compliance_incidents} compliance-related incidents'
        })
        total_score += compliance_score * RiskCalculator.RISK_WEIGHTS['compliance_violations']
        
        # Ensure score is within bounds
        total_score = max(0, min(100, total_score))
        
        # Determine risk level based on score
        risk_level = RiskCalculator.get_risk_level(total_score)
        
        # Calculate trend based on recent vs older incidents
        trend = RiskCalculator.calculate_trend(incidents)
        
        # Generate recommendations
        recommendations = RiskCalculator.generate_recommendations(total_score, risk_factors, department)
        
        logger.info(f"Department {department.name} - Risk Score: {total_score:.1f} ({risk_level})")
        
        return {
            'department_id': department.id,
            'department_name': department.name,
            'overall_risk_score': round(total_score, 1),
            'risk_level': risk_level,
            'incident_count': incident_count,
            'user_count': user_count,
            'average_severity': round(severity_score, 1) if incident_count > 0 else 0,
            'last_incident_date': incidents.order_by('-created_at').first().created_at if incidents.exists() else None,
            'risk_factors': risk_factors,
            'trend': trend,
            'recommendations': recommendations
        }
    @staticmethod
    def get_risk_level(score):
        """Convert numeric score to risk level"""
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        elif score >= 20:
            return 'low'
        else:
            return 'very_low'
    
    @staticmethod
    def calculate_trend(incidents):
        """Calculate risk trend based on incident pattern"""
        if not incidents.exists():
            return 'stable'
        
        now_time = now()
        last_30_days = incidents.filter(created_at__gte=now_time - timedelta(days=30)).count()
        previous_30_days = incidents.filter(
            created_at__gte=now_time - timedelta(days=60),
            created_at__lt=now_time - timedelta(days=30)
        ).count()
        
        if previous_30_days == 0:
            if last_30_days > 0:
                return 'increasing'
            return 'stable'
        
        ratio = last_30_days / previous_30_days
        if ratio > 1.5:
            return 'increasing'
        elif ratio < 0.5:
            return 'decreasing'
        return 'stable'
    
    @staticmethod
    def generate_recommendations(score, risk_factors, department):
        """Generate actionable recommendations based on risk factors"""
        recommendations = []
        
        if score >= 80:
            recommendations.append(f"🚨 CRITICAL: Immediate security audit required for {department.name}")
            recommendations.append("Implement emergency security controls")
            recommendations.append("Escalate to senior management for immediate action")
        elif score >= 60:
            recommendations.append(f"⚠️ HIGH: Schedule comprehensive security review for {department.name}")
            recommendations.append("Review and update access controls")
            recommendations.append("Conduct department-wide security training")
        elif score >= 40:
            recommendations.append(f"📋 MEDIUM: Monitor {department.name} for continued risk")
            recommendations.append("Implement additional security monitoring")
        else:
            recommendations.append(f"✅ LOW: Maintain current security posture for {department.name}")
            recommendations.append("Continue regular security awareness")
        
        for factor in risk_factors:
            if factor['score'] >= 70:
                if 'Incident Frequency' in factor['name']:
                    recommendations.append(f"Reduce incident frequency in {department.name} - investigate root causes")
                elif 'Incident Severity' in factor['name']:
                    recommendations.append(f"Address high-severity incidents in {department.name}")
                elif 'User Behavior' in factor['name']:
                    recommendations.append(f"Implement user behavior monitoring and training for {department.name}")
        
        return recommendations[:5]


class UserRiskAnalyzer:
    """Analyze risk profiles for individual users"""
    
    @staticmethod
    def calculate_user_risk(user, timeframe_days=90):
        """Calculate comprehensive risk score for a user"""
        
        # Get user incidents
        user_incidents = Incident.objects.filter(
            Q(created_by=user) | Q(assigned_to=user) | Q(log__user_email=user.email),
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).distinct()
        
        # Get user activity logs
        activity_logs = user.activity_logs.filter(
            timestamp__gte=now() - timedelta(days=30)
        )
        
        incident_count = user_incidents.count()
        
        # Use logger instead of print with level
        logger.info(f"Calculating risk for user: {user.email}")
        logger.info(f"  Incident count: {incident_count}")
        
        # 1. Incident-based risk (40% weight)
        if incident_count > 0:
            severity_sum = 0
            for incident in user_incidents:
                severity_score = RiskCalculator.SEVERITY_SCORES.get(incident.severity, 25)
                severity_sum += severity_score
                logger.info(f"    Incident {incident.incident_number}: severity={incident.severity}, score={severity_score}")
            
            avg_severity = severity_sum / incident_count
            incident_score = min(100, (incident_count * 15) + (avg_severity * 0.3))
            logger.info(f"  Incident score: {incident_score:.1f}")
        else:
            incident_score = 0
        
        # 2. Failed login risk (30% weight)
        failed_logins = activity_logs.filter(
            Q(activity='login_failed') | 
            Q(activity='login_otp_verify', is_success=False),
            is_success=False
        ).count()
        failed_score = min(100, failed_logins * 15)
        logger.info(f"  Failed logins: {failed_logins}, score: {failed_score:.1f}")
        
        # 3. Behavioral risk (30% weight)
        behavioral_score = UserRiskAnalyzer.calculate_behavioral_score(activity_logs)
        logger.info(f"  Behavioral score: {behavioral_score:.1f}")
        
        # Calculate overall risk
        total_score = (incident_score * 0.4) + (failed_score * 0.3) + (behavioral_score * 0.3)
        
        # Role-based adjustments
        role_multipliers = {
            'admin': 1.3,
            'hr_manager': 1.2,
            'security_analyst': 0.9,
            'compliance_officer': 1.0,
            'employee': 0.8
        }
        multiplier = role_multipliers.get(user.role, 1.0)
        total_score = min(100, total_score * multiplier)
        
        # Ensure users with incidents get at least a baseline score
        if incident_count > 0 and total_score < 30:
            total_score = 30 + (incident_count * 5)
            total_score = min(100, total_score)
        
        logger.info(f"  Final risk score: {total_score:.1f}")
        
        return {
            'user_id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role,
            'role_display': user.get_role_display() if hasattr(user, 'get_role_display') else user.role,
            'department_name': user.department.name if user.department else None,
            'risk_score': round(total_score, 1),
            'risk_level': RiskCalculator.get_risk_level(total_score),
            'incident_count': incident_count,
            'failed_logins': failed_logins,
            'last_incident_date': user_incidents.order_by('-created_at').first().created_at if user_incidents.exists() else None,
            'behavioral_score': round(behavioral_score, 1),
            'recent_activities': activity_logs.count()
        }
    
    @staticmethod
    def calculate_behavioral_score(activity_logs):
        """Calculate behavioral risk score based on activity patterns"""
        if not activity_logs.exists():
            return 0
        
        score = 0
        
        # Unusual hours (outside 9-5)
        unusual_hours = activity_logs.filter(
            Q(timestamp__hour__lt=8) | Q(timestamp__hour__gt=18)
        ).count()
        score += min(30, unusual_hours * 5)
        
        # Weekend activities
        weekend_activities = activity_logs.filter(
            timestamp__week_day__in=[6, 7]
        ).count()
        score += min(20, weekend_activities * 4)
        
        # Rapid sequential activities
        high_frequency = activity_logs.count() > 100
        if high_frequency:
            score += 20
        
        return min(100, score)


class SecurityMetricsCalculator:
    """Calculate overall security metrics"""
    
    @staticmethod
    def calculate_security_metrics(timeframe_days=90):
        """Calculate comprehensive security metrics"""
        
        incidents = Incident.objects.filter(
            created_at__gte=now() - timedelta(days=timeframe_days)
        )
        
        users = CustomUser.objects.filter(is_active=True)
        departments = Department.objects.filter(status='active')
        
        # Overall risk score
        department_scores = []
        for dept in departments:
            risk_data = RiskCalculator.calculate_department_risk(dept, timeframe_days)
            department_scores.append(risk_data['overall_risk_score'])
        
        total_risk_score = sum(department_scores) / len(department_scores) if department_scores else 0
        
        # Departments at risk
        departments_at_risk = len([score for score in department_scores if score >= 60])
        
        # High risk users
        high_risk_users = 0
        for user in users[:50]:
            user_risk = UserRiskAnalyzer.calculate_user_risk(user, 30)
            if user_risk['risk_score'] >= 60:
                high_risk_users += 1
        
        # Critical incidents
        critical_incidents = incidents.filter(severity='critical').count()
        high_incidents = incidents.filter(severity='high').count()
        
        # MTTR
        resolved_incidents = incidents.filter(
            status__in=['resolved', 'closed'],
            resolved_at__isnull=False,
            created_at__isnull=False
        )
        
        total_hours = 0
        count = 0
        for incident in resolved_incidents:
            delta = incident.resolved_at - incident.created_at
            total_hours += delta.total_seconds() / 3600
            count += 1
        
        mttr_hours = total_hours / count if count > 0 else 0
        
        # Compliance rate
        total_incidents = incidents.count()
        sla_compliant = incidents.filter(sla_violated=False).count()
        compliance_rate = (sla_compliant / total_incidents * 100) if total_incidents > 0 else 100
        
        return {
            'total_risk_score': round(total_risk_score, 1),
            'departments_at_risk': departments_at_risk,
            'high_risk_users': high_risk_users,
            'critical_incidents': critical_incidents,
            'high_incidents': high_incidents,
            'mttr_hours': round(mttr_hours, 1),
            'compliance_rate': round(compliance_rate, 1),
            'total_incidents': total_incidents,
            'total_departments': departments.count(),
            'total_users': users.count()
        }


class RiskTrendAnalyzer:
    """Analyze risk trends over time"""
    
    @staticmethod
    def calculate_risk_trends(timeframe_days=90, period='weekly'):
        """Calculate risk trends over specified periods"""
        
        trends = []
        now_time = now()
        
        if period == 'weekly':
            max_weeks = min(12, timeframe_days // 7)
            for i in range(max_weeks):
                week_end = now_time - timedelta(days=i*7)
                week_start = week_end - timedelta(days=7)
                
                week_incidents = Incident.objects.filter(
                    created_at__gte=week_start,
                    created_at__lt=week_end
                )
                
                if week_incidents.exists():
                    total_risk = 0
                    for inc in week_incidents:
                        risk = RiskCalculator.SEVERITY_SCORES.get(inc.severity, 25)
                        total_risk += risk
                    avg_risk = total_risk / week_incidents.count()
                else:
                    avg_risk = 0
                
                user_emails = week_incidents.values_list('created_by__email', flat=True).distinct()
                
                trends.append({
                    'period': f'Week {max_weeks - i}',
                    'risk_score': round(avg_risk, 1),
                    'incident_count': week_incidents.count(),
                    'user_count': len(set(user_emails))
                })
            
            trends.reverse()
        
        elif period == 'monthly':
            max_months = min(6, timeframe_days // 30)
            for i in range(max_months):
                month_end = now_time - timedelta(days=i*30)
                month_start = month_end - timedelta(days=30)
                
                month_incidents = Incident.objects.filter(
                    created_at__gte=month_start,
                    created_at__lt=month_end
                )
                
                if month_incidents.exists():
                    total_risk = 0
                    for inc in month_incidents:
                        risk = RiskCalculator.SEVERITY_SCORES.get(inc.severity, 25)
                        total_risk += risk
                    avg_risk = total_risk / month_incidents.count()
                else:
                    avg_risk = 0
                
                user_emails = month_incidents.values_list('created_by__email', flat=True).distinct()
                
                trends.append({
                    'period': f'Month {max_months - i}',
                    'risk_score': round(avg_risk, 1),
                    'incident_count': month_incidents.count(),
                    'user_count': len(set(user_emails))
                })
            
            trends.reverse()
        
        return trends
    
    @staticmethod
    def analyze_trend_pattern(trends):
        """Analyze the pattern of risk trends"""
        if len(trends) < 2:
            return "Insufficient data for trend analysis"
        
        scores = [t['risk_score'] for t in trends]
        first_score = scores[0]
        last_score = scores[-1]
        
        if last_score > first_score * 1.2:
            return "Risk is increasing significantly - immediate attention required"
        elif last_score > first_score * 1.05:
            return "Risk is slowly increasing - monitor closely"
        elif last_score < first_score * 0.8:
            return "Risk is decreasing - good progress"
        elif last_score < first_score * 0.95:
            return "Risk is slightly decreasing - continue current efforts"
        else:
            return "Risk is stable - maintain current security posture"


class VulnerabilityAssessor:
    """Assess vulnerabilities across different categories"""
    
    @staticmethod
    def assess_vulnerabilities():
        """Assess vulnerabilities across security categories"""
        
        vulnerabilities = []
        
        # Get real data for assessment
        total_incidents = Incident.objects.count()
        critical_incidents = Incident.objects.filter(severity='critical').count()
        high_incidents = Incident.objects.filter(severity='high').count()
        
        # 1. Access Control
        access_incidents = Incident.objects.filter(
            Q(title__icontains='access') |
            Q(title__icontains='permission') |
            Q(description__icontains='unauthorized')
        ).count()
        
        access_score = max(0, 100 - (access_incidents * 10) - (critical_incidents * 5))
        vulnerabilities.append({
            'category': 'Access Control',
            'score': round(access_score, 1),
            'max_score': 100,
            'description': 'Evaluation of user access permissions, role-based controls, and authentication mechanisms',
            'recommendations': [
                "Implement role-based access control (RBAC)",
                "Enforce principle of least privilege",
                "Regularly review user permissions"
            ] if access_score < 70 else ["Maintain current access control measures"]
        })
        
        # 2. Data Security
        data_incidents = Incident.objects.filter(
            Q(title__icontains='data') |
            Q(title__icontains='breach') |
            Q(description__icontains='sensitive')
        ).count()
        
        data_score = max(0, 100 - (data_incidents * 15))
        vulnerabilities.append({
            'category': 'Data Security',
            'score': round(data_score, 1),
            'max_score': 100,
            'description': 'Protection of sensitive data, encryption, and data handling practices',
            'recommendations': [
                "Implement data classification scheme",
                "Encrypt sensitive data at rest and in transit",
                "Establish data retention policies"
            ] if data_score < 70 else ["Continue data protection practices"]
        })
        
        # 3. Network Security
        network_incidents = Incident.objects.filter(
            Q(title__icontains='network') |
            Q(title__icontains='firewall') |
            Q(description__icontains='connection')
        ).count()
        
        network_score = max(0, 100 - (network_incidents * 10) - (high_incidents * 3))
        vulnerabilities.append({
            'category': 'Network Security',
            'score': round(network_score, 1),
            'max_score': 100,
            'description': 'Network infrastructure protection, segmentation, and monitoring',
            'recommendations': [
                "Implement network segmentation",
                "Deploy intrusion detection systems",
                "Regular vulnerability scanning"
            ] if network_score < 70 else ["Maintain network security monitoring"]
        })
        
        # 4. Compliance
        compliance_incidents = Incident.objects.filter(
            Q(title__icontains='compliance') |
            Q(title__icontains='policy') |
            Q(title__icontains='violation')
        ).count()
        
        total_incidents_with_sla = Incident.objects.filter(sla_due_date__isnull=False).count()
        sla_violations = Incident.objects.filter(sla_violated=True).count()
        sla_compliance = ((total_incidents_with_sla - sla_violations) / total_incidents_with_sla * 100) if total_incidents_with_sla > 0 else 100
        
        compliance_score = max(0, 100 - (compliance_incidents * 20) - (100 - sla_compliance))
        vulnerabilities.append({
            'category': 'Compliance',
            'score': round(compliance_score, 1),
            'max_score': 100,
            'description': 'Adherence to security policies, regulations, and standards',
            'recommendations': [
                "Conduct regular compliance audits",
                "Update security policies quarterly",
                "Provide compliance training"
            ] if compliance_score < 70 else ["Continue compliance monitoring"]
        })
        
        # 5. User Behavior
        failed_logins = UserLog.objects.filter(
            Q(activity='login_failed') | Q(activity='login_otp_verify', is_success=False),
            is_success=False,
            timestamp__gte=now() - timedelta(days=30)
        ).count()
        
        user_score = max(0, 100 - (failed_logins / 10))
        vulnerabilities.append({
            'category': 'User Behavior',
            'score': round(user_score, 1),
            'max_score': 100,
            'description': 'Analysis of user activities, security awareness, and behavioral patterns',
            'recommendations': [
                "Implement security awareness training",
                "Monitor for anomalous user behavior",
                "Establish clear security policies"
            ] if user_score < 70 else ["Continue user security awareness"]
        })
        
        # 6. Incident Response
        resolution_score = 100
        if total_incidents > 0:
            resolved = Incident.objects.filter(status__in=['resolved', 'closed']).count()
            resolution_rate = (resolved / total_incidents) * 100
            resolution_score = resolution_rate
        
        vulnerabilities.append({
            'category': 'Incident Response',
            'score': round(resolution_score, 1),
            'max_score': 100,
            'description': 'Effectiveness of incident detection, response, and recovery processes',
            'recommendations': [
                "Develop incident response playbook",
                "Conduct regular incident response drills",
                "Establish clear communication channels"
            ] if resolution_score < 70 else ["Maintain incident response readiness"]
        })
        
        return vulnerabilities