# learningProgressApp/apps.py
from django.apps import AppConfig


class LearningProgressAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'learningProgressApp'
    verbose_name = 'Learning Progress'
    
    def ready(self):
        import learningProgressApp.signals