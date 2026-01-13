from django.apps import AppConfig


class AssistanceappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assistanceApp'
    verbose_name = 'AI Assistance'

    def ready(self):
        import assistanceApp.signals