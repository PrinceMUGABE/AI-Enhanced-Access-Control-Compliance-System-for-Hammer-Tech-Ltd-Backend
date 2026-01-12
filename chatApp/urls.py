from django.urls import path
from . import views

urlpatterns = [
    # Chat Room Management
    path('my-chats/', views.get_my_chat_rooms, name='get_my_chat_rooms'),
    path('create/', views.create_chat_room, name='create_chat_room'),
    path('<int:room_id>/', views.get_chat_room, name='get_chat_room'),
    
    # Message Handling
    path('<int:room_id>/messages/', views.get_messages, name='get_messages'),
    path('messages/send/', views.send_message, name='send_message'),
    path('messages/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('<int:room_id>/mark-read/', views.mark_messages_as_read, name='mark_messages_as_read'),
    
    # Participant Management
    path('<int:room_id>/participants/add/', views.add_participant, name='add_participant'),
    path('<int:room_id>/participants/<int:user_id>/remove/', views.remove_participant, name='remove_participant'),
    
    # Chat Discovery
    path('discover/', views.discover_chats, name='discover_chats'),
    path('one-on-one/<int:user_id>/', views.get_or_create_one_on_one, name='get_or_create_one_on_one'),
    
    # Get Chat by ID (detailed view)
    path('chat/<int:chat_id>/', views.get_chat_by_id, name='get_chat_by_id'),


    # Video Call URLs
    path('video-call/initiate/', views.initiate_video_call, name='initiate_video_call'),
    path('video-call/signal/', views.handle_webrtc_signal, name='handle_webrtc_signal'),
    path('video-call/<str:call_id>/', views.get_call_details, name='get_call_details'),
    
    # Typing Indicators
    path('typing/update/', views.update_typing_status, name='update_typing_status'),
    path('<int:room_id>/typing/', views.get_active_typing, name='get_active_typing'),
    
    # File Upload
    path('messages/upload/', views.upload_file, name='upload_file'),


    path('start-conference/', views.start_conference_call, name='start_conference_call'),
    path('join-conference/', views.join_conference_call, name='join_conference_call'),
    path('conference/<str:call_id>/participants/', views.get_conference_participants, name='get_conference_participants'),
]