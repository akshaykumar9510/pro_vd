from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import base64
import os
import time

from registration.utils.utils import save_user_data, create_required_directories, update_registration_status
from registration.utils.db import get_user, update_user, is_mongodb_available
from registration.utils.video_processor import process_video, extract_frames, store_frames_in_db
from registration.utils.model_trainer import train_yolo_model
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from registration.utils.monitor_engine import ExamMonitor
import json

monitor_instance = ExamMonitor()

create_required_directories()

def index(request):
    return render(request, 'index.html')

@csrf_exempt
def register(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        education = request.POST.get('education')
        user_id = save_user_data(name, email, phone, education)
        return JsonResponse({'status': 'success', 'user_id': user_id})

@csrf_exempt
def save_video(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            video_data = data.get('video_data', '')
            user_id = data.get('user_id', '')

            if not video_data or not user_id:
                return JsonResponse({'status': 'error', 'message': 'Missing video data or user ID'})

            # Log the video data length for debugging
            print(f"Received video data of length: {len(video_data)}")
            
            try:
                # Make sure the video data is properly formatted
                if ',' not in video_data:
                    return JsonResponse({'status': 'error', 'message': 'Invalid video data format'})
                
                video_data = video_data.split(',')[1]
                user_dir = os.path.join('static', 'data', user_id)
                os.makedirs(user_dir, exist_ok=True)

                video_path = os.path.join(user_dir, 'video.webm')
                try:
                    decoded_data = base64.b64decode(video_data)
                    with open(video_path, 'wb') as f:
                        f.write(decoded_data)
                    print(f"Video saved to {video_path}, size: {len(decoded_data)} bytes")
                    
                    # Check if video file is valid (not empty or too small)
                    if os.path.getsize(video_path) < 1000:  # Less than 1KB is suspicious
                        error_msg = f"Video file too small: {os.path.getsize(video_path)} bytes"
                        print(error_msg)
                        update_user(user_id, {"registration_status": "video_too_small"})
                        return JsonResponse({'status': 'error', 'message': 'Recorded video is too small or empty'})
                        
                except Exception as e:
                    print(f"Base64 decoding error: {str(e)}")
                    return JsonResponse({'status': 'error', 'message': 'Invalid video data encoding'})

                if is_mongodb_available():
                    update_user(user_id, {
                        "video_saved": True,
                        "video_saved_at": time.time(),
                        "registration_status": "video_captured"
                    })

                frames_dir = os.path.join(user_dir, 'frames')
                os.makedirs(frames_dir, exist_ok=True)
                
                # More detailed frame extraction
                extract_result = extract_frames(video_path, frames_dir)
                if not extract_result:
                    print(f"Frame extraction failed for user {user_id}")
                    update_user(user_id, {"registration_status": "frame_extraction_failed"})
                    return JsonResponse({'status': 'error', 'message': 'Failed to extract frames from video'})

                # Log the number of extracted frames
                frames_count = len([f for f in os.listdir(frames_dir) if f.endswith('.jpg')])
                print(f"Extracted {frames_count} frames from video")

                if frames_count == 0:
                    update_user(user_id, {"registration_status": "no_frames_extracted"})
                    return JsonResponse({'status': 'error', 'message': 'No frames could be extracted from video'})

                annotations_dir = os.path.join(user_dir, 'annotations')
                os.makedirs(annotations_dir, exist_ok=True)
                
                process_result = process_video(frames_dir, annotations_dir, user_id)
                if not process_result:
                    print(f"Annotation generation failed for user {user_id}")
                    update_user(user_id, {"registration_status": "annotation_generation_failed"})
                    return JsonResponse({'status': 'error', 'message': 'Annotation generation failed'})

                store_result = store_frames_in_db(frames_dir, user_id)
                if not store_result and is_mongodb_available():
                    print(f"Warning: Failed to store frames in database for user {user_id}")
                    # Continue anyway as this is not critical

                model_dir = os.path.join('static', 'models')
                os.makedirs(model_dir, exist_ok=True)
                update_user(user_id, {"registration_status": "model_training_started"})

                result = train_yolo_model(frames_dir, annotations_dir, model_dir, user_id)
                if not result:
                    print(f"Model training failed for user {user_id}, but registration will complete")
                    update_registration_status(user_id, True, "completed_without_model")
                    return JsonResponse({'status': 'partial_success', 'message': 'Model training failed but registration completed'})

                update_registration_status(user_id, True, "completed_successfully")
                return JsonResponse({'status': 'success', 'message': 'Model trained successfully'})
                
            except Exception as e:
                # More detailed exception handling
                import traceback
                error_trace = traceback.format_exc()
                print(f"Video processing error for user {user_id}: {str(e)}")
                print(error_trace)
                
                error_type = type(e).__name__
                if is_mongodb_available():
                    update_user(user_id, {
                        "registration_status": "error",
                        "error_type": error_type,
                        "error_message": str(e),
                        "error_time": time.time()
                    })
                
                # Create error log file
                error_log_dir = os.path.join('logs', 'errors')
                os.makedirs(error_log_dir, exist_ok=True)
                error_log_path = os.path.join(error_log_dir, f"error_{user_id}_{int(time.time())}.log")
                
                with open(error_log_path, 'w') as f:
                    f.write(f"Error Type: {error_type}\n")
                    f.write(f"Error Message: {str(e)}\n")
                    f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Traceback: {error_trace}\n")
                
                return JsonResponse({
                    'status': 'error', 
                    'message': 'An error occurred while processing your video',
                    'details': str(e),
                    'error_type': error_type
                })
        except json.JSONDecodeError:
            print("Invalid JSON in request body")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON in request'})
        except Exception as e:
            import traceback
            print(f"Unexpected error in save_video: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'status': 'error', 'message': f'Unexpected error: {str(e)}'})
    
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'})

@csrf_exempt
def monitor_frame(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})

    try:
        data = json.loads(request.body)
        frame = data.get('frame')

        if not frame:
            return JsonResponse({'status': 'error', 'message': 'No frame provided'})

        result = monitor_instance.monitor_single_frame(frame)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def log_tab_switch(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        event_data = data.get('event_data', {})
        
        if not user_id or not session_id:
            return JsonResponse({'status': 'error', 'message': 'Missing user_id or session_id'})
        
        result = monitor_instance.log_tab_switch(user_id, session_id, event_data)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def log_mouse_movement(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        movement_data = data.get('movement_data', {})
        
        if not user_id or not session_id:
            return JsonResponse({'status': 'error', 'message': 'Missing user_id or session_id'})
        
        result = monitor_instance.log_mouse_movement(user_id, session_id, movement_data)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def detect_screen_capture(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        event_data = data.get('event_data', {})
        
        if not user_id or not session_id:
            return JsonResponse({'status': 'error', 'message': 'Missing user_id or session_id'})
        
        result = monitor_instance.detect_screen_capture(user_id, session_id, event_data)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def log_copy_paste(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        event_data = data.get('event_data', {})
        
        if not user_id or not session_id:
            return JsonResponse({'status': 'error', 'message': 'Missing user_id or session_id'})
        
        result = monitor_instance.log_copy_paste(user_id, session_id, event_data)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
def processing_status(request):
    """Endpoint to check the status of video processing for a specific user"""
    user_id = request.GET.get('user_id')
    if not user_id:
        return JsonResponse({'status': 'error', 'message': 'Missing user_id parameter'})
    
    user_data = get_user(user_id)
    if not user_data:
        return JsonResponse({'status': 'error', 'message': 'User not found'})
    
    # Get registration status from database
    status = user_data.get('registration_status', 'unknown')
    
    if status in ['completed_successfully', 'completed_without_model']:
        # Processing is complete
        return JsonResponse({
            'status': 'completed',
            'progress': 100,
            'step': 'Processing complete'
        })
    elif status in ['error', 'frame_extraction_failed', 'video_too_small', 'annotation_generation_failed']:
        # Processing failed
        return JsonResponse({
            'status': 'failed',
            'message': user_data.get('error_message', f'Processing failed: {status}')
        })
    elif status == 'video_captured':
        # Just started processing
        return JsonResponse({
            'status': 'processing',
            'progress': 30,
            'step': 'Extracting frames from video...'
        })
    elif status == 'frame_extraction_complete':
        # Extracted frames, processing annotations
        return JsonResponse({
            'status': 'processing',
            'progress': 50,
            'step': 'Generating annotations...'
        })
    elif status == 'model_training_started':
        # Training model
        return JsonResponse({
            'status': 'processing',
            'progress': 75,
            'step': 'Training recognition model...'
        })
    elif status == 'processing_skipped':
        # User skipped processing
        return JsonResponse({
            'status': 'completed',
            'progress': 100,
            'step': 'Processing skipped'
        })
    else:
        # Default response for unknown or other statuses
        return JsonResponse({
            'status': 'processing',
            'progress': 50,
            'step': 'Processing your video...'
        })

@csrf_exempt
def skip_processing(request):
    """Endpoint to mark processing as skipped and continue to confirmation"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        if not user_id:
            return JsonResponse({'status': 'error', 'message': 'Missing user ID'})
        
        # Update user status in database
        if is_mongodb_available():
            update_user(user_id, {
                "registration_status": "processing_skipped",
                "processing_skipped_at": time.time()
            })
        
        return JsonResponse({'status': 'success', 'message': 'Processing skipped'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def confirmation(request, user_id):
    user_data = get_user(user_id)
    if not user_data:
        user_data = {
            'id': user_id,
            'name': 'Unknown',
            'email': 'unknown@example.com',
            'status': 'Unavailable'
        }
    return render(request, 'confirmation.html', {'user': user_data})

def monitor(request, user_id):
    """Display the monitoring setup page with webcam initialization"""
    user_data = get_user(user_id)
    if not user_data:
        user_data = {
            'id': user_id,
            'name': 'Unknown',
            'email': 'unknown@example.com',
            'status': 'Unavailable'
        }
    return render(request, 'monitor.html', {'user': user_data})

def exam(request, user_id):
    """Display the exam page with active monitoring"""
    user_data = get_user(user_id)
    if not user_data:
        user_data = {
            'id': user_id,
            'name': 'Unknown',
            'email': 'unknown@example.com',
            'status': 'Unavailable'
        }
    return render(request, 'exam.html', {'user': user_data})
