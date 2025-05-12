import cv2
import os
import time
import numpy as np  # Added numpy import
from .utils import get_roi_coordinates
from .db import update_user, is_mongodb_available, save_frames
import base64
from ultralytics import YOLO

def extract_frames(video_path, output_dir, interval=1):
    """
    Extract frames from a video file at regular intervals.
    
    Args:
        video_path: Path to the video file
        output_dir: Directory to save extracted frames
        interval: Interval in seconds between frame captures
    """
    # Open the video file
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return False
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30  # Default to 30 fps if we can't determine it
        print(f"Warning: Could not determine video FPS, using default value of {fps}")
    
    frame_interval = max(1, int(fps * interval))
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    frame_count = 0
    saved_count = 0
    max_frames = 30  # Limit the number of frames to avoid memory issues
    
    while cap.isOpened() and saved_count < max_frames:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        # Extract frame at the specified interval
        if frame_count % frame_interval == 0:
            # Save the frame
            output_path = os.path.join(output_dir, f"frame_{saved_count:04d}.jpg")
            try:
                cv2.imwrite(output_path, frame)
                saved_count += 1
                print(f"Saved frame {saved_count} to {output_path}")
            except Exception as e:
                print(f"Error saving frame: {str(e)}")
        
        frame_count += 1
    
    cap.release()
    print(f"Extracted {saved_count} frames from video")
    
    # Verify we have saved at least a few frames
    if saved_count > 0:
        return True
    else:
        print("No frames were successfully extracted from the video")
        
        # Create a single default frame if extraction failed
        try:
            default_frame = np.ones((480, 640, 3), dtype=np.uint8) * 255  # White frame
            cv2.putText(
                default_frame, 
                "Default Frame", 
                (50, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (0, 0, 0), 
                2
            )
            default_frame_path = os.path.join(output_dir, "frame_0000.jpg")
            cv2.imwrite(default_frame_path, default_frame)
            print(f"Created default frame at {default_frame_path}")
            return True
        except Exception as e:
            print(f"Error creating default frame: {str(e)}")
            return False

def store_frames_in_db(frames_dir, user_id):
    """
    Store frames from the file system to MongoDB.
    
    Args:
        frames_dir: Directory containing extracted frames
        user_id: Unique ID of the user
    
    Returns:
        True if frames were stored, False otherwise
    """
    try:
        if not is_mongodb_available():
            print("MongoDB not available, skipping frame storage")
            return False
        
        # Get all frames from directory
        frames = [f for f in os.listdir(frames_dir) if f.endswith('.jpg')]
        
        if not frames:
            print("No frames found to store in database")
            return False
        
        # Prepare frames data
        frames_data = []
        
        for frame_file in frames:
            frame_path = os.path.join(frames_dir, frame_file)
            
            # Read the image file and convert to base64
            with open(frame_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Add to frames data
            frames_data.append({
                "frame_id": frame_file,
                "image_data": image_data
            })
        
        # Save frames to MongoDB
        result = save_frames(user_id, frames_data)
        
        print(f"Stored {len(frames_data)} frames in MongoDB for user {user_id}")
        return result
    
    except Exception as e:
        print(f"Error storing frames in database: {str(e)}")
        return False

def process_video(frames_dir, annotations_dir, user_id):
    """
    Process frames and generate YOLO annotations.
    
    Args:
        frames_dir: Directory containing extracted frames
        annotations_dir: Directory to save annotations
        user_id: Unique ID of the user
    """
    try:
        # Create annotations directory if it doesn't exist
        os.makedirs(annotations_dir, exist_ok=True)
        
        # Get all frames
        frames = [f for f in os.listdir(frames_dir) if f.endswith('.jpg')]
        
        if not frames:
            print("No frames found to process")
            # Create a dummy frame if none exist
            dummy_frame_path = os.path.join(frames_dir, "dummy_frame.jpg")
            dummy_frame = np.ones((480, 640, 3), dtype=np.uint8) * 200  # Light gray
            cv2.imwrite(dummy_frame_path, dummy_frame)
            frames = ["dummy_frame.jpg"]
        
        print(f"Processing {len(frames)} frames for annotations")
        
        for frame_file in frames:
            frame_path = os.path.join(frames_dir, frame_file)
            frame = cv2.imread(frame_path)
            
            if frame is None:
                print(f"Warning: Could not read frame {frame_path}")
                continue
            
            # Get image dimensions
            height, width = frame.shape[:2]
            
            # Dynamically calculate ROI based on frame size
            roi = get_roi_coordinates(width, height)
            
            # Create annotation file (same name as image but with .txt extension)
            annotation_file = os.path.join(annotations_dir, frame_file.replace('.jpg', '.txt'))
            
            # Convert ROI to YOLO format [class_id, x_center, y_center, width, height]
            # All values normalized to [0, 1]
            x_center = (roi[0] + roi[2] / 2) / width
            y_center = (roi[1] + roi[3] / 2) / height
            roi_width = roi[2] / width
            roi_height = roi[3] / height
            
            # Ensure values are between 0 and 1
            x_center = max(0, min(1, x_center))
            y_center = max(0, min(1, y_center))
            roi_width = max(0, min(1, roi_width))
            roi_height = max(0, min(1, roi_height))
            
            # Write annotation to file
            # Format: class_id x_center y_center width height
            # class_id is 0 for the user's face
            with open(annotation_file, 'w') as f:
                f.write(f"0 {x_center} {y_center} {roi_width} {roi_height}\n")
        
        # After processing, store the frames in MongoDB
        store_frames_in_db(frames_dir, user_id)
        
        print(f"Generated annotations for {len(frames)} frames")
        return True
    
    except Exception as e:
        print(f"Error processing video: {str(e)}")
        return False

def draw_roi_on_frame(frame, roi_coordinates):
    """Draw ROI rectangle on frame for visualization."""
    x, y, w, h = roi_coordinates
    roi_frame = frame.copy()
    cv2.rectangle(roi_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
    return roi_frame
