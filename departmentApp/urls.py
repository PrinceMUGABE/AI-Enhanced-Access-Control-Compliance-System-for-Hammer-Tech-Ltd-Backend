# departmentApp/urls.py

from django.urls import path
from . import views

app_name = 'departments'

urlpatterns = [
    # Create department (Admin only)
    path('create/', views.create_department, name='create_department'),
    
    # Get all departments (All authenticated users)
    path('all/', views.get_all_departments, name='get_all_departments'),
    
    # Get department by ID (All authenticated users)
    path('<int:department_id>/', views.get_department_by_id, name='get_department_by_id'),
    
    # Update department (Admin only)
    path('<int:department_id>/update/', views.update_department, name='update_department'),
    
    # Delete department (Admin only)
    path('<int:department_id>/delete/', views.delete_department, name='delete_department'),
    
    # Get departments created by logged-in user
    path('my-departments/', views.get_my_departments, name='get_my_departments'),
]