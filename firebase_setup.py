"""
Firebase Infrastructure Setup for Project GRAFTING VINE
Architectural Choice: Firebase provides serverless, real-time state management
critical for maintaining zero idle cost architecture and learning memory.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore, db
from firebase_admin.exceptions import FirebaseError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirebaseInitializer:
    """Robust Firebase initialization with comprehensive error handling"""
    
    def __init__(self, credential_path: str = "./firebase_credentials.json"):
        self.credential_path = Path(credential_path)
        self.app = None
        self.db = None
        self.realtime_db = None
        
    def validate_credentials_file(self) -> bool:
        """Verify credentials file exists and is valid JSON"""
        if not self.credential_path.exists():
            logger.error(f"Firebase credentials not found at {self.credential_path}")
            return False
            
        try:
            with open(self.credential_path, 'r') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in credentials file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error reading credentials file: {e}")
            return False
    
    def initialize_firebase(self) -> bool:
        """Initialize Firebase Admin SDK with multiple fallback strategies"""
        
        # Strategy 1: Check for credentials file
        if not self.validate_credentials_file():
            logger.warning("Credentials file validation failed. Checking environment variables...")
            
            # Strategy 2: Try environment variable
            cred_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
            if cred_json:
                try:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                    self.app = firebase_admin.initialize_app(cred)
                    logger.info("Firebase initialized from environment variable")
                except Exception as e:
                    logger.error(f"Failed to parse credentials from env var: {e}")
                    return False
            else:
                logger.error("No Firebase credentials found. Please provide credentials.json or set FIREBASE_CREDENTIALS_JSON environment variable")
                return False
        else:
            # Use credentials file
            try:
                cred = credentials.Certificate(str(self.credential_path))
                self.app = firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized from credentials file")
            except FirebaseError as e:
                logger.error(f"Firebase initialization error: {e}")
                return False
        
        # Initialize Firestore and Realtime Database
        try:
            self.db = firestore.client()
            self.realtime_db = db.reference('/')
            
            # Create initial collections structure if they don't exist
            self._initialize_collections()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase services: {e}")
            return False
    
    def _initialize_collections(self) -> None:
        """Create initial Firestore collections structure"""
        collections = [
            'opportunities_stream',
            'execution_history', 
            'skill_registry',
            'economic_state',
            'configuration',
            'gas_price_history'
        ]
        
        for collection in collections:
            # Firestore creates collections automatically on first write
            # We'll just create a dummy document to ensure collection exists
            try:
                doc_ref = self.db.collection(collection).document('_initial')
                if not doc_ref.get().exists:
                    doc_ref.set({
                        'created_at': firestore.SERVER_TIMESTAMP,
                        'initialized': True,
                        'system': 'grafting_vine_v1'
                    })
                    logger.info(f"Created collection: {collection}")
            except Exception as e:
                logger.warning(f"Could not initialize collection {collection}: {e}")
    
    def get_firestore(self):
        """Get Firestore client instance"""
        if not self.db:
            self.initialize_firebase()
        return self.db
    
    def get_realtime_db(self):
        """Get Realtime Database reference"""
        if not self.realtime_db:
            self.initialize_firebase()
        return self.realtime_db

# Singleton instance for global access
firebase_init = FirebaseInitializer()

# Convenience function for direct initialization
def init_firebase() -> bool:
    """Initialize Firebase and return success status"""
    return firebase_init.initialize_firebase()

if __name__ == "__main__":
    # Test initialization
    if init_firebase():
        print("✅ Firebase setup successful")
    else:
        print("❌ Firebase setup failed - manual intervention required")
        print("\nHUMAN REQUEST FORMAT (Firebase Setup):")
        print("""
        Service: Firebase Project Creation
        Why Necessary: Real-time state management and learning memory critical for autonomous evolution
        Free Alternative: None - Firebase is free tier up to usage limits
        Account Details: graftingvine@[your-domain].com / Password: [generate_secure_password_here]
        
        Steps Required:
        1. Go to https://firebase.google.com
        2. Create new project 'grafting-vine'
        3. Enable Firestore Database (start in test mode)
        4. Enable Realtime Database
        5. Generate service account key (Project Settings > Service Accounts > Generate New Private Key)
        6. Save as 'firebase_credentials.json' in project root
        """)