# learningProgressApp/serializers.py
from rest_framework import serializers
from .models import (
    LearningProgress, ModuleCompletion, MaterialProgress, 
    LearningSession, LearningAchievement
)
from trainingApp.models import Training, Module, TrainingMaterial
from trainingCandidateApp.models import Candidate
from userApp.models import CustomUser


class MaterialProgressSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.get_filename', read_only=True)
    material_size = serializers.CharField(source='material.get_file_size', read_only=True)
    
    class Meta:
        model = MaterialProgress
        fields = [
            'id', 'material', 'material_name', 'material_size',
            'is_viewed', 'is_downloaded', 'viewed_at', 'downloaded_at',
            'view_duration_seconds'
        ]
        read_only_fields = ['viewed_at', 'downloaded_at']


class ModuleCompletionSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    module_description = serializers.CharField(source='module.description', read_only=True)
    materials_count = serializers.IntegerField(source='module.get_materials_count', read_only=True)
    material_progress = MaterialProgressSerializer(many=True, read_only=True)
    
    class Meta:
        model = ModuleCompletion
        fields = [
            'id', 'module', 'module_name', 'module_description',
            'materials_count', 'is_completed', 'started_at', 'completed_at',
            'time_spent_minutes', 'material_progress'
        ]
        read_only_fields = ['started_at', 'completed_at']


class LearningProgressSerializer(serializers.ModelSerializer):
    training_name = serializers.CharField(source='training.name', read_only=True)
    training_description = serializers.CharField(source='training.description', read_only=True)
    learner_name = serializers.SerializerMethodField()
    learner_id = serializers.SerializerMethodField()
    learner_email = serializers.SerializerMethodField()
    module_completions = ModuleCompletionSerializer(many=True, read_only=True)
    
    class Meta:
        model = LearningProgress
        fields = [
            'id', 'candidate', 'training', 'training_name', 'training_description',
            'learner_name', 'learner_id', 'learner_email',  # Fixed fields
            'total_modules', 'completed_modules', 'progress_percentage',
            'started_at', 'last_activity', 'estimated_completion_date',
            'module_completions'
        ]
        read_only_fields = [
            'total_modules', 'completed_modules', 'progress_percentage',
            'started_at', 'last_activity'
        ]
    
    def get_learner_name(self, obj):
        # Access learner through candidate
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.full_name
        return "Unknown"
    
    def get_learner_id(self, obj):
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.id
        return None
    
    def get_learner_email(self, obj):
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.email
        return None

class LearningProgressSummarySerializer(serializers.ModelSerializer):
    """Simplified serializer for progress summaries without nested details"""
    training_name = serializers.CharField(source='training.name', read_only=True)
    learner_name = serializers.SerializerMethodField()
    learner_id = serializers.SerializerMethodField()
    
    class Meta:
        model = LearningProgress
        fields = [
            'id', 'training', 'training_name', 'learner_name', 'learner_id',
            'total_modules', 'completed_modules', 'progress_percentage',
            'started_at', 'last_activity'
        ]
    
    def get_learner_name(self, obj):
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.full_name
        return "Unknown"
    
    def get_learner_id(self, obj):
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.id
        return None

class LearningSessionSerializer(serializers.ModelSerializer):
    training_name = serializers.CharField(source='training.name', read_only=True)
    module_name = serializers.CharField(source='module.name', read_only=True)
    learner_name = serializers.SerializerMethodField()
    
    class Meta:
        model = LearningSession
        fields = [
            'id', 'candidate', 'training', 'training_name', 'module',
            'module_name', 'learner_name', 'session_start', 'session_end',
            'duration_minutes', 'activities_completed'
        ]
        read_only_fields = ['session_start', 'session_end', 'duration_minutes']
    
    def get_learner_name(self, obj):
        # Fixed typo: obj.candiadte -> obj.candidate
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.full_name
        return "Unknown"
    


class LearningAchievementSerializer(serializers.ModelSerializer):
    achievement_display = serializers.CharField(source='get_achievement_type_display', read_only=True)
    training_name = serializers.CharField(source='training.name', read_only=True)
    learner_name = serializers.SerializerMethodField()
    
    class Meta:
        model = LearningAchievement
        fields = [
            'id', 'candidate', 'achievement_type', 'achievement_display',
            'training', 'training_name', 'learner_name', 'earned_at', 'description'
        ]
        read_only_fields = ['earned_at']
    
    def get_learner_name(self, obj):
        if obj.candidate and obj.candidate.learner:
            return obj.candidate.learner.full_name
        return "Unknown"


class ModuleCompletionUpdateSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)
    module_description = serializers.CharField(source='module.description', read_only=True)
    materials_count = serializers.SerializerMethodField()  # Changed to method field
    material_progress = MaterialProgressSerializer(many=True, read_only=True)
    
    class Meta:
        model = ModuleCompletion
        fields = [
            'id', 'module', 'module_name', 'module_description',
            'materials_count', 'is_completed', 'started_at', 'completed_at',
            'time_spent_minutes', 'material_progress'
        ]
        read_only_fields = ['started_at', 'completed_at']
    
    def get_materials_count(self, obj):
        # Use the get_materials_count method from Module model
        if obj.module:
            return obj.module.get_materials_count()
        return 0

class MaterialProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating material progress"""
    
    class Meta:
        model = MaterialProgress
        fields = ['is_viewed', 'is_downloaded', 'view_duration_seconds']
    
    def update(self, instance, validated_data):
        if validated_data.get('is_viewed'):
            duration = validated_data.get('view_duration_seconds', 0)
            instance.mark_viewed(duration)
        
        if validated_data.get('is_downloaded'):
            instance.mark_downloaded()
        
        return instance
    




