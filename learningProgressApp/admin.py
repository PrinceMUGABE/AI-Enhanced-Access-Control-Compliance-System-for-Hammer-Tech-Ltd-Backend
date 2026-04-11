# learningProgressApp/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    LearningProgress, ModuleCompletion, MaterialProgress,
    LearningSession, LearningAchievement
)


@admin.register(LearningProgress)
class LearningProgressAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 'training_name', 'progress_percentage', 
        'completed_modules', 'total_modules', 'progress_bar', 'last_activity'
    ]
    list_filter = ['training', 'started_at', 'last_activity']
    search_fields = [
        'candidate__learner__first_name', 'candidate__learner__last_name',
        'training__name'
    ]
    readonly_fields = [
        'total_modules', 'completed_modules', 'progress_percentage',
        'started_at', 'last_activity'
    ]
    date_hierarchy = 'started_at'
    
    def candidate_name(self, obj):
        learner = obj.candidate.learner
        return f"{learner.first_name} {learner.last_name}".strip()
    candidate_name.short_description = 'Candidate'
    
    def training_name(self, obj):
        return obj.training.name
    training_name.short_description = 'Training'
    
    def progress_bar(self, obj):
        percentage = obj.progress_percentage
        if percentage >= 100:
            color = 'green'
        elif percentage >= 75:
            color = 'lightgreen'
        elif percentage >= 50:
            color = 'orange'
        else:
            color = 'red'
        
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0; border-radius: 3px;">'
            '<div style="width: {}%; background-color: {}; height: 20px; border-radius: 3px; text-align: center; line-height: 20px; color: white; font-size: 12px;">'
            '{}%</div></div>',
            percentage, color, round(percentage, 1)
        )
    progress_bar.short_description = 'Progress'


@admin.register(ModuleCompletion)
class ModuleCompletionAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 'module_name', 'training_name', 
        'is_completed', 'time_spent_minutes', 'completed_at'
    ]
    list_filter = ['is_completed', 'module__training', 'completed_at']
    search_fields = [
        'learning_progress__candidate__learner__first_name',
        'learning_progress__candidate__learner__last_name',
        'module__name', 'module__training__name'
    ]
    readonly_fields = ['started_at', 'completed_at']
    
    def candidate_name(self, obj):
        learner = obj.learning_progress.candidate.learner
        return f"{learner.first_name} {learner.last_name}".strip()
    candidate_name.short_description = 'Candidate'
    
    def module_name(self, obj):
        return obj.module.name
    module_name.short_description = 'Module'
    
    def training_name(self, obj):
        return obj.module.training.name
    training_name.short_description = 'Training'


@admin.register(MaterialProgress)
class MaterialProgressAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 'material_name', 'module_name',
        'is_viewed', 'is_downloaded', 'view_duration_display', 'viewed_at'
    ]
    list_filter = ['is_viewed', 'is_downloaded', 'viewed_at']
    search_fields = [
        'module_completion__learning_progress__candidate__learner__first_name',
        'module_completion__learning_progress__candidate__learner__last_name',
        'module_completion__module__name'
    ]
    readonly_fields = ['viewed_at', 'downloaded_at']
    
    def candidate_name(self, obj):
        learner = obj.module_completion.learning_progress.candidate.learner
        return f"{learner.first_name} {learner.last_name}".strip()
    candidate_name.short_description = 'Candidate'
    
    def material_name(self, obj):
        return obj.material.get_filename() or 'N/A'
    material_name.short_description = 'Material'
    
    def module_name(self, obj):
        return obj.module_completion.module.name
    module_name.short_description = 'Module'
    
    def view_duration_display(self, obj):
        minutes = obj.view_duration_seconds // 60
        seconds = obj.view_duration_seconds % 60
        return f"{minutes}m {seconds}s"
    view_duration_display.short_description = 'View Duration'


@admin.register(LearningSession)
class LearningSessionAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 'training_name', 'module_name',
        'session_start', 'duration_display', 'activities_completed'
    ]
    list_filter = ['training', 'session_start', 'session_end']
    search_fields = [
        'candidate__learner__first_name', 'candidate__learner__last_name',
        'training__name', 'module__name'
    ]
    readonly_fields = ['session_start', 'session_end', 'duration_minutes']
    date_hierarchy = 'session_start'
    
    def candidate_name(self, obj):
        learner = obj.candidate.learner
        return f"{learner.first_name} {learner.last_name}".strip()
    candidate_name.short_description = 'Candidate'
    
    def training_name(self, obj):
        return obj.training.name
    training_name.short_description = 'Training'
    
    def module_name(self, obj):
        return obj.module.name if obj.module else 'General'
    module_name.short_description = 'Module'
    
    def duration_display(self, obj):
        if obj.duration_minutes:
            hours = obj.duration_minutes // 60
            minutes = obj.duration_minutes % 60
            if hours:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return "Active" if not obj.session_end else "0m"
    duration_display.short_description = 'Duration'


@admin.register(LearningAchievement)
class LearningAchievementAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 'achievement_display', 'training_name', 'earned_at'
    ]
    list_filter = ['achievement_type', 'training', 'earned_at']
    search_fields = [
        'candidate__learner__first_name', 'candidate__learner__last_name',
        'training__name', 'description'
    ]
    readonly_fields = ['earned_at']
    date_hierarchy = 'earned_at'
    
    def candidate_name(self, obj):
        learner = obj.candidate.learner
        return f"{learner.first_name} {learner.last_name}".strip()
    candidate_name.short_description = 'Candidate'
    
    def achievement_display(self, obj):
        return obj.get_achievement_type_display()
    achievement_display.short_description = 'Achievement'
    
    def training_name(self, obj):
        return obj.training.name if obj.training else 'General'
    training_name.short_description = 'Training'