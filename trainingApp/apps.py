# trainingApp/apps.py

from django.apps import AppConfig

class TrainingappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trainingApp'
    
    def ready(self):
        import trainingApp.signals  # Register signals