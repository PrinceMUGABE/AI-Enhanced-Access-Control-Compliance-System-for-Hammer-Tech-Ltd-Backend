# assistanceApp/routing.py
from django.urls import re_path
from . import consumers

print("=" * 50)
print("LOADING assistanceApp/routing.py")
print("=" * 50)

websocket_urlpatterns = [
    # Assistance WebSocket - match patterns like: ws/assistance/assist_49699985/
    # Using [\w-]+ to match alphanumeric, underscore, and hyphen characters
    re_path(r'ws/assistance/(?P<session_id>[\w-]+)/$', consumers.AssistanceConsumer.as_asgi()),
    
    # Support notifications WebSocket
    re_path(r'ws/support/notifications/$', consumers.SupportNotificationConsumer.as_asgi()),
]

print(f"✅ assistanceApp WebSocket patterns loaded: {len(websocket_urlpatterns)}")
for pattern in websocket_urlpatterns:
    print(f"  - {pattern.pattern}")
print("=" * 50)