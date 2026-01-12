from django.urls import re_path
from . import consumers

# Debug print to confirm this file is being loaded
print("=" * 50)
print("LOADING routing.py - WITH USER NOTIFICATIONS")
print("=" * 50)

websocket_urlpatterns = [
    # Chat room WebSocket
    re_path(r'ws/chat/(?P<room_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    
    # Video call WebSocket
    re_path(r'ws/video-call/(?P<call_id>[^/]+)/$', consumers.VideoCallConsumer.as_asgi()),
    
    re_path(r'ws/user/notifications/$', consumers.UserNotificationConsumer.as_asgi()),
]

print("✅ WebSocket URL patterns loaded:")
for pattern in websocket_urlpatterns:
    print(f"  - {pattern.pattern}")
print("=" * 50)