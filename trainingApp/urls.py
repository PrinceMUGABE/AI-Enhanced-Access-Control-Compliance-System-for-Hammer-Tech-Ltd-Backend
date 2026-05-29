# urls.py in trainingApp
from django.urls import path
from . import views

urlpatterns = [
    # Training CRUD operations
    path('trainings/', views.get_all_trainings, name='get_all_trainings'),
    path('create/', views.create_training, name='create_training'),
    path('create-with-modules/', views.create_training_with_modules, name='create_training_with_modules'),
    path('<int:pk>/', views.get_training_by_id, name='get_training_by_id'),
    path('update/<int:pk>/', views.update_training, name='update_training'),
    path('delete/<int:pk>/', views.delete_training, name='delete_training'),
    
    # Module operations
    path('<int:training_id>/modules/', views.get_modules_by_training, name='get_modules_by_training'),
    path('<int:training_id>/modules/all/', views.get_all_modules, name='get_all_modules'),
    path('<int:training_id>/modules/create/', views.create_module, name='create_module'),
    path('modules/<int:module_id>/', views.get_module_by_id, name='get_module_by_id'),
    path('modules/<int:module_id>/update/', views.update_module, name='update_module'),
    path('modules/<int:module_id>/delete/', views.delete_module, name='delete_module'),
    
    # Training material operations
    path('modules/<int:module_id>/materials/upload/', views.upload_material_to_module, name='upload_material_to_module'),
    path('materials/<int:material_id>/download/', views.download_material, name='download_material'),
    path('materials/<int:material_id>/delete/', views.delete_material, name='delete_material'),
    
    
    
    path('completed-trainings/', views.completed_trainings_view, name='completed_trainings'),
    path('training-detail/<int:training_id>/', views.training_detail_view, name='training_detail'),
]