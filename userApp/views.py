# views.py

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.db.utils import IntegrityError
from django.contrib.auth.hashers import make_password, check_password
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import CustomUser
from .serializers import CustomUserSerializer, ContactUsSerializer, DepartmentSerializer
import re
import random
import string
import logging
import traceback
from departmentApp.models import Department

# Configure logging
logger = logging.getLogger(__name__)

# ==================== HELPER FUNCTIONS ====================

def is_valid_password(password):
    """Validate password complexity."""
    try:
        if len(password) < 8:
            return "Password must be at least 8 characters long."
        if not any(char.isdigit() for char in password):
            return "Password must include at least one number."
        if not any(char.isupper() for char in password):
            return "Password must include at least one uppercase letter."
        if not any(char.islower() for char in password):
            return "Password must include at least one lowercase letter."
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return "Password must include at least one special character (!@#$%^&* etc.)."
        return None
    except Exception as e:
        error_msg = f"Error validating password: {str(e)}"
        print(error_msg)
        return "Error validating password format."

def is_valid_email(email):
    """Validate email format and domain."""
    try:
        email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        
        # Check format
        if not re.match(email_regex, email):
            return "Invalid email format."
        
        # Check if it's a Gmail for personal email
        if not email.endswith("@gmail.com"):
            return "Only Gmail addresses are allowed for personal email."
        
        return None
    except Exception as e:
        error_msg = f"Error validating email: {str(e)}"
        print(error_msg)
        return "Error validating email format."

def is_valid_phone(phone_number):
    """Validate phone number format."""
    try:
        # Remove spaces and check if it contains only digits and + sign
        cleaned_phone = phone_number.replace(" ", "").replace("-", "")
        if not cleaned_phone.startswith("+"):
            return "Phone number must start with country code (e.g., +250)"
        
        # Check if remaining characters are digits
        if not cleaned_phone[1:].isdigit():
            return "Phone number must contain only digits after the country code."
        
        # Check length (international format typically 10-15 digits)
        if len(cleaned_phone) < 10 or len(cleaned_phone) > 16:
            return "Phone number must be between 10 and 15 digits (including country code)."
        
        return None
    except Exception as e:
        error_msg = f"Error validating phone number: {str(e)}"
        print(error_msg)
        return "Error validating phone number format."

def generate_secure_password():
    """Generate a secure random password that meets complexity requirements."""
    try:
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special_chars = "!@#$%^&*(),.?\":{}|<>"
        
        password = [
            random.choice(lowercase),
            random.choice(uppercase),
            random.choice(digits),
            random.choice(special_chars)
        ]
        
        all_chars = lowercase + uppercase + digits + special_chars
        password.extend(random.choice(all_chars) for _ in range(4))
        
        random.shuffle(password)
        return ''.join(password)
    except Exception as e:
        error_msg = f"Error generating secure password: {str(e)}"
        print(error_msg)
        return None

# ==================== AUTHENTICATION VIEWS ====================



@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    
    try:
            print(f"\n{'='*50}")
            print(f"REGISTRATION REQUEST RECEIVED")
            print(f"{'='*50}")
            print(f"Submitted data: {request.data}\n")
            
            # Extract data
            phone_number = request.data.get('phone_number', '').strip()
            email = request.data.get('email', '').strip()
            full_name = request.data.get('full_name', '').strip()
            department = request.data.get('department', 0)
            departments = request.data.get('departments', [])  # For mentors
            role = request.data.get('role', 'mentee').strip().lower()
            requesting_user = request.user if request.user.is_authenticated else None
            
            # Validate required fields
            if not phone_number:
                error_msg = "Phone number is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if not email:
                error_msg = "Email address is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if not full_name:
                error_msg = "Full name is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Validate phone number format
            phone_error = is_valid_phone(phone_number)
            if phone_error:
                print(f"ERROR: {phone_error}")
                return Response({"error": phone_error}, status=400)
            
            # Validate email format
            email_error = is_valid_email(email)
            if email_error:
                print(f"ERROR: {email_error}")
                return Response({"error": email_error}, status=400)
            
            # Check role-based permissions
            if role not in ['admin', 'mentor', 'mentee', 'hr']:
                error_msg = f"Invalid role '{role}'. Must be one of: admin, mentor, mentee, hr"
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Department validation based on role
            if role == 'mentee':
                if not department:
                    error_msg = "Department is required for mentee users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate department exists and is active
                try:
                    dept_obj = Department.objects.get(id=department, status='active')
                except Department.DoesNotExist:
                    error_msg = "Invalid or inactive department selected."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role == 'mentor':
                if not departments or len(departments) == 0:
                    error_msg = "At least one department is required for mentor users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate all departments exist and are active
                valid_depts = Department.objects.filter(id__in=departments, status='active')
                if valid_depts.count() != len(departments):
                    error_msg = "One or more selected departments are invalid or inactive."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role in ['admin', 'hr']:
                # Admin and HR don't require departments
                department = None
                departments = []
            
            # Role-based permission checks
            if role != 'mentee' and not requesting_user:
                error_msg = "Only admin or HR can create users with roles other than 'mentee'."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if requesting_user:
                if role == 'admin' and not requesting_user.is_admin:
                    error_msg = "Only admin can create admin users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'hr' and not requesting_user.is_admin:
                    error_msg = "Only admin can create HR users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'mentor' and not (requesting_user.is_admin or requesting_user.is_hr):
                    error_msg = "Only admin or HR can create mentor users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
            
            # Check for existing users
            if CustomUser.objects.filter(phone_number=phone_number).exists():
                error_msg = "A user with this phone number already exists."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if CustomUser.objects.filter(email=email).exists():
                error_msg = "A user with this email already exists."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Handle password
            if requesting_user:
                password = generate_secure_password()
                if not password:
                    error_msg = "Failed to generate secure password. Please try again."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=500)
            else:
                password = request.data.get('password', '').strip()
                confirm_password = request.data.get('confirm_password', '').strip()
                
                if not password:
                    error_msg = "Password is required."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                if not confirm_password:
                    error_msg = "Password confirmation is required."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                if password != confirm_password:
                    error_msg = "Passwords do not match."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                password_error = is_valid_password(password)
                if password_error:
                    print(f"ERROR: {password_error}")
                    return Response({"error": password_error}, status=400)
            
            # Generate work mail address
            try:
                work_mail_address = CustomUser.objects.generate_work_mail(full_name, role)
                print(f"Generated work email: {work_mail_address}")
            except Exception as e:
                error_msg = f"Failed to generate work email address: {str(e)}"
                print(f"ERROR: {error_msg}")
                print(traceback.format_exc())
                return Response({"error": "Failed to generate work email address. Please try again."}, status=500)
            
            # Create user with proper parameters based on role
            try:
                if role == 'mentee':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=department,  # Pass department ID for mentee
                        departments=None,
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                elif role == 'mentor':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=None,
                        departments=departments,  # Pass departments list for mentor
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                else:  # admin or hr
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=None,
                        departments=None,
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                
                print(f"SUCCESS: User created with ID: {user.id}")
                print(f"User details: {user.full_name} - {user.work_mail_address}")
                
                if role == 'mentor':
                    print(f"Mentor departments: {[d.name for d in user.departments.all()]}")
                    
            except IntegrityError as e:
                error_msg = f"Database integrity error: A user with this information already exists."
                print(f"ERROR: {error_msg}")
                print(f"IntegrityError details: {str(e)}")
                return Response({"error": "A user with this information already exists."}, status=400)
            except Exception as e:
                error_msg = f"Error creating user: {str(e)}"
                print(f"ERROR: {error_msg}")
                print(traceback.format_exc())
                return Response({"error": "Failed to create user account. Please try again."}, status=500)
            
            # Send email with credentials
            try:
                # Get department info for email
                dept_info = ""
                if role == 'mentee':
                    dept_info = f"Department: {user.department.name}"
                elif role == 'mentor':
                    dept_names = [d.name for d in user.departments.all()]
                    dept_info = f"Departments: {', '.join(dept_names)}"
                else:
                    dept_info = "Department: N/A (Admin/HR)"
                
                subject = "Welcome to BTSL Mentorship System"
                message = f"""
            Hello {full_name},

            Your account has been successfully created in the BTSL Mentorship System.

            Account Details:
            - Full Name: {full_name}
            - Role: {role.title()}
                - {dept_info}
                - Work Email: {work_mail_address}
                - Personal Email: {email}
                - Password: {password}

                Please use your work email ({work_mail_address}) to log in to the system.

                Important: This is a system-generated password. For security reasons, please change it after your first login.

                If you have any questions, please contact our support team.

                Best regards,
                BTSL Mentorship Team
                            """
                            
                send_mail(
                                subject=subject,
                                message=message,
                                from_email="no-reply@btsl_mentorship.com",
                                recipient_list=[email],
                                fail_silently=False,
                            )
                print(f"SUCCESS: Email sent to {email}")
                
                success_msg = "User registered successfully. Please check your email for login credentials."
                print(f"SUCCESS: {success_msg}")
                print(f"{'='*50}\n")
                        
                return Response({
                            "message": success_msg,
                            "work_mail_address": work_mail_address,
                            "status": user.status,
                            "role": user.role
                        }, status=201)
                        
            except Exception as e:
                error_msg = f"Warning: User created but email failed to send: {str(e)}"
                print(f"WARNING: {error_msg}")
                
                # User created successfully but email failed - still return success
                success_msg = "User registered successfully. Please check your email for login credentials (email delivery may be delayed)."
                print(f"SUCCESS: {success_msg}")
                print(f"{'='*50}\n")
                        
                return Response({
                            "message": success_msg,
                            "work_mail_address": work_mail_address,
                            "status": user.status,
                            "role": user.role,
                            "warning": "Email delivery may be delayed"
                        }, status=201)

    except Exception as e:
            error_msg = f"Unexpected error during registration: {str(e)}"
            print(f"CRITICAL ERROR: {error_msg}")
            print(traceback.format_exc())
            return Response({
                "error": "An unexpected error occurred during registration. Please try again or contact support."
            }, status=500)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login_user(request):
    """Login user with work mail."""
    try:
        print(f"\n{'='*50}")
        print(f"LOGIN REQUEST RECEIVED")
        print(f"{'='*50}")
        
        identifier = request.data.get('work_mail_address', '').strip()
        password = request.data.get('password', '').strip()
        
        print(f"Login attempt with identifier: {identifier}")
        
        if not identifier:
            error_msg = "Work email is required."
            print(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if not password:
            error_msg = "Password is required."
            print(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        user = CustomUser.objects.filter(work_mail_address=identifier).first()
        
        if not user:
            error_msg = "Invalid credentials. Please check your email and password."
            print(f"ERROR: User not found with identifier: {identifier}")
            return Response({"error": error_msg}, status=401)
        
        print(f"User found: {user.full_name} ({user.email})")
        
        if not check_password(password, user.password):
            error_msg = "Invalid credentials. Please check your email and password."
            print(f"ERROR: Invalid password for user: {user.email}")
            return Response({"error": error_msg}, status=401)
        
        if not user.is_active:
            error_msg = "Your account is inactive. Please contact the administrator."
            print(f"ERROR: Inactive account: {user.email}")
            return Response({"error": error_msg}, status=401)
        
        if user.status == 'pending':
            error_msg = "Your account is pending approval. Please wait for administrator approval."
            print(f"ERROR: Pending account: {user.email}")
            return Response({"error": error_msg}, status=401)
        
        if user.status == 'rejected':
            error_msg = "Your account has been rejected. Please contact the administrator for more information."
            print(f"ERROR: Rejected account: {user.email}")
            return Response({"error": error_msg}, status=401)
        
        try:
            refresh = RefreshToken.for_user(user)
            print(f"SUCCESS: Login successful for user: {user.email}")
        except Exception as e:
            error_msg = f"Error generating authentication token: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({"error": "Authentication error. Please try again."}, status=500)
        
        serializer = CustomUserSerializer(user)
        
        print(f"{'='*50}\n")
        
        return Response({
            **serializer.data,
            "token": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "message": "Login successful."
        }, status=200)
        
    except Exception as e:
        error_msg = f"Unexpected error during login: {str(e)}"
        print(f"CRITICAL ERROR: {error_msg}")
        print(traceback.format_exc())
        return Response({
            "error": "An unexpected error occurred during login. Please try again."
        }, status=500)

# ==================== PASSWORD MANAGEMENT ====================


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_or_deactivate_user(request, user_id):
    """Delete or deactivate user based on role."""
    try:
        target_user = CustomUser.objects.get(id=user_id)
        current_user = request.user
        
        if not current_user.is_admin:
            if current_user.is_hr and target_user.role == 'admin':
                return Response({"error": "HR cannot delete admin users."}, status=403)
            if current_user.is_mentor and target_user.role in ['admin', 'hr']:
                return Response({"error": "Mentors cannot delete admin or HR users."}, status=403)
        
        if current_user.is_admin:
            target_user.delete()
            action = "deleted"
        else:
            target_user.is_active = False
            target_user.availability_status = 'inactive'
            target_user.save()
            action = "deactivated"
        
        return Response({"message": f"User {action} successfully."}, status=200)
        
    except ObjectDoesNotExist:
        return Response({"error": "User not found."}, status=404)



@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    """Update user information with department validation."""
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to update user information."}, status=403)
    
    try:
        target_user = CustomUser.objects.get(id=user_id)
        
        phone_number = request.data.get('phone_number')
        email = request.data.get('email')
        full_name = request.data.get('full_name')
        department = request.data.get('department')
        departments = request.data.get('departments', [])
        role = request.data.get('role')
        status_val = request.data.get('status')
        availability_status = request.data.get('availability_status')
        
        # Check if user can update departments
        if ('department' in request.data or 'departments' in request.data):
            if not request.user.can_update_departments():
                print("ERROR: Only admin and HR users can update departments.")
                return Response({
                    "error": "Only admin and HR users can update departments."
                }, status=403)
        
        # Prevent changing work mail address
        if 'work_mail_address' in request.data:
            print("ERROR: Work mail address cannot be changed.")
            return Response({"error": "Work mail address cannot be changed."}, status=400)
        
        # Validate uniqueness
        if phone_number and CustomUser.objects.filter(phone_number=phone_number).exclude(id=user_id).exists():
            print("ERROR: A user with this phone number already exists.")
            return Response({"error": "A user with this phone number already exists."}, status=400)
        
        if email and CustomUser.objects.filter(email=email).exclude(id=user_id).exists():
            print("ERROR: A user with this email already exists.")
            return Response({"error": "A user with this email already exists."}, status=400)
        
        # Role-based department validation
        if role:
            if role == 'mentee':
                # Mentee must have exactly one department
                if department is None:
                    print("ERROR: Mentee users must have a department assigned.")
                    return Response({
                        "error": "Mentee users must have a department assigned."
                    }, status=400)
                
                try:
                    dept_obj = Department.objects.get(id=department, status='active')
                    target_user.department = dept_obj
                    # Clear M2M departments for mentee
                    # We'll do this after save to avoid issues
                except Department.DoesNotExist:
                    print("ERROR: Invalid or inactive department selected.")
                    return Response({
                        "error": "Invalid or inactive department selected."
                    }, status=400)
            
            elif role == 'mentor':
                # Mentor must have at least one department
                if not departments or len(departments) == 0:
                    print("ERROR: Mentor users must have at least one department assigned.")
                    return Response({
                        "error": "Mentor users must have at least one department assigned."
                    }, status=400)
                
                valid_depts = Department.objects.filter(id__in=departments, status='active')
                if valid_depts.count() != len(departments):
                    print("ERROR: One or more selected departments are invalid or inactive.")
                    return Response({
                        "error": "One or more selected departments are invalid or inactive."
                    }, status=400)
                
                # Clear FK department for mentor
                target_user.department = None
            
            elif role in ['admin', 'hr']:
                # Admin/HR don't have departments
                target_user.department = None
            
            target_user.role = role
        
        # If department is being updated without role change
        elif 'department' in request.data and target_user.role == 'mentee':
            if department is None:
                print("ERROR: Mentee users must have a department assigned.")
                return Response({
                    "error": "Mentee users must have a department assigned."
                }, status=400)
            
            try:
                dept_obj = Department.objects.get(id=department, status='active')
                target_user.department = dept_obj
            except Department.DoesNotExist:
                print("ERROR: Invalid or inactive department selected.")
                return Response({
                    "error": "Invalid or inactive department selected."
                }, status=400)
        
        # If departments are being updated without role change
        elif 'departments' in request.data and target_user.role == 'mentor':
            if not departments or len(departments) == 0:
                print("ERROR: Mentor users must have at least one department assigned.")
                return Response({
                    "error": "Mentor users must have at least one department assigned."
                }, status=400)
            
            valid_depts = Department.objects.filter(id__in=departments, status='active')
            if valid_depts.count() != len(departments):
                print("ERROR: One or more selected departments are invalid or inactive.")
                return Response({
                    "error": "One or more selected departments are invalid or inactive."
                }, status=400)
        
        # Update other fields
        if phone_number:
            target_user.phone_number = phone_number
        if email:
            target_user.email = email
        if full_name:
            target_user.full_name = full_name
        if status_val:
            target_user.status = status_val
        if availability_status:
            target_user.availability_status = availability_status
        
        # Save with skip_validation to avoid full_clean() issues
        target_user.save(skip_validation=True)
        
        # Now update M2M relationships after save based on role
        if target_user.role == 'mentor':
            if 'departments' in request.data:
                # Update mentor departments
                target_user.departments.set(Department.objects.filter(id__in=departments, status='active'))
                print(f"SUCCESS: Updated mentor with {len(departments)} departments")
        elif target_user.role == 'mentee':
            # Clear M2M departments for mentee (they use FK)
            target_user.departments.clear()
            print("SUCCESS: Cleared M2M departments for mentee")
        elif target_user.role in ['admin', 'hr']:
            # Clear both FK and M2M for admin/hr
            target_user.departments.clear()
            print("SUCCESS: Cleared departments for admin/hr")
        
        serializer = CustomUserSerializer(target_user)
        print(f"SUCCESS: User {target_user.id} updated successfully")
        return Response({
            "message": "User updated successfully.",
            "user": serializer.data
        }, status=200)
        
    except ObjectDoesNotExist:
        print("ERROR: User with the given ID does not exist.")
        return Response({"error": "User with the given ID does not exist."}, status=404)
    except ValidationError as ve:
        print(f"ERROR: Validation error: {str(ve)}")
        return Response({"error": f"Validation error: {str(ve)}"}, status=400)
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
    
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_all_users(request):
    """List all users with proper permissions."""
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to view all users."}, status=403)
    
    users = CustomUser.objects.all()
    serializer = CustomUserSerializer(users, many=True)
    return Response({"users": serializer.data}, status=200)





@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_mentors(request):
    """List all mentors with proper permissions."""
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to view all mentors."}, status=403)

    mentors = CustomUser.objects.filter(role='mentor')
    serializer = CustomUserSerializer(mentors, many=True)
    return Response({"users": serializer.data}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_mentees(request):
    """List all mentees with proper permissions."""
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to view all mentees."}, status=403)

    mentees = CustomUser.objects.filter(role='mentee')
    serializer = CustomUserSerializer(mentees, many=True)
    return Response({"users": serializer.data}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_by_id(request, user_id):
    """Get user by ID."""
    try:
        user = CustomUser.objects.get(id=user_id)
        serializer = CustomUserSerializer(user)
        return Response(serializer.data, status=200)
    except ObjectDoesNotExist:
        return Response({"error": "User with the given ID does not exist."}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_by_email(request):
    """Get user by email."""
    email = request.query_params.get('email')
    
    if not email:
        return Response({"error": "Email is required to search for a user."}, status=400)
    
    try:
        user = CustomUser.objects.get(email=email)
        
        # Check permissions - users can only view their own profile unless admin/HR
        if not request.user.is_admin and not request.user.is_hr and request.user.email != email:
            return Response({"error": "You are not authorized to access this user."}, status=403)
        
        serializer = CustomUserSerializer(user)
        return Response(serializer.data, status=200)
    except ObjectDoesNotExist:
        return Response({"error": "User with the given email does not exist."}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_by_phone(request):
    """Get user by phone number."""
    phone_number = request.query_params.get('phone_number')
    
    if not phone_number:
        return Response({"error": "Phone number is required to search for a user."}, status=400)
    
    try:
        user = CustomUser.objects.get(phone_number=phone_number)
        
        # Check permissions - users can only view their own profile unless admin/HR
        if not request.user.is_admin and not request.user.is_hr and request.user.phone_number != phone_number:
            return Response({"error": "You are not authorized to access this user."}, status=403)
        
        serializer = CustomUserSerializer(user)
        return Response(serializer.data, status=200)
    except ObjectDoesNotExist:
        return Response({"error": "User with the given phone number does not exist."}, status=404)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def activate_user(request, user_id):
    """Activate user account."""
    try:
        # Check permissions
        if not request.user.is_admin and not request.user.is_hr:
            return Response({"error": "You are not authorized to activate users."}, status=403)
        
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Check if the user is already active
        if user.status == 'approved':
            return Response({"message": "This user account is already activated."}, status=400)
        
        # Activate the user
        user.status = 'approved'
        user.is_active = True
        user.availability_status = 'active'
        user.save()
        
        # Send notification email
        send_mail(
            subject="Account Activated - BTSL Mentorship",
            message=f"Your account has been activated. You can now log in using your work email: {user.work_mail_address}",
            from_email="no-reply@btsl_mentorship.com",
            recipient_list=[user.email],
        )
        
        return Response({"message": "User activated successfully."}, status=200)
        
    except Exception as e:
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def deactivate_user(request, user_id):
    """Deactivate user account."""
    try:
        # Check permissions
        if not request.user.is_admin and not request.user.is_hr:
            return Response({"error": "You are not authorized to deactivate users."}, status=403)
        
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Check if the user is already deactivated
        if user.status != 'approved':
            return Response({"message": "This user account is already deactivated."}, status=400)
        
        # Deactivate the user
        user.status = 'rejected'
        user.is_active = False
        user.availability_status = 'inactive'
        user.save()
        
        return Response({"message": "User deactivated successfully."}, status=200)
        
    except Exception as e:
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user_status(request, user_id):
    """Admin/HR can update user status."""
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to update user status."}, status=403)
    
    try:
        target_user = CustomUser.objects.get(id=user_id)
        new_status = request.data.get('status')
        
        if new_status not in ['pending', 'approved', 'rejected']:
            return Response({"error": "Invalid status value."}, status=400)
        
        target_user.status = new_status
        
        if new_status == 'approved':
            target_user.availability_status = 'active'
            target_user.is_active = True
        else:
            target_user.availability_status = 'inactive'
            target_user.is_active = False
        
        target_user.save()
        
        # Send notification email
        if new_status == 'approved':
            send_mail(
                subject="Account Approved - BTSL Mentorship",
                message=f"Your account has been approved. You can now log in using your work email: {target_user.work_mail_address}",
                from_email="no-reply@btsl_mentorship.com",
                recipient_list=[target_user.email],
            )
        
        serializer = CustomUserSerializer(target_user)
        return Response({
            "message": f"User status updated to {new_status}.",
            "user": serializer.data
        }, status=200)
        
    except ObjectDoesNotExist:
        return Response({"error": "User not found."}, status=404)

# ==================== PROFILE MANAGEMENT ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """Get logged-in user's information."""
    serializer = CustomUserSerializer(request.user)
    print("\n user profile: ", serializer.data, "\n")
    return Response(serializer.data, status=200)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user's own profile (cannot change departments)."""
    user = request.user
    
    if 'work_mail_address' in request.data:
        return Response({"error": "Work mail address cannot be changed."}, status=400)
    
    if 'role' in request.data:
        return Response({"error": "Role cannot be changed."}, status=400)
    
    if 'department' in request.data or 'departments' in request.data:
        return Response({
            "error": "You cannot change your department(s). Please contact admin or HR."
        }, status=403)
    
    allowed_fields = ['phone_number', 'email', 'full_name', 'availability_status']
    
    for field in allowed_fields:
        if field in request.data:
            setattr(user, field, request.data[field])
    
    try:
        if 'phone_number' in request.data:
            if CustomUser.objects.filter(phone_number=request.data['phone_number']).exclude(id=user.id).exists():
                return Response({"error": "Phone number already exists."}, status=400)
        
        if 'email' in request.data:
            if CustomUser.objects.filter(email=request.data['email']).exclude(id=user.id).exists():
                return Response({"error": "Email already exists."}, status=400)
        
        user.save()
        serializer = CustomUserSerializer(user)
        return Response({
            "message": "Profile updated successfully.",
            "user": serializer.data
        }, status=200)
    except IntegrityError:
        return Response({"error": "Update failed due to data conflict."}, status=400)
    except Exception as e:
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)


# ==================== CONTACT US ====================

@api_view(['POST'])
@permission_classes([AllowAny])
def contact_us(request):
    """Handle contact us form submission."""
    logger.info("Received contact request with data: %s", request.data)
    
    serializer = ContactUsSerializer(data=request.data)
    
    if serializer.is_valid():
        names = serializer.validated_data['names']
        email = serializer.validated_data['email']
        subject = serializer.validated_data['subject']
        description = serializer.validated_data['description']
        
        # Check for empty fields
        if not names.strip():
            logger.error("Name field is empty.")
            return Response({"error": "Name field cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        if not subject.strip():
            logger.error("Subject field is empty.")
            return Response({"error": "Subject field cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        if not description.strip():
            logger.error("Description field is empty.")
            return Response({"error": "Description field cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            logger.error("Invalid email format: %s", email)
            return Response({"error": "Invalid email format."}, status=status.HTTP_400_BAD_REQUEST)

        # Sending email
        try:
            send_mail(
                subject=f"Contact Us: {subject}",
                message=f"Name: {names}\nEmail: {email}\n\nDescription:\n{description}",
                from_email=email,
                recipient_list=['princemugabe568@gmail.com'],
                fail_silently=False,
            )
            logger.info("Email sent successfully to %s", email)
            return Response({"message": "Email sent successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("An error occurred while sending email: %s", e)
            return Response({"error": "Failed to send email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    logger.error("Invalid serializer data: %s", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)






import traceback
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import CustomUser
from .utils import generate_otp, store_otp, verify_otp, send_otp_email
import logging

logger = logging.getLogger(__name__)

def is_valid_password(password):
    """Validate password complexity."""
    try:
        if len(password) < 8:
            return "Password must be at least 8 characters long."
        if not any(char.isdigit() for char in password):
            return "Password must include at least one number."
        if not any(char.isupper() for char in password):
            return "Password must include at least one uppercase letter."
        if not any(char.islower() for char in password):
            return "Password must include at least one lowercase letter."
        import re
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return "Password must include at least one special character (!@#$%^&* etc.)."
        return None
    except Exception as e:
        logger.error(f"Error validating password: {str(e)}")
        return "Error validating password format."


@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset_otp(request):
    """Request OTP for password reset"""
    try:
        logger.info("\n" + "="*50)
        logger.info("PASSWORD RESET OTP REQUEST")
        logger.info("="*50)
        
        work_mail_address = request.data.get('work_mail_address', '').strip()
        
        if not work_mail_address:
            error_msg = "Work email address is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Check if user exists with this work email
        try:
            user = CustomUser.objects.get(work_mail_address=work_mail_address)
            logger.info(f"User found: {user.full_name}")
        except CustomUser.DoesNotExist:
            error_msg = "No account found with this work email address."
            logger.error(f"ERROR: {error_msg} - {work_mail_address}")
            return Response({"error": error_msg}, status=404)
        
        # Check if user is active
        if not user.is_active or user.status != 'approved':
            error_msg = "Your account is not active. Please contact administrator."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Generate OTP
        otp = generate_otp(6)
        logger.info(f"Generated OTP: {otp} for user: {work_mail_address}")
        
        # Store OTP in cache (expires in 30 seconds)
        cache_key = store_otp(work_mail_address, otp, expiry_seconds=30)
        logger.info(f"OTP stored with cache key: {cache_key}")
        
        # Send OTP via email
        logger.info(f"Attempting to send OTP email to {user.email}...")
        email_sent = send_otp_email(user, otp)
        
        if not email_sent:
            error_msg = "Failed to send OTP email. Please try again."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=500)
        
        logger.info(f"SUCCESS: OTP sent to {user.email}")
        logger.info("="*50 + "\n")
        
        return Response({
            "message": "OTP has been sent to your registered email address.",
            "work_mail_address": work_mail_address,
            "email": user.email,  # For debugging
            "expires_in": "30 seconds"
        }, status=200)
        
    except Exception as e:
        error_msg = f"Unexpected error during OTP request: {str(e)}"
        logger.error(f"CRITICAL ERROR: {error_msg}")
        logger.error(traceback.format_exc())
        return Response({
            "error": "An unexpected error occurred. Please try again.",
            "detail": str(e)  # Include detail for debugging
        }, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_reset_otp(request):
    """Verify OTP for password reset"""
    try:
        logger.info("\n" + "="*50)
        logger.info("VERIFY RESET OTP")
        logger.info("="*50)
        
        work_mail_address = request.data.get('work_mail_address', '').strip()
        otp = request.data.get('otp', '').strip()
        
        if not work_mail_address:
            error_msg = "Work email address is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if not otp:
            error_msg = "OTP is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        logger.info(f"Verifying OTP for: {work_mail_address}")
        
        # Verify OTP
        is_valid, message = verify_otp(work_mail_address, otp)
        
        if not is_valid:
            logger.error(f"ERROR: OTP verification failed - {message}")
            return Response({"error": message}, status=400)
        
        logger.info(f"SUCCESS: OTP verified for {work_mail_address}")
        logger.info("="*50 + "\n")
        
        return Response({
            "message": "OTP verified successfully. You can now reset your password.",
            "verified": True,
            "work_mail_address": work_mail_address
        }, status=200)
        
    except Exception as e:
        error_msg = f"Unexpected error during OTP verification: {str(e)}"
        logger.error(f"CRITICAL ERROR: {error_msg}")
        logger.error(traceback.format_exc())
        return Response({
            "error": "An unexpected error occurred. Please try again.",
            "detail": str(e)
        }, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_with_otp(request):
    """Reset password after OTP verification"""
    try:
        logger.info("\n" + "="*50)
        logger.info("PASSWORD RESET WITH OTP")
        logger.info("="*50)
        
        work_mail_address = request.data.get('work_mail_address', '').strip()
        # otp = request.data.get('otp', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()
        
        # Validate inputs
        if not work_mail_address:
            error_msg = "Work email address is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # if not otp:
        #     error_msg = "OTP is required."
        #     logger.error(f"ERROR: {error_msg}")
        #     return Response({"error": error_msg}, status=400)
        
        if not new_password:
            error_msg = "New password is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if not confirm_password:
            error_msg = "Password confirmation is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if new_password != confirm_password:
            error_msg = "Passwords do not match."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Validate password strength
        password_error = is_valid_password(new_password)
        if password_error:
            logger.error(f"ERROR: {password_error}")
            return Response({"error": password_error}, status=400)
        
        # Verify OTP one more time
        # is_valid, message = verify_otp(work_mail_address, otp)
        
        # if not is_valid:
        #     logger.error(f"ERROR: OTP verification failed - {message}")
        #     return Response({"error": message}, status=400)
        
        # Get user
        try:
            user = CustomUser.objects.get(work_mail_address=work_mail_address)
            logger.info(f"User found: {user.full_name}")
        except CustomUser.DoesNotExist:
            error_msg = "User not found."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=404)
        
        # Update password
        user.set_password(new_password)
        user.save()
        logger.info(f"SUCCESS: Password updated for user: {work_mail_address}")
        
        # Send confirmation email
        try:
            send_mail(
                subject="Password Reset Successful - BTSL Mentorship",
                message=f"""
Hello {user.full_name},

Your password has been successfully reset for the BTSL Digital Mentorship System.

If you did not perform this action, please contact our support team immediately.

Best regards,
BTSL Digital Mentorship Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"SUCCESS: Confirmation email sent to {user.email}")
        except Exception as e:
            logger.warning(f"WARNING: Password reset successful but email failed: {str(e)}")
        
        logger.info("="*50 + "\n")
        
        return Response({
            "message": "Password reset successfully. You can now login with your new password.",
            "success": True
        }, status=200)
        
    except Exception as e:
        error_msg = f"Unexpected error during password reset: {str(e)}"
        logger.error(f"CRITICAL ERROR: {error_msg}")
        logger.error(traceback.format_exc())
        return Response({
            "error": "An unexpected error occurred. Please try again.",
            "detail": str(e)
        }, status=500)
    





@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def users_list_create(request):
    """
    GET: List all users (admin/HR only)
    POST: Create new user (admin/HR only)
    """
    # Check permissions for both methods
    if not request.user.is_admin and not request.user.is_hr:
        return Response({
            "error": "You are not authorized to perform this action."
        }, status=403)
    
    if request.method == 'GET':
        users = CustomUser.objects.all()
        serializer = CustomUserSerializer(users, many=True)
        return Response({"users": serializer.data}, status=200)
    
    elif request.method == 'POST':
        try:
            print(f"\n{'='*50}")
            print(f"REGISTRATION REQUEST RECEIVED")
            print(f"{'='*50}")
            print(f"Submitted data: {request.data}\n")
            
            # Extract data
            phone_number = request.data.get('phone_number', '').strip()
            email = request.data.get('email', '').strip()
            full_name = request.data.get('full_name', '').strip()
            department = request.data.get('department', '').strip() or None
            departments = request.data.get('departments', [])  # For mentors
            role = request.data.get('role', 'mentee').strip().lower()
            requesting_user = request.user if request.user.is_authenticated else None
            
            # Validate required fields
            if not phone_number:
                error_msg = "Phone number is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if not email:
                error_msg = "Email address is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if not full_name:
                error_msg = "Full name is required."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Validate phone number format
            phone_error = is_valid_phone(phone_number)
            if phone_error:
                print(f"ERROR: {phone_error}")
                return Response({"error": phone_error}, status=400)
            
            # Validate email format
            email_error = is_valid_email(email)
            if email_error:
                print(f"ERROR: {email_error}")
                return Response({"error": email_error}, status=400)
            
            # Check role-based permissions
            if role not in ['admin', 'mentor', 'mentee', 'hr']:
                error_msg = f"Invalid role '{role}'. Must be one of: admin, mentor, mentee, hr"
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Department validation based on role
            if role == 'mentee':
                if not department:
                    error_msg = "Department is required for mentee users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate department exists and is active
                try:
                    dept_obj = Department.objects.get(id=department, status='active')
                except Department.DoesNotExist:
                    error_msg = "Invalid or inactive department selected."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role == 'mentor':
                if not departments or len(departments) == 0:
                    error_msg = "At least one department is required for mentor users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate all departments exist and are active
                valid_depts = Department.objects.filter(id__in=departments, status='active')
                if valid_depts.count() != len(departments):
                    error_msg = "One or more selected departments are invalid or inactive."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role in ['admin', 'hr']:
                # Admin and HR don't require departments
                department = None
                departments = []
            
            # Role-based permission checks
            if role != 'mentee' and not requesting_user:
                error_msg = "Only admin or HR can create users with roles other than 'mentee'."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if requesting_user:
                if role == 'admin' and not requesting_user.is_admin:
                    error_msg = "Only admin can create admin users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'hr' and not requesting_user.is_admin:
                    error_msg = "Only admin can create HR users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'mentor' and not (requesting_user.is_admin or requesting_user.is_hr):
                    error_msg = "Only admin or HR can create mentor users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
            
            # Check for existing users
            if CustomUser.objects.filter(phone_number=phone_number).exists():
                error_msg = "A user with this phone number already exists."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if CustomUser.objects.filter(email=email).exists():
                error_msg = "A user with this email already exists."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Handle password
            if requesting_user:
                password = generate_secure_password()
                if not password:
                    error_msg = "Failed to generate secure password. Please try again."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=500)
            else:
                password = request.data.get('password', '').strip()
                confirm_password = request.data.get('confirm_password', '').strip()
                
                if not password:
                    error_msg = "Password is required."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                if not confirm_password:
                    error_msg = "Password confirmation is required."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                if password != confirm_password:
                    error_msg = "Passwords do not match."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                password_error = is_valid_password(password)
                if password_error:
                    print(f"ERROR: {password_error}")
                    return Response({"error": password_error}, status=400)
            
            # Generate work mail address
            try:
                work_mail_address = CustomUser.objects.generate_work_mail(full_name, role)
                print(f"Generated work email: {work_mail_address}")
            except Exception as e:
                error_msg = f"Failed to generate work email address: {str(e)}"
                print(f"ERROR: {error_msg}")
                print(traceback.format_exc())
                return Response({"error": "Failed to generate work email address. Please try again."}, status=500)
            
            # Create user with proper parameters based on role
            try:
                if role == 'mentee':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=department,  # Pass department ID for mentee
                        departments=None,
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                elif role == 'mentor':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=None,
                        departments=departments,  # Pass departments list for mentor
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                else:  # admin or hr
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=None,
                        departments=None,
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                
                print(f"SUCCESS: User created with ID: {user.id}")
                print(f"User details: {user.full_name} - {user.work_mail_address}")
                
                if role == 'mentor':
                    print(f"Mentor departments: {[d.name for d in user.departments.all()]}")
                    
            except IntegrityError as e:
                error_msg = f"Database integrity error: A user with this information already exists."
                print(f"ERROR: {error_msg}")
                print(f"IntegrityError details: {str(e)}")
                return Response({"error": "A user with this information already exists."}, status=400)
            except Exception as e:
                error_msg = f"Error creating user: {str(e)}"
                print(f"ERROR: {error_msg}")
                print(traceback.format_exc())
                return Response({"error": "Failed to create user account. Please try again."}, status=500)
            
            # Send email with credentials
            try:
                # Get department info for email
                dept_info = ""
                if role == 'mentee':
                    dept_info = f"Department: {user.department.name}"
                elif role == 'mentor':
                    dept_names = [d.name for d in user.departments.all()]
                    dept_info = f"Departments: {', '.join(dept_names)}"
                else:
                    dept_info = "Department: N/A (Admin/HR)"
                
                subject = "Welcome to BTSL Mentorship System"
                message = f"""
            Hello {full_name},

            Your account has been successfully created in the BTSL Mentorship System.

            Account Details:
            - Full Name: {full_name}
            - Role: {role.title()}
                - {dept_info}
                - Work Email: {work_mail_address}
                - Personal Email: {email}
                - Password: {password}

                Please use your work email ({work_mail_address}) to log in to the system.

                Important: This is a system-generated password. For security reasons, please change it after your first login.

                If you have any questions, please contact our support team.

                Best regards,
                BTSL Mentorship Team
                            """
                            
                send_mail(
                                subject=subject,
                                message=message,
                                from_email="no-reply@btsl_mentorship.com",
                                recipient_list=[email],
                                fail_silently=False,
                            )
                print(f"SUCCESS: Email sent to {email}")
                
                success_msg = "User registered successfully. Please check your email for login credentials."
                print(f"SUCCESS: {success_msg}")
                print(f"{'='*50}\n")
                        
                return Response({
                            "message": success_msg,
                            "work_mail_address": work_mail_address,
                            "status": user.status,
                            "role": user.role
                        }, status=201)
                        
            except Exception as e:
                error_msg = f"Warning: User created but email failed to send: {str(e)}"
                print(f"WARNING: {error_msg}")
                
                # User created successfully but email failed - still return success
                success_msg = "User registered successfully. Please check your email for login credentials (email delivery may be delayed)."
                print(f"SUCCESS: {success_msg}")
                print(f"{'='*50}\n")
                        
                return Response({
                            "message": success_msg,
                            "work_mail_address": work_mail_address,
                            "status": user.status,
                            "role": user.role,
                            "warning": "Email delivery may be delayed"
                        }, status=201)

        except Exception as e:
            error_msg = f"Unexpected error during registration: {str(e)}"
            print(f"CRITICAL ERROR: {error_msg}")
            print(traceback.format_exc())
            return Response({
                "error": "An unexpected error occurred during registration. Please try again or contact support."
            }, status=500)



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
    




@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change password for logged-in user with current password verification"""
    try:
        logger.info("\n" + "="*50)
        logger.info("PASSWORD CHANGE REQUEST")
        logger.info("="*50)
        
        user = request.user
        current_password = request.data.get('current_password', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()
        
        # Validate required fields
        if not current_password:
            error_msg = "Current password is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if not new_password:
            error_msg = "New password is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if not confirm_password:
            error_msg = "Password confirmation is required."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Verify current password
        if not user.check_password(current_password):
            error_msg = "Current password is incorrect."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Check if new password is same as current
        if user.check_password(new_password):
            error_msg = "New password cannot be the same as current password."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Check password match
        if new_password != confirm_password:
            error_msg = "New passwords do not match."
            logger.error(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Validate password strength
        password_error = is_valid_password(new_password)
        if password_error:
            logger.error(f"ERROR: {password_error}")
            return Response({"error": password_error}, status=400)
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        logger.info(f"SUCCESS: Password changed for user: {user.work_mail_address}")
        
        # Send notification email
        try:
            send_mail(
                subject="Password Changed Successfully - BTSL Mentorship",
                message=f"""
Hello {user.full_name},

Your password has been successfully changed for the BTSL Digital Mentorship System.

If you did not make this change, please contact our support team immediately.

Best regards,
BTSL Digital Mentorship Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"SUCCESS: Notification email sent to {user.email}")
        except Exception as e:
            logger.warning(f"WARNING: Password changed but email failed: {str(e)}")
        
        logger.info("="*50 + "\n")
        
        return Response({
            "message": "Password changed successfully.",
            "success": True
        }, status=200)
        
    except Exception as e:
        error_msg = f"Unexpected error during password change: {str(e)}"
        logger.error(f"CRITICAL ERROR: {error_msg}")
        logger.error(traceback.format_exc())
        return Response({
            "error": "An unexpected error occurred. Please try again.",
            "detail": str(e)
        }, status=500)
    

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Logout user and blacklist refresh token"""
    try:
        print("\n" + "="*50)
        print("LOGOUT REQUEST")
        print("="*50)
        
        refresh_token = request.data.get('refresh_token')
        
        if not refresh_token:
            print("No refresh token provided")
            return Response({
                "message": "Logged out successfully (no token to blacklist)"
            }, status=200)
        
        try:
            # Blacklist the refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()
            print(f"SUCCESS: Token blacklisted for user: {request.user.work_mail_address}")
        except TokenError as e:
            print(f"Token error during blacklist: {str(e)}")
            # Token might already be invalid/blacklisted, but we still log them out
        
        print("="*50 + "\n")
        
        return Response({
            "message": "Logged out successfully"
        }, status=200)
        
    except Exception as e:
        print(f"Error during logout: {str(e)}")
        print(traceback.format_exc())
        # Even if there's an error, we return success to ensure user is logged out on frontend
        return Response({
            "message": "Logged out successfully"
        }, status=200)


# Add this endpoint to verify token validity
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_token(request):
    """Verify if the current access token is valid"""
    try:
        user = request.user
        serializer = CustomUserSerializer(user)
        
        return Response({
            "valid": True,
            "user": serializer.data
        }, status=200)
        
    except Exception as e:
        return Response({
            "valid": False,
            "error": str(e)
        }, status=401)