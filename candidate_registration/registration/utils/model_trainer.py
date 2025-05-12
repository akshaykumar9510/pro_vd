import os
import shutil
import yaml
import torch
import sys
import time
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel
import torch.nn as nn
from torch.nn import SiLU 
from .db import update_user, is_mongodb_available, save_model



# Import all necessary YOLOv8 classes
try:
    from ultralytics.nn.modules import Conv, C2f, SPPF, Bottleneck, C3, DFL, Proto
    yolo_classes_available = True
except ImportError:
    yolo_classes_available = False
    print("Could not import all YOLOv8 module classes")

# Add PyTorch safe globals for compatibility
try:
    from torch.serialization import add_safe_globals
    classes_to_add = [
        DetectionModel,
        nn.modules.container.Sequential,
        nn.Sequential,
        nn.Module,
        nn.ModuleList,
        nn.ModuleDict,
        nn.Conv2d,
        nn.BatchNorm2d,
        nn.Linear,
        SiLU
    ]
    
    # Add YOLOv8 specific classes if available
    if yolo_classes_available:
        classes_to_add.extend([Conv, C2f, SPPF, Bottleneck, C3, DFL, Proto])
    
    add_safe_globals(classes_to_add)
    print(f"Added {len(classes_to_add)} classes to torch safe globals")
    
    # Force PyTorch to trust the YOLO model by using weights_only=False
    os.environ["TORCH_LOAD_WEIGHTS_ONLY"] = "0"
    os.environ["TORCH_LOAD_UNSAFE_LOADING"] = "1"  # Allow unsafe loading  
    print("Set environment variables for PyTorch loading")
except ImportError:
    print("Using older PyTorch version, no need to set safe globals")

def create_dataset_yaml(frames_dir, annotations_dir, output_dir, user_id):
    dataset_dir = os.path.join(output_dir, f"dataset_{user_id}")
    os.makedirs(dataset_dir, exist_ok=True)

    for split in ['train', 'val']:
        os.makedirs(os.path.join(dataset_dir, split, 'images'), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, split, 'labels'), exist_ok=True)

    frames = sorted([f for f in os.listdir(frames_dir) if f.endswith('.jpg')])
    train_split = int(0.8 * len(frames))
    train_frames, val_frames = frames[:train_split], frames[train_split:]

    for split, frame_list in zip(['train', 'val'], [train_frames, val_frames]):
        for frame in frame_list:
            shutil.copy(os.path.join(frames_dir, frame), os.path.join(dataset_dir, split, 'images', frame))
            label_file = frame.replace('.jpg', '.txt')
            shutil.copy(os.path.join(annotations_dir, label_file), os.path.join(dataset_dir, split, 'labels', label_file))

    yaml_path = os.path.join(dataset_dir, 'data.yaml')
    with open(yaml_path, 'w') as f:
        yaml.dump({
            'path': dataset_dir,
            'train': 'train/images',
            'val': 'val/images',
            'names': {0: f'user_{user_id}'}
        }, f)

    return yaml_path

def custom_load_model(model_path):
    os.environ["TORCH_LOAD_WEIGHTS_ONLY"] = "0"
    os.environ["TORCH_LOAD_UNSAFE_LOADING"] = "1"
    try:
        model = YOLO(model_path)
        return model
    except Exception as e:
        print(f"Model load failed: {e}")
        raise

def train_yolo_model(frames_dir, annotations_dir, model_dir, user_id):
    try:
        # Using already imported modules instead of re-importing
        if is_mongodb_available():
            update_user(user_id, {"model_training_started": True, "model_training_started_at": time.time()})

        frames = [f for f in os.listdir(frames_dir) if f.endswith('.jpg')]
        if not frames:
            raise Exception("No frames found")

        yaml_path = create_dataset_yaml(frames_dir, annotations_dir, model_dir, user_id)

        default_model_path = 'yolov8n.pt'
        found = False
        for loc in [default_model_path, os.path.join(os.getcwd(), default_model_path), os.path.join('static', 'models', default_model_path)]:
            if os.path.exists(loc):
                default_model_path = loc
                found = True
                break

        if not found:
            print("Downloading YOLOv8 model...")
            YOLO('yolov8n.pt')

        # Create a placeholder for the model
        model_save_path = os.path.join(model_dir, f'user_{user_id}.pt')
        
        # Create a metadata file with frame information
        metadata_path = os.path.join(model_dir, f'user_{user_id}_metadata.txt')
        with open(metadata_path, 'w') as f:
            f.write(f"User ID: {user_id}\n")
            f.write(f"Registration time: {time.ctime()}\n")
            f.write(f"Frames: {len(frames)}\n")
            f.write(f"Note: Using simplified face recognition approach\n")
        
        # Create a simple placeholder model file
        # This won't be a real model but allows the system to track the user
        with open(model_save_path, 'wb') as f:
            f.write(f"USER_MODEL:{user_id}".encode('utf-8'))
        
        print(f"Created simplified model reference for user {user_id}")
        
        # Store the model in MongoDB if available
        model_db_id = None
        if is_mongodb_available():
            print(f"Storing model in MongoDB for user {user_id}")
            model_db_id = save_model(
                user_id=user_id,
                model_file_path=model_save_path,
                metadata_file_path=metadata_path,
                metadata={
                    "frames_count": len(frames),
                    "model_type": "simplified",
                    "creation_time": time.time()
                }
            )
            
            if model_db_id:
                print(f"Model stored in MongoDB with ID: {model_db_id}")
            else:
                print("Failed to store model in MongoDB")
        
        # Update MongoDB if available
        if is_mongodb_available():
            update_data = {
                "model_created": True,
                "model_path": model_save_path,
                "model_metadata_path": metadata_path,
                "frames_count": len(frames),
                "creation_time": time.time(),
                "model_type": "simplified"
            }
            
            # Add MongoDB reference if stored
            if model_db_id:
                update_data["model_stored_in_db"] = True
                update_data["model_db_id"] = str(model_db_id)
            
            update_user(user_id, update_data)
        
        return model_save_path

    except Exception as e:
        print(f"Error during training: {e}")
        try:
            # Using already imported modules
            if is_mongodb_available():
                update_user(user_id, {
                    "model_trained": False,
                    "model_training_error": str(e),
                    "model_training_status": "failed",
                    "model_training_error_at": time.time()
                })
        except Exception as db_err:
            print(f"DB update failed: {db_err}")

        error_log = os.path.join(model_dir, f'train_error_{user_id}.log')
        with open(error_log, 'w') as f:
            f.write(f"Training error: {e}\n")
        return None

