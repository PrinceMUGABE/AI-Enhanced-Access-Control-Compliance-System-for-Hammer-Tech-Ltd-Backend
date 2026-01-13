# assistanceApp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Public endpoints
    path('start/', views.start_assistance_session, name='start_assistance'),
    path('ask/', views.ask_question, name='ask_question'),
    path('session/<str:session_id>/', views.get_chat_session, name='get_chat_session'),
    path('faqs/', views.get_faqs, name='get_faqs'),
    path('faqs/<int:pk>/', views.faq_detail, name='faq_detail'),
    
    # Admin/HR endpoints
    path('escalate/', views.escalate_chat, name='escalate_chat'),
    path('human-response/', views.send_human_response, name='send_human_response'),
    path('chats/all/', views.get_all_chats, name='get_all_chats'),
    path('chats/<int:chat_id>/status/', views.update_chat_status, name='update_chat_status'),
    path('chats/<int:chat_id>/resolve/', views.resolve_chat, name='resolve_chat'),
    path('chats/<int:chat_id>/take-over/', views.take_over_chat, name='take_over_chat'),
    
    # FAQ management
    path('create-faq/', views.create_faq, name='create_faq'),
    path('faqs/<int:faq_id>/feedback/', views.update_faq_feedback, name='update_faq_feedback'),
    
    # Analytics and reporting
    path('analytics/', views.get_assistance_analytics, name='get_analytics'),
    path('analytics/detailed/', views.get_chat_analytics_detailed, name='get_detailed_analytics'),
    path('analytics/popular-questions/', views.get_popular_questions, name='get_popular_questions'),
    path('analytics/faq-effectiveness/', views.get_faq_effectiveness, name='get_faq_effectiveness'),
    path('analytics/faq-suggestions/', views.get_faq_suggestions, name='get_faq_suggestions'),
    path('analytics/system-health/', views.get_system_health, name='get_system_health'),
    
    # Maintenance endpoints
    path('batch-update-faq-usage/', views.batch_update_faq_usage, name='batch_update_faq_usage'),
    
    # Legacy endpoints (keep for backward compatibility)
    path('escalated-chats/', views.get_escalated_chats, name='get_escalated_chats'),


    # User chat management (authenticated and anonymous)
    path('my/chats/', views.get_my_chats, name='get_my_chats'),
    path('my/chats/link/', views.link_my_sessions, name='link_my_sessions'),
    path('my/chats/unlinked/', views.find_my_unlinked_chats, name='find_unlinked_chats'),
    path('my/chats/<int:chat_id>/resolve/', views.mark_chat_resolved, name='mark_chat_resolved'),
    
    # Chat session access (public with permissions)
    path('chat/<str:session_id>/', views.get_chat_by_session, name='get_chat_by_session'),
    path('chat/<str:session_id>/continue/', views.continue_chat_session, name='continue_chat_session'),
    path('chat/claim/', views.claim_chat_session, name='claim_chat_session'),
]