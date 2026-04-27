from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging
from django.utils.timezone import now
from datetime import timedelta
import traceback

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

# Debug helper
def debug_print(message, data=None, level="INFO"):
    """Print debug messages with formatting"""
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "STEP": "📍",
        "DATA": "📊"
    }.get(level, "ℹ️")
    
    print(f"\n{prefix} {message}")
    if data is not None:
        print(f"   Data: {data}")
    
    # Also log to logger
    if level == "ERROR":
        logger.error(message)
    elif level == "WARNING":
        logger.warning(message)
    else:
        logger.info(message)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_risk_assessments(request):
    """Get risk assessments for all departments"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_DEPARTMENT_RISK_ASSESSMENTS - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        debug_print("Checking user permissions...", level="INFO")
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission to view risk assessments", level="ERROR")
            return Response(
                {"error": "You don't have permission to view risk assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        debug_print("Permission granted", level="SUCCESS")
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Get all active departments
        debug_print("Fetching active departments...", level="STEP")
        departments = Department.objects.filter(status='active')
        debug_print(f"Found {departments.count()} active departments", level="DATA")
        
        for dept in departments:
            debug_print(f"  - {dept.name} (ID: {dept.id})", level="INFO")
        
        # Calculate risk for each department
        debug_print("Calculating risk for each department...", level="STEP")
        risk_assessments = []
        
        for idx, department in enumerate(departments, 1):
            debug_print(f"\n[{idx}/{departments.count()}] Processing: {department.name}", level="STEP")
            
            # Filter based on user permissions
            if user.role == 'security_analyst':
                if user.departments.exists() and department not in user.departments.all():
                    debug_print(f"  Skipping - not in analyst's departments", level="WARNING")
                    continue
            
            risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
            debug_print(f"  Risk Score: {risk_data['overall_risk_score']:.1f} ({risk_data['risk_level']})", level="DATA")
            debug_print(f"  Incidents: {risk_data['incident_count']}, Users: {risk_data['user_count']}", level="INFO")
            
            risk_assessments.append(risk_data)
        
        # Sort by risk score (highest first)
        risk_assessments.sort(key=lambda x: x['overall_risk_score'], reverse=True)
        debug_print(f"\nTotal departments assessed: {len(risk_assessments)}", level="SUCCESS")
        
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
        
        debug_print("GET_DEPARTMENT_RISK_ASSESSMENTS - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "count": len(risk_assessments),
            "assessments": serializer.data
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_department_risk_assessments: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get risk assessments."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_dashboard_data(request):
    """Get data for risk assessment dashboard (frontend) - WITH IMPROVED HIGH-RISK USER DETECTION"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_RISK_DASHBOARD_DATA - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        debug_print("Checking user permissions...", level="INFO")
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission to view risk dashboard", level="ERROR")
            return Response(
                {"error": "You don't have permission to view risk dashboard."},
                status=status.HTTP_403_FORBIDDEN
            )
        debug_print("Permission granted", level="SUCCESS")
        
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # STEP 1: Get department risk distribution
        debug_print("\n📍 STEP 1: Fetching department risk distribution", level="STEP")
        departments = Department.objects.filter(status='active')
        debug_print(f"Found {departments.count()} active departments", level="DATA")
        
        department_risks = []
        for department in departments:
            # Skip if security analyst doesn't have access
            if user.role == 'security_analyst':
                if user.departments.exists() and department not in user.departments.all():
                    debug_print(f"  Skipping {department.name} - not in analyst's departments", level="WARNING")
                    continue
            
            risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
            department_risks.append({
                'department': department.name,
                'risk': risk_data['overall_risk_score'],
                'incident_count': risk_data['incident_count'],
                'user_count': risk_data['user_count'],
                'risk_level': risk_data['risk_level']
            })
            debug_print(f"  {department.name}: Risk={risk_data['overall_risk_score']:.1f}, Incidents={risk_data['incident_count']}", level="INFO")
        
        # Sort by risk score (highest first)
        department_risks.sort(key=lambda x: x['risk'], reverse=True)
        debug_print(f"Department risks collected: {len(department_risks)}", level="SUCCESS")
        
        # STEP 2: Get risk categories data
        debug_print("\n📍 STEP 2: Fetching vulnerability assessments", level="STEP")
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        debug_print(f"Found {len(vulnerabilities)} vulnerability categories", level="DATA")
        
        risk_categories = []
        for vuln in vulnerabilities:
            risk_categories.append({
                'category': vuln['category'],
                'score': vuln['score'],
                'maxScore': vuln['max_score'],
                'description': vuln['description'][:100] + '...' if len(vuln['description']) > 100 else vuln['description']
            })
            debug_print(f"  {vuln['category']}: Score={vuln['score']:.1f}/{vuln['max_score']}", level="INFO")
        
        # STEP 3: Get high-risk users - IMPROVED VERSION
        debug_print("\n📍 STEP 3: Fetching high-risk users (IMPROVED)", level="STEP")
        users = CustomUser.objects.filter(is_active=True)
        debug_print(f"Total active users: {users.count()}", level="DATA")
        
        # Apply department filter for security analysts
        if user.role == 'security_analyst' and user.departments.exists():
            dept_ids = list(user.departments.values_list('id', flat=True))
            users = users.filter(department__in=dept_ids)
            debug_print(f"Filtered to analyst's departments: {users.count()} users", level="INFO")
        
        high_risk_users = []
        user_count_processed = 0
        
        # Process ALL users (no limit)
        for target_user in users:
            user_count_processed += 1
            debug_print(f"\n  [{user_count_processed}/{users.count()}] Processing: {target_user.email}", level="INFO")
            
            risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, 30)
            debug_print(f"    Risk Score: {risk_data['risk_score']:.1f} ({risk_data['risk_level']})", level="INFO")
            debug_print(f"    Incidents: {risk_data['incident_count']}, Failed Logins: {risk_data['failed_logins']}", level="INFO")
            
            # Lower threshold to 30 to catch more users
            if risk_data['risk_score'] >= 30:
                high_risk_users.append({
                    'name': target_user.full_name,
                    'avatar': ''.join([name[0] for name in target_user.full_name.split()[:2]]).upper(),
                    'department': target_user.department.name if target_user.department else 'N/A',
                    'role': target_user.role,
                    'riskScore': risk_data['risk_score'],
                    'risk_level': risk_data['risk_level'],
                    'incident_count': risk_data['incident_count'],
                    'failed_logins': risk_data['failed_logins']
                })
                debug_print(f"    ✅ ADDED to high-risk list (score {risk_data['risk_score']:.1f} >= 30)", level="WARNING")
            else:
                debug_print(f"    ❌ Skipped (score below threshold)", level="INFO")
        
        debug_print(f"\nProcessed {user_count_processed} users, found {len(high_risk_users)} users with risk score >= 30", level="SUCCESS")
        
        # Sort by risk score (highest first)
        high_risk_users.sort(key=lambda x: x['riskScore'], reverse=True)
        
        # Log top high-risk users
        if high_risk_users:
            debug_print(f"\nTop 5 High-Risk Users:", level="DATA")
            for i, u in enumerate(high_risk_users[:5], 1):
                debug_print(f"  {i}. {u['name']} - Risk: {u['riskScore']:.1f} ({u['risk_level']}), Dept: {u['department']}", level="INFO")
        
        # STEP 4: Get risk trends
        debug_print("\n📍 STEP 4: Fetching risk trends", level="STEP")
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, 'weekly')
        debug_print(f"Found {len(trends)} trend periods", level="DATA")
        
        risk_trends = []
        for trend in trends[-6:]:  # Last 6 weeks
            risk_trends.append({
                'week': trend['period'],
                'risk': trend['risk_score'],
                'incident_count': trend.get('incident_count', 0),
                'user_count': trend.get('user_count', 0)
            })
            debug_print(f"  {trend['period']}: Risk={trend['risk_score']:.1f}, Incidents={trend.get('incident_count', 0)}", level="INFO")
        
        # STEP 5: Get identified vulnerabilities
        debug_print("\n📍 STEP 5: Identifying critical vulnerabilities", level="STEP")
        identified_vulnerabilities = []
        for i, vuln in enumerate(vulnerabilities):
            severity = 'high' if vuln['score'] < 50 else 'medium' if vuln['score'] < 70 else 'low'
            identified_vulnerabilities.append({
                'id': i + 1,
                'title': f"{vuln['category']} Vulnerability",
                'severity': severity,
                'affected': 'System-wide' if vuln['score'] < 50 else 'Department-specific',
                'recommendation': vuln['recommendations'][0] if vuln['recommendations'] else 'Monitor and review',
                'score': vuln['score']
            })
            if severity == 'high':
                debug_print(f"  CRITICAL: {vuln['category']} (Score: {vuln['score']:.1f})", level="WARNING")
            else:
                debug_print(f"  {vuln['category']}: {severity.upper()} risk (Score: {vuln['score']:.1f})", level="INFO")
        
        # STEP 6: Get security metrics
        debug_print("\n📍 STEP 6: Calculating security metrics", level="STEP")
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        debug_print(f"Security Metrics:", level="DATA")
        debug_print(f"  Total Risk Score: {metrics['total_risk_score']:.1f}", level="INFO")
        debug_print(f"  Departments at Risk: {metrics['departments_at_risk']}", level="INFO")
        debug_print(f"  High Risk Users (calculated): {metrics['high_risk_users']}", level="INFO")
        debug_print(f"  Critical Incidents: {metrics['critical_incidents']}", level="INFO")
        debug_print(f"  Compliance Rate: {metrics['compliance_rate']:.1f}%", level="INFO")
        
        # Calculate overall risk level
        overall_risk_level = RiskCalculator.get_risk_level(metrics['total_risk_score'])
        debug_print(f"Overall Risk Level: {overall_risk_level.upper()}", level="STEP")
        
        # Prepare final response
        dashboard_data = {
            "overall_risk_score": metrics['total_risk_score'],
            "overall_risk_level": overall_risk_level,
            "department_risks": department_risks,
            "risk_categories": risk_categories,
            "high_risk_users": high_risk_users[:10],  # Top 10 high-risk users
            "risk_trends": risk_trends,
            "vulnerabilities": identified_vulnerabilities[:5],  # Top 5 vulnerabilities
            "security_metrics": {
                "total_risk_score": metrics['total_risk_score'],
                "departments_at_risk": metrics['departments_at_risk'],
                "high_risk_users": metrics['high_risk_users'],
                "critical_incidents": metrics['critical_incidents'],
                "high_incidents": metrics['high_incidents'],
                "mttr_hours": metrics['mttr_hours'],
                "compliance_rate": metrics['compliance_rate'],
                "total_incidents": metrics['total_incidents'],
                "total_departments": metrics['total_departments'],
                "total_users": metrics['total_users']
            }
        }
        
        debug_print("\n" + "=" * 40, level="STEP")
        debug_print("DASHBOARD DATA SUMMARY", level="STEP")
        debug_print("=" * 40)
        debug_print(f"Departments Assessed: {len(department_risks)}", level="DATA")
        debug_print(f"Risk Categories: {len(risk_categories)}", level="DATA")
        debug_print(f"High Risk Users Found: {len(high_risk_users)}", level="DATA")
        debug_print(f"Risk Trends: {len(risk_trends)}", level="DATA")
        debug_print(f"Vulnerabilities: {len(identified_vulnerabilities)}", level="DATA")
        
        debug_print("\nGET_RISK_DASHBOARD_DATA - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "dashboard_data": dashboard_data
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_risk_dashboard_data: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": f"Failed to get dashboard data: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_security_metrics(request):
    """Get overall security metrics - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_SECURITY_METRICS - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission", level="ERROR")
            return Response(
                {"error": "You don't have permission to view security metrics."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Calculate security metrics
        debug_print("Calculating security metrics...", level="STEP")
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        debug_print(f"Total Risk Score: {metrics['total_risk_score']:.1f}", level="DATA")
        debug_print(f"Departments at Risk: {metrics['departments_at_risk']}", level="DATA")
        debug_print(f"High Risk Users: {metrics['high_risk_users']}", level="DATA")
        debug_print(f"Critical Incidents: {metrics['critical_incidents']}", level="DATA")
        debug_print(f"MTTR: {metrics['mttr_hours']:.1f} hours", level="DATA")
        debug_print(f"Compliance Rate: {metrics['compliance_rate']:.1f}%", level="DATA")
        
        # Get risk trends
        debug_print("Calculating risk trends...", level="STEP")
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, period='weekly')
        debug_print(f"Found {len(trends)} trend periods", level="DATA")
        
        # Get vulnerability assessment
        debug_print("Assessing vulnerabilities...", level="STEP")
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        debug_print(f"Assessed {len(vulnerabilities)} vulnerability categories", level="DATA")
        
        # Calculate recommendations
        recommendations = []
        if metrics['total_risk_score'] > 60:
            recommendations.append("Immediate action required: Overall risk score is high")
        if metrics['departments_at_risk'] > 0:
            recommendations.append(f"{metrics['departments_at_risk']} departments require immediate attention")
        if metrics['mttr_hours'] > 24:
            recommendations.append("Incident resolution time is too high - improve response processes")
        if metrics['compliance_rate'] < 90:
            recommendations.append("Improve SLA compliance rate")
        
        debug_print(f"Generated {len(recommendations)} recommendations", level="SUCCESS")
        debug_print("GET_SECURITY_METRICS - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "metrics": metrics,
            "trends": trends,
            "vulnerabilities": vulnerabilities,
            "recommendations": recommendations,
            "risk_level": RiskCalculator.get_risk_level(metrics['total_risk_score'])
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_security_metrics: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get security metrics."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_trends(request):
    """Get risk trends over time - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_RISK_TRENDS - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission", level="ERROR")
            return Response(
                {"error": "You don't have permission to view risk trends."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        timeframe_days = int(request.query_params.get('timeframe', 90))
        period = request.query_params.get('period', 'weekly')
        debug_print(f"Timeframe: {timeframe_days} days, Period: {period}", level="INFO")
        
        # Calculate trends
        trends = RiskTrendAnalyzer.calculate_risk_trends(timeframe_days, period)
        debug_print(f"Generated {len(trends)} trend entries", level="DATA")
        
        for trend in trends:
            debug_print(f"  {trend['period']}: Risk={trend['risk_score']:.1f}, Incidents={trend.get('incident_count', 0)}", level="INFO")
        
        # Calculate overall trend direction
        if len(trends) >= 2:
            first_score = trends[0]['risk_score']
            last_score = trends[-1]['risk_score']
            
            if last_score > first_score * 1.2:
                trend_direction = 'increasing'
                debug_print(f"Trend Direction: INCREASING (Risk increased from {first_score:.1f} to {last_score:.1f})", level="WARNING")
            elif last_score < first_score * 0.8:
                trend_direction = 'decreasing'
                debug_print(f"Trend Direction: DECREASING (Risk decreased from {first_score:.1f} to {last_score:.1f})", level="SUCCESS")
            else:
                trend_direction = 'stable'
                debug_print(f"Trend Direction: STABLE (Risk: {first_score:.1f} to {last_score:.1f})", level="INFO")
        else:
            trend_direction = 'insufficient_data'
            debug_print(f"Insufficient data for trend analysis (only {len(trends)} data points)", level="WARNING")
        
        debug_print("GET_RISK_TRENDS - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "period": period,
            "trends": trends,
            "trend_direction": trend_direction,
            "analysis": RiskTrendAnalyzer.analyze_trend_pattern(trends) if len(trends) >= 2 else "Insufficient data for trend analysis"
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_risk_trends: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get risk trends."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_vulnerability_assessment(request):
    """Get vulnerability assessment across categories - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_VULNERABILITY_ASSESSMENT - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission", level="ERROR")
            return Response(
                {"error": "You don't have permission to view vulnerability assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get vulnerability assessment
        debug_print("Assessing vulnerabilities across categories...", level="STEP")
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        debug_print(f"Assessed {len(vulnerabilities)} categories", level="DATA")
        
        # Calculate overall score
        total_score = sum(vuln['score'] for vuln in vulnerabilities)
        avg_score = total_score / len(vulnerabilities) if vulnerabilities else 0
        debug_print(f"Average vulnerability score: {avg_score:.1f}/100", level="DATA")
        
        # Identify critical vulnerabilities
        critical_vulns = [vuln for vuln in vulnerabilities if vuln['score'] < 50]
        debug_print(f"Critical vulnerabilities found: {len(critical_vulns)}", level="WARNING")
        
        for vuln in critical_vulns:
            debug_print(f"  - {vuln['category']}: Score={vuln['score']:.1f}", level="WARNING")
        
        debug_print("GET_VULNERABILITY_ASSESSMENT - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "average_score": round(avg_score, 1),
            "overall_risk_level": RiskCalculator.get_risk_level(100 - avg_score),
            "vulnerabilities": vulnerabilities,
            "critical_count": len(critical_vulns),
            "recommendations": [
                "Prioritize remediation of critical vulnerabilities",
                "Implement security controls for high-risk areas",
                "Schedule regular vulnerability assessments"
            ]
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_vulnerability_assessment: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get vulnerability assessment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_risk_assessment(request):
    """Run comprehensive risk assessment and generate report - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("RUN_RISK_ASSESSMENT - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Only admin, HR, and security analysts can run assessments
        if not (user.is_admin or user.is_hr or user.role == 'security_analyst'):
            debug_print(f"User {user.email} lacks permission to run assessments", level="ERROR")
            return Response(
                {"error": "You don't have permission to run risk assessments."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get parameters
        timeframe_days = request.data.get('timeframe_days', 90)
        include_departments = request.data.get('include_departments', True)
        include_users = request.data.get('include_users', False)
        generate_report = request.data.get('generate_report', True)
        
        debug_print(f"Parameters:", level="INFO")
        debug_print(f"  Timeframe: {timeframe_days} days", level="INFO")
        debug_print(f"  Include Departments: {include_departments}", level="INFO")
        debug_print(f"  Include Users: {include_users}", level="INFO")
        debug_print(f"  Generate Report: {generate_report}", level="INFO")
        
        results = {
            "timestamp": now().isoformat(),
            "executed_by": user.email,
            "timeframe_days": timeframe_days,
            "assessments": {}
        }
        
        if include_departments:
            debug_print("\n📍 Assessing departments...", level="STEP")
            departments = Department.objects.filter(status='active')
            debug_print(f"Found {departments.count()} active departments", level="DATA")
            
            dept_assessments = []
            for department in departments:
                if user.role == 'security_analyst':
                    if user.departments.exists() and department not in user.departments.all():
                        debug_print(f"  Skipping {department.name} (not in analyst's departments)", level="WARNING")
                        continue
                
                risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
                dept_assessments.append(risk_data)
                debug_print(f"  {department.name}: Risk={risk_data['overall_risk_score']:.1f} ({risk_data['risk_level']})", level="INFO")
            
            results["assessments"]["departments"] = dept_assessments
            debug_print(f"Assessed {len(dept_assessments)} departments", level="SUCCESS")
        
        if include_users:
            debug_print("\n📍 Assessing users...", level="STEP")
            users = CustomUser.objects.filter(is_active=True)[:50]
            debug_print(f"Analyzing first {users.count()} active users", level="DATA")
            
            user_assessments = []
            for target_user in users:
                risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, 30)
                if risk_data['risk_score'] >= 50:
                    user_assessments.append(risk_data)
                    debug_print(f"  High-risk user: {target_user.email} (Risk: {risk_data['risk_score']:.1f})", level="WARNING")
            
            results["assessments"]["users"] = user_assessments
            debug_print(f"Found {len(user_assessments)} high-risk users", level="SUCCESS")
        
        # Get security metrics
        debug_print("\n📍 Calculating security metrics...", level="STEP")
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        results["assessments"]["metrics"] = metrics
        debug_print(f"Total Risk Score: {metrics['total_risk_score']:.1f}", level="DATA")
        
        # Get vulnerability assessment
        debug_print("\n📍 Assessing vulnerabilities...", level="STEP")
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        results["assessments"]["vulnerabilities"] = vulnerabilities
        debug_print(f"Assessed {len(vulnerabilities)} vulnerability categories", level="SUCCESS")
        
        # Calculate overall risk score
        if dept_assessments:
            dept_scores = [dept['overall_risk_score'] for dept in dept_assessments]
            overall_score = sum(dept_scores) / len(dept_scores)
        else:
            overall_score = metrics['total_risk_score']
        
        results["overall_risk_score"] = round(overall_score, 1)
        results["overall_risk_level"] = RiskCalculator.get_risk_level(overall_score)
        debug_print(f"\nOverall Risk Score: {results['overall_risk_score']:.1f} ({results['overall_risk_level'].upper()})", level="STEP")
        
        # Generate recommendations
        recommendations = []
        if overall_score >= 70:
            recommendations.append("🔴 CRITICAL: Immediate action required across organization")
            recommendations.append("Conduct emergency security audit")
            recommendations.append("Implement enhanced monitoring immediately")
            debug_print("CRITICAL recommendations generated", level="WARNING")
        elif overall_score >= 50:
            recommendations.append("🟡 HIGH: Significant improvements needed")
            recommendations.append("Schedule comprehensive security review")
            recommendations.append("Prioritize high-risk department remediation")
            debug_print("HIGH recommendations generated", level="WARNING")
        else:
            recommendations.append("🟢 MODERATE: Maintain current practices with monitoring")
            recommendations.append("Continue regular security assessments")
            recommendations.append("Focus on continuous improvement")
            debug_print("MODERATE recommendations generated", level="SUCCESS")
        
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
        
        debug_print("\nRUN_RISK_ASSESSMENT - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "message": "Risk assessment completed successfully",
            "results": results
        })
    
    except Exception as e:
        debug_print(f"ERROR in run_risk_assessment: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to run risk assessment."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_risk_detail(request, department_id):
    """Get detailed risk assessment for a specific department - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print(f"GET_DEPARTMENT_RISK_DETAIL - START (Department ID: {department_id})", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Get department
        debug_print(f"Fetching department with ID: {department_id}", level="INFO")
        department = get_object_or_404(Department, id=department_id)
        debug_print(f"Department found: {department.name}", level="SUCCESS")
        
        # Check permissions
        debug_print("Checking user permissions...", level="INFO")
        if not (user.is_admin or user.is_hr):
            if user.role == 'security_analyst':
                if user.departments.exists() and department not in user.departments.all():
                    debug_print(f"User {user.email} cannot access department {department.name} (not in assigned departments)", level="ERROR")
                    return Response(
                        {"error": "You don't have permission to view this department's risk assessment."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                debug_print(f"Security analyst access granted for department {department.name}", level="SUCCESS")
            else:
                debug_print(f"User {user.email} lacks permission for department risk detail", level="ERROR")
                return Response(
                    {"error": "You don't have permission to view risk assessments."},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            debug_print(f"Admin/HR access granted for department {department.name}", level="SUCCESS")
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Calculate detailed risk assessment
        debug_print(f"Calculating risk assessment for {department.name}...", level="STEP")
        risk_data = RiskCalculator.calculate_department_risk(department, timeframe_days)
        debug_print(f"Risk Score: {risk_data['overall_risk_score']:.1f} ({risk_data['risk_level']})", level="DATA")
        debug_print(f"Incident Count: {risk_data['incident_count']}", level="INFO")
        debug_print(f"User Count: {risk_data['user_count']}", level="INFO")
        debug_print(f"Trend: {risk_data['trend']}", level="INFO")
        
        # Get department incidents for additional context
        debug_print(f"Fetching recent incidents for {department.name}...", level="STEP")
        incidents = department.incidents.filter(
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).order_by('-created_at')[:10]
        debug_print(f"Found {incidents.count()} incidents in timeframe", level="DATA")
        
        for inc in incidents[:3]:  # Show first 3
            debug_print(f"  - {inc.incident_number}: {inc.severity} severity, Created: {inc.created_at.strftime('%Y-%m-%d')}", level="INFO")
        
        # Get high-risk users in department
        debug_print(f"Identifying high-risk users in {department.name}...", level="STEP")
        department_users = department.users.filter(is_active=True)
        debug_print(f"Total active users in department: {department_users.count()}", level="DATA")
        
        high_risk_users = []
        for dept_user in department_users[:10]:  # Limit to 10 users for performance
            user_risk = UserRiskAnalyzer.calculate_user_risk(dept_user, 30)  # Last 30 days
            if user_risk['risk_score'] >= 60:
                high_risk_users.append(user_risk)
                debug_print(f"  High-risk user: {dept_user.email} (Risk: {user_risk['risk_score']:.1f})", level="WARNING")
        
        # Sort high risk users by score
        high_risk_users.sort(key=lambda x: x['risk_score'], reverse=True)
        debug_print(f"Found {len(high_risk_users)} high-risk users", level="SUCCESS")
        
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
        
        debug_print(f"GET_DEPARTMENT_RISK_DETAIL - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
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
        debug_print(f"ERROR in get_department_risk_detail: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get department risk detail."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_risk_profiles(request):
    """Get risk profiles for users - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_USER_RISK_PROFILES - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        debug_print("Checking user permissions...", level="INFO")
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission to view user risk profiles", level="ERROR")
            return Response(
                {"error": "You don't have permission to view user risk profiles."},
                status=status.HTTP_403_FORBIDDEN
            )
        debug_print("Permission granted", level="SUCCESS")
        
        # Get query parameters
        timeframe_days = int(request.query_params.get('timeframe', 30))
        department_id = request.query_params.get('department_id')
        min_risk_score = int(request.query_params.get('min_risk', 50))
        limit = int(request.query_params.get('limit', 20))
        
        debug_print(f"Parameters:", level="INFO")
        debug_print(f"  Timeframe: {timeframe_days} days", level="INFO")
        debug_print(f"  Department ID: {department_id or 'All'}", level="INFO")
        debug_print(f"  Min Risk Score: {min_risk_score}", level="INFO")
        debug_print(f"  Limit: {limit}", level="INFO")
        
        # Get users based on filters
        users = CustomUser.objects.filter(is_active=True)
        debug_print(f"Total active users: {users.count()}", level="DATA")
        
        if department_id:
            users = users.filter(department_id=department_id)
            debug_print(f"Filtered to department ID {department_id}: {users.count()} users", level="INFO")
        
        # Apply role-based filtering
        if user.role == 'security_analyst':
            if user.departments.exists():
                dept_ids = list(user.departments.values_list('id', flat=True))
                users = users.filter(department__in=dept_ids)
                debug_print(f"Security analyst filter - accessible departments: {dept_ids}", level="INFO")
                debug_print(f"Users after department filter: {users.count()}", level="DATA")
        
        # Calculate risk for each user
        debug_print(f"\nCalculating risk profiles for up to {min(limit, users.count())} users...", level="STEP")
        risk_profiles = []
        processed_count = 0
        
        for target_user in users[:limit]:
            processed_count += 1
            debug_print(f"\n  [{processed_count}/{min(limit, users.count())}] Processing: {target_user.email}", level="INFO")
            
            risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, timeframe_days)
            debug_print(f"    Risk Score: {risk_data['risk_score']:.1f} ({risk_data['risk_level']})", level="DATA")
            debug_print(f"    Incident Count: {risk_data['incident_count']}", level="INFO")
            debug_print(f"    Failed Logins: {risk_data['failed_logins']}", level="INFO")
            
            if risk_data['risk_score'] >= min_risk_score:
                risk_profiles.append(risk_data)
                debug_print(f"    ✓ Added to high-risk list (score {risk_data['risk_score']:.1f} >= {min_risk_score})", level="SUCCESS")
            else:
                debug_print(f"    ✗ Skipped (score below threshold)", level="INFO")
        
        # Sort by risk score (highest first)
        risk_profiles.sort(key=lambda x: x['risk_score'], reverse=True)
        
        debug_print(f"\nTotal risk profiles generated: {len(risk_profiles)}", level="SUCCESS")
        debug_print(f"High-risk users (score >= 60): {len([p for p in risk_profiles if p['risk_score'] >= 60])}", level="WARNING")
        
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
        
        debug_print("GET_USER_RISK_PROFILES - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "count": len(risk_profiles),
            "profiles": serializer.data
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_user_risk_profiles: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get user risk profiles."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_risk_profile_detail(request, user_id):
    """Get detailed risk profile for a specific user - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print(f"GET_USER_RISK_PROFILE_DETAIL - START (User ID: {user_id})", level="STEP")
    
    try:
        user = request.user
        debug_print(f"Requesting user: {user.email} (Role: {user.role})", level="INFO")
        
        # Get target user
        debug_print(f"Fetching target user with ID: {user_id}", level="INFO")
        target_user = get_object_or_404(CustomUser, id=user_id, is_active=True)
        debug_print(f"Target user found: {target_user.email} (Role: {target_user.role})", level="SUCCESS")
        
        # Check permissions
        debug_print("Checking user permissions...", level="INFO")
        has_permission = False
        
        if user.is_admin or user.is_hr:
            has_permission = True
            debug_print("Admin/HR permission granted", level="SUCCESS")
        elif user.role == 'security_analyst':
            # Check if target user is in analyst's departments
            if user.departments.exists():
                if target_user.department and target_user.department in user.departments.all():
                    has_permission = True
                    debug_print(f"Security analyst permission granted - user in department {target_user.department.name}", level="SUCCESS")
                else:
                    debug_print(f"Target user not in analyst's departments", level="WARNING")
            else:
                debug_print("Security analyst has no departments assigned", level="WARNING")
        elif user.id == target_user.id:
            has_permission = True
            debug_print("User viewing own profile - permission granted", level="SUCCESS")
        
        if not has_permission:
            debug_print(f"User {user.email} lacks permission to view {target_user.email}'s risk profile", level="ERROR")
            return Response(
                {"error": "You don't have permission to view this user's risk profile."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Calculate detailed risk assessment
        debug_print(f"Calculating risk profile for {target_user.email}...", level="STEP")
        risk_data = UserRiskAnalyzer.calculate_user_risk(target_user, timeframe_days)
        
        debug_print(f"Risk Profile Summary:", level="DATA")
        debug_print(f"  Overall Risk Score: {risk_data['risk_score']:.1f} ({risk_data['risk_level']})", level="INFO")
        debug_print(f"  Incident Count: {risk_data['incident_count']}", level="INFO")
        debug_print(f"  Failed Logins: {risk_data['failed_logins']}", level="INFO")
        debug_print(f"  Behavioral Score: {risk_data['behavioral_score']:.1f}", level="INFO")
        debug_print(f"  Recent Activities: {risk_data['recent_activities']}", level="INFO")
        
        # Get user's incidents
        debug_print(f"Fetching user's incidents...", level="STEP")
        user_incidents = Incident.objects.filter(
            Q(created_by=target_user) | Q(assigned_to=target_user),
            created_at__gte=now() - timedelta(days=timeframe_days)
        ).order_by('-created_at')[:10]
        debug_print(f"Found {user_incidents.count()} incidents in timeframe", level="DATA")
        
        for inc in user_incidents[:3]:
            debug_print(f"  - {inc.incident_number}: {inc.severity} severity, Status: {inc.status}", level="INFO")
        
        # Get user's recent activities
        debug_print(f"Fetching user's recent activities...", level="STEP")
        recent_activities = target_user.activity_logs.filter(
            timestamp__gte=now() - timedelta(days=30)
        ).order_by('-timestamp')[:10]
        debug_print(f"Found {recent_activities.count()} recent activities", level="DATA")
        
        for act in recent_activities[:3]:
            debug_print(f"  - {act.activity}: {act.is_success and 'Success' or 'Failed'} at {act.timestamp.strftime('%Y-%m-%d %H:%M')}", level="INFO")
        
        debug_print(f"GET_USER_RISK_PROFILE_DETAIL - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "user_profile": {
                "id": target_user.id,
                "full_name": target_user.full_name,
                "email": target_user.email,
                "role": target_user.role,
                "department": target_user.department.name if target_user.department else None,
                "is_active": target_user.is_active,
                "created_at": target_user.created_at
            },
            "risk_assessment": risk_data,
            "recent_incidents": [
                {
                    "incident_number": inc.incident_number,
                    "title": inc.title,
                    "severity": inc.severity,
                    "status": inc.status,
                    "created_at": inc.created_at,
                    "assigned_to": inc.assigned_to.email if inc.assigned_to else None
                }
                for inc in user_incidents
            ],
            "recent_activities": [
                {
                    "activity": act.activity,
                    "description": act.description[:100] if act.description else "",
                    "timestamp": act.timestamp,
                    "is_success": act.is_success,
                    "ip_address": act.ip_address
                }
                for act in recent_activities
            ],
            "timeframe_days": timeframe_days
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_user_risk_profile_detail: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get user risk profile detail."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_summary(request):
    """Get a summary of all risk assessments - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_RISK_SUMMARY - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission to view risk summary", level="ERROR")
            return Response(
                {"error": "You don't have permission to view risk summary."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Get departments
        debug_print("Fetching departments...", level="STEP")
        departments = Department.objects.filter(status='active')
        debug_print(f"Found {departments.count()} active departments", level="DATA")
        
        # Calculate department risks
        debug_print("Calculating department risks...", level="STEP")
        department_summaries = []
        total_risk_score = 0
        departments_with_high_risk = 0
        
        for dept in departments:
            risk_data = RiskCalculator.calculate_department_risk(dept, timeframe_days)
            department_summaries.append({
                "name": dept.name,
                "risk_score": risk_data['overall_risk_score'],
                "risk_level": risk_data['risk_level'],
                "incident_count": risk_data['incident_count'],
                "user_count": risk_data['user_count']
            })
            total_risk_score += risk_data['overall_risk_score']
            if risk_data['overall_risk_score'] >= 60:
                departments_with_high_risk += 1
            
            debug_print(f"  {dept.name}: {risk_data['overall_risk_score']:.1f} ({risk_data['risk_level']})", level="INFO")
        
        avg_risk_score = total_risk_score / len(departments) if departments else 0
        debug_print(f"Average Risk Score: {avg_risk_score:.1f}", level="DATA")
        debug_print(f"Departments with High Risk: {departments_with_high_risk}", level="WARNING")
        
        # Get overall metrics
        debug_print("Calculating overall security metrics...", level="STEP")
        metrics = SecurityMetricsCalculator.calculate_security_metrics(timeframe_days)
        debug_print(f"Total Incidents: {metrics['total_incidents']}", level="DATA")
        debug_print(f"Critical Incidents: {metrics['critical_incidents']}", level="DATA")
        debug_print(f"Compliance Rate: {metrics['compliance_rate']:.1f}%", level="DATA")
        
        # Get vulnerability summary
        debug_print("Assessing vulnerabilities...", level="STEP")
        vulnerabilities = VulnerabilityAssessor.assess_vulnerabilities()
        
        critical_vulns = [v for v in vulnerabilities if v['score'] < 50]
        high_vulns = [v for v in vulnerabilities if 50 <= v['score'] < 70]
        medium_vulns = [v for v in vulnerabilities if 70 <= v['score'] < 85]
        low_vulns = [v for v in vulnerabilities if v['score'] >= 85]
        
        debug_print(f"Vulnerability Summary:", level="DATA")
        debug_print(f"  Critical: {len(critical_vulns)}", level="WARNING")
        debug_print(f"  High: {len(high_vulns)}", level="INFO")
        debug_print(f"  Medium: {len(medium_vulns)}", level="INFO")
        debug_print(f"  Low: {len(low_vulns)}", level="SUCCESS")
        
        # Generate overall recommendations
        recommendations = []
        if avg_risk_score >= 60:
            recommendations.append("Overall risk score is HIGH - immediate action required")
        if departments_with_high_risk > 0:
            recommendations.append(f"{departments_with_high_risk} departments require immediate attention")
        if metrics['compliance_rate'] < 80:
            recommendations.append("Compliance rate is below acceptable threshold")
        if len(critical_vulns) > 0:
            recommendations.append(f"Address {len(critical_vulns)} critical vulnerabilities")
        
        if not recommendations:
            recommendations.append("Overall risk posture is acceptable - continue monitoring")
        
        debug_print(f"Generated {len(recommendations)} recommendations", level="SUCCESS")
        debug_print("GET_RISK_SUMMARY - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "summary": {
                "overall_risk_score": round(avg_risk_score, 1),
                "overall_risk_level": RiskCalculator.get_risk_level(avg_risk_score),
                "departments_assessed": len(department_summaries),
                "departments_at_risk": departments_with_high_risk,
                "total_incidents": metrics['total_incidents'],
                "critical_incidents": metrics['critical_incidents'],
                "compliance_rate": round(metrics['compliance_rate'], 1),
                "vulnerabilities": {
                    "critical": len(critical_vulns),
                    "high": len(high_vulns),
                    "medium": len(medium_vulns),
                    "low": len(low_vulns)
                }
            },
            "departments": department_summaries,
            "recommendations": recommendations,
            "generated_at": now().isoformat()
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_risk_summary: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get risk summary."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_risk_heatmap_data(request):
    """Get data for risk heatmap visualization - WITH DEBUGGING"""
    debug_print("=" * 80, level="STEP")
    debug_print("GET_RISK_HEATMAP_DATA - START", level="STEP")
    
    try:
        user = request.user
        debug_print(f"User: {user.email} (Role: {user.role})", level="INFO")
        
        # Check permissions
        if not (user.is_admin or user.is_hr or user.role in ['security_analyst', 'compliance_officer']):
            debug_print(f"User {user.email} lacks permission to view risk heatmap", level="ERROR")
            return Response(
                {"error": "You don't have permission to view risk heatmap."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get timeframe from query params
        timeframe_days = int(request.query_params.get('timeframe', 90))
        debug_print(f"Timeframe: {timeframe_days} days", level="INFO")
        
        # Get all departments
        debug_print("Fetching departments for heatmap...", level="STEP")
        departments = Department.objects.filter(status='active')
        debug_print(f"Found {departments.count()} departments", level="DATA")
        
        heatmap_data = []
        
        for dept in departments:
            # Skip if security analyst doesn't have access
            if user.role == 'security_analyst':
                if user.departments.exists() and dept not in user.departments.all():
                    debug_print(f"  Skipping {dept.name} (not in analyst's departments)", level="WARNING")
                    continue
            
            # Get department risk data
            risk_data = RiskCalculator.calculate_department_risk(dept, timeframe_days)
            
            # Get additional metrics for heatmap
            incident_severity_distribution = {
                'critical': dept.incidents.filter(severity='critical').count(),
                'high': dept.incidents.filter(severity='high').count(),
                'medium': dept.incidents.filter(severity='medium').count(),
                'low': dept.incidents.filter(severity='low').count()
            }
            
            # Calculate risk by category for this department
            risk_by_category = {
                'access_control': RiskCalculator.calculate_category_risk(dept, 'access_control'),
                'data_security': RiskCalculator.calculate_category_risk(dept, 'data_security'),
                'network_security': RiskCalculator.calculate_category_risk(dept, 'network_security'),
                'user_behavior': RiskCalculator.calculate_category_risk(dept, 'user_behavior'),
                'incident_response': RiskCalculator.calculate_category_risk(dept, 'incident_response')
            }
            
            heatmap_data.append({
                'department_id': dept.id,
                'department_name': dept.name,
                'risk_score': risk_data['overall_risk_score'],
                'risk_level': risk_data['risk_level'],
                'incident_count': risk_data['incident_count'],
                'user_count': risk_data['user_count'],
                'severity_distribution': incident_severity_distribution,
                'risk_by_category': risk_by_category,
                'trend': risk_data['trend']
            })
            
            debug_print(f"  {dept.name}: Risk={risk_data['overall_risk_score']:.1f} ({risk_data['risk_level']}), Incidents={risk_data['incident_count']}", level="INFO")
        
        # Sort by risk score for heatmap ordering
        heatmap_data.sort(key=lambda x: x['risk_score'], reverse=True)
        
        debug_print(f"Heatmap data generated for {len(heatmap_data)} departments", level="SUCCESS")
        debug_print("GET_RISK_HEATMAP_DATA - COMPLETED SUCCESSFULLY", level="SUCCESS")
        debug_print("=" * 80)
        
        return Response({
            "success": True,
            "timeframe_days": timeframe_days,
            "heatmap_data": heatmap_data,
            "color_scale": {
                "min": 0,
                "max": 100,
                "thresholds": {
                    "critical": {"min": 80, "max": 100, "color": "#DC2626"},
                    "high": {"min": 60, "max": 79, "color": "#FF6B35"},
                    "medium": {"min": 40, "max": 59, "color": "#FFA07A"},
                    "low": {"min": 20, "max": 39, "color": "#4ECDC4"},
                    "very_low": {"min": 0, "max": 19, "color": "#10B981"}
                }
            }
        })
    
    except Exception as e:
        debug_print(f"ERROR in get_risk_heatmap_data: {str(e)}", level="ERROR")
        debug_print(traceback.format_exc(), level="ERROR")
        return Response(
            {"error": "Failed to get risk heatmap data."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Helper method for RiskCalculator (add to RiskCalculator class)
@staticmethod
def calculate_category_risk(department, category):
    """Calculate risk score for a specific category within a department"""
    try:
        if category == 'access_control':
            incidents = department.incidents.filter(
                Q(title__icontains='access') |
                Q(title__icontains='permission') |
                Q(description__icontains='unauthorized')
            )
        elif category == 'data_security':
            incidents = department.incidents.filter(
                Q(title__icontains='data') |
                Q(title__icontains='breach') |
                Q(description__icontains='sensitive')
            )
        elif category == 'network_security':
            incidents = department.incidents.filter(
                Q(title__icontains='network') |
                Q(title__icontains='firewall') |
                Q(description__icontains='connection')
            )
        elif category == 'user_behavior':
            incidents = department.incidents.filter(
                Q(title__icontains='behavior') |
                Q(title__icontains='activity')
            )
        else:  # incident_response
            incidents = department.incidents.filter(
                status__in=['resolved', 'closed']
            )
        
        if incidents.count() == 0:
            return 0
        
        # Calculate average severity score
        total_severity = sum(RiskCalculator.SEVERITY_SCORES.get(inc.severity, 25) for inc in incidents)
        return min(100, total_severity / incidents.count())
        
    except Exception as e:
        logger.error(f"Error calculating category risk: {str(e)}")
        return 0
    
    
    
    
