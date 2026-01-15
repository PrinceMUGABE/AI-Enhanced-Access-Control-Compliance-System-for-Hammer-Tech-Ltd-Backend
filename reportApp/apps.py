# reportApp/apps.py
from django.apps import AppConfig


class ReportappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reportApp'
    verbose_name = 'Report Management'
    
    def ready(self):
        """
        Perform initialization when the app is ready.
        This method is called once at startup.
        """
        pass