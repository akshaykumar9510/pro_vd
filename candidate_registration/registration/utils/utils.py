import os
import json
import time
import uuid
from .db import save_user, update_user, init_db, is_mongodb_available, JSONEncoder, save_model



def create_required_directories():
    """Create all required directories for the application."""
    os.makedirs('static/data', exist_ok=True)
    os.makedirs('static/models', exist_ok=True)
    os.makedirs('static/temp', exist_ok=True)
    
    # Initialize the MongoDB connection
    init_db()

def save_user_data(name, email, phone, education):
    """Save user registration data and return a unique user ID."""
    user_id = str(uuid.uuid4())
    
    # Create user directory
    user_dir = os.path.join('static', 'data', user_id)
    os.makedirs(user_dir, exist_ok=True)
    
    # Define paths for files
    video_path = os.path.join('static', 'data', user_id, 'video.webm')
    frames_dir = os.path.join('static', 'data', user_id, 'frames')
    model_path = os.path.join('static', 'models', f'user_{user_id}.pt')
    
    # Prepare user data
    user_data = {
        'id': user_id,
        'name': name,
        'email': email,
        'phone': phone,
        'education': education,
        'registration_time': time.time(),
        'video_path': video_path,
        'frames_dir': frames_dir,
        'model_path': model_path,
        'registration_status': 'initiated',
        'registration_complete': False
    }
    
    # Save to MongoDB only if available
    if is_mongodb_available():
        mongo_id = save_user(user_data)
        # Don't include ObjectId in JSON file
    
    # Save to JSON file for backward compatibility
    try:
        with open(os.path.join(user_dir, 'user_data.json'), 'w') as f:
            json.dump(user_data, f, indent=4, cls=JSONEncoder)
    except Exception as e:
        print(f"Error saving user data to JSON: {str(e)}")
    
    return user_id

def update_registration_status(user_id, status=True, status_message="completed"):
    """Update user registration status."""
    update_data = {
        'registration_complete': status,
        'registration_status': status_message,
        'registration_completed_at': time.time()
    }
    
    # Update in MongoDB if available
    if is_mongodb_available():
        update_user(user_id, update_data)
    
    # Also update JSON file
    try:
        user_dir = os.path.join('static', 'data', user_id)
        json_path = os.path.join(user_dir, 'user_data.json')
        
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                user_data = json.load(f)
            
            user_data.update(update_data)
            
            with open(json_path, 'w') as f:
                json.dump(user_data, f, indent=4, cls=JSONEncoder)
    except Exception as e:
        print(f"Error updating JSON file: {str(e)}")

def get_roi_coordinates(frame_width=640, frame_height=480):
    """
    Return the Region of Interest coordinates adjusted for frame size.
    
    Args:
        frame_width: Width of the video frame
        frame_height: Height of the video frame
        
    Returns:
        List containing [x_min, y_min, width, height]
    """
    # Calculate dynamic ROI that scales with frame size
    # Center ROI in the frame with appropriate size for face detection
    roi_width = min(400, int(frame_width * 0.625))  # ~62.5% of frame width
    roi_height = min(300, int(frame_height * 0.625))  # ~62.5% of frame height
    
    # Center the ROI in the frame
    x_min = int((frame_width - roi_width) / 2)
    y_min = int((frame_height - roi_height) / 2)
    
    return [x_min, y_min, roi_width, roi_height]

def import_existing_models_to_mongodb():
    """
    Import all existing model files from the file system into MongoDB.
    Useful for migrating existing models to the database.
    
    Returns:
        tuple: (imported_count, failed_count, skipped_count)
    """
    if not is_mongodb_available():
        print("MongoDB not available. Cannot import models.")
        return 0, 0, 0
    
    model_dir = os.path.join('static', 'models')
    imported_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Get all user model files
    model_files = [f for f in os.listdir(model_dir) if f.startswith('user_') and f.endswith('.pt')]
    
    for model_file in model_files:
        try:
            # Extract user_id from filename
            user_id = model_file.replace('user_', '').replace('.pt', '')
            
            # Check if valid UUID
            try:
                uuid_obj = uuid.UUID(user_id)
            except ValueError:
                print(f"Skipping {model_file}: Invalid UUID format")
                skipped_count += 1
                continue
            
            model_path = os.path.join(model_dir, model_file)
            metadata_path = os.path.join(model_dir, f"user_{user_id}_metadata.txt")
            
            # Check if metadata file exists
            metadata_exists = os.path.exists(metadata_path)
            
            # Import model to MongoDB
            print(f"Importing model for user {user_id}...")
            model_id = save_model(
                user_id=user_id,
                model_file_path=model_path,
                metadata_file_path=metadata_path if metadata_exists else None
            )
            
            if model_id:
                print(f"✅ Successfully imported model for user {user_id}")
                imported_count += 1
                
                # Update user document to indicate model is stored in DB
                update_user(user_id, {
                    "model_stored_in_db": True,
                    "model_db_id": str(model_id),
                    "model_stored_at": time.time()
                })
            else:
                print(f"❌ Failed to import model for user {user_id}")
                failed_count += 1
                
        except Exception as e:
            print(f"Error importing model {model_file}: {str(e)}")
            failed_count += 1
    
    print(f"\nImport summary:")
    print(f"- {imported_count} models successfully imported")
    print(f"- {failed_count} models failed to import")
    print(f"- {skipped_count} files skipped (invalid format)")
    
    return imported_count, failed_count, skipped_count
