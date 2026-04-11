# learningProgressApp/views.py
from django.forms import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db import models

from .models import (
    LearningProgress, ModuleCompletion, MaterialProgress,
    LearningSession, LearningAchievement
)
from .serializers import (
    LearningProgressSerializer, LearningProgressSummarySerializer,
    ModuleCompletionSerializer, ModuleCompletionUpdateSerializer,
    MaterialProgressUpdateSerializer, LearningSessionSerializer,
    LearningAchievementSerializer
)
from trainingCandidateApp.models import Candidate
from trainingApp.models import Training, Module, TrainingMaterial
from userApp.models import CustomUser

# learningProgressApp/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import LearningProgress, ModuleCompletion, MaterialProgress
from trainingApp.models import Training, Module
from trainingCandidateApp.models import Candidate
from django.shortcuts import get_object_or_404
import math

# Replace the existing get_training_progress view with this improved version

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_training_progress(request, training_id):
    """
    Get detailed progress for a specific training including candidate status
    """
    try:
        user = request.user
        
        # Get training
        training = get_object_or_404(Training, id=training_id)
        
        # Get candidate for this user and training
        candidate = get_object_or_404(Candidate, learner=user, training=training)
        
        # Get or create learning progress
        progress, created = LearningProgress.objects.get_or_create(
            candidate=candidate,
            training=training,
            defaults={'total_modules': training.modules.count()}
        )
        
        if created:
            # Initialize module completions for all modules
            for module in training.modules.all():
                ModuleCompletion.objects.get_or_create(
                    learning_progress=progress,
                    module=module
                )
        
        # Update progress statistics
        progress.update_progress()
        
        # Update candidate status based on progress
        candidate.update_status_based_on_progress()
        
        # Get detailed module progress
        module_progress = []
        for module in training.modules.all().order_by('id'):
            completion = ModuleCompletion.objects.filter(
                learning_progress=progress,
                module=module
            ).first()
            
            module_progress.append({
                'id': module.id,
                'name': module.name,
                'description': module.description,
                'is_completed': completion.is_completed if completion else False,
                'started_at': completion.started_at if completion else None,
                'completed_at': completion.completed_at if completion else None,
                'time_spent_minutes': completion.time_spent_minutes if completion else 0,
                'materials_count': module.materials.count()
            })
        
        # Calculate next module
        next_module = None
        for module in module_progress:
            if not module['is_completed']:
                next_module = module['id']
                break
        
        response_data = {
            'candidate_id': candidate.id,
            'training_id': training.id,
            'training_name': training.name,
            'candidate_status': candidate.status,  # Add candidate status
            'progress': {
                'total_modules': progress.total_modules,
                'completed_modules': progress.completed_modules,
                'progress_percentage': float(progress.progress_percentage),
                'is_completed': progress.is_completed(),
                'started_at': progress.started_at,
                'last_activity': progress.last_activity
            },
            'modules': module_progress,
            'next_module': next_module
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'You are not registered for this training'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"Error in get_training_progress: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

    
def get_next_incomplete_module(progress):
    """Helper function to find the first incomplete module"""
    completed_module_ids = progress.module_completions.filter(
        is_completed=True
    ).values_list('module_id', flat=True)
    
    next_module = progress.training.modules.exclude(
        id__in=completed_module_ids
    ).order_by('id').first()
    
    return next_module.id if next_module else None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_module_completion(request):
    """
    Save module completion status for a candidate
    """
    try:
        print(f"=== SAVE MODULE COMPLETION START ===")
        print(f"Request user: {request.user}")
        print(f"Request user phone: {getattr(request.user, 'phone_number', 'No phone')}")
        print(f"Submitted data: {request.data}")
        
        # Validate required fields
        module_id = request.data.get('module_id')
        if not module_id:
            error_msg = "Module ID is required"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        is_completed = request.data.get('is_completed', True)
        print(f"Processing module_id: {module_id}, is_completed: {is_completed}")
        
        # Try to get learner using different approaches
        learner = None
        candidate = None
        
        try:
            # First approach: learner created by the user
            learner = CustomUser.objects.get(id=request.user.id)
            print(f"Found learner (created_by): {learner}")
        except CustomUser.DoesNotExist:
            try:
                # Second approach: learner associated with user directly
                learner = CustomUser.objects.get(id=request.user.id)
                print(f"Found learner (user field): {learner}")
            except CustomUser.DoesNotExist:
                error_msg = f"No learner found for user {request.user}. User ID: {request.user.id}"
                print(f"ERROR: {error_msg}")
                return Response({'error': error_msg}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            error_msg = f"Unexpected error finding learner: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Try to get module first to determine which training we're dealing with
        try:
            module = Module.objects.get(id=module_id)
            print(f"Found module: {module}")
        except Module.DoesNotExist:
            error_msg = f"Module with ID {module_id} not found"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            error_msg = f"Invalid module ID format: {module_id}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = f"Unexpected error finding module: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        training = module.training
        print(f"Module belongs to training: {training}")
        
        # Get the specific candidate for this training
        try:
            candidate = Candidate.objects.get(learner=learner, training=training)
            print(f"Found candidate for training: {candidate}")
        except Candidate.DoesNotExist:
            error_msg = f"Candidate not found for learner {learner} and training {training}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_404_NOT_FOUND)
        except Candidate.MultipleObjectsReturned:
            # This shouldn't happen with learner+training combination, but handle it
            error_msg = f"Multiple candidates found for learner {learner} and training {training}. Data integrity issue."
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = f"Unexpected error finding candidate: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Get or create learning progress
        try:
            progress, created = LearningProgress.objects.get_or_create(
                candidate=candidate,
                training=training,
                defaults={'total_modules': training.modules.count()}
            )
            print(f"Learning progress: {progress} (created: {created})")
        except Exception as e:
            error_msg = f"Error creating/getting learning progress: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Update or create module completion
        try:
            with transaction.atomic():
                module_completion, created = ModuleCompletion.objects.get_or_create(
                    learning_progress=progress,
                    module=module,
                    defaults={'is_completed': is_completed}
                )
                print(f"Module completion: {module_completion} (created: {created})")
                
                if not created and module_completion.is_completed != is_completed:
                    module_completion.is_completed = is_completed
                    if is_completed:
                        module_completion.completed_at = timezone.now()
                        print(f"Marked module as completed at: {module_completion.completed_at}")
                    module_completion.save()
                    print(f"Updated module completion status")
                
                # Update overall progress
                progress.update_progress()
                print(f"Updated overall progress: {progress.progress_percentage}%")
                
                # Get next module
                next_module = get_next_incomplete_module(progress)
                print(f"Next incomplete module: {next_module}")
                
                response_data = {
                    'success': True,
                    'progress_percentage': float(progress.progress_percentage),
                    'next_module': next_module,
                    'completed_modules': progress.completed_modules,
                    'total_modules': progress.total_modules
                }
                print(f"SUCCESS: Returning response: {response_data}")
                return Response(response_data, status=status.HTTP_200_OK)
                
        except ValidationError as e:
            error_msg = f"Validation error: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = f"Database error during module completion update: {str(e)}"
            print(f"ERROR: {error_msg}")
            return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        error_msg = f"Unexpected error in save_module_completion: {str(e)}"
        print(f"CRITICAL ERROR: {error_msg}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return Response({'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        print(f"=== SAVE MODULE COMPLETION END ===")
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_achievements(request):
    """
    Get achievements for the authenticated candidate
    """
    try:
        candidate = get_object_or_404(Candidate, learner=request.user.id)
        
        achievements = LearningAchievement.objects.filter(candidate=candidate)
        training_id = request.query_params.get('training_id')
        if training_id:
            achievements = achievements.filter(training_id=training_id)
        
        serializer = LearningAchievementSerializer(achievements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_learning_session(request):
    """
    Start a new learning session
    """
    try:
        candidate = get_object_or_404(Candidate, learner=request.user.id)
        
        training_id = request.data.get('training_id')
        module_id = request.data.get('module_id')
        
        if not training_id:
            return Response(
                {'error': 'Training ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        training = get_object_or_404(Training, id=training_id)
        module = None
        
        if module_id:
            module = get_object_or_404(Module, id=module_id, training=training)
        
        # Check if candidate is registered for this training
        if not Candidate.objects.filter(learner=candidate.learner, training=training).exists():
            return Response(
                {'error': 'You are not registered for this training'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # End any active sessions first
        active_sessions = LearningSession.objects.filter(
            candidate=candidate,
            session_end__isnull=True
        )
        for session in active_sessions:
            session.end_session()
        
        # Create new session
        session = LearningSession.objects.create(
            candidate=candidate,
            training=training,
            module=module
        )
        
        serializer = LearningSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_learning_session(request, session_id):
    """
    End a learning session
    """
    try:
        candidate = get_object_or_404(Candidate, learner=request.user.id)
        
        session = get_object_or_404(
            LearningSession, 
            id=session_id, 
            candidate=candidate,
            session_end__isnull=True
        )
        
        activities_completed = request.data.get('activities_completed', 0)
        session.activities_completed = activities_completed
        session.end_session()
        
        serializer = LearningSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except LearningSession.DoesNotExist:
        return Response(
            {'error': 'Active learning session not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_training_progress(request, training_id):
    """
    Allow a logged-in training candidate to see training progress on a specific training
    """
    try:
        if not request.user:
            print("No user found")
            return Response(
                {'error': 'You are not authorized to access this api'}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        learner = CustomUser.objects.get(id=request.user.id)
        
        training = get_object_or_404(Training, id=training_id)
        
        candidate = get_object_or_404(Candidate, learner=learner, training=training)
        
        # Check if candidate is registered for this training
        if not Candidate.objects.filter(learner=candidate.learner, training=training).exists():
            return Response(
                {'error': 'You are not registered for this training'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get or create learning progress
        learning_progress, created = LearningProgress.objects.get_or_create(
            candidate=candidate,
            training=training,
            defaults={'total_modules': training.modules.count()}
        )
        
        if created:
            # Initialize module completions for all modules
            for module in training.modules.all():
                ModuleCompletion.objects.get_or_create(
                    learning_progress=learning_progress,
                    module=module
                )
        
        serializer = LearningProgressSerializer(learning_progress)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_training_progress(request):
    """
    Allow a logged-in training candidate to see general training progress for all registered trainings
    """
    try:
        candidate = get_object_or_404(Candidate, learner=request.user.id)
        
        # Get all learning progress for this candidate
        learning_progress_list = LearningProgress.objects.filter(candidate=candidate)
        
        # If no progress exists, create them for all registered trainings
        if not learning_progress_list.exists():
            candidate_trainings = Candidate.objects.filter(learner=candidate.learner)
            for candidate_training in candidate_trainings:
                learning_progress, created = LearningProgress.objects.get_or_create(
                    candidate=candidate_training,
                    training=candidate_training.training,
                    defaults={'total_modules': candidate_training.training.modules.count()}
                )
                
                # Initialize module completions
                for module in candidate_training.training.modules.all():
                    ModuleCompletion.objects.get_or_create(
                        learning_progress=learning_progress,
                        module=module
                    )
        
        # Refresh the queryset
        learning_progress_list = LearningProgress.objects.filter(candidate=candidate)
        serializer = LearningProgressSummarySerializer(learning_progress_list, many=True)
        
        return Response({
            'count': learning_progress_list.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Candidate profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_get_all_candidates_progress(request):
    """
    Allow admin to see all training candidates progress for all registered trainings
    """
    # Check if user is admin
    if not hasattr(request.user, 'role') or request.user.role != 'admin':
        return Response(
            {'error': 'Admin access required'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get all learning progress
        learning_progress_list = LearningProgress.objects.all()
        
        # Filter by training if specified
        training_id = request.query_params.get('training_id')
        if training_id:
            learning_progress_list = learning_progress_list.filter(training_id=training_id)
        
        # Filter by status if specified
        status_filter = request.query_params.get('status')
        if status_filter == 'completed':
            learning_progress_list = learning_progress_list.filter(
                completed_modules__gte=models.F('total_modules'),
                total_modules__gt=0
            )
        elif status_filter == 'in_progress':
            learning_progress_list = learning_progress_list.filter(
                completed_modules__lt=models.F('total_modules')
            )
        
        serializer = LearningProgressSummarySerializer(learning_progress_list, many=True)
        
        # Calculate summary statistics
        total_candidates = learning_progress_list.count()
        completed_trainings = learning_progress_list.filter(
            completed_modules__gte=models.F('total_modules'),
            total_modules__gt=0
        ).count()
        
        return Response({
            'summary': {
                'total_candidates': total_candidates,
                'completed_trainings': completed_trainings,
                'completion_rate': round((completed_trainings / total_candidates * 100) if total_candidates > 0 else 0, 2)
            },
            'count': total_candidates,
            'results': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_get_training_candidates_progress(request, training_id):
    """
    Allow admin to see all training candidates progress on a specific training
    """
    # Check if user is admin
    if not hasattr(request.user, 'role') or request.user.role != 'admin':
        return Response(
            {'error': 'Admin access required'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        training = get_object_or_404(Training, id=training_id)
        
        # Get all learning progress for this training
        learning_progress_list = LearningProgress.objects.filter(training=training)
        
        # If no progress exists, create them for all registered candidates
        registered_candidates = Candidate.objects.filter(training=training)
        for candidate in registered_candidates:
            learning_progress, created = LearningProgress.objects.get_or_create(
                candidate=candidate,
                training=training,
                defaults={'total_modules': training.modules.count()}
            )
            
            if created:
                # Initialize module completions
                for module in training.modules.all():
                    ModuleCompletion.objects.get_or_create(
                        learning_progress=learning_progress,
                        module=module
                    )
        
        # Refresh the queryset and serialize with detailed data
        learning_progress_list = LearningProgress.objects.filter(training=training)
        serializer = LearningProgressSerializer(learning_progress_list, many=True)
        
        # Calculate training-specific statistics
        total_candidates = learning_progress_list.count()
        completed_candidates = learning_progress_list.filter(
            completed_modules__gte=models.F('total_modules'),
            total_modules__gt=0
        ).count()
        
        avg_progress = learning_progress_list.aggregate(
            avg_progress=models.Avg('progress_percentage')
        )['avg_progress'] or 0
        
        return Response({
            'training': {
                'id': training.id,
                'name': training.name,
                'description': training.description,
                'total_modules': training.modules.count()
            },
            'summary': {
                'total_candidates': total_candidates,
                'completed_candidates': completed_candidates,
                'completion_rate': round((completed_candidates / total_candidates * 100) if total_candidates > 0 else 0, 2),
                'average_progress': round(avg_progress, 2)
            },
            'count': total_candidates,
            'results': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_material_progress(request):
    """
    Update progress on individual training materials
    """
    try:
        candidate = get_object_or_404(Candidate, learner__created_by=request.user)
        
        material_id = request.data.get('material_id')
        is_viewed = request.data.get('is_viewed', False)
        is_downloaded = request.data.get('is_downloaded', False)
        view_duration = request.data.get('view_duration_seconds', 0)
        
        if not material_id:
            return Response(
                {'error': 'Material ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        material = get_object_or_404(TrainingMaterial, id=material_id)
        
        # Get the module completion
        try:
            learning_progress = LearningProgress.objects.get(
                candidate=candidate,
                training=material.module.training
            )
            module_completion = ModuleCompletion.objects.get(
                learning_progress=learning_progress,
                module=material.module
            )
        except (LearningProgress.DoesNotExist, ModuleCompletion.DoesNotExist):
            return Response(
                {'error': 'Progress tracking not initialized for this material'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get or create material progress
        material_progress, created = MaterialProgress.objects.get_or_create(
            module_completion=module_completion,
            material=material
        )
        
        # Update material progress
        serializer = MaterialProgressUpdateSerializer(
            material_progress,
            data={
                'is_viewed': is_viewed,
                'is_downloaded': is_downloaded,
                'view_duration_seconds': view_duration
            },
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def check_and_create_achievements(candidate, learning_progress):
    """
    Helper function to check and create achievements for candidates
    """
    try:
        # First module completion achievement
        if learning_progress.completed_modules == 1:
            LearningAchievement.objects.get_or_create(
                candidate=candidate,
                achievement_type='first_module',
                training=learning_progress.training,
                defaults={
                    'description': f'Completed first module in {learning_progress.training.name}'
                }
            )
        
        # Training completion achievement
        if learning_progress.is_completed():
            LearningAchievement.objects.get_or_create(
                candidate=candidate,
                achievement_type='training_completed',
                training=learning_progress.training,
                defaults={
                    'description': f'Successfully completed {learning_progress.training.name} training'
                }
            )
        
        # Fast learner achievement (completed in less than average time)
        # This would require more complex logic based on average completion times
        
    except Exception:
        # Don't let achievement creation errors affect main functionality
        pass


# Additional utility views

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_learning_sessions(request):
    """
    Get learning sessions for the authenticated candidate
    """
    try:
        candidate = get_object_or_404(Candidate, learner__created_by=request.user)
        
        sessions = LearningSession.objects.filter(candidate=candidate)
        training_id = request.query_params.get('training_id')
        if training_id:
            sessions = sessions.filter(training_id=training_id)
        
        serializer = LearningSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_candidate_training_progress(request, candidate_id, training_id):
    """
    Get progress for a specific candidate and training (for admin/manager view)
    """
    # Check if user has permission to view other candidates' progress
    user = request.user
    
    if user.role not in ['admin', 'hr_manager', 'compliance_officer']:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get candidate
        candidate = get_object_or_404(Candidate, id=candidate_id)
        
        # Get training
        training = get_object_or_404(Training, id=training_id)
        
        # Verify candidate is registered for this training
        if candidate.training.id != training.id:
            return Response(
                {'error': 'Candidate is not registered for this training'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get learning progress
        progress = get_object_or_404(
            LearningProgress, 
            candidate=candidate,
            training=training
        )
        
        # Update progress statistics
        progress.update_progress()
        
        # Get detailed module progress
        module_progress = []
        for module in training.modules.all().order_by('id'):
            completion = ModuleCompletion.objects.filter(
                learning_progress=progress,
                module=module
            ).first()
            
            # Get material progress for this module
            material_progress = []
            if completion:
                for material_prog in completion.material_progress.all():
                    material_progress.append({
                        'material_id': material_prog.material.id,
                        'filename': material_prog.material.get_filename(),
                        'is_viewed': material_prog.is_viewed,
                        'is_downloaded': material_prog.is_downloaded,
                        'viewed_at': material_prog.viewed_at,
                        'view_duration_seconds': material_prog.view_duration_seconds
                    })
            
            module_progress.append({
                'id': module.id,
                'name': module.name,
                'description': module.description,
                'is_completed': completion.is_completed if completion else False,
                'started_at': completion.started_at if completion else None,
                'completed_at': completion.completed_at if completion else None,
                'time_spent_minutes': completion.time_spent_minutes if completion else 0,
                'materials': material_progress
            })
        
        response_data = {
            'candidate': {
                'id': candidate.id,
                'learner_name': candidate.learner.full_name,
                'learner_email': candidate.learner.email,
                'learner_phone': candidate.learner.phone_number,
                'status': candidate.status,
                'enrollment_date': candidate.created_at
            },
            'training': {
                'id': training.id,
                'name': training.name,
                'description': training.description,
                'total_modules': training.modules.count()
            },
            'progress': {
                'total_modules': progress.total_modules,
                'completed_modules': progress.completed_modules,
                'progress_percentage': float(progress.progress_percentage),
                'is_completed': progress.is_completed(),
                'started_at': progress.started_at,
                'last_activity': progress.last_activity,
                'estimated_completion_date': progress.estimated_completion_date
            },
            'module_progress': module_progress
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"Error in get_candidate_training_progress: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )