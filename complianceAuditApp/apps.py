from django.apps import AppConfig


class ComplianceAuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'complianceAuditApp'
    
    def ready(self):
        """
        Initialize app signals and startup tasks
        """
        # Import and initialize signals
        try:
            import complianceAuditApp.signals
            # Call initialization function if needed
            from complianceAuditApp.signals import initialize_signals
            initialize_signals()
            
            # Import signal handlers to ensure they're registered
            from complianceAuditApp import signals  # noqa
            
        except ImportError as e:
            # Log error but don't crash the app
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not import compliance audit signals: {e}")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error initializing compliance audit signals: {e}")