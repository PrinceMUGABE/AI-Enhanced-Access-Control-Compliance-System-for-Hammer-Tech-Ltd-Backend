#riskAssessmentApp/serializers.py
from rest_framework import serializers
from django.db.models import Count, Avg, Q, F
from datetime import datetime, timedelta
from django.utils.timezone import now
from incidentApp.models import Incident
from userApp.models import CustomUser, UserLog
from departmentApp.models import Department
from django.core.cache import cache
import json


class RiskFactorSerializer(serializers.Serializer):
    """Serializer for risk factors"""
    name = serializers.CharField()
    score = serializers.FloatField(min_value=0, max_value=100)
    weight = serializers.FloatField(min_value=0, max_value=1)
    description = serializers.CharField()


class DepartmentRiskAssessmentSerializer(serializers.Serializer):
    """Serializer for department risk assessment"""
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    overall_risk_score = serializers.FloatField(min_value=0, max_value=100)
    risk_level = serializers.CharField()
    incident_count = serializers.IntegerField(min_value=0)
    user_count = serializers.IntegerField(min_value=0)
    average_severity = serializers.FloatField(min_value=0, max_value=10)
    last_incident_date = serializers.DateTimeField(allow_null=True)
    risk_factors = RiskFactorSerializer(many=True)
    trend = serializers.CharField()
    recommendations = serializers.ListField(child=serializers.CharField())


class UserRiskProfileSerializer(serializers.Serializer):
    """Serializer for user risk profiles"""
    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    department_name = serializers.CharField(allow_null=True)
    risk_score = serializers.FloatField(min_value=0, max_value=100)
    risk_level = serializers.CharField()
    incident_count = serializers.IntegerField(min_value=0)
    last_incident_date = serializers.DateTimeField(allow_null=True)
    behavioral_score = serializers.FloatField(min_value=0, max_value=100)


class SecurityMetricsSerializer(serializers.Serializer):
    """Serializer for overall security metrics"""
    total_risk_score = serializers.FloatField(min_value=0, max_value=100)
    departments_at_risk = serializers.IntegerField(min_value=0)
    high_risk_users = serializers.IntegerField(min_value=0)
    critical_incidents = serializers.IntegerField(min_value=0)
    mttr_hours = serializers.FloatField(min_value=0)  # Mean Time to Resolution
    compliance_rate = serializers.FloatField(min_value=0, max_value=100)


class RiskTrendSerializer(serializers.Serializer):
    """Serializer for risk trends over time"""
    period = serializers.CharField()
    risk_score = serializers.FloatField(min_value=0, max_value=100)
    incident_count = serializers.IntegerField(min_value=0)
    user_count = serializers.IntegerField(min_value=0)


class VulnerabilityAssessmentSerializer(serializers.Serializer):
    """Serializer for vulnerability assessments"""
    category = serializers.CharField()
    score = serializers.FloatField(min_value=0, max_value=100)
    max_score = serializers.IntegerField(min_value=0)
    description = serializers.CharField()
    recommendations = serializers.ListField(child=serializers.CharField())