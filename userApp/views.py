# views.py

from datetime import timezone
import time
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
from django.core.cache import cache
from departmentApp.models import Department
from .utils import generate_otp, store_otp, verify_otp, ActivityLogger
from django.db import models
from rest_framework_simplejwt.exceptions import TokenError
from datetime import timedelta
from django.utils.timezone import now
from collections import Counter
from .login_attempts import LoginAttemptManager

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
    
    print("\nReceived registration request with data:", request.data)
    try:
        print(f"\n{'='*50}")
        print(f"REGISTRATION REQUEST RECEIVED")
        print(f"{'='*50}")
        
        # Extract data
        phone_number = request.data.get('phone_number', '').strip()
        email = request.data.get('email', '').strip()
        full_name = request.data.get('full_name', '').strip()
        department = request.data.get('department')
        departments = request.data.get('departments', [])  # For security analysts
        role = request.data.get('role', 'employee').strip().lower()
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
        valid_roles = ['admin', 'employee', 'compliance_officer', 'security_analyst', 'hr_manager']
        if role not in valid_roles:
            error_msg = f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}"
            print(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        # Role-based permission checks
        if role != 'employee' and not requesting_user:
            error_msg = "Only admin or HR can create users with roles other than 'employee'."
            print(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=400)
        
        if requesting_user:
            if role == 'admin' and not requesting_user.is_admin:
                error_msg = "Only admin can create admin users."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=403)
            if role == 'hr_manager' and not requesting_user.is_admin:
                error_msg = "Only admin can create HR Manager users."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=403)
            if role == 'security_analyst' and not (requesting_user.is_admin or requesting_user.is_hr):
                error_msg = "Only admin or HR can create Security Analyst users."
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
        
        # Generate system password
        password = generate_secure_password()
        if not password:
            error_msg = "Failed to generate secure password. Please try again."
            print(f"ERROR: {error_msg}")
            return Response({"error": error_msg}, status=500)
        
        # Generate work mail address
        try:
            work_mail_address = CustomUser.objects.generate_work_mail(full_name, role)
            print(f"Generated work email: {work_mail_address}")
        except Exception as e:
            error_msg = f"Failed to generate work email address: {str(e)}"
            print(f"ERROR: {error_msg}")
            print(traceback.format_exc())
            return Response({"error": "Failed to generate work email address. Please try again."}, status=500)
        
        # Create user with proper parameters
        try:
            user = CustomUser.objects.create_user(
                phone_number=phone_number,
                email=email,
                full_name=full_name,
                department=department if role == 'employee' else None,
                departments=departments if role == 'security_analyst' else None,
                role=role,
                work_mail_address=work_mail_address,
                password=password,
                created_by=requesting_user,
                status='approved' if requesting_user else 'pending',
                availability_status='active' if requesting_user else 'inactive',
            )
            
            print(f"SUCCESS: User created with ID: {user.id}")
            print(f"User details: {user.full_name} - {user.work_mail_address}")
            
            if role == 'employee' and department:
                print(f"Employee department: {user.department.name if user.department else 'None'}")
            elif role == 'security_analyst' and departments:
                print(f"Security Analyst departments: {[d.name for d in user.departments.all()]}")
                
        except IntegrityError as e:
            error_msg = f"Database integrity error: A user with this information already exists."
            print(f"ERROR: {error_msg}")
            print(f"IntegrityError details: {str(e)}")
            return Response({"error": "A user with this information already exists."}, status=400)
        except ValueError as e:
            error_msg = f"Validation error: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            error_msg = f"Error creating user: {str(e)}"
            print(f"ERROR: {error_msg}")
            print(traceback.format_exc())
            return Response({"error": "Failed to create user account. Please try again."}, status=500)
        
        # Send email with credentials
        try:
            # Get department info for email
            dept_info = ""
            if role == 'employee' and user.department:
                dept_info = f"Department: {user.department.name}"
            elif role == 'security_analyst':
                dept_names = [d.name for d in user.departments.all()]
                if dept_names:
                    dept_info = f"Departments: {', '.join(dept_names)}"
            
            subject = "Welcome to Hammer Tech - Your Account Details"
            message = f"""
        Hello {full_name},

        Your account has been successfully created in the Hammer Tech System.
        Account Details:
        - Full Name: {full_name}
        - Role: {role.title()}
        {f'- {dept_info}' if dept_info else ''}
        - Work Email: {work_mail_address}
        - Personal Email: {email}
        - Password: {password}

        Please use your work email ({work_mail_address}) to log in to the system.

        Important: This is a system-generated password. For security reasons, please change it after your first login.

        If you have any questions, please contact our support team.

        Best regards,
        Hammer Tech Team
                        """
                        
            send_mail(
                subject=subject,
                message=message,
                from_email="no-reply@hammer_grp_tech.com",
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
                "role": user.role,
                "department": user.department.name if user.department else None,
                "departments": [d.name for d in user.departments.all()] if user.departments.exists() else []
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
                "department": user.department.name if user.department else None,
                "departments": [d.name for d in user.departments.all()] if user.departments.exists() else [],
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
@permission_classes([AllowAny])
def login_with_otp_request(request):
    """Step 1: Request OTP for login with attempt tracking"""
    start_time = time.time()
    
    try:
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '').strip()
        
        if not email or not password:
            print(f"ERROR: Missing email or password for login attempt.")
            response = Response({
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
            ActivityLogger.log_authentication(
                user=None,
                activity='login_otp_request',
                description=f'Failed: Missing credentials for {email}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        try:
            user = CustomUser.objects.get(email=email, is_active=True)
        except CustomUser.DoesNotExist:
            print(f"ERROR: User with email {email} not found or inactive.")
            response = Response({
                'message': 'Invalid credentials or account is inactive'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
            ActivityLogger.log_authentication(
                user=None,
                activity='login_otp_request',
                description=f'Failed: User {email} not found or inactive',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check if account is locked due to too many attempts
        can_attempt, lock_message, remaining_seconds = LoginAttemptManager.check_login_attempts(user)
        if not can_attempt:
            response = Response({
                'message': lock_message,
                'is_locked': True,
                'remaining_seconds': remaining_seconds,
                'remaining_minutes': remaining_seconds // 60,
                'remaining_seconds_display': remaining_seconds % 60
            }, status=status.HTTP_423_LOCKED)  # 423 Locked status code
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_blocked',
                description=f'Login blocked - Account locked: {lock_message}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Verify password
        if not user.check_password(password):
            print(f"ERROR: Invalid password for user {email}")
            # Handle failed login attempt
            is_locked, fail_message, lock_duration = LoginAttemptManager.handle_failed_login(user, request)
            
            if is_locked:
                response = Response({
                    'message': fail_message,
                    'is_locked': True,
                    'remaining_seconds': lock_duration,
                    'remaining_minutes': lock_duration // 60,
                    'failed_attempts': user.failed_login_attempts
                }, status=status.HTTP_423_LOCKED)
            else:
                print(f"ERROR: Invalid password for user {email}. {3 - user.failed_login_attempts} attempts remaining.")
                response = Response({
                    'message': fail_message,
                    'remaining_attempts': 3 - user.failed_login_attempts,
                    'failed_attempts': user.failed_login_attempts
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_request',
                description=f'Failed: Invalid password - {fail_message}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check if account is approved
        if user.status != 'approved':
            response = Response({
                'message': f'Account is {user.status}. Please contact administrator.'
            }, status=status.HTTP_403_FORBIDDEN)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_request',
                description=f'Failed: Account status is {user.status}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Reset login attempts on successful password verification
        LoginAttemptManager.handle_successful_login(user, request)
        
        # Generate and store OTP
        otp = generate_otp()
        store_otp(user.email, otp, expiry_seconds=120)
        
        # Send OTP to email
        if send_otp_email(user, otp):
            response = Response({
                'message': 'OTP has been sent to your email',
                'email': user.email
            }, status=status.HTTP_200_OK)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_request',
                description=f'OTP sent to {user.email} - Password verified successfully',
                request=request,
                response=response,
                is_success=True,
                start_time=start_time
            )
            return response
        else:
            print(f"ERROR: Failed to send OTP email to {user.email}")
            response = Response({
                'message': 'Failed to send OTP. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_request',
                description=f'Failed to send OTP to {user.email}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
    
    except Exception as e:
        print(f"CRITICAL ERROR during OTP login request: {str(e)}")
        print(traceback.format_exc())
        response = Response({
            'message': 'An error occurred during login',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        ActivityLogger.log_authentication(
            user=None,
            activity='login_otp_request',
            description=f'Error: {str(e)}',
            request=request,
            response=response,
            is_success=False,
            start_time=start_time
        )
        return response  


@api_view(['POST'])
@permission_classes([AllowAny])
def login_with_otp_verify(request):
    """Step 2: Verify OTP and complete login with attempt tracking"""
    start_time = time.time()
    
    try:
        email = request.data.get('email', '').strip()
        otp = request.data.get('otp', '').strip()
        
        if not email or not otp:
            response = Response({
                'message': 'Email and OTP are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
            ActivityLogger.log_authentication(
                user=None,
                activity='login_otp_verify',
                description='Failed: Missing email or OTP',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        try:
            user = CustomUser.objects.get(email=email, is_active=True)
        except CustomUser.DoesNotExist:
            print(f"ERROR: User with email {email} not found or inactive.")
            response = Response({
                'message': 'Invalid credentials or account is inactive'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
            ActivityLogger.log_authentication(
                user=None,
                activity='login_otp_verify',
                description=f'Failed: User {email} not found',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check if account is locked
        if user.is_account_locked():
            remaining = user.get_lock_remaining_seconds()
            minutes = remaining // 60
            seconds = remaining % 60
            
            message = f"Account is locked. Please try again in {minutes} minute(s) and {seconds} second(s)."
            response = Response({
                'message': message,
                'is_locked': True,
                'remaining_seconds': remaining
            }, status=status.HTTP_423_LOCKED)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_verify',
                description=f'Failed: Account locked - {message}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Verify OTP
        is_valid, message = verify_otp(user.email, otp)
        
        if not is_valid:
            # Increment failed login attempts for OTP failure
            is_locked, fail_message, lock_duration = LoginAttemptManager.handle_failed_login(user, request)
            
            if is_locked:
                print(f"ERROR: OTP verification failed for {email}. Account locked due to too many failed attempts.")
                response = Response({
                    'message': fail_message,
                    'is_locked': True,
                    'remaining_seconds': lock_duration,
                    'failed_attempts': user.failed_login_attempts
                }, status=status.HTTP_423_LOCKED)
            else:
                print(f"ERROR: OTP verification failed for {email}. {3 - user.failed_login_attempts} attempts remaining.")
                response = Response({
                    'message': message,
                    'remaining_attempts': 3 - user.failed_login_attempts,
                    'failed_attempts': user.failed_login_attempts
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_verify',
                description=f'Failed: Invalid OTP - {message}. Attempt {user.failed_login_attempts}/3',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check if account is approved
        if user.status != 'approved':
            print(f"ERROR: Account status for {email} is {user.status}. Login denied.")
            response = Response({
                'message': f'Account is {user.status}. Please contact administrator.'
            }, status=status.HTTP_403_FORBIDDEN)
            
            ActivityLogger.log_authentication(
                user=user,
                activity='login_otp_verify',
                description=f'Failed: Account status is {user.status}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Reset login attempts on successful OTP verification
        LoginAttemptManager.handle_successful_login(user, request)
        
        # Clear OTP from cache after successful verification
        cache_key = f"reset_otp_{user.email}"
        cache.delete(cache_key)
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        serializer = CustomUserSerializer(user)
        
        response_data = {
            'message': 'Login successful',
            'user': serializer.data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }
        
        response = Response(response_data, status=status.HTTP_200_OK)
        
        # Log successful login
        ActivityLogger.log_authentication(
            user=user,
            activity='login',
            description=f'Login successful via OTP verification',
            request=request,
            response=response,
            is_success=True,
            start_time=start_time
        )
        
        return response
    
    except Exception as e:
        print(f"CRITICAL ERROR during OTP verification: {str(e)}")
        print(traceback.format_exc())
        response = Response({
            'message': 'An error occurred during login',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        ActivityLogger.log_authentication(
            user=None,
            activity='login_otp_verify',
            description=f'Error: {str(e)}',
            request=request,
            response=response,
            is_success=False,
            start_time=start_time
        )
        return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Logout user and blacklist refresh token"""
    start_time = time.time()
    user = request.user
    
    try:
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            try:
                # Blacklist the refresh token
                token = RefreshToken(refresh_token)
                token.blacklist()
                
                ActivityLogger.log_authentication(
                    user=user,
                    activity='logout',
                    description='Logged out successfully with token blacklisted',
                    request=request,
                    response=None,
                    is_success=True,
                    start_time=start_time
                )
                
            except TokenError as e:
                ActivityLogger.log_authentication(
                    user=user,
                    activity='logout',
                    description=f'Token blacklist failed: {str(e)}',
                    request=request,
                    response=None,
                    is_success=True,
                    start_time=start_time
                )
        else:
            ActivityLogger.log_authentication(
                user=user,
                activity='logout',
                description='Logged out (no token provided)',
                request=request,
                response=None,
                is_success=True,
                start_time=start_time
            )
        
        return Response({
            "message": "Logged out successfully"
        }, status=200)
        
    except Exception as e:
        response = Response({
            "message": "Logged out successfully",
            "error": str(e)
        }, status=200)
        
        ActivityLogger.log_authentication(
            user=user,
            activity='logout',
            description=f'Logout with error: {str(e)}',
            request=request,
            response=response,
            is_success=True,
            start_time=start_time
        )
        
        return response

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

    print(f"\n Submitted user data to update: {request.data}\n")
    if not request.user.is_admin and not request.user.is_hr:
        return Response({"error": "You are not authorized to update user information."}, status=403)
    
    try:
        target_user = CustomUser.objects.get(id=user_id)
        
        # Store the original status before any updates
        original_status = target_user.status
        original_is_active = target_user.is_active
        
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
        
        # Update basic fields
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
        
        # Handle role change
        if role:
            target_user.role = role
        
        # Save the user first
        target_user.save()
        
        # Handle department assignments based on role
        if role:
            if role == 'employee':
                # Employee: set single department
                if department:
                    try:
                        dept_obj = Department.objects.get(id=department, status='active')
                        target_user.department = dept_obj
                        target_user.departments.clear()  # Clear M2M
                    except Department.DoesNotExist:
                        return Response({
                            "error": "Invalid or inactive department selected."
                        }, status=400)
                else:
                    return Response({
                        "error": "Employee users must have a department assigned."
                    }, status=400)
            
            elif role == 'security_analyst':
                # Security Analyst: set multiple departments
                if departments:
                    valid_depts = Department.objects.filter(id__in=departments, status='active')
                    if valid_depts.count() == len(departments):
                        target_user.department = None  # Clear FK
                        target_user.departments.set(valid_depts)
                    else:
                        return Response({
                            "error": "One or more selected departments are invalid or inactive."
                        }, status=400)
                else:
                    return Response({
                        "error": "Security Analyst users must have at least one department assigned."
                    }, status=400)
            
            elif role in ['admin', 'hr_manager']:
                # Admin/HR: clear all departments
                target_user.department = None
                target_user.departments.clear()
        
        # If no role change but department/departments are being updated
        elif 'department' in request.data:
            if target_user.role == 'employee':
                if department:
                    try:
                        dept_obj = Department.objects.get(id=department, status='active')
                        target_user.department = dept_obj
                        target_user.departments.clear()  # Clear M2M
                    except Department.DoesNotExist:
                        return Response({
                            "error": "Invalid or inactive department selected."
                        }, status=400)
                else:
                    return Response({
                        "error": "Employee users must have a department assigned."
                    }, status=400)
        
        elif 'departments' in request.data:
            if target_user.role == 'security_analyst':
                if departments:
                    valid_depts = Department.objects.filter(id__in=departments, status='active')
                    if valid_depts.count() == len(departments):
                        target_user.department = None  # Clear FK
                        target_user.departments.set(valid_depts)
                    else:
                        return Response({
                            "error": "One or more selected departments are invalid or inactive."
                        }, status=400)
                else:
                    return Response({
                        "error": "Security Analyst users must have at least one department assigned."
                    }, status=400)
        
        target_user.save()
        
        # Check if status changed from inactive to active and send email
        status_changed_to_active = (
            original_status in ['pending', 'rejected'] and 
            target_user.status == 'approved'
        )
        
        if status_changed_to_active:
            print(f"Status changed from '{original_status}' to 'approved' - sending activation email")
            
            try:
                # Get department info for email
                dept_info = ""
                if target_user.role == 'employee' and target_user.department:
                    dept_info = f"\n- Department: {target_user.department.name}"
                elif target_user.role == 'security_analyst':
                    dept_names = [d.name for d in target_user.departments.all()]
                    if dept_names:
                        dept_info = f"\n- Departments: {', '.join(dept_names)}"
                
                subject = "Account Activated - Hammer Tech System"
                message = f"""
Hello {target_user.full_name},

Great news! Your account has been approved and activated in the Hammer Tech System.
Account Details:
- Full Name: {target_user.full_name}
- Role: {target_user.role.title()}
- Work Email: {target_user.work_mail_address}
- Personal Email: {target_user.email}{dept_info}

You can now log in to the system using your work email address ({target_user.work_mail_address}) and your password.

If you have forgotten your password, you can reset it using the "Forgot Password" link on the login page.

Access the system at: [Your System URL]

If you have any questions or need assistance, please don't hesitate to contact our support team.

Welcome aboard!

Best regards,
Hammer Tech Team
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email="no-reply@hammer_grp_tech.com",
                    recipient_list=[target_user.email],
                    fail_silently=False,
                )
                
                print(f"SUCCESS: Account activation email sent to {target_user.email}")
                
            except Exception as e:
                error_msg = f"Warning: User updated but activation email failed to send: {str(e)}"
                print(f"WARNING: {error_msg}")
                # Continue even if email fails - user is still activated
        
        serializer = CustomUserSerializer(target_user)
        print(f"SUCCESS: User {target_user.id} updated successfully")
        print(f"Department: {target_user.department.name if target_user.department else 'None'}")
        print(f"Departments: {[d.name for d in target_user.departments.all()]}")
        
        response_message = "User updated successfully."
        if status_changed_to_active:
            response_message += " Activation email has been sent to the user."
        
        return Response({
            "message": response_message,
            "user": serializer.data,
            "email_sent": status_changed_to_active
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
            subject="Account Activated - Hammer Tech System",
            message=f"Your account has been activated. You can now log in using your work email: {user.work_mail_address}",
            from_email="no-reply@hammer_grp_tech.com",
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
                subject="Account Approved - Hammer Tech System",
                message=f"Your account has been approved. You can now log in using your work email: {target_user.work_mail_address}",
                from_email="no-reply@hammer_grp_tech.com",
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
    """Get logged-in user's information"""
    start_time = time.time()
    
    try:
        user = request.user
        serializer = CustomUserSerializer(user)
        
        # Log profile view
        ActivityLogger.log_profile(
            user=user,
            activity='profile_view',
            description='Viewed own profile details',
            request=request,
            response=Response(serializer.data, status=200),
            is_success=True,
            start_time=start_time
        )
        
        print(f"\n retrieved user data: {serializer.data}\n")
        return Response(serializer.data, status=200)
        
    except Exception as e:
        response = Response({"error": str(e)}, status=500)
        ActivityLogger.log_profile(
            user=request.user if request.user.is_authenticated else None,
            activity='profile_view',
            description=f'Failed to view profile: {str(e)}',
            request=request,
            response=response,
            is_success=False,
            start_time=start_time
        )
        return response






@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user's own profile"""
    start_time = time.time()
    user = request.user
    
    try:
        # Log the attempt
        ActivityLogger.log_profile(
            user=user,
            activity='profile_update',
            description='Attempting to update profile',
            request=request,
            response=None,
            start_time=start_time
        )
        
        # Extract data
        data = request.data.copy()
        current_data = {
            'phone_number': user.phone_number,
            'email': user.email,
            'full_name': user.full_name,
            'availability_status': user.availability_status
        }
        
        # Validation checks
        if 'work_mail_address' in data:
            response = Response({"error": "Work mail address cannot be changed."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description=f'Failed: Attempted to change work email from {user.work_mail_address} to {data.get("work_mail_address")}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        if 'role' in data:
            response = Response({"error": "Role cannot be changed."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description=f'Failed: Attempted to change role from {user.role} to {data.get("role")}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        if 'department' in data or 'departments' in data:
            response = Response({
                "error": "You cannot change your department(s). Please contact admin or HR."
            }, status=403)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description='Failed: Attempted to change department(s)',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Validate phone number format
        if 'phone_number' in data:
            phone_error = is_valid_phone(data['phone_number'])
            if phone_error:
                response = Response({"error": phone_error}, status=400)
                ActivityLogger.log_profile(
                    user=user,
                    activity='profile_update',
                    description=f'Failed: Invalid phone number format - {phone_error}',
                    request=request,
                    response=response,
                    is_success=False,
                    start_time=start_time
                )
                return response
        
        # Validate email format
        if 'email' in data:
            email_error = is_valid_email(data['email'])
            if email_error:
                response = Response({"error": email_error}, status=400)
                ActivityLogger.log_profile(
                    user=user,
                    activity='profile_update',
                    description=f'Failed: Invalid email format - {email_error}',
                    request=request,
                    response=response,
                    is_success=False,
                    start_time=start_time
                )
                return response
        
        # Check uniqueness
        if 'phone_number' in data:
            if CustomUser.objects.filter(phone_number=data['phone_number']).exclude(id=user.id).exists():
                response = Response({"error": "Phone number already exists."}, status=400)
                ActivityLogger.log_profile(
                    user=user,
                    activity='profile_update',
                    description=f'Failed: Phone number {data["phone_number"]} already exists',
                    request=request,
                    response=response,
                    is_success=False,
                    start_time=start_time
                )
                return response
        
        if 'email' in data:
            if CustomUser.objects.filter(email=data['email']).exclude(id=user.id).exists():
                response = Response({"error": "Email already exists."}, status=400)
                ActivityLogger.log_profile(
                    user=user,
                    activity='profile_update',
                    description=f'Failed: Email {data["email"]} already exists',
                    request=request,
                    response=response,
                    is_success=False,
                    start_time=start_time
                )
                return response
        
        # Update fields
        changes = []
        allowed_fields = ['phone_number', 'email', 'full_name', 'availability_status']
        
        for field in allowed_fields:
            if field in data and data[field] != getattr(user, field):
                old_value = getattr(user, field)
                new_value = data[field]
                setattr(user, field, new_value)
                changes.append(f"{field}: '{old_value}' → '{new_value}'")
        
        if not changes:
            response = Response({"message": "No changes detected."}, status=200)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description='No changes made to profile',
                request=request,
                response=response,
                is_success=True,
                start_time=start_time
            )
            return response
        
        try:
            user.save()
            serializer = CustomUserSerializer(user)
            
            # Log successful update
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description=f'Profile updated successfully. Changes: {", ".join(changes)}',
                request=request,
                response=Response({"message": "Profile updated successfully"}, status=200),
                is_success=True,
                start_time=start_time
            )
            
            return Response({
                "message": "Profile updated successfully.",
                "changes": changes,
                "user": serializer.data
            }, status=200)
            
        except IntegrityError as e:
            response = Response({"error": "Update failed due to data conflict."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description=f'Failed: Integrity error - {str(e)}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
            
        except Exception as e:
            response = Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
            ActivityLogger.log_profile(
                user=user,
                activity='profile_update',
                description=f'Failed: Unexpected error - {str(e)}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
            
    except Exception as e:
        response = Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
        ActivityLogger.log_profile(
            user=user,
            activity='profile_update',
            description=f'Error: {str(e)}',
            request=request,
            response=response,
            is_success=False,
            start_time=start_time
        )
        return response

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
                subject="Password Reset Successful - Hammer Tech System",
                message=f"""
Hello {user.full_name},

Your password has been successfully reset for the Hammer Tech System.

If you did not perform this action, please contact our support team immediately.

Best regards,
Hammer Tech Team
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
        print(f"Retrieved users data {serializer.data}\n")
        return Response({"users": serializer.data}, status=200)
    
    elif request.method == 'POST':
        try:
            print(f"\n{'='*50}")
            print(f"REGISTRATION REQUEST RECEIVED")
            print(f"{'='*50}")
            
            # Extract data
            phone_number = request.data.get('phone_number', '').strip()
            email = request.data.get('email', '').strip()
            full_name = request.data.get('full_name', '').strip()
            department = request.data.get('department', 0)
            departments = request.data.get('departments', [])  # For security analysts
            role = request.data.get('role', 'employee').strip().lower()
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
            
            # Check role-based permissions - Use actual role values from model
            valid_roles = ['admin', 'employee', 'compliance_officer', 'security_analyst', 'hr_manager']
            if role not in valid_roles:
                error_msg = f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}"
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            # Department validation based on role
            if role == 'employee':
                if not department:
                    error_msg = "Department is required for employee users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate department exists and is active
                try:
                    dept_obj = Department.objects.get(id=department, status='active')
                except Department.DoesNotExist:
                    error_msg = "Invalid or inactive department selected."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role == 'security_analyst':
                if not departments or len(departments) == 0:
                    error_msg = "At least one department is required for Security Analyst users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
                
                # Validate all departments exist and are active
                valid_depts = Department.objects.filter(id__in=departments, status='active')
                if valid_depts.count() != len(departments):
                    error_msg = "One or more selected departments are invalid or inactive."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=400)
            
            elif role in ['admin', 'hr_manager']:
                # Admin and HR don't require departments
                department = None
                departments = []
            
            # Role-based permission checks
            if role != 'employee' and not requesting_user:
                error_msg = "Only admin or HR can create users with roles other than 'employee'."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=400)
            
            if requesting_user:
                if role == 'admin' and not requesting_user.is_admin:
                    error_msg = "Only admin can create admin users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'hr_manager' and not requesting_user.is_admin:
                    error_msg = "Only admin can create HR Manager users."
                    print(f"ERROR: {error_msg}")
                    return Response({"error": error_msg}, status=403)
                if role == 'security_analyst' and not (requesting_user.is_admin or requesting_user.is_hr):
                    error_msg = "Only admin or HR can create Security Analyst users."
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
            
            # Generate system password
            password = generate_secure_password()
            if not password:
                error_msg = "Failed to generate secure password. Please try again."
                print(f"ERROR: {error_msg}")
                return Response({"error": error_msg}, status=500)
            
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
                if role == 'employee':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=department,  # Pass department ID for employee
                        departments=None,
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                elif role == 'security_analyst':
                    user = CustomUser.objects.create_user(
                        phone_number=phone_number,
                        email=email,
                        full_name=full_name,
                        department=None,
                        departments=departments,  # Pass departments list for security analyst
                        role=role,
                        work_mail_address=work_mail_address,
                        password=password,
                        created_by=requesting_user,
                        status='approved' if requesting_user else 'pending',
                        availability_status='active' if requesting_user else 'inactive'
                    )
                else:  # admin or hr_manager
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
                
                if role == 'security_analyst':
                    print(f"Security Analyst departments: {[d.name for d in user.departments.all()]}")
                    
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
                if role == 'employee':
                    dept_info = f"Department: {user.department.name}"
                elif role == 'security_analyst':
                    dept_names = [d.name for d in user.departments.all()]
                    dept_info = f"Departments: {', '.join(dept_names)}"
                else:
                    dept_info = "Department: N/A (Admin/HR)"
                
                subject = "Welcome to Hammer Tech System"
                message = f"""
            Hello {full_name},

            Your account has been successfully created in the Hammer Tech System.
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
            Hammer Tech Team
                            """
                            
                send_mail(
                    subject=subject,
                    message=message,
                    from_email="no-reply@hammer_grp_tech.com",
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
    start_time = time.time()
    user = request.user
    
    try:
        current_password = request.data.get('current_password', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()
        
        # Validate required fields
        if not current_password:
            response = Response({"error": "Current password is required."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: Current password is required',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        if not new_password:
            response = Response({"error": "New password is required."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: New password is required',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        if not confirm_password:
            response = Response({"error": "Password confirmation is required."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: Password confirmation is required',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Verify current password
        if not user.check_password(current_password):
            response = Response({"error": "Current password is incorrect."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: Current password is incorrect',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check if new password is same as current
        if user.check_password(new_password):
            response = Response({"error": "New password cannot be the same as current password."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: New password same as current',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Check password match
        if new_password != confirm_password:
            response = Response({"error": "New passwords do not match."}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description='Failed: Passwords do not match',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Validate password strength
        password_error = is_valid_password(new_password)
        if password_error:
            response = Response({"error": password_error}, status=400)
            ActivityLogger.log_profile(
                user=user,
                activity='password_change',
                description=f'Failed: Password validation error - {password_error}',
                request=request,
                response=response,
                is_success=False,
                start_time=start_time
            )
            return response
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        # Send notification email
        try:
            send_mail(
                subject="Password Changed Successfully - Hammer Tech",
                message=f"""
Hello {user.full_name},

Your password has been successfully changed for the Hammer Tech System.
If you did not make this change, please contact our support team immediately.

Best regards,
Hammer Tech Team
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Warning: Password changed but email failed: {str(e)}")
        
        response = Response({
            "message": "Password changed successfully.",
            "success": True
        }, status=200)
        
        # Log successful password change
        ActivityLogger.log_profile(
            user=user,
            activity='password_change',
            description='Password changed successfully',
            request=request,
            response=response,
            is_success=True,
            start_time=start_time
        )
        
        return response
        
    except Exception as e:
        response = Response({
            "error": "An unexpected error occurred. Please try again.",
            "detail": str(e)
        }, status=500)
        
        ActivityLogger.log_profile(
            user=user,
            activity='password_change',
            description=f'Error: {str(e)}',
            request=request,
            response=response,
            is_success=False,
            start_time=start_time
        )
        return response



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







import json
from functools import wraps
from collections import Counter
from django.db import models
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import UserLog
from .serializers import UserLogSerializer
from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend


def display_response_data(func):
    """Decorator to display returned data on terminal"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        
        if isinstance(response, Response):
            print("\n" + "="*80)
            print(f"📊 RESPONSE DATA from {func.__name__}")
            print("="*80)
            
            # Get response data
            response_data = response.data
            
            # Pretty print the data
            if isinstance(response_data, dict):
                print("📁 Response Structure (dict):")
                for key, value in response_data.items():
                    if key == 'logs' and isinstance(value, list):
                        print(f"  📝 {key}: List with {len(value)} items")
                        if value and len(value) > 0:
                            print(f"     First item keys: {list(value[0].keys())}")
                    elif key == 'data' and isinstance(value, dict):
                        print(f"  📊 {key}: Dictionary with keys: {list(value.keys())}")
                        for subkey, subvalue in value.items():
                            if isinstance(subvalue, list):
                                print(f"    📋 {subkey}: List with {len(subvalue)} items")
                            else:
                                print(f"    📋 {subkey}: {type(subvalue).__name__}")
                    elif isinstance(value, list):
                        print(f"  📋 {key}: List with {len(value)} items")
                        if value and len(value) > 0 and isinstance(value[0], dict):
                            print(f"     Sample item keys: {list(value[0].keys())}")
                    else:
                        print(f"  📋 {key}: {value if len(str(value)) < 100 else str(value)[:100] + '...'}")
            elif isinstance(response_data, list):
                print(f"📋 Response Structure (list): {len(response_data)} items")
                if response_data and len(response_data) > 0:
                    print(f"  First item type: {type(response_data[0])}")
                    if isinstance(response_data[0], dict):
                        print(f"  First item keys: {list(response_data[0].keys())}")
            
            # Display status code
            print(f"\n📡 Status Code: {response.status_code}")
            print(f"🔧 Content Type: {response.get('content-type', 'N/A')}")
            
            # If it's a list of logs, display summary
            if isinstance(response_data, dict) and 'logs' in response_data:
                logs = response_data['logs']
                if isinstance(logs, list):
                    print(f"\n📈 LOGS SUMMARY:")
                    print(f"  Total logs: {len(logs)}")
                    
                    # Count by activity type
                    if logs and len(logs) > 0:
                        activity_counter = Counter(log.get('activity', 'Unknown') for log in logs)
                        print(f"  Activities found: {len(activity_counter)}")
                        print(f"  Top 3 activities:")
                        for activity, count in activity_counter.most_common(3):
                            print(f"    - {activity}: {count} times")
                        
                        # Success rate
                        success_count = sum(1 for log in logs if log.get('is_success', False))
                        if len(logs) > 0:
                            success_rate = (success_count / len(logs)) * 100
                            print(f"  Success rate: {success_rate:.1f}% ({success_count}/{len(logs)})")
            
            # If it's user data, display summary
            elif isinstance(response_data, dict) and 'data' in response_data:
                data = response_data['data']
                if isinstance(data, list):
                    print(f"\n👥 USERS SUMMARY:")
                    print(f"  Total users: {len(data)}")
                    
                    if data and len(data) > 0:
                        # Count by role
                        role_counter = Counter(user.get('role', 'Unknown') for user in data)
                        print(f"  Role distribution:")
                        for role, count in role_counter.most_common():
                            print(f"    - {role}: {count}")
                        
                        # Count by status
                        status_counter = Counter(user.get('status', 'Unknown') for user in data)
                        print(f"  Status distribution:")
                        for status, count in status_counter.most_common():
                            print(f"    - {status}: {count}")
                        
                        # Risk scores
                        risk_scores = [user.get('risk_score', 0) for user in data]
                        if risk_scores:
                            avg_risk = sum(risk_scores) / len(risk_scores)
                            high_risk = sum(1 for score in risk_scores if score > 70)
                            print(f"  Risk scores - Avg: {avg_risk:.1f}, High risk (>70): {high_risk}")
            
            # If it's statistics data
            elif isinstance(response_data, dict) and 'data' in response_data:
                stats = response_data['data']
                if isinstance(stats, dict):
                    print(f"\n📊 STATISTICS SUMMARY:")
                    print(f"  Total users: {stats.get('total_users', 'N/A')}")
                    print(f"  Active users: {stats.get('active_users', 'N/A')}")
                    print(f"  Pending users: {stats.get('pending_users', 'N/A')}")
                    print(f"  Suspended users: {stats.get('suspended_users', 'N/A')}")
                    print(f"  Recent activity: {stats.get('recent_activity_count', 'N/A')} logs")
                    print(f"  MFA enabled: {stats.get('mfa_enabled_percentage', 'N/A')}%")
            
            print("\n" + "="*80 + "\n")
        
        return response
    return wrapper

# Apply decorator to UserLogListAPIView
class UserLogListAPIView(generics.ListAPIView):
    """View user activity logs with filtering"""
    serializer_class = UserLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['log_type', 'activity', 'user_email', 'user_role', 'is_success']
    search_fields = ['user_email', 'description', 'endpoint']
    ordering_fields = ['timestamp', 'created_at']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        user = self.request.user
        
        # Admins can see all logs
        if user.is_admin or user.role == 'security_analyst':
            return UserLog.objects.all()
        
        # HR can see logs except admin activities
        elif user.is_hr:
            return UserLog.objects.exclude(user_role='admin')
        
        # Users can only see their own logs
        else:
            return UserLog.objects.filter(user_email=user.email)
    
    @display_response_data
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Add activity log for viewing logs
        ActivityLogger.create_log(
            user=request.user,
            log_type='system',
            activity='log_view',
            description=f'Viewed activity logs with filters: {dict(request.query_params)}',
            request=request,
            response=None,
            is_success=True
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# Apply decorator to UserLogDetailAPIView
class UserLogDetailAPIView(generics.RetrieveAPIView):
    """View details of a specific log entry"""
    serializer_class = UserLogSerializer
    permission_classes = [IsAuthenticated]
    queryset = UserLog.objects.all()
    
    @display_response_data
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Check permissions
        if not (request.user.is_admin or 
                request.user.is_hr or 
                request.user.role == 'security_analyst' or
                instance.user_email == request.user.email):
            return Response(
                {"error": "You don't have permission to view this log."},
                status=403
            )
        
        # Log the view
        ActivityLogger.create_log(
            user=request.user,
            log_type='system',
            activity='log_detail_view',
            description=f'Viewed log entry {instance.id}',
            request=request,
            response=None,
            is_success=True
        )
        
        serializer = self.get_serializer(instance)
        print(f" User logs: {serializer.data} ")
        return Response(serializer.data)

# Apply decorator to API views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@display_response_data
def get_my_activity_logs(request):
    """Get current user's activity logs"""
    try:
        user = request.user
        logs = UserLog.objects.filter(user_email=user.email).order_by('-timestamp')[:50]
        serializer = UserLogSerializer(logs, many=True)
        
        # Log this activity
        ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity='my_logs_view',
            description='Viewed own activity logs',
            request=request,
            response=Response({"logs": serializer.data}, status=200),
            is_success=True
        )
        
        return Response({
            "count": logs.count(),
            "logs": serializer.data
        }, status=200)
        
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@display_response_data
def get_access_control_stats(request):
    """Get statistics for access control dashboard"""
    try:
        user = request.user
        print(f"User with role: {user.role} is accessing this endpoint\n")
        
        # Fix: Check if user has permission (admin, HR, or security_analyst)
        if not (user.is_admin or user.is_hr or user.role == 'security_analyst'):
            print(f"❌ Access denied for user {user.email} - Role: {user.role}")
            return Response({
                "error": "You are not authorized to view these statistics."
            }, status=403)
        
        print(f"✅ Access granted for user {user.email} - Role: {user.role}")
        
        # Get total users
        total_users = CustomUser.objects.count()
        active_users = CustomUser.objects.filter(is_active=True, status='approved').count()
        suspended_users = CustomUser.objects.filter(is_active=False).count()
        pending_users = CustomUser.objects.filter(status='pending').count()
        
        # Get role distribution
        role_distribution = CustomUser.objects.values('role').annotate(
            count=models.Count('id')
        ).order_by('-count')
        
        # Get recent activity logs count
        from datetime import timedelta
        from django.utils.timezone import now
        recent_logs_count = UserLog.objects.filter(
            timestamp__gte=now() - timedelta(hours=24)
        ).count()
        
        # Get MFA/OTP usage (you might need to track this separately)
        # For now, we'll assume 85% based on your mock data
        mfa_enabled_count = int(total_users * 0.85)  # Update this based on actual data
        
        return Response({
            "success": True,
            "data": {
                "total_users": total_users,
                "active_users": active_users,
                "suspended_users": suspended_users,
                "pending_users": pending_users,
                "recent_activity_count": recent_logs_count,
                "mfa_enabled_count": mfa_enabled_count,
                "mfa_enabled_percentage": 85,  # Update this based on actual data
                "role_distribution": list(role_distribution),
                "last_updated": now().isoformat()
            }
        }, status=200)
        
    except Exception as e:
        print(f"❌ Error in get_access_control_stats: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@display_response_data
def get_users_for_access_control(request):
    """Get users with additional access control information"""
    print(f"\n User {request.user.email} with role: {request.user.role} is fetching access control endpoint\n")
    try:
        user = request.user
        
        if not user.is_admin and not user.is_hr and user.role != 'security_analyst':
            print(f"Unauthorized access attempt by user: {user.work_mail_address} to access control data")
            return Response({"error": "You are not authorized to view user access data."}, status=403)
        
        # Get all users with additional info
        users = CustomUser.objects.all().select_related('department').prefetch_related('departments')
        
        # Apply search filter if provided
        search_query = request.query_params.get('search', '')
        if search_query:
            users = users.filter(
                models.Q(full_name__icontains=search_query) |
                models.Q(email__icontains=search_query) |
                models.Q(work_mail_address__icontains=search_query) |
                models.Q(role__icontains=search_query)
            )
        
        # Apply role filter if provided
        role_filter = request.query_params.get('role', '')
        if role_filter:
            users = users.filter(role=role_filter)
        
        # Apply status filter if provided
        status_filter = request.query_params.get('status', '')
        if status_filter:
            if status_filter == 'active':
                users = users.filter(is_active=True, status='approved')
            elif status_filter == 'suspended':
                users = users.filter(is_active=False)
            elif status_filter == 'pending':
                users = users.filter(status='pending')
        
        # Get user log activity for risk assessment
        from django.utils.timezone import now
        from datetime import timedelta
        
        users_data = []
        for user_obj in users:
            # Get last login time
            last_login = None
            last_login_log = UserLog.objects.filter(
                user_email=user_obj.email,
                activity='login'
            ).order_by('-timestamp').first()
            
            if last_login_log:
                last_login = last_login_log.timestamp
            
            # Calculate risk score based on various factors
            risk_score = calculate_user_risk_score(user_obj, last_login)
            
            # Get department info
            department_name = user_obj.department.name if user_obj.department else "N/A"
            
            users_data.append({
                "id": user_obj.id,
                "name": user_obj.full_name,
                "email": user_obj.email,
                "work_mail_address": user_obj.work_mail_address,
                "role": user_obj.get_role_display(),
                "role_code": user_obj.role,
                "department": department_name,
                "status": "active" if user_obj.is_active and user_obj.status == 'approved' else 
                         "suspended" if not user_obj.is_active else 
                         "pending",
                "last_login": last_login,
                "last_login_display": format_last_login(last_login) if last_login else "Never",
                "risk_score": risk_score,
                "created_at": user_obj.created_at,
                "avatar": get_user_avatar_initials(user_obj.full_name),
                "departments": [dept.name for dept in user_obj.departments.all()] if user_obj.role == 'security_analyst' else []
            })
        
        # Sort users by risk score (descending)
        users_data.sort(key=lambda x: x['risk_score'], reverse=True)
        
        response_data = {
            "success": True,
            "count": len(users_data),
            "data": users_data
        }
        
        # Display response data on terminal
        print("\n" + "=" * 120)
        print(f"USER ACCESS CONTROL DATA - {len(users_data)} users retrieved")
        print("=" * 120)
        
        for user_info in users_data:
            print(f"\n{'─' * 120}")
            print(f"ID: {user_info['id']:4d} | Name: {user_info['name']:30s} | Avatar: {user_info['avatar']}")
            print(f"Email: {user_info['email']:40s} | Work Email: {user_info['work_mail_address']}")
            print(f"Role: {user_info['role']:20s} ({user_info['role_code']:20s}) | Department: {user_info['department']}")
            print(f"Status: {user_info['status']:10s} | Risk Score: {user_info['risk_score']:5.2f} | Last Login: {user_info['last_login_display']}")
            
            if user_info['departments']:
                print(f"Department Access: {', '.join(user_info['departments'])}")
            
            print(f"Created: {user_info['created_at']}")
        
        print("\n" + "=" * 120)
        print(f"Total Users: {len(users_data)}")
        print("=" * 120 + "\n")
        
        return Response(response_data, status=200)
        
    except Exception as e:
        error_response = {"error": str(e)}
        print(f"\n{'!' * 120}")
        print(f"ERROR: {str(e)}")
        print(f"{'!' * 120}\n")
        return Response(error_response, status=500)



def calculate_user_risk_score(user, last_login):
    """Calculate risk score based on various factors"""
    risk_score = 0
    
    # Base score based on role
    role_weights = {
        'admin': 10,
        'hr_manager': 15,
        'security_analyst': 20,
        'compliance_officer': 15,
        'employee': 5
    }
    risk_score += role_weights.get(user.role, 10)
    
    # Add score based on last login
    if last_login:
        from django.utils.timezone import now
        days_since_login = (now() - last_login).days
        if days_since_login > 30:
            risk_score += 30
        elif days_since_login > 7:
            risk_score += 15
        elif days_since_login > 1:
            risk_score += 5
    else:
        risk_score += 40  # Never logged in
    
    # Add score based on status
    if not user.is_active:
        risk_score += 50
    elif user.status == 'pending':
        risk_score += 25
    
    # Cap the score at 100
    return min(risk_score, 100)

def format_last_login(last_login):
    """Format last login time for display"""
    from django.utils.timezone import now
    from datetime import timedelta
    
    if not last_login:
        return "Never"
    
    time_diff = now() - last_login
    
    if time_diff < timedelta(minutes=1):
        return "Just now"
    elif time_diff < timedelta(hours=1):
        minutes = int(time_diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif time_diff < timedelta(days=1):
        hours = int(time_diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif time_diff < timedelta(days=7):
        days = time_diff.days
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return last_login.strftime("%b %d, %Y")

def get_user_avatar_initials(full_name):
    """Get initials for user avatar"""
    names = full_name.split()
    if len(names) >= 2:
        return f"{names[0][0]}{names[-1][0]}".upper()
    elif len(full_name) >= 2:
        return full_name[:2].upper()
    else:
        return "U"

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@display_response_data
def get_user_activity_logs(request, user_id):
    """Get activity logs for a specific user"""
    try:
        requesting_user = request.user
        
        print("\n" + "="*60)
        print(f"📋 GET USER ACTIVITY LOGS - User ID: {user_id}")
        print(f"Requesting User: {requesting_user.email}")
        print(f"Query Params: {dict(request.query_params)}")
        print("="*60)
        
        # Check permissions
        if not requesting_user.is_admin and not requesting_user.is_hr and requesting_user.role != 'security_analyst':
            try:
                if requesting_user.id != int(user_id):
                    print("❌ Permission denied: User can only view their own logs")
                    return Response({
                        "success": False,
                        "error": "You are not authorized to view these logs."
                    }, status=403)
            except ValueError:
                print("❌ Invalid user ID format")
                return Response({
                    "success": False,
                    "error": "Invalid user ID format."
                }, status=400)
        
        try:
            target_user = CustomUser.objects.get(id=user_id)
            print(f"✅ Target User Found: {target_user.full_name} ({target_user.email})")
        except CustomUser.DoesNotExist:
            print(f"❌ User not found: ID {user_id}")
            return Response({
                "success": False,
                "error": f"User with ID {user_id} does not exist."
            }, status=404)
        
        # Get logs for the user
        logs = UserLog.objects.filter(user_email=target_user.email).order_by('-timestamp')
        print(f"📊 Found {logs.count()} total logs for user {target_user.email}")
        
        # Apply filters
        activity_filter = request.query_params.get('activity', '')
        if activity_filter:
            logs = logs.filter(activity=activity_filter)
            print(f"🔍 Applied activity filter: {activity_filter}")
        
        log_type_filter = request.query_params.get('log_type', '')
        if log_type_filter:
            logs = logs.filter(log_type=log_type_filter)
            print(f"🔍 Applied log_type filter: {log_type_filter}")
        
        date_from = request.query_params.get('date_from', '')
        date_to = request.query_params.get('date_to', '')
        if date_from:
            try:
                logs = logs.filter(timestamp__date__gte=date_from)
                print(f"📅 Applied date_from filter: {date_from}")
            except ValueError:
                print(f"⚠️ Invalid date_from format: {date_from}")
        if date_to:
            try:
                logs = logs.filter(timestamp__date__lte=date_to)
                print(f"📅 Applied date_to filter: {date_to}")
            except ValueError:
                print(f"⚠️ Invalid date_to format: {date_to}")
        
        # Get filtered logs
        filtered_logs = list(logs)
        print(f"📊 Filtered logs count: {len(filtered_logs)}")
        
        # Get summary statistics
        total_logs = len(filtered_logs)
        successful_logs = sum(1 for log in filtered_logs if log.is_success)
        failed_logs = total_logs - successful_logs
        
        # Get most frequent activities
        activity_counter = Counter(log.activity for log in filtered_logs if log.activity)
        top_activities = [{"activity": activity, "count": count} 
                         for activity, count in activity_counter.most_common(5)]
        
        # Serialize logs
        serialized_logs = []
        for log in filtered_logs:
            serialized_log = {
                "id": log.id,
                "activity": log.activity,
                "log_type": log.log_type,
                "description": log.description,
                "user_email": log.user_email,
                "user_role": log.user_role,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "duration": log.duration.total_seconds() if log.duration else None,
                "ip_address": log.ip_address,
                "endpoint": log.endpoint,
                "http_method": log.http_method,
                "is_success": log.is_success,
                "user_agent": log.user_agent,
                "status_log": log.status_code,
            }
            
            # Add optional fields if they exist
            if hasattr(log, 'request_data') and log.request_data:
                serialized_log["request_data"] = log.request_data
            if hasattr(log, 'response_data') and log.response_data:
                serialized_log["response_data"] = log.response_data
            if hasattr(log, 'status_code') and log.status_code:
                serialized_log["status_code"] = log.status_code
            
            serialized_logs.append(serialized_log)
        
        # Create response data
        response_data = {
            "success": True,
            "user": {
                "id": target_user.id,
                "name": target_user.full_name,
                "email": target_user.email,
                "role": target_user.role,
                "status": "active" if target_user.is_active and target_user.status == 'approved' else "inactive"
            },
            "summary": {
                "total_logs": total_logs,
                "successful_logs": successful_logs,
                "failed_logs": failed_logs,
                "success_rate": round((successful_logs / total_logs * 100) if total_logs > 0 else 0, 1),
                "top_activities": top_activities
            },
            "logs": serialized_logs,
            "pagination": {
                "page": 1,
                "page_size": total_logs,
                "total_items": total_logs,
                "total_pages": 1,
                "has_previous": False,
                "has_next": False
            }
        }
        
        # Display debug info in terminal
        print(f"\n📈 SUMMARY STATISTICS:")
        print(f"   Total Logs: {total_logs}")
        print(f"   Successful: {successful_logs}")
        print(f"   Failed: {failed_logs}")
        print(f"   Success Rate: {response_data['summary']['success_rate']}%")
        
        if top_activities:
            print(f"\n🏆 TOP ACTIVITIES:")
            for i, activity in enumerate(top_activities, 1):
                print(f"   {i}. {activity['activity']}: {activity['count']} times")
        
        # ==================== NEW: DETAILED LOG DISPLAY ====================
        print(f"\n📋 DETAILED LOGS ({len(filtered_logs)} total):")
        print("-" * 120)
        
        for i, log in enumerate(filtered_logs, 1):
            status_icon = "✅" if log.is_success else "❌"
            timestamp = log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "N/A"
            duration_str = f"{log.duration.total_seconds():.2f}s" if log.duration else "N/A"
            
            print(f"\n{status_icon} LOG #{i} - ID: {log.id}")
            print(f"   📅 Timestamp: {timestamp}")
            print(f"   👤 User: {log.user_email} ({log.user_role})")
            print(f"   📌 Activity: {log.activity} ({log.log_type})")
            print(f"   📝 Description: {log.description}")
            print(f"   ⏱️  Duration: {duration_str}")
            print(f"   🌐 IP Address: {log.ip_address or 'N/A'}")
            print(f"   🔗 Endpoint: {log.endpoint or 'N/A'}")
            print(f"   📡 HTTP Method: {log.http_method or 'N/A'}")
            print(f"   📊 Status Code: {log.status_code or 'N/A'}")
            print(f"   ✔️  Success: {log.is_success}")
            print(f"   🤖 Auto-generated: {log.is_auto_generated}")
            
            # Display target user if exists
            if log.target_user:
                print(f"   🎯 Target User: {log.target_user.full_name} ({log.target_user.email})")
            
            # Display target department if exists
            if log.target_department:
                print(f"   🏢 Target Dept: {log.target_department.name}")
            
            # Display request data if exists (truncated)
            if hasattr(log, 'request_data') and log.request_data:
                import json
                request_str = json.dumps(log.request_data, indent=2)
                if len(request_str) > 200:
                    request_str = request_str[:200] + "..."
                print(f"   📤 Request Data: {request_str}")
            
            # Display response data if exists (truncated)
            if hasattr(log, 'response_data') and log.response_data:
                import json
                response_str = json.dumps(log.response_data, indent=2)
                if len(response_str) > 200:
                    response_str = response_str[:200] + "..."
                print(f"   📥 Response Data: {response_str}")
            
            # Display user agent if exists (truncated)
            if log.user_agent:
                user_agent_str = log.user_agent[:100] + "..." if len(log.user_agent) > 100 else log.user_agent
                print(f"   🖥️  User Agent: {user_agent_str}")
            
            print("-" * 120)
        
        # ==================== END: DETAILED LOG DISPLAY ====================
        
        print("="*60)
        print(f"✅ Returning {len(serialized_logs)} logs to frontend")
        print("="*60)
        
        # Log this activity
        ActivityLogger.create_log(
            user=requesting_user,
            log_type='system',
            activity='view_user_logs',
            description=f'Viewed activity logs for user {target_user.email} ({total_logs} logs)',
            request=request,
            response=None,
            is_success=True,
            target_user=target_user
        )
        
        return Response(response_data, status=200)
        
    except Exception as e:
        print(f"\n❌ ERROR in get_user_activity_logs: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return Response({
            "success": False,
            "error": str(e)
        }, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@display_response_data
def log_activity(request):
    """Manual activity logging endpoint"""
    try:
        activity = request.data.get('activity', '')
        description = request.data.get('description', '')
        user_id = request.data.get('user_id')
        target_user_email = request.data.get('user_email')  # Renamed to avoid confusion
        is_success = request.data.get('is_success', True)
        
        # Determine which user to log for
        target_user = None
        if user_id:
            try:
                target_user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                pass
        elif target_user_email:
            try:
                target_user = CustomUser.objects.get(email=target_user_email)
            except CustomUser.DoesNotExist:
                pass
        
        # Create the log
        log = ActivityLogger.create_log(
            user=request.user,
            log_type='user_management',
            activity=activity,
            description=description,
            request=request,
            response=None,
            is_success=is_success,
            target_user=target_user  # Pass target_user instead of user_email
        )
        
        return Response({
            "success": True,
            "message": "Activity logged successfully",
            "log_id": log.id if log else None
        }, status=200)
        
    except Exception as e:
        print(f"Error logging activity: {str(e)}")
        return Response({
            "success": False,
            "error": str(e)
        }, status=500)





@api_view(['POST'])
@permission_classes([AllowAny])
def check_account_lock_status(request):
    """Check if an account is locked before login attempt"""
    try:
        email = request.data.get('email', '').strip()
        
        if not email:
            return Response({
                'error': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Return generic response for security
            return Response({
                'is_locked': False,
                'message': 'Account status checked successfully'
            }, status=status.HTTP_200_OK)
        
        if user.is_account_locked():
            remaining = user.get_lock_remaining_seconds()
            minutes = remaining // 60
            seconds = remaining % 60
            
            return Response({
                'is_locked': True,
                'remaining_seconds': remaining,
                'remaining_minutes': minutes,
                'remaining_seconds_display': seconds,
                'message': f'Account is locked. Please try again in {minutes} minute(s) and {seconds} second(s).',
                'failed_attempts': user.failed_login_attempts
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'is_locked': False,
                'message': 'Account is not locked',
                'failed_attempts': user.failed_login_attempts
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for monitoring and debugging.
    Returns system status and basic information.
    """
    try:
        # Check database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return Response({
        "status": "healthy",
        "timestamp": now().isoformat(),
        "database": db_status,
        "version": "2.1.0",
        "environment": "production"  # Change as needed
    }, status=200)