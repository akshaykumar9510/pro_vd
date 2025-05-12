import cv2
import face_recognition
import numpy as np
import time
import os
import base64
import winsound
import pytesseract
import difflib
import re
from pymongo import MongoClient
from ultralytics import YOLO
import torch
from torch.nn.modules.pooling import MaxPool2d
from torch.nn.modules.upsampling import Upsample

# Import the required ultralytics classes
try:
    from ultralytics.nn.modules import Concat, Detect
    has_ultralytics_modules = True
except ImportError:
    has_ultralytics_modules = False
    print("Warning: Could not import required classes from ultralytics.nn.modules")

# Add required classes to safe globals to fix model loading issues
try:
    from torch.serialization import add_safe_globals
    classes_to_add = [MaxPool2d, Upsample]
    
    # Add ultralytics specific classes if available
    if has_ultralytics_modules:
        classes_to_add.extend([Concat, Detect])
        
    add_safe_globals(classes_to_add)
    print(f"Added {len(classes_to_add)} classes to safe globals")
except ImportError:
    print("Warning: Could not add classes to safe globals, using older PyTorch version")

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class ExamMonitor:
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['candidate_registration']
        self.users_collection = self.db['users']
        self.frames_collection = self.db['user_frames']
        self.alert_dir = "alerts"
        self.log_dir = "logs"
        os.makedirs(self.alert_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.model = YOLO('yolov8s.pt')
        self.class_names = self.model.names

        self.user_face_encodings = {}
        self.user_info_map = {}

        self.cooldown_period = 30
        self.last_alert_time = {"impersonation": 0, "multiple_people": 0, "mobile_phone": 0}

        self.load_registered_users()

    def load_registered_users(self):
        registered_users = list(self.users_collection.find({"registration_status": "completed_successfully"}))
        for user in registered_users:
            user_id = user['id']
            encodings = self.get_encodings_from_db(user_id)
            if encodings:
                mean_encoding = np.mean(encodings, axis=0)
                self.user_face_encodings[user_id] = mean_encoding
                self.user_info_map[user_id] = user

    def get_encodings_from_db(self, user_id):
        frames_cursor = self.frames_collection.find({"user_id": user_id})
        encodings = []
        for frame in frames_cursor:
            try:
                image_data = base64.b64decode(frame['image_data'])
                img = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
                rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_img)
                if face_locations:
                    encoding = face_recognition.face_encodings(rgb_img, face_locations)[0]
                    encodings.append(encoding)
            except Exception:
                pass
        return encodings

    def extract_id_number(self, text):
        patterns = [r'\b\d{6,12}\b', r'\b[A-Z]{1,2}[-\s]?\d{5,10}\b', r'\b[A-Z]{2,3}\d{5,8}\b', r'\bID[-\s]?\d{5,10}\b']
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def verify_id_against_user(self, id_number, user):
        if 'id_number' in user and user['id_number'] == id_number:
            return True, 100.0
        for field in ['id', 'email', 'phone']:
            if field in user and user[field]:
                similarity = difflib.SequenceMatcher(None, str(user[field]), id_number).ratio() * 100
                if similarity > 70:
                    return True, similarity
        return False, 0.0

    def analyze_frame(self, frame):
        results = self.model(frame)
        detections = {"person": 0, "cell phone": 0}
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                class_name = self.class_names[cls]
                if class_name in detections:
                    detections[class_name] += 1
        return detections

    def match_face(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for i, encoding in enumerate(face_encodings):
            best_match_id, best_distance = None, float("inf")
            for user_id, stored_encoding in self.user_face_encodings.items():
                distance = face_recognition.face_distance([stored_encoding], encoding)[0]
                matches = face_recognition.compare_faces([stored_encoding], encoding, tolerance=0.55)
                if matches[0] and distance < best_distance:
                    best_distance, best_match_id = distance, user_id

            if best_match_id:
                return self.user_info_map[best_match_id], (1 - best_distance) * 100
        return None, 0

    def monitor_single_frame(self, base64_image):
        try:
            image_data = base64.b64decode(base64_image.split(',')[1])
            frame = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            detections = self.analyze_frame(frame)
            identified_user, confidence = self.match_face(frame)
            return {
                "status": "success",
                "detections": detections,
                "user": identified_user['name'] if identified_user else None,
                "user_id": identified_user['id'] if identified_user else None,
                "confidence": round(confidence, 2)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def log_tab_switch(self, user_id, session_id, event_data):
        """
        Log tab switching events and trigger alerts
        
        Args:
            user_id: ID of the user
            session_id: Current session ID
            event_data: Dict containing visibility state change details
        """
        try:
            timestamp = time.time()
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            tab_switch_log = {
                "user_id": user_id,
                "session_id": session_id,
                "event_type": "tab_switch",
                "visible": event_data.get('visible', False),
                "timestamp": timestamp,
                "formatted_time": formatted_time
            }
            
            # Log to MongoDB
            self.db['monitoring_logs'].insert_one(tab_switch_log)
            
            # Log to file system
            log_file = os.path.join(self.log_dir, f"tab_switch_{user_id}_{session_id}.log")
            with open(log_file, 'a') as f:
                f.write(f"{formatted_time}: Tab {'visible' if event_data.get('visible') else 'hidden'}\n")
            
            # If tab was hidden/switched, create an alert
            if not event_data.get('visible', True):
                alert = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "alert_type": "tab_switch",
                    "severity": "high",
                    "description": "User switched to another tab or application",
                    "timestamp": timestamp,
                    "formatted_time": formatted_time
                }
                self.db['alerts'].insert_one(alert)
                
                # Save a screenshot if provided
                if 'screenshot' in event_data:
                    alert_filename = f"tab_switch_{user_id}_{session_id}_{int(timestamp)}.jpg"
                    alert_path = os.path.join(self.alert_dir, alert_filename)
                    with open(alert_path, 'wb') as f:
                        f.write(base64.b64decode(event_data['screenshot']))
            
            return {"status": "success", "logged": True}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def log_mouse_movement(self, user_id, session_id, movement_data):
        """
        Log mouse movement data for analysis
        
        Args:
            user_id: ID of the user
            session_id: Current session ID
            movement_data: Dict containing x,y coordinates and timestamp
        """
        try:
            # Only log every 5th mouse movement to reduce data volume
            if not hasattr(self, '_mouse_counter'):
                self._mouse_counter = 0
            
            self._mouse_counter += 1
            if self._mouse_counter % 5 != 0:
                return {"status": "success", "logged": False, "reason": "sampling"}
            
            timestamp = time.time()
            movement_log = {
                "user_id": user_id,
                "session_id": session_id,
                "event_type": "mouse_movement",
                "x": movement_data.get('x', 0),
                "y": movement_data.get('y', 0),
                "timestamp": timestamp
            }
            
            # Log to MongoDB (limited entries)
            self.db['mouse_movements'].insert_one(movement_log)
            
            # Check for suspicious patterns (rapid movement to corners)
            x, y = movement_data.get('x', 0), movement_data.get('y', 0)
            if (x < 10 or x > movement_data.get('screenWidth', 1000) - 10) and \
               (y < 10 or y > movement_data.get('screenHeight', 700) - 10):
                
                # Potential attempt to access other applications via screen corners
                alert = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "alert_type": "suspicious_mouse",
                    "severity": "medium",
                    "description": "Mouse moved to screen corner",
                    "coordinates": {"x": x, "y": y},
                    "timestamp": timestamp
                }
                self.db['alerts'].insert_one(alert)
            
            return {"status": "success", "logged": True}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def detect_screen_capture(self, user_id, session_id, event_data):
        """
        Detect and log screen capture attempts (print screen, screen recording)
        
        Args:
            user_id: ID of the user
            session_id: Current session ID
            event_data: Dict containing event details
        """
        try:
            timestamp = time.time()
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            
            capture_log = {
                "user_id": user_id,
                "session_id": session_id,
                "event_type": "screen_capture",
                "capture_type": event_data.get('type', 'unknown'),
                "timestamp": timestamp,
                "formatted_time": formatted_time
            }
            
            # Log to MongoDB
            self.db['monitoring_logs'].insert_one(capture_log)
            
            # Create an alert
            alert = {
                "user_id": user_id,
                "session_id": session_id,
                "alert_type": "screen_capture",
                "severity": "critical",
                "description": f"Screen capture detected: {event_data.get('type', 'unknown')}",
                "timestamp": timestamp,
                "formatted_time": formatted_time
            }
            self.db['alerts'].insert_one(alert)
            
            # Log to file system
            log_file = os.path.join(self.log_dir, f"security_{user_id}_{session_id}.log")
            with open(log_file, 'a') as f:
                f.write(f"{formatted_time}: Screen capture detected: {event_data.get('type', 'unknown')}\n")
            
            return {"status": "success", "logged": True, "alert": True}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def log_copy_paste(self, user_id, session_id, event_data):
        """
        Log copy-paste actions and prevent them if configured to do so
        
        Args:
            user_id: ID of the user
            session_id: Current session ID
            event_data: Dict containing copy/paste details
        """
        try:
            timestamp = time.time()
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            
            action_type = event_data.get('type', 'unknown')  # 'copy', 'paste', 'cut'
            
            # Create log entry
            log_entry = {
                "user_id": user_id,
                "session_id": session_id,
                "event_type": "clipboard",
                "action": action_type,
                "content_length": len(event_data.get('content', '')),
                "timestamp": timestamp,
                "formatted_time": formatted_time
            }
            
            # Store full content only if it's short (for privacy and storage reasons)
            if len(event_data.get('content', '')) < 200:
                log_entry["content"] = event_data.get('content', '')
            
            # Log to MongoDB
            self.db['monitoring_logs'].insert_one(log_entry)
            
            # Create alert for paste actions (as these might be bringing external content in)
            if action_type == 'paste':
                alert = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "alert_type": "clipboard_paste",
                    "severity": "high",
                    "description": "User attempted to paste content",
                    "content_length": len(event_data.get('content', '')),
                    "timestamp": timestamp
                }
                self.db['alerts'].insert_one(alert)
            
            # Return whether this action should be blocked
            # Adjust the blocked actions based on your requirements
            blocked = action_type in ['copy', 'paste', 'cut']
            
            return {
                "status": "success", 
                "logged": True,
                "blocked": blocked,
                "message": "Copy-paste actions are disabled during the exam" if blocked else None
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_alert_snapshot(self, user_id, alert_type, frame, detection_info=None):
        """
        Save a snapshot of the detected violation as proof.

        Args:
            user_id: ID of the user
            alert_type: Type of alert (e.g., 'mobile_phone', 'multiple_people')
            frame: The image frame containing the violation
            detection_info: Additional information about the detection

        Returns:
            str: Path to the saved snapshot file
        """
        try:
            # Create user directory if it doesn't exist
            user_dir = os.path.join(self.alert_dir, user_id)
            os.makedirs(user_dir, exist_ok=True)

            timestamp = int(time.time())
            alert_filename = f"{alert_type}_{timestamp}.jpg"
            alert_path = os.path.join(user_dir, alert_filename)

            # Add detection boxes and annotations to the frame before saving
            if detection_info and 'boxes' in detection_info:
                for box in detection_info['boxes']:
                    x1, y1, x2, y2 = box[:4]
                    label = box[4] if len(box) > 4 else alert_type
                    confidence = box[5] if len(box) > 5 else None

                    # Draw bounding box on frame
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)

                    # Draw label with confidence if available
                    label_text = f"{label}"
                    if confidence is not None:
                        label_text += f": {confidence:.2f}"

                    cv2.putText(frame, label_text, (int(x1), int(y1) - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Add timestamp to the frame
            formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            cv2.putText(frame, formatted_time, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Save the image
            cv2.imwrite(alert_path, frame)

            # Log the alert in MongoDB
            alert_data = {
                "user_id": user_id,
                "alert_type": alert_type,
                "snapshot_path": alert_path,
                "timestamp": timestamp,
                "formatted_time": formatted_time,
                "additional_info": detection_info
            }
            self.db['violation_snapshots'].insert_one(alert_data)

            return alert_path

        except Exception as e:
            print(f"Error saving alert snapshot: {str(e)}")
            return None
