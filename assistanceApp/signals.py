from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import AssistanceChat, FAQ
from userApp.models import CustomUser as User
from .services import AssistanceManager


assistance_manager = AssistanceManager()

@receiver(post_save, sender=User)
def link_user_assistance_sessions(sender, instance, created, **kwargs):
    """
    Automatically link anonymous chat sessions when a user:
    1. Registers (created=True)
    2. Logs in (we'll need to handle login separately)
    """
    if created and instance.email:
        # New user registration - link existing sessions with matching email
        linked_count = assistance_manager.link_user_sessions(instance)
        if linked_count > 0:
            print(f"🔗 Linked {linked_count} existing chat sessions to new user {instance.email}")


@receiver(post_save, sender=AssistanceChat)
def handle_chat_status_change(sender, instance, created, **kwargs):
    """Handle chat status changes and notifications"""
    if not created and instance.status == 'escalated':
        # Notify support staff about new escalation
        channel_layer = get_channel_layer()
        
        try:
            async_to_sync(channel_layer.group_send)(
                "support_staff",
                {
                    'type': 'new_assistance_ticket',
                    'chat_session_id': instance.session_id,
                    'timestamp': instance.updated_at.isoformat()
                }
            )
        except:
            pass  # WebSocket not available


@receiver(post_save, sender=FAQ)
def update_faq_cache(sender, instance, **kwargs):
    """Clear FAQ cache when FAQ is updated"""
    from django.core.cache import cache
    cache.clear()  # Or more specific cache invalidation