from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging
from django.utils.timezone import now
from datetime import timedelta

from .serializers import (
    DepartmentRiskAssessmentSerializer,
    UserRiskProfileSerializer,
    SecurityMetricsSerializer,
    RiskTrendSerializer,
    VulnerabilityAssessmentSerializer
)
from .utils import (
    RiskCalculator,
    UserRiskAnalyzer,
    SecurityMetricsCalculator,
    RiskTrendAnalyzer,
    VulnerabilityAssessor
)
from departmentApp.models import Department
from userApp.models import CustomUser
from incidentApp.models import Incident
from userApp.utils import ActivityLogger

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_risk_assessments(request):
    """Get risk assessments for all departments"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view risk assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        
        # Get all active departments
        departments = Department.objects.filter(status='active')
        
        # Calculate risk for each department
        risk_assessments = []
        for department in departments:
            risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
            
            # Filter based on user permissions
            if user.role == 'security_analyst':
                if user.departments.exists() and department not in user.departments.all():
                    continue  # Skip departments not assigned to this analyst
            
            risk_assessments.append(risk_data)
        
        # Sort by risk score (highest first)
        risk_assessments.sort(key=lambda x: x['overall_risk_score'], reverse=True)
        
        serializer = DepartmentRiskAssessmentSerializer(risk_assessments, many=True)
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='risk_assessment_view',
            description=f'Viewed department risk assessments for {len(risk_assessments)} departments',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "count": len(risk_assessments),
            "assessments": serializer.data
        })
    
    except Exception as e:
        logger.error(f"Error getting department risk assessments: {str(e)}")
        return Response(
            {"error": "Failed to get risk assessments."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_risk_detail(request, department_id):
    """Get detailed risk assessment for a specific department"""
    try:
        user = request.user
        department = get_object_or_404(Department, id=department_id)
        
        # Check permissions
        if not (user.is_admin or user.is_hr):
            if user.role == 'security_analyst':
                if user.departments.exists() and department not in user.departments.all():
                    return Response(
                        {"error": "You don't have permission to view this department's risk assessment."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {"error": "You don't have permission to view risk assessments."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        
        # Calculate detailed risk assessment
        risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
        
        # Get department incidents for additional context
        incidents = department.incidents.filter(
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).order_by('-created_at')[:10]
        
        # Get high-risk users in department
        department_users = department.users.filter(is_active=True)
        high_risk_users = []
        
        for dept_user in department_users[:10]:  # Limit to 10 users for performance
            user_risk = UserRiskAnalyzer.calculate_user_risk(dept_user, 30)  # Last 30 days
            if user_risk['risk_score'] >= 60:
                high_risk_users.append(user_risk)
        
        # Sort high risk users by score
        high_risk_users.sort(key=lambda x: x['risk_score'], reverse=True)
        
        serializer = DepartmentRiskAssessmentSerializer(risk_data)
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='risk_assessment_detail',
            description=f'Viewed detailed risk assessment for department {department.name}',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "department": {
                "id": department.id,
                "name": department.name,
                "description": department.description,
                "user_count": department_users.count(),
                "created_at": department.created_at
            },
            "risk_assessment": serializer.data,
            "recent_incidents": [
                {
                    "incident_number": inc.incident_number,
                    "title": inc.title,
                    "severity": inc.severity,
                    "status": inc.status,
                    "created_at": inc.created_at,
                    "risk_score": inc.risk_score
                }
                for inc in incidents
            ],
            "high_risk_users": high_risk_users[:5],  # Top 5 high-risk users
            "timeframe_days": timeframe_days
        })
    
    except Exception as e:
        logger.error(f"Error getting department risk detail: {str(e)}")
        return Response(
            {"error": "Failed to get department risk detail."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_risk_profiles(request):
    """Get risk profiles for users"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view user risk profiles."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get query parameters
        timeframe_days = int(request.query_params.get('timeframe', 30))
        department_id = request.query_params.get('department_id')
        min_risk_score = int(request.query_params.get('min_risk', 50))
        limit = int(request.query_params.get('limit', 20))
        
        # Get users based on filters
        users = CustomUser.objects.filter(is_active=True)
        
        if department_id:
            users = users.filter(department_id=department_id)
        
        # Apply role-based filtering
        if user.role == 'security_analyst':
            if user.departments.exists():
                # Only show users from analyst's departments
                department_users = []
                for dept in user.departments.all():
                    department_users.extend(list(dept.users.filter(is_active=True)))
                users = users.filter(id__in=[u.id for u in department_users])
        
        # Calculate risk for each user
        risk_profiles = []
        for target_user in users[:limit]:  # Limit for performance
            risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, timeframe_days)
            
            if risk_data['risk_score'] >= min_risk_score:
                risk_profiles.append(risk_data)
        
        # Sort by risk score (highest first)
        risk_profiles.sort(key=lambda x: x['risk_score'], reverse=True)
        
        serializer = UserRiskProfileSerializer(risk_profiles, many=True)
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='user_risk_profiles_view',
            description=f'Viewed risk profiles for {len(risk_profiles)} users',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "count": len(risk_profiles),
            "profiles": serializer.data
        })
    
    except Exception as e:
        logger.error(f"Error getting user risk profiles: {str(e)}")
        return Response(
            {"error": "Failed to get user risk profiles."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_security_metrics(request):
    """Get overall security metrics"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view security metrics."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        
        # Calculate security metrics
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        
        # Get risk trends
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, period='weekly')
        
        # Get vulnerability assessment
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        
        serializer = SecurityMetricsSerializer(metrics)
        trend_serializer = RiskTrendSerializer(trends, many=True)
        vuln_serializer = VulnerabilityAssessmentSerializer(vulnerabilities, many=True)
        
        # Calculate improvement recommendations
        recommendations = []
        if metrics['total_risk_score'] > 60:
            recommendations.append("Immediate action required: Overall risk score is high")
        if metrics['departments_at_risk'] > 0:
            recommendations.append(f"{metrics['departments_at_risk']} departments require immediate attention")
        if metrics['mttr_hours'] > 24:
            recommendations.append("Incident resolution time is too high - improve response processes")
        if metrics['compliance_rate'] < 90:
            recommendations.append("Improve SLA compliance rate")
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='security_metrics_view',
            description=f'Viewed security metrics for {timeframe_days} days',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "metrics": serializer.data,
            "trends": trend_serializer.data,
            "vulnerabilities": vuln_serializer.data,
            "recommendations": recommendations,
            "risk_level": RiskCalculator.get_risk_level(metrics['total_risk_score'])
        })
    
    except Exception as e:
        logger.error(f"Error getting security metrics: {str(e)}")
        return Response(
            {"error": "Failed to get security metrics."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_trends(request):
    """Get risk trends over time"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view risk trends."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get query parameters
        timeframe_days = int(request.query_params.get('timeframe', 90))
        period = request.query_params.get('period', 'weekly')
        
        # Validate period
        if period not in ['weekly', 'monthly']:
            period = 'weekly'
        
        # Calculate trends
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, period)
        
        serializer = RiskTrendSerializer(trends, many=True)
        
        # Calculate overall trend direction
        if len(trends) >= 2:
            first_score = trends[0]['risk_score']
            last_score = trends[-1]['risk_score']
            
            if last_score > first_score * 1.2:
                trend_direction = 'increasing'
            elif last_score < first_score * 0.8:
                trend_direction = 'decreasing'
            else:
                trend_direction = 'stable'
        else:
            trend_direction = 'insufficient_data'
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='risk_trends_view',
            description=f'Viewed risk trends for {timeframe_days} days ({period})',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "period": period,
            "trends": serializer.data,
            "trend_direction": trend_direction,
            "analysis": RiskTrendAnalyzer.analyze_trend_pattern(trends) if hasattr(RiskTrendAnalyzer, 'analyze_trend_pattern') else "Trend analysis available"
        })
    
    except Exception as e:
        logger.error(f"Error getting risk trends: {str(e)}")
        return Response(
            {"error": "Failed to get risk trends."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_vulnerability_assessment(request):
    """Get vulnerability assessment across categories"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view vulnerability assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get vulnerability assessment
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        
        # Calculate overall score
        total_score = sum(vuln['score'] for vuln in vulnerabilities)
        avg_score = total_score / len(vulnerabilities) if vulnerabilities else 0
        
        serializer = VulnerabilityAssessmentSerializer(vulnerabilities, many=True)
        
        # Identify critical vulnerabilities
        critical_vulns = [vuln for vuln in vulnerabilities if vuln['score'] < 50]
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='vulnerability_assessment_view',
            description=f'Viewed vulnerability assessment with {len(critical_vulns)} critical vulnerabilities',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "average_score": round(avg_score, 1),
            "overall_risk_level": RiskCalculator.get_risk_level(100 - avg_score),  # Invert score for risk level
            "vulnerabilities": serializer.data,
            "critical_count": len(critical_vulns),
            "recommendations": [
                "Prioritize remediation of critical vulnerabilities",
                "Implement security controls for high-risk areas",
                "Schedule regular vulnerability assessments"
            ]
        })
    
    except Exception as e:
        logger.error(f"Error getting vulnerability assessment: {str(e)}")
        return Response(
            {"error": "Failed to get vulnerability assessment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_risk_assessment(request):
    """Run comprehensive risk assessment and generate report"""
    try:
        user = request.user
        
        # Only admin, HR, and security analysts can run assessments
        if not (user.is_admin or user.is_hr or user.role == 'security_analyst'):
            return Response(
                {"error": "You don't have permission to run risk assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters
        timeframe_days = request.data.get('timeframe_days', 90)
        include_departments = request.data.get('include_departments', True)
        include_users = request.data.get('include_users', False)
        generate_report = request.data.get('generate_report', True)
        
        # Run assessments
        results = {
            "timestamp": now().isoformat(),
            "executed_by": user.email,
            "timeframe_days": timeframe_days,
            "assessments": {}
        }
        
        if include_departments:
            # Get department assessments
            departments = Department.objects.filter(status='active')
            dept_assessments = []
            
            for department in departments:
                if user.role == 'security_analyst':
                    if user.departments.exists() and department not in user.departments.all():
                        continue
                
                risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
                dept_assessments.append(risk_data)
            
            results["assessments"]["departments"] = dept_assessments
        
        if include_users:
            # Get high-risk user assessments
            users = CustomUser.objects.filter(is_active=True)[:50]  # Limit for performance
            user_assessments = []
            
            for target_user in users:
                risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, 30)  # Last 30 days
                if risk_data['risk_score'] >= 50:
                    user_assessments.append(risk_data)
            
            results["assessments"]["users"] = user_assessments
        
        # Get security metrics
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        results["assessments"]["metrics"] = metrics
        
        # Get vulnerability assessment
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        results["assessments"]["vulnerabilities"] = vulnerabilities
        
        # Calculate overall risk score
        if dept_assessments:
            dept_scores = [dept['overall_risk_score'] for dept in dept_assessments]
            overall_score = sum(dept_scores) / len(dept_scores)
        else:
            overall_score = metrics['total_risk_score']
        
        results["overall_risk_score"] = round(overall_score, 1)
        results["overall_risk_level"] = RiskCalculator.get_risk_level(overall_score)
        
        # Generate recommendations
        recommendations = []
        if overall_score >= 70:
            recommendations.append("🔴 CRITICAL: Immediate action required across organization")
            recommendations.append("Conduct emergency security audit")
            recommendations.append("Implement enhanced monitoring immediately")
        elif overall_score >= 50:
            recommendations.append("🟡 HIGH: Significant improvements needed")
            recommendations.append("Schedule comprehensive security review")
            recommendations.append("Prioritize high-risk department remediation")
        else:
            recommendations.append("🟢 MODERATE: Maintain current practices with monitoring")
            recommendations.append("Continue regular security assessments")
            recommendations.append("Focus on continuous improvement")
        
        results["recommendations"] = recommendations
        
        # Log activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='risk_assessment_executed',
            description=f'Executed comprehensive risk assessment with overall score: {overall_score}',
            request=request,
            response=None,
            is_success=True
        )
        
        return Response({
            "success": True,
            "message": "Risk assessment completed successfully",
            "results": results
        })
    
    except Exception as e:
        logger.error(f"Error running risk assessment: {str(e)}")
        return Response(
            {"error": "Failed to run risk assessment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_dashboard_data(request):
    """Get data for risk assessment dashboard (frontend)"""
    try:
        user = request.user
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            return Response(
                {"error": "You don't have permission to view risk dashboard."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeframe_days = 90
        
        # Get department risk distribution
        departments = Department.objects.filter(status='active')
        department_risks = []
        
        for department in departments:
            risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
            department_risks.append({
                'department': department.name,
                'risk': risk_data['overall_risk_score']
            })
        
        # Get risk categories data (for radar chart)
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        risk_categories = [
            {
                'category': vuln['category'],
                'score': vuln['score'],
                'maxScore': vuln['max_score']
            }
            for vuln in vulnerabilities
        ]
        
        # Get high-risk users
        users = CustomUser.objects.filter(is_active=True)[:10]
        high_risk_users = []
        
        for target_user in users:
            risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, 30)
            if risk_data['risk_score'] >= 60:
                high_risk_users.append({
                    'name': target_user.full_name,
                    'avatar': ''.join([name[0] for name in target_user.full_name.split()[:2]]).upper(),
                    'department': target_user.department.name if target_user.department else 'N/A',
                    'riskScore': risk_data['risk_score']
                })
        
        # Get risk trends
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, 'weekly')
        risk_trends = [
            {
                'week': trend['period'],
                'risk': trend['risk_score']
            }
            for trend in trends[-4:]  # Last 4 weeks
        ]
        
        # Get identified vulnerabilities for frontend
        identified_vulnerabilities = [
            {
                'id': i + 1,
                'title': f"{vuln['category']} Vulnerability",
                'severity': 'high' if vuln['score'] < 50 else 'medium' if vuln['score'] < 70 else 'low',
                'affected': 'System-wide' if vuln['score'] < 50 else 'Department-specific',
                'recommendation': vuln['recommendations'][0] if vuln['recommendations'] else 'No specific recommendation'
            }
            for i, vuln in enumerate(vulnerabilities)
            if vuln['score'] < 70  # Only show vulnerabilities with score < 70
        ]
        
        # Get security metrics
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        
        return Response({
            "success": True,
            "dashboard_data": {
                "department_risks": department_risks,
                "risk_categories": risk_categories,
                "high_risk_users": high_risk_users,
                "risk_trends": risk_trends,
                "vulnerabilities": identified_vulnerabilities,
                "security_metrics": {
                    "total_risk_score": metrics['total_risk_score'],
                    "departments_at_risk": metrics['departments_at_risk'],
                    "high_risk_users": metrics['high_risk_users'],
                    "critical_incidents": metrics['critical_incidents'],
                    "mttr_hours": metrics['mttr_hours'],
                    "compliance_rate": metrics['compliance_rate']
                }
            }
        })
    
    except Exception as e:
        logger.error(f"Error getting risk dashboard data: {str(e)}")
        return Response(
            {"error": "Failed to get dashboard data."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )