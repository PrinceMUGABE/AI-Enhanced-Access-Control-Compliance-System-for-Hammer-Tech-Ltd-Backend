# Create this file as utils/debug_utils.py

import logging
from functools import wraps
import traceback
import json

logger = logging.getLogger(__name__)

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def log_request(view_func):
    """Decorator to log API requests and responses"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Log request
        print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}{Colors.BOLD}API REQUEST: {view_func.__name__}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Method:{Colors.ENDC} {request.method}")
        print(f"{Colors.OKCYAN}Path:{Colors.ENDC} {request.path}")
        print(f"{Colors.OKCYAN}User:{Colors.ENDC} {request.user if hasattr(request, 'user') else 'Anonymous'}")
        
        # Log request data
        if request.method in ['POST', 'PUT', 'PATCH']:
            print(f"{Colors.OKCYAN}Data:{Colors.ENDC}")
            try:
                # Mask sensitive fields
                data = dict(request.data)
                sensitive_fields = ['password', 'current_password', 'new_password', 'confirm_password', 'token']
                for field in sensitive_fields:
                    if field in data:
                        data[field] = '***MASKED***'
                print(json.dumps(data, indent=2))
            except:
                print(request.data)
        
        # Call the view
        try:
            response = view_func(request, *args, **kwargs)
            
            # Log response
            status_color = Colors.OKGREEN if 200 <= response.status_code < 300 else Colors.FAIL
            print(f"\n{status_color}Response Status:{Colors.ENDC} {response.status_code}")
            
            if hasattr(response, 'data'):
                print(f"{status_color}Response Data:{Colors.ENDC}")
                print(json.dumps(response.data, indent=2, default=str))
            
            print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
            
            return response
        except Exception as e:
            print(f"\n{Colors.FAIL}{Colors.BOLD}ERROR in {view_func.__name__}:{Colors.ENDC}")
            print(f"{Colors.FAIL}{str(e)}{Colors.ENDC}")
            print(f"{Colors.FAIL}Traceback:{Colors.ENDC}")
            print(traceback.format_exc())
            print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
            raise
    
    return wrapper


def log_error(message, exception=None, extra_data=None):
    """Helper function to log errors with context"""
    print(f"\n{Colors.FAIL}{'='*80}{Colors.ENDC}")
    print(f"{Colors.FAIL}{Colors.BOLD}ERROR: {message}{Colors.ENDC}")
    print(f"{Colors.FAIL}{'='*80}{Colors.ENDC}")
    
    if exception:
        print(f"{Colors.FAIL}Exception: {str(exception)}{Colors.ENDC}")
        print(f"{Colors.FAIL}Traceback:{Colors.ENDC}")
        print(traceback.format_exc())
    
    if extra_data:
        print(f"{Colors.WARNING}Extra Data:{Colors.ENDC}")
        print(json.dumps(extra_data, indent=2, default=str))
    
    print(f"{Colors.FAIL}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.error(message, exc_info=exception is not None, extra={'extra_data': extra_data})


def log_success(message, data=None):
    """Helper function to log success messages"""
    print(f"\n{Colors.OKGREEN}{'='*80}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}SUCCESS: {message}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{'='*80}{Colors.ENDC}")
    
    if data:
        print(f"{Colors.OKCYAN}Data:{Colors.ENDC}")
        print(json.dumps(data, indent=2, default=str))
    
    print(f"{Colors.OKGREEN}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.info(message, extra={'data': data})


def log_warning(message, data=None):
    """Helper function to log warnings"""
    print(f"\n{Colors.WARNING}{'='*80}{Colors.ENDC}")
    print(f"{Colors.WARNING}{Colors.BOLD}WARNING: {message}{Colors.ENDC}")
    print(f"{Colors.WARNING}{'='*80}{Colors.ENDC}")
    
    if data:
        print(f"{Colors.WARNING}Data:{Colors.ENDC}")
        print(json.dumps(data, indent=2, default=str))
    
    print(f"{Colors.WARNING}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.warning(message, extra={'data': data})