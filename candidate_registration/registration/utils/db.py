import pymongo
import os
from pymongo import MongoClient
import datetime
import json
import base64
from gridfs import GridFS

# MongoDB connection string - replace with your own if using Atlas
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = 'candidate_registration'
COLLECTION_NAME = 'users'
FRAMES_COLLECTION_NAME = 'user_frames'
MODELS_COLLECTION_NAME = 'user_models'

# Initialize MongoDB client
client = None
db = None
users_collection = None
frames_collection = None
models_collection = None
fs = None
mongodb_available = False

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles MongoDB ObjectId"""
    def default(self, obj):
        from bson import ObjectId
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

def init_db():
    """Initialize the MongoDB connection."""
    global client, db, users_collection, frames_collection, models_collection, fs, mongodb_available
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)  # 2 second timeout
        # Test connection
        client.server_info()
        db = client[DB_NAME]
        users_collection = db[COLLECTION_NAME]
        frames_collection = db[FRAMES_COLLECTION_NAME]
        models_collection = db[MODELS_COLLECTION_NAME]
        fs = GridFS(db)
        
        # Create index for faster lookups
        users_collection.create_index("id", unique=True)
        frames_collection.create_index("user_id")
        models_collection.create_index("user_id")
        
        mongodb_available = True
        print("MongoDB connection established successfully")
        return True
    except Exception as e:
        mongodb_available = False
        print(f"MongoDB connection error: {str(e)}")
        print("The application will run without MongoDB. Data will be stored in files only.")
        return False

def is_mongodb_available():
    """Check if MongoDB is available"""
    global mongodb_available
    return mongodb_available

def save_user(user_data):
    """
    Save user data to MongoDB.
    
    Args:
        user_data: Dictionary containing user details
    
    Returns:
        ObjectId of the inserted document or None if an error occurred
    """
    global mongodb_available
    
    if not mongodb_available:
        if users_collection is None:
            init_db()
            
    if not mongodb_available:
        print("MongoDB not available, skipping database save")
        return None
    
    try:
        # Ensure we have a timestamp
        if 'registration_time' not in user_data:
            user_data['registration_time'] = datetime.datetime.now()
            
        # Insert user document
        result = users_collection.insert_one(user_data)
        print(f"User saved to MongoDB with ID: {result.inserted_id}")
        return result.inserted_id
    except Exception as e:
        print(f"Error saving user to MongoDB: {str(e)}")
        return None

def get_user(user_id):
    """
    Retrieve user data from MongoDB by user_id.
    
    Args:
        user_id: Unique user identifier
    
    Returns:
        User document or None if not found
    """
    global mongodb_available
    
    if not mongodb_available:
        return None
    
    if users_collection is None:
        if not init_db():
            return None
    
    try:
        user = users_collection.find_one({"id": user_id})
        return user
    except Exception as e:
        print(f"Error retrieving user from MongoDB: {str(e)}")
        return None

def update_user(user_id, update_data):
    """
    Update user data in MongoDB.
    
    Args:
        user_id: Unique user identifier
        update_data: Dictionary containing fields to update
    
    Returns:
        True if successful, False otherwise
    """
    global mongodb_available
    
    if not mongodb_available:
        return False
    
    if users_collection is None:
        if not init_db():
            return False
    
    try:
        result = users_collection.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        if result.modified_count > 0:
            return True
        else:
            print(f"No matching document found for ID: {user_id}")
            return False
    except Exception as e:
        print(f"Error updating user in MongoDB: {str(e)}")
        return False

def save_frames(user_id, frames_data):
    """
    Save user frames to MongoDB.
    
    Args:
        user_id: Unique user identifier
        frames_data: List of dictionaries containing frame data
                     Each dictionary should have 'frame_id' and 'image_data' (Base64 encoded)
    
    Returns:
        True if successful, False otherwise
    """
    global mongodb_available
    
    if not mongodb_available:
        print("MongoDB not available, skipping frame storage in database")
        return False
    
    if frames_collection is None:
        if not init_db():
            return False
    
    try:
        # Create a bulk operation for better performance
        bulk_operations = []
        
        for frame in frames_data:
            # Create a document for each frame
            frame_doc = {
                "user_id": user_id,
                "frame_id": frame["frame_id"],
                "image_data": frame["image_data"],
                "created_at": datetime.datetime.now()
            }
            
            # Add to bulk operations
            bulk_operations.append(pymongo.InsertOne(frame_doc))
        
        # Execute bulk operation if we have frames
        if bulk_operations:
            result = frames_collection.bulk_write(bulk_operations)
            print(f"Saved {result.inserted_count} frames to MongoDB for user {user_id}")
            
            # Update the user document to indicate frames are stored in DB
            users_collection.update_one(
                {"id": user_id},
                {"$set": {
                    "frames_stored_in_db": True,
                    "frames_count_in_db": len(frames_data),
                    "frames_stored_at": datetime.datetime.now()
                }}
            )
            
            return True
        else:
            print("No frames to save")
            return False
    except Exception as e:
        print(f"Error saving frames to MongoDB: {str(e)}")
        return False

def get_frames(user_id):
    """
    Retrieve user frames from MongoDB.
    
    Args:
        user_id: Unique user identifier
    
    Returns:
        List of frame documents or None if not found
    """
    global mongodb_available
    
    if not mongodb_available:
        return None
    
    if frames_collection is None:
        if not init_db():
            return None
    
    try:
        frames = list(frames_collection.find({"user_id": user_id}))
        return frames
    except Exception as e:
        print(f"Error retrieving frames from MongoDB: {str(e)}")
        return None

def save_model(user_id, model_file_path, metadata_file_path=None, metadata=None):
    """
    Save YOLO model to MongoDB using GridFS.
    
    Args:
        user_id: Unique user identifier
        model_file_path: Path to the trained model file
        metadata_file_path: Path to metadata file (optional)
        metadata: Dictionary with additional metadata (optional)
    
    Returns:
        GridFS file ID if successful, None otherwise
    """
    global mongodb_available
    
    if not mongodb_available:
        print("MongoDB not available, skipping model storage in database")
        return None
    
    if fs is None:
        if not init_db():
            return None
    
    try:
        # Read model file
        with open(model_file_path, 'rb') as model_file:
            model_data = model_file.read()
        
        # Prepare metadata
        model_metadata = {
            "user_id": user_id,
            "filename": os.path.basename(model_file_path),
            "created_at": datetime.datetime.now()
        }
        
        # Add additional metadata from file if provided
        if metadata_file_path and os.path.exists(metadata_file_path):
            try:
                with open(metadata_file_path, 'r') as meta_file:
                    file_metadata = meta_file.read()
                model_metadata["file_metadata"] = file_metadata
            except Exception as e:
                print(f"Error reading metadata file: {str(e)}")
        
        # Add additional metadata if provided
        if metadata and isinstance(metadata, dict):
            model_metadata.update(metadata)
        
        # Store model in GridFS
        file_id = fs.put(
            model_data, 
            filename=os.path.basename(model_file_path),
            metadata=model_metadata
        )
        
        # Store reference to model in models collection
        model_doc = {
            "user_id": user_id,
            "gridfs_id": file_id,
            "filename": os.path.basename(model_file_path),
            "created_at": datetime.datetime.now(),
            "metadata": model_metadata
        }
        models_collection.insert_one(model_doc)
        
        # Update user document to reference the model
        users_collection.update_one(
            {"id": user_id},
            {"$set": {
                "model_stored_in_db": True,
                "model_db_id": str(file_id),
                "model_stored_at": datetime.datetime.now()
            }}
        )
        
        print(f"Stored model for user {user_id} in MongoDB with ID {file_id}")
        return file_id
    except Exception as e:
        print(f"Error saving model to MongoDB: {str(e)}")
        return None

def get_model(user_id):
    """
    Retrieve user model from MongoDB GridFS.
    
    Args:
        user_id: Unique user identifier
    
    Returns:
        Tuple of (model_data, metadata) or (None, None) if not found
    """
    global mongodb_available
    
    if not mongodb_available:
        return None, None
    
    if fs is None or models_collection is None:
        if not init_db():
            return None, None
    
    try:
        # Find model document
        model_doc = models_collection.find_one({"user_id": user_id})
        
        if not model_doc:
            print(f"No model found for user {user_id}")
            return None, None
        
        # Get file from GridFS
        file_id = model_doc.get("gridfs_id")
        if not file_id:
            print(f"Invalid model document for user {user_id}, no GridFS ID")
            return None, None
        
        # Retrieve the file
        grid_out = fs.get(file_id)
        model_data = grid_out.read()
        
        return model_data, model_doc.get("metadata")
    except Exception as e:
        print(f"Error retrieving model from MongoDB: {str(e)}")
        return None, None

def save_model_to_file(user_id, output_path):
    """
    Retrieve user model from MongoDB and save to file.
    
    Args:
        user_id: Unique user identifier
        output_path: Path to save the model file
    
    Returns:
        True if successful, False otherwise
    """
    model_data, metadata = get_model(user_id)
    
    if not model_data:
        return False
    
    try:
        with open(output_path, 'wb') as f:
            f.write(model_data)
        
        print(f"Saved model for user {user_id} to {output_path}")
        return True
    except Exception as e:
        print(f"Error saving model to file: {str(e)}")
        return False
