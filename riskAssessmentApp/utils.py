#riskAssessmentApp/utils.py
from django.db.models import Count, Avg, Q, F, Sum, ExpressionWrapper, FloatField
from django.utils.timezone import now
from datetime import timedelta, datetime
from decimal import Decimal
import math
import logging
from django.utils.timezone import now
from datetime import timedelta
from incidentApp.models import Incident
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department

logger = logging.getLogger(__name__)


class RiskCalculator:
    """Utility class for calculating risk scores"""
    
    # Risk factor weights (adjust based on importance)
    RISK_WEIGHTS = {
        'incident_frequency': 0.25,
        'incident_severity': 0.30,
        'user_behavior': 0.20,
        'resolution_time': 0.15,
        'compliance_violations': 0.10
    }
    
    @staticmethod
    def calculate_department_risk(department, timeframe_days=90):
        """Calculate comprehensive risk score for a department"""
        
        # Get department incidents
        incidents = department.incidents.filter(
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).select_related('assigned_to', 'log')
        
        # Get department users
        department_users = department.users.filter(is_active=True)
        
        # Calculate risk factors
        risk_factors = []
        total_score = 0
        
        # 1. Incident Frequency Factor
        incident_count = incidents.count()
        freq_score = min(100, incident_count * 5)  # Each incident adds 5 points
        risk_factors.append({
            'name': 'Incident Frequency',
            'score': freq_score,
            'weight': RiskCalculator.RISK_WEIGHTS['incident_frequency'],
            'description': f'{incident_count} incidents in last {timeframe_days} days'
        })
        total_score += freq_score * RiskCalculator.RISK_WEIGHTS['incident_frequency']
        
        # 2. Incident Severity Factor
        severity_scores = {
            'critical': 100,
            'high': 75,
            'medium': 50,
            'low': 25
        }
        
        if incident_count > 0:
            severity_avg = incidents.aggregate(
                avg_severity=Avg(F('risk_score'))
            )['avg_severity'] or 0
            severity_score = min(100, severity_avg)
        else:
            severity_score = 0
        
        risk_factors.append({
            'name': 'Incident Severity',
            'score': severity_score,
            'weight': RiskCalculator.RISK_WEIGHTS['incident_severity'],
            'description': f'Average incident severity: {severity_score:.1f}'
        })
        total_score += severity_score * RiskCalculator.RISK_WEIGHTS['incident_severity']
        
        # 3. User Behavior Factor
        user_count = department_users.count()
        if user_count > 0:
            # Calculate failed logins per user
            failed_logins = 0
            for user in department_users:
                recent_failed = user.activity_logs.filter(
                    activity='login_failed',
                    is_success=False,
                    timestamp__gte=now() - timedelta(days=30)
                ).count()
                failed_logins += min(recent_failed, 10)  # Cap at 10 per user
            
            behavior_score = min(100, failed_logins * 10)
        else:
            behavior_score = 0
        
        risk_factors.append({
            'name': 'User Behavior',
            'score': behavior_score,
            'weight': RiskCalculator.RISK_WEIGHTS['user_behavior'],
            'description': f'User behavior risk assessment'
        })
        total_score += behavior_score * RiskCalculator.RISK_WEIGHTS['user_behavior']
        
        # 4. Resolution Time Factor
        resolved_incidents = incidents.filter(status__in=['resolved', 'closed'])
        if resolved_incidents.exists():
            resolution_times = []
            for incident in resolved_incidents:
                if incident.resolved_at and incident.created_at:
                    delta = incident.resolved_at - incident.created_at
                    resolution_times.append(delta.total_seconds() / 3600)  # Hours
            
            if resolution_times:
                avg_resolution = sum(resolution_times) / len(resolution_times)
                # Score: <24h = 0, >72h = 100, linear in between
                resolution_score = min(100, max(0, (avg_resolution - 24) / 48 * 100))
            else:
                resolution_score = 0
        else:
            resolution_score = 0
        
        risk_factors.append({
            'name': 'Resolution Time',
            'score': resolution_score,
            'weight': RiskCalculator.RISK_WEIGHTS['resolution_time'],
            'description': f'Average resolution time factor'
        })
        total_score += resolution_score * RiskCalculator.RISK_WEIGHTS['resolution_time']
        
        # 5. Compliance Violations Factor
        compliance_incidents = incidents.filter(
            Q(title__icontains='policy') |
            Q(title__icontains='compliance') |
            Q(description__icontains='violation') |
            Q(severity__in=['critical', 'high'])
        )
        
        compliance_score = min(100, compliance_incidents.count() * 20)
        risk_factors.append({
            'name': 'Compliance Violations',
            'score': compliance_score,
            'weight': RiskCalculator.RISK_WEIGHTS['compliance_violations'],
            'description': f'{compliance_incidents.count()} compliance-related incidents'
        })
        total_score += compliance_score * RiskCalculator.RISK_WEIGHTS['compliance_violations']
        
        # Apply departmental risk modifiers
        total_score = RiskCalculator.apply_department_modifiers(total_score, department)
        
        # Ensure score is within bounds
        total_score = max(0, min(100, total_score))
        
        return {
            'department_id': department.id,
            'department_name': department.name,
            'overall_risk_score': round(total_score, 1),
            'risk_level': RiskCalculator.get_risk_level(total_score),
            'incident_count': incident_count,
            'user_count': user_count,
            'average_severity': round(severity_score, 1),
            'last_incident_date': incidents.order_by('-created_at').first().created_at if incidents.exists() else None,
            'risk_factors': risk_factors,
            'trend': RiskCalculator.calculate_trend(department, timeframe_days),
            'recommendations': RiskCalculator.generate_recommendations(total_score, risk_factors)
        }
    
    @staticmethod
    def apply_department_modifiers(score, department):
        """Apply modifiers based on department characteristics"""
        modifiers = 0
        
        # Size modifier (larger departments might have more inherent risk)
        user_count = department.users.count()
        if user_count > 50:
            modifiers += 10
        elif user_count > 20:
            modifiers += 5
        
        # Department type modifier (IT departments might have different risk profiles)
        department_name_lower = department.name.lower()
        if any(keyword in department_name_lower for keyword in ['it', 'tech', 'security', 'network']):
            modifiers += 15  # Higher baseline for tech departments
        elif any(keyword in department_name_lower for keyword in ['hr', 'legal', 'compliance']):
            modifiers += 5  # Lower baseline for compliance-focused departments
        
        return min(100, score + modifiers)
    
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
            return 'very low'
    
    @staticmethod
    def calculate_trend(department, timeframe_days):
        """Calculate risk trend (increasing, decreasing, stable)"""
        # Compare recent vs older incidents
        recent_cutoff = now() - timedelta(days=timeframe_days // 2)
        old_cutoff = now() - timedelta(days=timeframe_days)
        
        recent_incidents = department.incidents.filter(
            created_at__gte=recent_cutoff
        ).count()
        
        older_incidents = department.incidents.filter(
            created_at__gte=old_cutoff,
            created_at__lt=recent_cutoff
        ).count()
        
        if recent_incidents == 0 and older_incidents == 0:
            return 'stable'
        
        if older_incidents == 0:
            return 'increasing' if recent_incidents > 0 else 'stable'
        
        trend_ratio = recent_incidents / older_incidents if older_incidents > 0 else 1
        
        if trend_ratio > 1.5:
            return 'increasing'
        elif trend_ratio < 0.5:
            return 'decreasing'
        else:
            return 'stable'
    
    @staticmethod
    def generate_recommendations(score, risk_factors):
        """Generate actionable recommendations based on risk factors"""
        recommendations = []
        
        if score >= 60:
            recommendations.append("Conduct immediate security audit")
            recommendations.append("Schedule department-wide security training")
        
        # Check specific risk factors
        for factor in risk_factors:
            if factor['score'] >= 70:
                if 'Incident Frequency' in factor['name']:
                    recommendations.append("Implement stricter access controls")
                    recommendations.append("Review user permissions quarterly")
                elif 'Incident Severity' in factor['name']:
                    recommendations.append("Enhance monitoring for critical systems")
                    recommendations.append("Create incident response playbook")
                elif 'User Behavior' in factor['name']:
                    recommendations.append("Implement mandatory security awareness training")
                    recommendations.append("Enforce stronger password policies")
                elif 'Resolution Time' in factor['name']:
                    recommendations.append("Establish SLA for incident response")
                    recommendations.append("Assign dedicated incident response team")
                elif 'Compliance Violations' in factor['name']:
                    recommendations.append("Conduct compliance review")
                    recommendations.append("Update security policies")
        
        # Add general recommendations
        if score < 40:
            recommendations.append("Continue current security practices")
            recommendations.append("Regular monitoring recommended")
        
        if len(recommendations) == 0:
            recommendations.append("No specific recommendations at this time")
        
        return recommendations[:5]  # Limit to top 5 recommendations


class UserRiskAnalyzer:
    """Analyze risk profiles for individual users"""
    
    @staticmethod
    def calculate_user_risk(user, timeframe_days=90):
        """Calculate comprehensive risk score for a user"""
        
        # Get user incidents
        user_incidents = Incident.objects.filter(
            Q(log__user_email=user.email) |
            Q(assigned_to=user) |
            Q(created_by=user),
            created_at__gte=now() - timedelta(days=timeframe_days)
        )
        
        # Get user activity logs
        activity_logs = user.activity_logs.filter(
            timestamp__gte=now() - timedelta(days=30)
        )
        
        # Calculate risk factors
        incident_count = user_incidents.count()
        
        # 1. Incident-based risk (40% weight)
        incident_score = min(100, incident_count * 25)
        
        # 2. Failed login risk (30% weight)
        failed_logins = activity_logs.filter(
            activity='login_failed',
            is_success=False
        ).count()
        failed_score = min(100, failed_logins * 20)
        
        # 3. Behavioral risk (30% weight)
        behavioral_score = UserRiskAnalyzer.calculate_behavioral_score(activity_logs)
        
        # Calculate overall risk
        total_score = (
            incident_score * 0.4 +
            failed_score * 0.3 +
            behavioral_score * 0.3
        )
        
        # Role-based adjustments
        if user.role == 'admin':
            total_score *= 1.5  # Admins have higher inherent risk
        elif user.role == 'security_analyst':
            total_score *= 0.8  # Security analysts have lower risk
        
        total_score = min(100, total_score)
        
        return {
            'user_id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role,
            'department_name': user.department.name if user.department else None,
            'risk_score': round(total_score, 1),
            'risk_level': RiskCalculator.get_risk_level(total_score),
            'incident_count': incident_count,
            'last_incident_date': user_incidents.order_by('-created_at').first().created_at if user_incidents.exists() else None,
            'behavioral_score': round(behavioral_score, 1)
        }
    
    @staticmethod
    def calculate_behavioral_score(activity_logs):
        """Calculate behavioral risk score based on activity patterns"""
        score = 0
        
        # Check for unusual activity patterns
        # 1. Multiple activities in short time
        recent_count = activity_logs.filter(
            timestamp__gte=now() - timedelta(hours=1)
        ).count()
        score += min(50, recent_count * 5)
        
        # 2. Failed activities
        failed_count = activity_logs.filter(is_success=False).count()
        score += min(30, failed_count * 10)
        
        # 3. Unusual hours (outside 9-5)
        unusual_hours = activity_logs.filter(
            timestamp__hour__lt=9,
            timestamp__hour__gte=17
        ).count()
        score += min(20, unusual_hours * 5)
        
        return min(100, score)


class SecurityMetricsCalculator:
    """Calculate overall security metrics"""
    
    @staticmethod
    def calculate_security_metrics(timeframe_days=90):
        """Calculate comprehensive security metrics"""
        
        # Get all incidents in timeframe
        incidents = Incident.objects.filter(
            created_at__gte=now() - timedelta(days=timeframe_days)
        )
        
        # Get all active users
        users = CustomUser.objects.filter(is_active=True)
        
        # 1. Overall risk score (weighted average of department scores)
        departments = Department.objects.filter(status='active')
        department_scores = []
        for dept in departments:
            risk_data = RiskCalculator.calculate_department_risk(dept, timeframe_days)
            department_scores.append(risk_data['overall_risk_score'])
        
        total_risk_score = sum(department_scores) / len(department_scores) if department_scores else 0
        
        # 2. Departments at risk
        departments_at_risk = len([score for score in department_scores if score >= 60])
        
        # 3. High risk users
        high_risk_users = 0
        for user in users[:50]:  # Sample first 50 users for performance
            user_risk = UserRiskAnalyzer.calculate_user_risk(user, timeframe_days)
            if user_risk['risk_score'] >= 60:
                high_risk_users += 1
        
        # 4. Critical incidents
        critical_incidents = incidents.filter(severity='critical').count()
        
        # 5. Mean Time to Resolution (MTTR)
        resolved_incidents = incidents.filter(status__in=['resolved', 'closed'])
        total_resolution_time = 0
        count = 0
        
        for incident in resolved_incidents:
            if incident.resolved_at and incident.created_at:
                delta = incident.resolved_at - incident.created_at
                total_resolution_time += delta.total_seconds() / 3600  # Hours
                count += 1
        
        mttr_hours = total_resolution_time / count if count > 0 else 0
        
        # 6. Compliance rate
        total_incidents = incidents.count()
        sla_compliant = incidents.filter(sla_violated=False).count()
        compliance_rate = (sla_compliant / total_incidents * 100) if total_incidents > 0 else 100
        
        return {
            'total_risk_score': round(total_risk_score, 1),
            'departments_at_risk': departments_at_risk,
            'high_risk_users': high_risk_users,
            'critical_incidents': critical_incidents,
            'mttr_hours': round(mttr_hours, 1),
            'compliance_rate': round(compliance_rate, 1)
        }


class RiskTrendAnalyzer:
    """Analyze risk trends over time"""
    
    @staticmethod
    def calculate_risk_trends(timeframe_days=90, period='weekly'):
        """Calculate risk trends over specified periods"""
        
        trends = []
        now_time = now()
        
        if period == 'weekly':
            periods = min(12, timeframe_days // 7)  # Max 12 weeks
            for i in range(periods):
                week_start = now_time - timedelta(days=(i+1)*7)
                week_end = now_time - timedelta(days=i*7)
                
                # Get incidents for this week
                week_incidents = Incident.objects.filter(
                    created_at__gte=week_start,
                    created_at__lt=week_end
                )
                
                # Get unique users with incidents
                user_emails = week_incidents.values_list('log__user_email', flat=True).distinct()
                
                # Calculate average risk for incidents
                if week_incidents.exists():
                    avg_risk = week_incidents.aggregate(
                        avg_risk=Avg('risk_score')
                    )['avg_risk'] or 0
                else:
                    avg_risk = 0
                
                trends.append({
                    'period': f'Week {i+1}',
                    'risk_score': round(avg_risk, 1),
                    'incident_count': week_incidents.count(),
                    'user_count': len(set(user_emails))
                })
        
        elif period == 'monthly':
            periods = min(6, timeframe_days // 30)  # Max 6 months
            for i in range(periods):
                month_start = now_time - timedelta(days=(i+1)*30)
                month_end = now_time - timedelta(days=i*30)
                
                # Get incidents for this month
                month_incidents = Incident.objects.filter(
                    created_at__gte=month_start,
                    created_at__lt=month_end
                )
                
                # Get unique users with incidents
                user_emails = month_incidents.values_list('log__user_email', flat=True).distinct()
                
                # Calculate average risk for incidents
                if month_incidents.exists():
                    avg_risk = month_incidents.aggregate(
                        avg_risk=Avg('risk_score')
                    )['avg_risk'] or 0
                else:
                    avg_risk = 0
                
                trends.append({
                    'period': f'Month {i+1}',
                    'risk_score': round(avg_risk, 1),
                    'incident_count': month_incidents.count(),
                    'user_count': len(set(user_emails))
                })
        
        # Reverse to show oldest first
        trends.reverse()
        
        return trends


class VulnerabilityAssessor:
    """Assess vulnerabilities across different categories"""
    
    @staticmethod
    def assess_vulnerabilities():
        """Assess vulnerabilities across security categories"""
        
        vulnerabilities = []
        
        # 1. Access Control
        access_score = VulnerabilityAssessor.assess_access_control()
        vulnerabilities.append({
            'category': 'Access Control',
            'score': access_score,
            'max_score': 100,
            'description': 'Evaluation of user access permissions, role-based controls, and authentication mechanisms',
            'recommendations': [
                "Implement role-based access control (RBAC)",
                "Enforce principle of least privilege",
                "Regularly review user permissions",
                "Implement multi-factor authentication"
            ]
        })
        
        # 2. Data Security
        data_score = VulnerabilityAssessor.assess_data_security()
        vulnerabilities.append({
            'category': 'Data Security',
            'score': data_score,
            'max_score': 100,
            'description': 'Protection of sensitive data, encryption, and data handling practices',
            'recommendations': [
                "Implement data classification scheme",
                "Encrypt sensitive data at rest and in transit",
                "Establish data retention policies",
                "Conduct regular data security audits"
            ]
        })
        
        # 3. Network Security
        network_score = VulnerabilityAssessor.assess_network_security()
        vulnerabilities.append({
            'category': 'Network Security',
            'score': network_score,
            'max_score': 100,
            'description': 'Network infrastructure protection, segmentation, and monitoring',
            'recommendations': [
                "Implement network segmentation",
                "Deploy intrusion detection systems",
                "Regular vulnerability scanning",
                "Monitor network traffic for anomalies"
            ]
        })
        
        # 4. Compliance
        compliance_score = VulnerabilityAssessor.assess_compliance()
        vulnerabilities.append({
            'category': 'Compliance',
            'score': compliance_score,
            'max_score': 100,
            'description': 'Adherence to security policies, regulations, and standards',
            'recommendations': [
                "Conduct regular compliance audits",
                "Update security policies quarterly",
                "Provide compliance training",
                "Document security controls and procedures"
            ]
        })
        
        # 5. User Behavior
        user_score = VulnerabilityAssessor.assess_user_behavior()
        vulnerabilities.append({
            'category': 'User Behavior',
            'score': user_score,
            'max_score': 100,
            'description': 'Analysis of user activities, security awareness, and behavioral patterns',
            'recommendations': [
                "Implement security awareness training",
                "Monitor for anomalous user behavior",
                "Establish clear security policies",
                "Regular phishing simulations"
            ]
        })
        
        # 6. Incident Response
        incident_score = VulnerabilityAssessor.assess_incident_response()
        vulnerabilities.append({
            'category': 'Incident Response',
            'score': incident_score,
            'max_score': 100,
            'description': 'Effectiveness of incident detection, response, and recovery processes',
            'recommendations': [
                "Develop incident response playbook",
                "Conduct regular incident response drills",
                "Establish clear communication channels",
                "Implement automated incident detection"
            ]
        })
        
        return vulnerabilities
    
    @staticmethod
    def assess_access_control():
        """Assess access control vulnerabilities"""
        score = 50  # Base score
        
        # Check for incidents related to access control
        access_incidents = Incident.objects.filter(
            Q(title__icontains='access') |
            Q(title__icontains='permission') |
            Q(title__icontains='authentication') |
            Q(description__icontains='unauthorized')
        ).count()
        
        score -= min(40, access_incidents * 5)
        
        # Check for users without MFA (simulated - would need actual MFA data)
        score -= 10  # Assuming some users don't have MFA
        
        return max(0, min(100, score))
    
    @staticmethod
    def assess_data_security():
        """Assess data security vulnerabilities"""
        score = 60  # Base score
        
        # Check for data-related incidents
        data_incidents = Incident.objects.filter(
            Q(title__icontains='data') |
            Q(title__icontains='breach') |
            Q(title__icontains='leak')
        ).count()
        
        score -= min(30, data_incidents * 10)
        
        return max(0, min(100, score))
    
    @staticmethod
    def assess_network_security():
        """Assess network security vulnerabilities"""
        score = 55  # Base score
        
        # Check for network-related incidents
        network_incidents = Incident.objects.filter(
            Q(title__icontains='network') |
            Q(title__icontains='firewall') |
            Q(title__icontains='intrusion') |
            Q(description__icontains='DDoS')
        ).count()
        
        score -= min(35, network_incidents * 7)
        
        return max(0, min(100, score))
    
    @staticmethod
    def assess_compliance():
        """Assess compliance vulnerabilities"""
        score = 65  # Base score
        
        # Check for compliance incidents
        compliance_incidents = Incident.objects.filter(
            Q(title__icontains='compliance') |
            Q(title__icontains='policy') |
            Q(title__icontains='violation') |
            Q(severity='critical')
        ).count()
        
        score -= min(45, compliance_incidents * 9)
        
        # Check SLA compliance
        total_incidents = Incident.objects.count()
        sla_violations = Incident.objects.filter(sla_violated=True).count()
        if total_incidents > 0:
            compliance_rate = (total_incidents - sla_violations) / total_incidents * 100
            score = score * 0.7 + compliance_rate * 0.3
        
        return max(0, min(100, score))
    
    @staticmethod
    def assess_user_behavior():
        """Assess user behavior vulnerabilities"""
        score = 70  # Base score
        
        # Check for failed logins
        failed_logins = UserLog.objects.filter(
            activity='login_failed',
            is_success=False,
            timestamp__gte=now() - timedelta(days=30)
        ).count()
        
        score -= min(40, failed_logins * 2)
        
        return max(0, min(100, score))
    
    @staticmethod
    def assess_incident_response():
        """Assess incident response vulnerabilities"""
        score = 45  # Base score
        
        # Check resolution times
        resolved_incidents = Incident.objects.filter(
            status__in=['resolved', 'closed'],
            resolved_at__isnull=False,
            created_at__isnull=False
        )
        
        if resolved_incidents.exists():
            resolution_times = []
            for incident in resolved_incidents:
                delta = incident.resolved_at - incident.created_at
                resolution_times.append(delta.total_seconds() / 3600)
            
            avg_resolution = sum(resolution_times) / len(resolution_times)
            if avg_resolution > 48:  # > 2 days
                score -= 30
            elif avg_resolution > 24:  # > 1 day
                score -= 15
        
        return max(0, min(100, score))