# views.py in trainingApp
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import Training, Module, TrainingMaterial
from .serializers import TrainingSerializer, ModuleSerializer, TrainingMaterialSerializer
from .models import Module
from trainingCandidateApp.models import ModuleProgress
from userApp.models import CustomUser


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_training(request):
    """
    Create a new training with the associated service.
    """
    name = request.data.get('name')
    description = request.data.get('description', '')
    picture_file = request.FILES.get('picture_data')  # Get the file from FILES
    
    print(f"Submitted data to save: {request.data}\n\n")
    print(f"Files received: {request.FILES}\n\n")

    if not name:
        print("Training name is required.")
        return Response({"error": "Training name is required."}, status=status.HTTP_400_BAD_REQUEST)

    if Training.objects.filter(name=name).exists():
        return Response({"error": "Training with this name already exists."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Create training object
    training_data = {
        'name': name,
        'description': description,
        'created_by': request.user,
    }
    
    # Handle picture upload if provided
    if picture_file:
        # Read the file content and store as binary data
        picture_content = picture_file.read()
        training_data['picture_data'] = picture_content

    training = Training.objects.create(**training_data)
    serializer = TrainingSerializer(training)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_training_with_modules(request):
    """
    Create a new training with modules and their materials in one request.
    Expected structure:
    {
        "name": "Training Name",
        "description": "Training Description",
        "modules": [
            {
                "name": "Module 1",
                "description": "Module 1 Description"
            }
        ]
    }
    Files: picture_data, module_0_materials, module_1_materials, etc.
    """
    import json
    
    print("Submitted data: ", request.data, "\n\n")
    name = request.data.get('name')
    description = request.data.get('description', '')
    picture_file = request.FILES.get('picture_data')
    modules_json = request.data.get('modules', '[]')  # Get as string
    
    try:
        # Parse the modules JSON string
        modules_data = json.loads(modules_json)
    except json.JSONDecodeError as e:
        print(f"Error parsing modules data: {str(e)}")
        return Response({"error": "Invalid modules data format"}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    if not name:
        print("Training name is required.")
        return Response({"error": "Training name is required."}, 
                       status=status.HTTP_400_BAD_REQUEST)

    if Training.objects.filter(name=name).exists():
        print("Training with this name already exists.")
        return Response({"error": "Training with this name already exists."},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        # Create training
        training_data = {
            'name': name,
            'description': description,
            'created_by': request.user,
        }
        
        if picture_file:
            training_data['picture_data'] = picture_file.read()

        training = Training.objects.create(**training_data)

        # Create modules and their materials
        if modules_data:
            for i, module_data in enumerate(modules_data):
                module = Module.objects.create(
                    training=training,
                    name=module_data.get('name', f'Module {i+1}'),
                    description=module_data.get('description', '')
                )
                
                # Handle materials for this module
                material_files = request.FILES.getlist(f'module_{i}_materials')
                for material_file in material_files:
                    TrainingMaterial.objects.create(module=module, file=material_file)

        serializer = TrainingSerializer(training)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Exception as e:
        # Clean up if something goes wrong
        if 'training' in locals():
            training.delete()
        print(f"Error creating training: {str(e)}")
        return Response({"error": f"Error creating training: {str(e)}"}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_module(request, training_id):
    """
    Creates a new module within a specific training.
    """
    try:
        training = Training.objects.get(pk=training_id)
    except Training.DoesNotExist:
        return Response({"error": "Training not found."}, status=status.HTTP_404_NOT_FOUND)

    # Extract module data
    module_data = {
        'training': training.id,
        'name': request.data.get('name', ''),
        'description': request.data.get('description', ''),
    }

    # Debugging: Check the data being passed to the serializer
    print(f"Module data before serialization: {module_data}")

    serializer = ModuleSerializer(data=module_data)
    if serializer.is_valid():
        module = serializer.save()  # Save the module

        # Handle file uploads separately
        if 'materials' in request.FILES:
            materials = request.FILES.getlist('materials')
            for material in materials:
                try:
                    TrainingMaterial.objects.create(module=module, file=material)
                    print(f"Successfully uploaded material: {material.name}")
                except Exception as e:
                    print(f"Error uploading material {material.name}: {str(e)}")
                    continue

        # Return the updated module with materials
        updated_serializer = ModuleSerializer(module)
        return Response(updated_serializer.data, status=status.HTTP_201_CREATED)

    # Debugging: Check the serializer errors
    print(f"Serializer errors: {serializer.errors}")
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_material_to_module(request, module_id):
    """
    Uploads training materials to a specific module.
    """
    try:
        module = Module.objects.get(pk=module_id)
    except Module.DoesNotExist:
        print('Module not found.')
        return Response({"error": "Module not found."}, status=status.HTTP_404_NOT_FOUND)

    files = request.FILES.getlist('materials')
    if not files:
        return Response({"error": "No files uploaded."}, status=status.HTTP_400_BAD_REQUEST)

    uploaded_materials = []
    for file in files:
        try:
            material = TrainingMaterial.objects.create(module=module, file=file)
            uploaded_materials.append({
                'id': material.id,
                'filename': file.name,
                'size': file.size,
                'uploaded_at': material.uploaded_at
            })
        except Exception as e:
            print(f"Error uploading {file.name}: {str(e)}")
            continue

    return Response({
        "message": f"Successfully uploaded {len(uploaded_materials)} materials.",
        "materials": uploaded_materials
    }, status=status.HTTP_201_CREATED)


import logging
logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_training_by_id(request, pk):
    """
    Retrieve a training by its ID, including modules and candidate progress.
    """
    try:
        training = Training.objects.get(pk=pk)
        candidate_id = request.query_params.get('candidate_id')
        candidate_progress = {}

        # Fetch progress if candidate_id is provided
        if candidate_id:
            progress_qs = ModuleProgress.objects.filter(candidate_id=candidate_id, module__training=training)
            candidate_progress = {progress.module_id: progress.is_studied for progress in progress_qs}

        serializer = TrainingSerializer(training)
        training_data = serializer.data

        # Add progress information to each module
        for module in training_data.get('modules', []):
            module['is_completed'] = candidate_progress.get(module['id'], False)

        # Log the training data to the terminal
        logger.info("Training Data Retrieved: %s", training_data)

        return Response(training_data)
    except Training.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    

@api_view(['GET'])
def get_all_trainings(request):
    """
    Retrieve all trainings.
    """
    trainings = Training.objects.all()
    serializer = TrainingSerializer(trainings, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def get_all_modules(request, training_id):
    """
    Retrieve all modules of a specific training.
    """
    try:
        training = Training.objects.get(pk=training_id)
        modules = training.modules.all()
        serializer = ModuleSerializer(modules, many=True)
        return Response(serializer.data)
    except Training.DoesNotExist:
        return Response({"error": "Training not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_training(request, pk):
    """
    Update a training.
    """
    try:
        training = Training.objects.get(pk=pk)
    except Training.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    # Handle picture update if provided
    if 'picture_data' in request.FILES:
        picture_file = request.FILES.get('picture_data')
        if picture_file:
            training.picture_data = picture_file.read()
            training.save()

    # Update other fields
    serializer = TrainingSerializer(training, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_module(request, module_id):
    """
    Update a specific module within a training.
    """
    try:
        module = Module.objects.get(pk=module_id)
    except Module.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    # Update module basic info
    serializer = ModuleSerializer(module, data=request.data, partial=True)
    
    # Handle materials update
    if 'materials' in request.FILES:
        # Option 1: Replace all materials
        if request.data.get('replace_materials', 'false').lower() == 'true':
            module.materials.all().delete()
        
        # Add new materials
        materials = request.FILES.getlist('materials')
        for material in materials:
            try:
                TrainingMaterial.objects.create(module=module, file=material)
            except Exception as e:
                print(f"Error uploading material: {str(e)}")
                continue

    if serializer.is_valid():
        serializer.save()
        # Return updated module with materials
        updated_serializer = ModuleSerializer(module)
        return Response(updated_serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_training(request, pk):
    """
    Delete a training by its ID.
    """
    try:
        training = Training.objects.get(pk=pk)
        training.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Training.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_module(request, module_id):
    """
    Delete a specific module within a training.
    """
    try:
        module = Module.objects.get(pk=module_id)
        module.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Module.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_material(request, material_id):
    """
    Delete a specific training material.
    """
    try:
        material = TrainingMaterial.objects.get(pk=material_id)
        material.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except TrainingMaterial.DoesNotExist:
        return Response({"error": "Material not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_modules_by_training(request, training_id):
    """
    Retrieve all modules associated with a specific training by training ID.
    """
    try:
        training = Training.objects.get(pk=training_id)
    except Training.DoesNotExist:
        return Response({"error": "Training not found."}, status=status.HTTP_404_NOT_FOUND)

    modules = training.modules.all()
    serializer = ModuleSerializer(modules, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


from rest_framework.generics import get_object_or_404

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_module_by_id(request, module_id):
    """
    Retrieve a specific module by its ID along with associated training materials.
    """
    try:
        module = Module.objects.get(pk=module_id)
    except Module.DoesNotExist:
        return Response({"error": "Module not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ModuleSerializer(module)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_material(request, material_id):
    """
    Download a specific training material file.
    """
    try:
        material = TrainingMaterial.objects.get(pk=material_id)
        # Return file info for frontend to handle download
        return Response({
            'id': material.id,
            'filename': material.file.name.split('/')[-1],
            'url': material.file.url,
            'size': material.file.size,
            'uploaded_at': material.uploaded_at
        })
    except TrainingMaterial.DoesNotExist:
        return Response({"error": "Material not found."}, status=status.HTTP_404_NOT_FOUND)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
# views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from trainingCandidateApp.models import Candidate



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def completed_trainings_view(request):
    """
    API view to get trainings completed by the logged-in learner.
    Only accessible to users with 'learner' role.
    """
    # Check if the logged-in user is a learner
    if request.user.role != 'employee':
        return Response(
            {'error': 'Access denied. Only learners can access this endpoint.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get the learner object associated with the logged-in user
        learner = get_object_or_404(CustomUser, created_by=request.user)
        
        # Get all candidates (training registrations) for this learner with completed status
        completed_candidates = Candidate.objects.filter(
            learner=learner,
            status='completed'
        ).select_related('training').order_by('-created_at')
        
        # Prepare data for response
        completed_trainings = []
        
        for candidate in completed_candidates:
            training = candidate.training
            
            
            # Calculate completion details
            total_modules = training.modules.count()
            completed_modules = candidate.module_progresses.filter(is_studied=True).count()
            
            training_data = {
                'id': training.id,
                'name': training.name,
                'description': training.description,
                'candidate_id': candidate.id,
                'completion_date': candidate.created_at.isoformat(),
                'total_modules': total_modules,
                'completed_modules': completed_modules,
                'completion_percentage': round((completed_modules / total_modules * 100), 2) if total_modules > 0 else 0,
            }
            completed_trainings.append(training_data)
        
        # Pagination
        page_number = request.GET.get('page', 1)
        page_size = request.GET.get('page_size', 10)
        
        try:
            page_number = int(page_number)
            page_size = int(page_size)
        except ValueError:
            page_number = 1
            page_size = 10
            
        paginator = Paginator(completed_trainings, page_size)
        page_obj = paginator.get_page(page_number)
        
        # Statistics
        total_completed = len(completed_trainings)
        total_with_exams = sum(1 for t in completed_trainings if t['has_exam'])
        total_passed_exams = sum(1 for t in completed_trainings if t['exam_passed'])
        
        return Response({
            'status': 'success',
            'data': {
                'trainings': list(page_obj),
                'pagination': {
                    'current_page': page_obj.number,
                    'total_pages': paginator.num_pages,
                    'total_items': paginator.count,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                    'page_size': page_size
                },
                'statistics': {
                    'total_completed': total_completed,
                    'total_with_exams': total_with_exams,
                    'total_passed_exams': total_passed_exams,
                    'success_rate': round((total_passed_exams / total_with_exams * 100), 2) if total_with_exams > 0 else 0
                }
            }
        }, status=status.HTTP_200_OK)
        
    except CustomUser.DoesNotExist:
        return Response(
            {'error': 'Learner profile not found for this user.'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return Response(
            {'error': f'An unexpected error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def training_detail_view(request, training_id):
    """
    API view to get detailed information about a specific completed training.
    """
    if request.user.role != 'learner':
        return Response(
            {'error': 'Access denied. Only learners can access this endpoint.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        learner = get_object_or_404(CustomUser, created_by=request.user)
        
        # Get the specific candidate record for this training
        candidate = get_object_or_404(
            Candidate,
            learner=learner,
            training_id=training_id,
            status='completed'
        )
        
        training = candidate.training
        
        # Get all module progress for this candidate
        module_progresses = candidate.module_progresses.filter(
            is_studied=True
        ).select_related('module').order_by('studied_at')
        
        
        # Get training modules
        training_modules = training.modules.all().order_by('id')
        
        return Response({
            'status': 'success',
            'data': {
                'training': {
                    'id': training.id,
                    'name': training.name,
                    'description': training.description,
                    'created_at': training.created_at.isoformat() if hasattr(training, 'created_at') else None,
                    'total_modules': training_modules.count()
                },
                'candidate': {
                    'id': candidate.id,
                    'completion_date': candidate.created_at.isoformat(),
                    'status': candidate.status
                },
                'modules': {
                    'total': training_modules.count(),
                    'completed': module_progresses.count(),
                    'completion_percentage': round((module_progresses.count() / training_modules.count() * 100), 2) if training_modules.count() > 0 else 0,
                    'details': [
                        {
                            'id': mp.module.id,
                            'name': mp.module.name,
                            'description': getattr(mp.module, 'description', ''),
                            'studied_at': mp.studied_at.isoformat() if mp.studied_at else None,
                        }
                        for mp in module_progresses
                    ]
                }
            }
        }, status=status.HTTP_200_OK)
        
    except Candidate.DoesNotExist:
        return Response(
            {'error': 'Training not found or not completed by this learner.'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        return Response(
            {'error': f'An unexpected error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )