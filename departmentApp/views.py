# departmentApp/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from .models import Department
from .serializers import (
    DepartmentSerializer, 
    DepartmentCreateSerializer, 
    DepartmentUpdateSerializer
)
from userApp.models import CustomUser


def is_admin(user):
    """Helper function to check if user is admin"""
    return user.is_authenticated and hasattr(user, 'role') and user.role == 'admin'


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_department(request):
    """
    Create a new department (Admin only)
    """
    try:
        # Check if user is admin
        if not is_admin(request.user):
            return Response(
                {
                    'success': False,
                    'message': 'Permission denied. Only administrators can create departments.'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate request data
        if not request.data:
            return Response(
                {
                    'success': False,
                    'message': 'No data provided. Please provide department details.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = DepartmentCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            # Save with created_by
            department = serializer.save(created_by=request.user)
            
            # Return full department details
            response_serializer = DepartmentSerializer(department)
            
            return Response(
                {
                    'success': True,
                    'message': 'Department created successfully.',
                    'data': response_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        
        return Response(
            {
                'success': False,
                'message': 'Validation failed. Please check your input.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except IntegrityError as e:
        return Response(
            {
                'success': False,
                'message': 'A department with this name already exists.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while creating the department: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_departments(request):
    """
    Get all departments (All authenticated users)
    """
    try:
        departments = Department.objects.all()
        
        # Optional filtering by status
        status_filter = request.query_params.get('status', None)
        if status_filter:
            if status_filter not in ['active', 'inactive']:
                return Response(
                    {
                        'success': False,
                        'message': 'Invalid status filter. Use "active" or "inactive".'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            departments = departments.filter(status=status_filter)
        
        serializer = DepartmentSerializer(departments, many=True)
        
        return Response(
            {
                'success': True,
                'message': 'Departments retrieved successfully.',
                'count': departments.count(),
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while retrieving departments: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_by_id(request, department_id):
    """
    Get a single department by ID (All authenticated users)
    """
    try:
        # Validate department_id
        if not department_id:
            return Response(
                {
                    'success': False,
                    'message': 'Department ID is required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': f'Department with ID {department_id} does not exist.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid department ID format.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = DepartmentSerializer(department)
        
        return Response(
            {
                'success': True,
                'message': 'Department retrieved successfully.',
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while retrieving the department: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_department(request, department_id):
    """
    Update a department (Admin only)
    """
    try:
        # Check if user is admin
        if not is_admin(request.user):
            return Response(
                {
                    'success': False,
                    'message': 'Permission denied. Only administrators can update departments.'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate department_id
        if not department_id:
            return Response(
                {
                    'success': False,
                    'message': 'Department ID is required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': f'Department with ID {department_id} does not exist.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid department ID format.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request data
        if not request.data:
            return Response(
                {
                    'success': False,
                    'message': 'No data provided. Please provide department details to update.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use partial update for PATCH, full update for PUT
        partial = request.method == 'PATCH'
        serializer = DepartmentUpdateSerializer(department, data=request.data, partial=partial)
        
        if serializer.is_valid():
            updated_department = serializer.save()
            
            # Return full department details
            response_serializer = DepartmentSerializer(updated_department)
            
            return Response(
                {
                    'success': True,
                    'message': 'Department updated successfully.',
                    'data': response_serializer.data
                },
                status=status.HTTP_200_OK
            )
        
        return Response(
            {
                'success': False,
                'message': 'Validation failed. Please check your input.',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except IntegrityError as e:
        return Response(
            {
                'success': False,
                'message': 'A department with this name already exists.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while updating the department: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_department(request, department_id):
    """
    Delete a department (Admin only)
    """
    try:
        # Check if user is admin
        if not is_admin(request.user):
            return Response(
                {
                    'success': False,
                    'message': 'Permission denied. Only administrators can delete departments.'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate department_id
        if not department_id:
            return Response(
                {
                    'success': False,
                    'message': 'Department ID is required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': f'Department with ID {department_id} does not exist.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid department ID format.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Store department name before deletion
        department_name = department.name
        
        # Delete the department
        department.delete()
        
        return Response(
            {
                'success': True,
                'message': f'Department "{department_name}" has been deleted successfully.'
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while deleting the department: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_departments(request):
    """
    Get departments the logged-in user belongs to based on their role:
    - Mentee: Returns their single assigned department (ForeignKey)
    - Mentor: Returns all departments they're associated with (ManyToMany)
    - Admin/HR: Returns all departments in the system
    """
    try:
        user = CustomUser.objects.get(id=request.user.id)
    except CustomUser.DoesNotExist:
        print(f"User with ID {request.user.id} does not exist.")
        return Response(
            {
                'success': False,
                'message': 'User not found.'
            },
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        # Determine which departments to return based on user role
        if user.role == 'mentee':
            # Mentee: get their single department (ForeignKey)
            if user.department:
                departments = Department.objects.filter(id=user.department.id)
            else:
                departments = Department.objects.none()
        
        elif user.role == 'mentor':
            # Mentor: get all departments they're associated with (ManyToMany)
            departments = user.departments.all()
        
        elif user.role in ['admin', 'hr']:
            # Admin/HR: get all departments in the system
            departments = Department.objects.all()
        
        else:
            # Unknown role
            departments = Department.objects.none()
        
        # Optional filtering by status
        status_filter = request.query_params.get('status', None)
        if status_filter:
            if status_filter not in ['active', 'inactive']:
                return Response(
                    {
                        'success': False,
                        'message': 'Invalid status filter. Use "active" or "inactive".'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            departments = departments.filter(status=status_filter)
        
        serializer = DepartmentSerializer(departments, many=True)
        
        # Build response message based on role
        if user.role == 'mentee':
            message = 'Your assigned department retrieved successfully.'
        elif user.role == 'mentor':
            message = 'Your associated departments retrieved successfully.'
        elif user.role in ['admin', 'hr']:
            message = 'All departments retrieved successfully.'
        else:
            message = 'Departments retrieved successfully.'
        
        return Response(
            {
                'success': True,
                'message': message,
                'count': departments.count(),
                'user_role': user.role,
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        return Response(
            {
                'success': False,
                'message': f'An error occurred while retrieving your departments: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )