# learningProgressApp/urls.py
from django.urls import path
from . import views


urlpatterns = [
    # Candidate endpoints
    path('module-completion/', views.save_module_completion, name='save_module_completion'),
    path('training/<int:training_id>/progress/', views.get_training_progress, name='get_training_progress'),
    path('all-progress/', views.get_all_training_progress, name='get_all_training_progress'),
    path('material-progress/', views.update_material_progress, name='update_material_progress'),
    path('sessions/', views.get_learning_sessions, name='get_learning_sessions'),
    path('sessions/start/', views.start_learning_session, name='start_learning_session'),
    path('sessions/<int:session_id>/end/', views.end_learning_session, name='end_learning_session'),
    path('achievements/', views.get_achievements, name='get_achievements'),
    
    # Admin endpoints
    path('admin/all-candidates-progress/', views.admin_get_all_candidates_progress, name='admin_get_all_candidates_progress'),
    path('admin/training/<int:training_id>/candidates-progress/', views.admin_get_training_candidates_progress, name='admin_get_training_candidates_progress'),

    path('candidate/<int:candidate_id>/training/<int:training_id>/progress/', 
         views.get_candidate_training_progress, name='get_candidate_training_progress'),
]