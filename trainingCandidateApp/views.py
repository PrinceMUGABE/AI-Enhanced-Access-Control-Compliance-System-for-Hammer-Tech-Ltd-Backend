import io
import logging
import base64
import numpy as np
import cv2
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Candidate
from trainingApp.models import Training
from .serializers import CandidateSerializer
from rest_framework.permissions import IsAuthenticated
from userApp.models import CustomUser
import traceback


# views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


# views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import Candidate
import logging
import base64
import numpy as np
import cv2
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_candidate(request):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Log incoming request data
    logger.debug("=== Create Candidate Request Data ===")
    logger.debug(f"User ID: {request.user.id}")
    logger.debug(f"Content Type: {request.content_type}")
    logger.debug("Request Data Keys: " + ", ".join(request.data.keys()))
    
    training_id = request.data.get('training_id')
    user = request.user


    # Get training
    try:
        training = Training.objects.get(id=training_id)
        logger.debug(f"Found training: {training.id}")
    except Training.DoesNotExist:
        logger.error(f"Training not found: {training_id}")
        return Response({"detail": "Training not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check existing registration
    if Candidate.objects.filter(learner=user.id, training=training).exists():
        logger.error("Duplicate registration attempt")
        return Response({"detail": "Already registered"}, status=status.HTTP_400_BAD_REQUEST)

    try:
            logger.debug("Creating candidate record")
            candidate = Candidate(
                learner=user,
                training=training,
                status='pending'
            )
            candidate.save()
            logger.debug(f"Candidate created successfully: {candidate.id}")

            serializer = CandidateSerializer(candidate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Exception as e:
            logger.error(f"Database error: {str(e)}")
            return Response({"detail": "Failed to save candidate"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_candidate_by_id(request, candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
        serializer = CandidateSerializer(candidate)
        return Response(serializer.data)
    except Candidate.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_candidates_training(request):
    try:
        candidates = Candidate.objects.filter(training__in=request.user.training_set.all())
        serializer = CandidateSerializer(candidates, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({'error': str(e)}, status=500)




@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_candidate(request, candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
        serializer = CandidateSerializer(candidate, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Candidate.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)







@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_candidate(request, candidate_id):
    try:
        candidate = Candidate.objects.get(id=candidate_id)
        candidate.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Candidate.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def display_all_candidates(request):
    candidates = Candidate.objects.all()
    serializer = CandidateSerializer(candidates, many=True)
    print(f"\n Training candidates: {serializer.data}\n")
    return Response(serializer.data)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_registered_trainings(request):
    
    print(f'User found: {request.user}')
    
    learner = CustomUser.objects.filter(id=request.user.id)
    print(f'Learner ID: {learner}')
    
    
    # Fetch all the Candidate records where the user matches the logged-in user
    candidates = Candidate.objects.filter(learner=learner.first())
    
    print(f'Candidate ID: {candidates}')

    
    # Serialize the Candidate data, which includes training details
    serializer = CandidateSerializer(candidates, many=True)
    # print(f'Serializer: {serializer}')
    # Return the serialized data as response
    return Response(serializer.data)







# views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from .models import ModuleProgress, Candidate
from trainingApp.models import Module
from userApp.models import CustomUser as User


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_module_as_studied(request, candidate_id, module_id):
    # Get the logged-in user
    user = request.user

    # Fetch the CommunityHealthlearner for the logged-in user
    learner = get_object_or_404(CustomUser, id=user.id)

    # Get the candidate using the candidate_id and verify it belongs to the learner
    candidate = get_object_or_404(Candidate, id=candidate_id, learner=learner)

    # Get the module using the module_id and ensure it belongs to the candidate's training
    module = get_object_or_404(Module, id=module_id, training=candidate.training)

    # Update or create a ModuleProgress entry for this candidate and module
    progress, created = ModuleProgress.objects.get_or_create(candidate=candidate, module=module)
    progress.is_studied = True
    progress.studied_at = timezone.now()
    progress.save()

    # Check if all modules are now completed for the training
    all_completed = candidate.has_completed_training()

    return JsonResponse({
        "module_id": module_id,
        "candidate_id": candidate_id,
        "all_modules_completed": all_completed
    })


# Add this function to views.py
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_candidate_module_progress(request, candidate_id):
    try:
        # Verify the candidate belongs to the current user
        learner = get_object_or_404(CustomUser, id=request.user.id)
        candidate = get_object_or_404(Candidate, id=candidate_id, learner=learner)
        
        # Get all module progress records for this candidate
        progress_records = ModuleProgress.objects.filter(candidate=candidate)
        
        # Format the data for the response
        progress_data = [{
            'id': record.id,
            'module': record.module.id,
            'module_name': record.module.name,
            'is_studied': record.is_studied,
            'studied_at': record.studied_at
        } for record in progress_records]
        
        return Response(progress_data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
# views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Count, Q
from .models import Candidate
from .serializers import TrainingSerializer
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_top_popular_courses(request):
    """
    Get the top 3 most popular courses based on number of candidates enrolled.
    Optionally filter by status (pending, completed, failed) or get all enrollments.
    
    Query parameters:
    - status: Filter by candidate status (optional)
    - include_all: Include all statuses if set to 'true' (default behavior)
    """
    try:
        # Get query parameters
        status_filter = request.query_params.get('status', None)
        include_all = request.query_params.get('include_all', 'true').lower() == 'true'
        
        # Base queryset
        queryset = Candidate.objects.select_related('training', 'training__created_by')
        
        # Apply status filter if provided and not including all
        if status_filter and not include_all:
            if status_filter not in ['pending', 'completed', 'failed']:
                return Response(
                    {'error': 'Invalid status. Must be one of: pending, completed, failed'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(status=status_filter)
        
        # Get top 3 trainings by candidate count
        popular_trainings = (
            queryset
            .values('training')
            .annotate(
                candidate_count=Count('id'),
                completed_count=Count('id', filter=Q(status='completed')),
                pending_count=Count('id', filter=Q(status='pending')),
                failed_count=Count('id', filter=Q(status='failed'))
            )
            .order_by('-candidate_count')[:3]
        )
        
        # Get the actual training objects with their details
        training_ids = [item['training'] for item in popular_trainings]
        trainings = {}
        
        # Create a mapping of training data
        from trainingApp.models import Training
        for training in Training.objects.filter(id__in=training_ids).select_related('created_by'):
            trainings[training.id] = training
        
        # Build response data
        response_data = []
        for item in popular_trainings:
            training_id = item['training']
            training = trainings.get(training_id)
            
            if training:
                # Serialize the training data
                training_data = TrainingSerializer(training).data
                
                # Add popularity statistics
                training_data['popularity_stats'] = {
                    'total_candidates': item['candidate_count'],
                    'completed_candidates': item['completed_count'],
                    'pending_candidates': item['pending_count'],
                    'failed_candidates': item['failed_count'],
                    'completion_rate': round(
                        (item['completed_count'] / item['candidate_count']) * 100, 2
                    ) if item['candidate_count'] > 0 else 0
                }
                
                response_data.append(training_data)
        
        logger.info(f"Retrieved top {len(response_data)} popular courses")
        
        return Response({
            'success': True,
            'message': f'Top {len(response_data)} popular courses retrieved successfully',
            'data': response_data,
            'total_count': len(response_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error retrieving popular courses: {str(e)}")
        return Response(
            {'error': 'An error occurred while retrieving popular courses'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_course_popularity_details(request, training_id):
    """
    Get detailed popularity information for a specific course/training.
    
    Path parameters:
    - training_id: ID of the training to get details for
    """
    try:
        from trainingApp.models import Training
        
        # Check if training exists
        try:
            training = Training.objects.select_related('created_by').get(id=training_id)
        except Training.DoesNotExist:
            return Response(
                {'error': 'Training not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get candidate statistics for this training
        candidates_stats = (
            Candidate.objects
            .filter(training=training)
            .aggregate(
                total_candidates=Count('id'),
                completed_candidates=Count('id', filter=Q(status='completed')),
                pending_candidates=Count('id', filter=Q(status='pending')),
                failed_candidates=Count('id', filter=Q(status='failed'))
            )
        )
        
        # Get recent candidates (last 10)
        recent_candidates = (
            Candidate.objects
            .filter(training=training)
            .select_related('learner', 'learner__created_by')
            .order_by('-created_at')[:10]
        )
        
        # Serialize training data
        training_data = TrainingSerializer(training).data
        
        # Add detailed statistics
        training_data['detailed_stats'] = {
            **candidates_stats,
            'completion_rate': round(
                (candidates_stats['completed_candidates'] / candidates_stats['total_candidates']) * 100, 2
            ) if candidates_stats['total_candidates'] > 0 else 0,
            'failure_rate': round(
                (candidates_stats['failed_candidates'] / candidates_stats['total_candidates']) * 100, 2
            ) if candidates_stats['total_candidates'] > 0 else 0
        }
        
        # Add recent candidates info
        from .serializers import CandidateSerializer
        training_data['recent_candidates'] = CandidateSerializer(recent_candidates, many=True).data
        
        return Response({
            'success': True,
            'message': 'Course popularity details retrieved successfully',
            'data': training_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error retrieving course popularity details: {str(e)}")
        return Response(
            {'error': 'An error occurred while retrieving course details'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    




from django.db.models import Q

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unregistered_trainings(request):
    """
    Get all trainings that the current user is NOT registered to.
    Returns all training data including modules and materials.
    """
    try:
        user = request.user
        
        # Get all training IDs that the user IS registered to
        registered_training_ids = Candidate.objects.filter(
            learner=user
        ).values_list('training_id', flat=True)
        
        # Get all trainings EXCEPT the ones user is registered to
        from trainingApp.models import Training
        
        unregistered_trainings = Training.objects.exclude(
            id__in=registered_training_ids
        ).select_related('created_by').prefetch_related(
            'modules',
            'modules__materials'
        )
        
        # Serialize the trainings
        serializer = TrainingSerializer(unregistered_trainings, many=True)
        
        return Response({
            'success': True,
            'message': f'Found {len(serializer.data)} trainings you are not registered to',
            'data': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error retrieving unregistered trainings: {str(e)}")
        return Response({
            'error': 'Failed to retrieve unregistered trainings',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    




