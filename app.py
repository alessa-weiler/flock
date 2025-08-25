import os
import warnings
# Fix for macOS TensorFlow threading issues
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['CUDA_VISIBLE_DEVICES'] = ''


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import secrets
import threading
import time
import math
import requests
import numpy as np
import json
import os
import sqlite3
import hashlib
import secrets
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote


# Suppress protobuf warnings
warnings.filterwarnings("ignore", category=UserWarning)

from functools import wraps
try:
    import tensorflow as tf
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    HAS_ML_LIBRARIES = True
except ImportError:
    HAS_ML_LIBRARIES = False
    print("Warning: TensorFlow/sklearn not installed. Using fallback methods.")


# Flask and related imports
from flask import (
    Flask, render_template_string, request, redirect, session, 
    jsonify, flash, url_for, send_from_directory, abort
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# External APIs
from openai import OpenAI
from dotenv import load_dotenv

from enhanced_matching_system import (
    EnhancedMatchingSystem, 
    InteractionTracker, 
    integrate_enhanced_matching
)

# Load environment variables
load_dotenv()

# ============================================================================
# APP CONFIGURATION
# ============================================================================

app = Flask(__name__)
app.secret_key = 'pont-matching-secret-key-change-in-production'
CORS(app, origins="*", supports_credentials=True)

# Configuration
API_KEY = os.environ.get('OPENAI_API_KEY')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_FROM = os.environ.get('EMAIL_FROM', EMAIL_USER)

# Global processing status storage
processing_status = {}

# ============================================================================
# AUTHENTICATION DECORATOR
# ============================================================================

def login_required(f):
    """Decorator to require user authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# USER AUTHENTICATION SYSTEM
# ============================================================================

class UserAuthSystem:
    """Handles user authentication and account management"""
    
    def __init__(self):
        self.init_user_database()
    
    def init_user_database(self):
        """Initialize user accounts database with all required tables"""
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                profile_completed BOOLEAN DEFAULT 0,
                profile_date TIMESTAMP
            )
        ''')
        # Add new columns for enhanced profile features
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN bio TEXT')
            print("✓ Added bio column to users table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Bio column addition error: {e}")
        
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN profile_photo_url TEXT')
            print("✓ Added profile_photo_url column to users table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                print(f"Profile photo URL column addition error: {e}")
        
        # Create profile privacy settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profile_privacy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                share_personality_scores BOOLEAN DEFAULT 1,
                share_values_scores BOOLEAN DEFAULT 1,
                share_lifestyle_info BOOLEAN DEFAULT 1,
                share_social_preferences BOOLEAN DEFAULT 1,
                share_contact_info BOOLEAN DEFAULT 1,
                share_detailed_analysis BOOLEAN DEFAULT 1,
                share_bio BOOLEAN DEFAULT 1,
                share_photo BOOLEAN DEFAULT 1,
                share_exact_location BOOLEAN DEFAULT 0,
                share_age BOOLEAN DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
        ''')
    
        # User profiles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                profile_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # User matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                matched_user_id INTEGER NOT NULL,
                matched_user_name TEXT NOT NULL,
                matched_user_email TEXT,
                compatibility_score INTEGER,
                personality_score INTEGER,
                values_score INTEGER,
                lifestyle_score INTEGER,
                emotional_score INTEGER,
                social_score INTEGER,
                communication_score INTEGER,
                location_score INTEGER,
                overall_score INTEGER,
                compatibility_analysis TEXT,
                distance_miles REAL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (matched_user_id) REFERENCES users (id)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE user_matches ADD COLUMN matched_user_phone TEXT')
            print("✓ Added matched_user_phone column to user_matches table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("✓ matched_user_phone column already exists")
            else:
                raise e
            
        # Blocked users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                blocked_email TEXT,
                blocked_phone TEXT,
                blocked_name TEXT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contact_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL,
                requested_id INTEGER NOT NULL,
                requester_name TEXT NOT NULL,
                requested_name TEXT NOT NULL,
                requester_phone TEXT NOT NULL,
                requested_phone TEXT NOT NULL,
                message TEXT,
                status TEXT DEFAULT 'pending', -- pending, accepted, denied
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                responded_at TIMESTAMP,
                FOREIGN KEY (requester_id) REFERENCES users (id),
                FOREIGN KEY (requested_id) REFERENCES users (id),
                UNIQUE(requester_id, requested_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()
        conn.close()
        print("✓ User authentication database initialized")
    
    def create_user(self, email: str, password: str, first_name: str = None, 
                   last_name: str = None, phone: str = None) -> Dict[str, Any]:
        """Create new user account"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                conn.close()
                return {'success': False, 'error': 'Email already registered'}
            
            # Create password hash and insert user
            password_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (email, password_hash, first_name, last_name, phone)
                VALUES (?, ?, ?, ?, ?)
            ''', (email, password_hash, first_name, last_name, phone))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return {'success': True, 'user_id': user_id}
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return {'success': False, 'error': 'Account creation failed'}
    
    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user login"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, password_hash, first_name, last_name, profile_completed
                FROM users WHERE email = ? AND is_active = 1
            ''', (email,))
            
            user = cursor.fetchone()
            
            if user and check_password_hash(user[1], password):
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
                ''', (user[0],))
                conn.commit()
                conn.close()
                
                return {
                    'success': True,
                    'user_id': user[0],
                    'first_name': user[2],
                    'last_name': user[3],
                    'profile_completed': bool(user[4])
                }
            
            conn.close()
            return {'success': False, 'error': 'Invalid email or password'}
            
        except Exception as e:
            print(f"Error authenticating user: {e}")
            return {'success': False, 'error': 'Authentication failed'}
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT email, first_name, last_name, phone, profile_completed, profile_date
                FROM users WHERE id = ?
            ''', (user_id,))
            
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return {
                    'email': user[0],
                    'first_name': user[1],
                    'last_name': user[2],
                    'phone': user[3],
                    'profile_completed': bool(user[4]),
                    'profile_date': user[5]
                }
            return None
            
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None
    def get_user_by_email(self, email: str):
        """Get user by email"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, email, first_name, last_name 
                FROM users 
                WHERE LOWER(email) = LOWER(?)
            ''', (email,))
            
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return {
                    'id': user[0],
                    'email': user[1],
                    'first_name': user[2],
                    'last_name': user[3]
                }
            return None
            
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None

    def save_user_profile(self, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """Save user profile data"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Save/update profile
            cursor.execute('''
                INSERT OR REPLACE INTO user_profiles (user_id, profile_data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, json.dumps(profile_data)))
            
            # Update user record
            cursor.execute('''
                UPDATE users 
                SET profile_completed = 1, profile_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error saving profile: {e}")
            return False
    
    def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile data"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT profile_data FROM user_profiles WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return json.loads(result[0])
            return None
            
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
    
    def save_user_matches(self, user_id: int, matches: List[Dict[str, Any]]) -> bool:
        """Save user matches to database"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Clear existing matches
            cursor.execute('DELETE FROM user_matches WHERE user_id = ?', (user_id,))
            
            # Save new matches
            for match in matches:
                cursor.execute('''
                    INSERT INTO user_matches 
                    (user_id, matched_user_id, matched_user_name, matched_user_email, matched_user_phone,
                    compatibility_score, personality_score, values_score, lifestyle_score,
                    emotional_score, social_score, communication_score, location_score, 
                    overall_score, compatibility_analysis, distance_miles)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    match['matched_user_id'],
                    match['matched_user_name'],
                    match.get('matched_user_email', ''),
                    match.get('matched_user_phone', ''),
                    match['compatibility_score'],
                    match['personality_score'],
                    match.get('values_score', 75),
                    match.get('lifestyle_score', 75),
                    match.get('emotional_score', 75),
                    match.get('social_score', 75),
                    match.get('communication_score', 75),
                    match['location_score'],
                    match['overall_score'],
                    match['compatibility_analysis'],
                    match.get('distance_miles', 0)
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error saving matches: {e}")
            return False
    
    def get_user_matches(self, user_id: int) -> List[Dict[str, Any]]:
        """Get saved user matches with follow-up response data"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    um.matched_user_id, um.matched_user_name, um.matched_user_email, um.matched_user_phone,
                    um.compatibility_score, um.personality_score, um.values_score, um.lifestyle_score,
                    um.emotional_score, um.social_score, um.communication_score, um.location_score,
                    um.overall_score, um.compatibility_analysis, um.distance_miles,
                    um.user_would_meet_again, um.match_would_meet_again
                FROM user_matches um
                WHERE um.user_id = ? AND um.is_active = 1
                ORDER BY um.overall_score DESC
            ''', (user_id,))
            
            matches = cursor.fetchall()
            conn.close()
            
            results = []
            for match in matches:
                results.append({
                    'matched_user_id': match[0],
                    'matched_user_name': match[1],
                    'matched_user_email': match[2],
                    'matched_user_phone': match[3],
                    'compatibility_score': match[4],
                    'personality_score': match[5],
                    'values_score': match[6] or 75,
                    'lifestyle_score': match[7] or 75,
                    'emotional_score': match[8] or 75,
                    'social_score': match[9] or 75,
                    'communication_score': match[10] or 75,
                    'location_score': match[11],
                    'overall_score': match[12],
                    'compatibility_analysis': match[13],
                    'distance_miles': match[14],
                    'user_would_meet_again': match[15],  # Your response
                    'match_would_meet_again': match[16]   # Their response
                })
            
            return results
            
        except Exception as e:
            print(f"Error getting matches: {e}")
            return []
    
    def get_all_users_for_matching(self, exclude_user_id: int) -> List[Dict[str, Any]]:
        """Get all users with completed profiles for matching"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.email, u.first_name, u.last_name, u.phone, up.profile_data
                FROM users u
                JOIN user_profiles up ON u.id = up.user_id
                WHERE u.id != ? AND u.is_active = 1 AND u.profile_completed = 1
            ''', (exclude_user_id,))
            
            users = cursor.fetchall()
            conn.close()
            
            results = []
            for user in users:
                try:
                    profile_data = json.loads(user[5]) if user[5] else {}
                    results.append({
                        'user_id': user[0],
                        'email': user[1],
                        'first_name': user[2],
                        'last_name': user[3],
                        'phone': user[4],
                        'profile': profile_data
                    })
                except json.JSONDecodeError:
                    continue
            
            return results
            
        except Exception as e:
            print(f"Error getting users for matching: {e}")
            return []
    
    def get_random_users(self, limit=15, exclude_user_id=None):
        """Get random users for visualization"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            if exclude_user_id:
                cursor.execute('''
                    SELECT id, first_name, last_name, email 
                    FROM users 
                    WHERE id != ? AND is_active = 1
                    ORDER BY RANDOM() 
                    LIMIT ?
                ''', (exclude_user_id, limit))
            else:
                cursor.execute('''
                    SELECT id, first_name, last_name, email 
                    FROM users 
                    WHERE is_active = 1
                    ORDER BY RANDOM() 
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            users = []
            
            for row in rows:
                users.append({
                    'user_id': row[0],
                    'first_name': row[1] or 'Anonymous',
                    'last_name': row[2] or '',
                    'email': row[3]
                })
            
            conn.close()
            return users
            
        except Exception as e:
            print(f"Error getting random users: {e}")
            return []

    # Blocking functionality
    def add_blocked_user(self, user_id: int, blocked_email: str = None, 
                        blocked_phone: str = None, blocked_name: str = None, 
                        reason: str = None) -> bool:
        """Add a user to the block list"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO blocked_users (user_id, blocked_email, blocked_phone, blocked_name, reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, blocked_email, blocked_phone, blocked_name, reason))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error adding blocked user: {e}")
            return False
    
    def get_blocked_users(self, user_id: int) -> Dict[str, List[str]]:
        """Get list of blocked users for a user"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT blocked_email, blocked_phone, blocked_name
                FROM blocked_users WHERE user_id = ?
            ''', (user_id,))
            
            blocked = cursor.fetchall()
            conn.close()
            
            return {
                'emails': [b[0] for b in blocked if b[0]],
                'phones': [b[1] for b in blocked if b[1]],
                'names': [b[2] for b in blocked if b[2]]
            }
            
        except Exception as e:
            print(f"Error getting blocked users: {e}")
            return {'emails': [], 'phones': [], 'names': []}
    
    def clear_blocked_users(self, user_id: int) -> bool:
        """Clear all blocked users for a user"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error clearing blocked users: {e}")
            return False
    
    def send_contact_request(self, requester_id: int, requested_id: int, message: str = '') -> Dict[str, Any]:
        """Send a contact request"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Get requester info
            cursor.execute('SELECT first_name, last_name, phone FROM users WHERE id = ?', (requester_id,))
            requester = cursor.fetchone()
            
            # Get requested user info
            cursor.execute('SELECT first_name, last_name, phone FROM users WHERE id = ?', (requested_id,))
            requested = cursor.fetchone()
            
            if not requester or not requested:
                conn.close()
                return {'success': False, 'error': 'User not found'}
            
            # Check if request already exists
            cursor.execute('SELECT id, status FROM contact_requests WHERE requester_id = ? AND requested_id = ?', (requester_id, requested_id))
            existing = cursor.fetchone()
            
            if existing:
                conn.close()
                if existing[1] == 'pending':
                    return {'success': False, 'error': 'Request already pending'}
                else:
                    return {'success': False, 'error': f'Previous request was {existing[1]}'}
            
            # Create contact request
            cursor.execute('''
                INSERT INTO contact_requests 
                (requester_id, requested_id, requester_name, requested_name, 
                requester_phone, requested_phone, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                requester_id, requested_id,
                f"{requester[0]} {requester[1]}",
                f"{requested[0]} {requested[1]}",
                requester[2], requested[2], message
            ))
            
            conn.commit()
            conn.close()
            return {'success': True, 'message': 'Contact request sent successfully'}
            
        except Exception as e:
            print(f"Error sending contact request: {e}")
            return {'success': False, 'error': 'Failed to send request'}
    
    def get_contact_requests(self, user_id: int, request_type: str = 'received') -> List[Dict[str, Any]]:
            """Get contact requests for a user (received or sent)"""
            try:
                conn = sqlite3.connect('users.db')
                cursor = conn.cursor()
                
                if request_type == 'received':
                    cursor.execute('''
                        SELECT id, requester_id, requester_name, requester_phone, message, status, created_at
                        FROM contact_requests WHERE requested_id = ? ORDER BY created_at DESC
                    ''', (user_id,))
                else:  # sent
                    cursor.execute('''
                        SELECT id, requested_id, requested_name, requested_phone, message, status, created_at
                        FROM contact_requests WHERE requester_id = ? ORDER BY created_at DESC
                    ''', (user_id,))
                
                requests = cursor.fetchall()
                conn.close()
                
                results = []
                for req in requests:
                    results.append({
                        'id': req[0], 'other_user_id': req[1], 'other_user_name': req[2],
                        'other_user_phone': req[3], 'message': req[4], 'status': req[5], 'created_at': req[6]
                    })
                return results
                
            except Exception as e:
                print(f"Error getting contact requests: {e}")
                return []
    
    def respond_to_contact_request(self, request_id: int, user_id: int, response: str) -> Dict[str, Any]:
            """Respond to a contact request (accept/deny)"""
            try:
                conn = sqlite3.connect('users.db')
                cursor = conn.cursor()
                
                # Verify this request belongs to the user
                cursor.execute('SELECT requester_id, requested_id, status FROM contact_requests WHERE id = ?', (request_id,))
                result = cursor.fetchone()
                
                if not result or result[1] != user_id:
                    conn.close()
                    return {'success': False, 'error': 'Request not found or unauthorized'}
                
                if result[2] != 'pending':
                    conn.close()
                    return {'success': False, 'error': 'Request already responded to'}
                
                requester_id = result[0]
                requested_id = result[1]
                
                # Update request status
                cursor.execute('''
                    UPDATE contact_requests SET status = ?, responded_at = CURRENT_TIMESTAMP WHERE id = ?
                ''', (response, request_id))
                
                conn.commit()
                conn.close()
                
                # If accepted, schedule follow-up email
                if response == 'accepted':
                    email_followup.schedule_followup_email(request_id, requester_id, requested_id)
                    print(f"✓ Follow-up email scheduled for contact request {request_id}")
                
                return {'success': True, 'message': f'Request {response} successfully'}
                
            except Exception as e:
                print(f"Error responding to contact request: {e}")
                return {'success': False, 'error': 'Failed to respond to request'}


    def get_request_status(self, requester_id: int, requested_id: int) -> Optional[str]:
        """Get status of contact request between two users"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM contact_requests WHERE requester_id = ? AND requested_id = ?', (requester_id, requested_id))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            return None

    def create_password_reset_token(self, email: str) -> Dict[str, Any]:
        """Create a password reset token for a user"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute('SELECT id, first_name FROM users WHERE email = ? AND is_active = 1', (email,))
            user = cursor.fetchone()
            
            if not user:
                conn.close()
                # Don't reveal if email exists or not for security
                return {'success': True, 'message': 'If this email exists, a reset link has been sent'}
            
            user_id, first_name = user
            
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=1)  # Token expires in 1 hour
            
            # Store token in database
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (?, ?, ?)
            ''', (user_id, token, expires_at))
            
            conn.commit()
            conn.close()
            
            # Send reset email
            self.send_password_reset_email(email, first_name, token)
            
            return {'success': True, 'message': 'If this email exists, a reset link has been sent'}
            
        except Exception as e:
            print(f"Error creating password reset token: {e}")
            return {'success': False, 'error': 'Failed to process reset request'}

    def send_password_reset_email(self, to_email: str, first_name: str, token: str):
        """Send password reset email"""
        try:
            base_url = os.environ.get('BASE_URL', 'http://localhost:8080')
            reset_url = f"{base_url}/reset-password/{token}"
            
            subject = "Reset Your Connect Password"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Inter', sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #167a60, #c6e19b); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .button {{ display: inline-block; padding: 15px 30px; margin: 10px; text-decoration: none; border-radius: 6px; font-weight: bold; text-align: center; background: #167a60; color: white; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }}
                    .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 6px; margin: 20px 0; color: #856404; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 24px;">Password Reset</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">Reset your Connect password</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {first_name}!</h2>
                        
                        <p>We received a request to reset your password for your Connect account. If you didn't make this request, you can safely ignore this email.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_url}" class="button">Reset My Password</a>
                        </div>
                        
                        <div class="warning">
                            <strong>Security Note:</strong> This link will expire in 1 hour and can only be used once. If you need a new reset link, please request another one from the login page.
                        </div>
                        
                        <p>If the button doesn't work, copy and paste this link into your browser:</p>
                        <p style="word-break: break-all; font-family: monospace; background: #f8f9fa; padding: 10px; border-radius: 4px;">{reset_url}</p>
                        
                        <p>Best regards,<br>The Connect Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>This email was sent because a password reset was requested for your Connect account.</p>
                        <p>If you have any questions, please contact us at support@connect.com</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send the email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = to_email
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
                
            print(f"✓ Password reset email sent to {to_email}")
            
        except Exception as e:
            print(f"Error sending password reset email to {to_email}: {e}")

    def validate_reset_token(self, token: str) -> Dict[str, Any]:
        """Validate a password reset token"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT prt.user_id, prt.expires_at, prt.used, u.email, u.first_name
                FROM password_reset_tokens prt
                JOIN users u ON prt.user_id = u.id
                WHERE prt.token = ?
            ''', (token,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return {'valid': False, 'error': 'Invalid reset token'}
            
            user_id, expires_at, used, email, first_name = result
            
            # Check if token is used
            if used:
                return {'valid': False, 'error': 'This reset link has already been used'}
            
            # Check if token is expired
            expires_datetime = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expires_datetime:
                return {'valid': False, 'error': 'This reset link has expired. Please request a new one.'}
            
            return {
                'valid': True,
                'user_id': user_id,
                'email': email,
                'first_name': first_name
            }
            
        except Exception as e:
            print(f"Error validating reset token: {e}")
            return {'valid': False, 'error': 'Invalid reset token'}

    def reset_password_with_token(self, token: str, new_password: str) -> Dict[str, Any]:
        """Reset password using a valid token"""
        try:
            # First validate the token
            validation = self.validate_reset_token(token)
            if not validation['valid']:
                return {'success': False, 'error': validation['error']}
            
            user_id = validation['user_id']
            
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Update password
            password_hash = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
            
            # Mark token as used
            cursor.execute('UPDATE password_reset_tokens SET used = 1 WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': 'Password reset successfully'}
            
        except Exception as e:
            print(f"Error resetting password: {e}")
            return {'success': False, 'error': 'Failed to reset password'}

    def cleanup_expired_tokens(self):
        """Clean up expired password reset tokens (call this periodically)"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM password_reset_tokens WHERE expires_at < ?', (datetime.now(),))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                print(f"✓ Cleaned up {deleted_count} expired password reset tokens")
            
        except Exception as e:
            print(f"Error cleaning up expired tokens: {e}")


# ============================================================================
# EMAIL FOLLOW-UP SYSTEM
# ============================================================================

class EmailFollowupSystem:
    """Handles automated follow-up emails after successful connections"""
    
    def __init__(self, user_auth_system):
        self.user_auth = user_auth_system
        self.init_followup_database()
        
    def init_followup_database(self):
        """Initialize follow-up tracking tables"""
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Follow-up tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS followup_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_request_id INTEGER NOT NULL,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                user1_name TEXT NOT NULL,
                user2_name TEXT NOT NULL,
                user1_email TEXT NOT NULL,
                user2_email TEXT NOT NULL,
                email_sent_at TIMESTAMP,
                user1_token TEXT UNIQUE,
                user2_token TEXT UNIQUE,
                user1_response BOOLEAN,
                user2_response BOOLEAN,
                user1_responded_at TIMESTAMP,
                user2_responded_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_request_id) REFERENCES contact_requests (id),
                FOREIGN KEY (user1_id) REFERENCES users (id),
                FOREIGN KEY (user2_id) REFERENCES users (id)
            )
        ''')
        
        # Update the user_matches table to include follow-up data
        try:
            cursor.execute('ALTER TABLE user_matches ADD COLUMN user_would_meet_again BOOLEAN')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise e
                
        try:
            cursor.execute('ALTER TABLE user_matches ADD COLUMN match_would_meet_again BOOLEAN')
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise e
        
        conn.commit()
        conn.close()
        print("✓ Email follow-up database initialized")
    
    def schedule_followup_email(self, contact_request_id, user1_id, user2_id):
        """Schedule a follow-up email to be sent in 5 days"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Get user information
            cursor.execute('SELECT first_name, last_name, email FROM users WHERE id = ?', (user1_id,))
            user1_info = cursor.fetchone()
            
            cursor.execute('SELECT first_name, last_name, email FROM users WHERE id = ?', (user2_id,))
            user2_info = cursor.fetchone()
            
            if not user1_info or not user2_info:
                print(f"Error: Could not find user info for follow-up scheduling")
                conn.close()
                return False
            
            # Generate unique tokens for email responses
            user1_token = secrets.token_urlsafe(32)
            user2_token = secrets.token_urlsafe(32)
            
            # Store follow-up tracking record
            cursor.execute('''
                INSERT INTO followup_tracking 
                (contact_request_id, user1_id, user2_id, user1_name, user2_name, 
                 user1_email, user2_email, user1_token, user2_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contact_request_id, user1_id, user2_id,
                f"{user1_info[0]} {user1_info[1]}", f"{user2_info[0]} {user2_info[1]}",
                user1_info[2], user2_info[2], user1_token, user2_token
            ))
            
            followup_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Schedule the email to be sent in 5 days
            send_time = datetime.now() + timedelta(days=5)
            threading.Timer(5 * 24 * 60 * 60, self.send_followup_emails, args=[followup_id]).start()
            
            print(f"✓ Follow-up email scheduled for {send_time} (followup_id: {followup_id})")
            return True
            
        except Exception as e:
            print(f"Error scheduling follow-up email: {e}")
            return False
    
    def send_followup_emails(self, followup_id):
        """Send follow-up emails to both users"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user1_id, user2_id, user1_name, user2_name, user1_email, user2_email, 
                       user1_token, user2_token
                FROM followup_tracking WHERE id = ?
            ''', (followup_id,))
            
            followup = cursor.fetchone()
            if not followup:
                print(f"Follow-up record {followup_id} not found")
                return
            
            user1_id, user2_id, user1_name, user2_name, user1_email, user2_email, user1_token, user2_token = followup
            
            # Send email to user1 about user2
            self.send_individual_followup_email(
                user1_email, user1_name, user2_name, user1_token, followup_id
            )
            
            # Send email to user2 about user1
            self.send_individual_followup_email(
                user2_email, user2_name, user1_name, user2_token, followup_id
            )
            
            # Update that emails were sent
            cursor.execute('''
                UPDATE followup_tracking SET email_sent_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (followup_id,))
            
            conn.commit()
            conn.close()
            
            print(f"✓ Follow-up emails sent for followup_id: {followup_id}")
            
        except Exception as e:
            print(f"Error sending follow-up emails: {e}")
    
    def send_individual_followup_email(self, to_email, user_name, other_user_name, token, followup_id):
        """Send individual follow-up email"""
        try:
            # Create the email content
            subject = f"How did your meetup with {other_user_name} go?"
            
            # Get the base URL for your app
            base_url = os.environ.get('BASE_URL', 'http://localhost:8080')
            yes_url = f"{base_url}/followup-response/{token}/yes"
            no_url = f"{base_url}/followup-response/{token}/no"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Inter', sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #167a60, #c6e19b); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .button {{ display: inline-block; padding: 15px 30px; margin: 10px; text-decoration: none; border-radius: 6px; font-weight: bold; text-align: center; }}
                    .btn-yes {{ background: #28a745; color: white; }}
                    .btn-no {{ background: #dc3545; color: white; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 24px;">Connect Follow-up</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">How did your connection go?</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {user_name}!</h2>
                        
                        <p>It's been 5 days since you connected with <strong>{other_user_name}</strong> through our platform. We hope you had a chance to meet up!</p>
                        
                        <p>To help us improve our matching system and provide better recommendations in the future, we'd love to know:</p>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 6px; text-align: center; margin: 25px 0;">
                            <h3 style="margin-top: 0; color: #167a60;">Would you want to meet {other_user_name} again?</h3>
                            
                            <div style="margin: 20px 0;">
                                <a href="{yes_url}" class="button btn-yes">✅ Yes, I'd meet them again!</a>
                                <a href="{no_url}" class="button btn-no">❌ No, not a good match</a>
                            </div>
                        </div>
                        
                        <p><small>Your response helps us understand how well our matching system is working and will be used to improve future matches. This information is kept confidential.</small></p>
                        
                        <p>Thank you for being part of the Connect community!</p>
                        
                        <p>Best regards,<br>The Connect Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>This email was sent because you recently connected with someone through Connect.</p>
                        <p>If you have any questions, please contact us at support@connect.com</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send the email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = to_email
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
                
            print(f"✓ Follow-up email sent to {to_email}")
            
        except Exception as e:
            print(f"Error sending follow-up email to {to_email}: {e}")
    
    def record_followup_response(self, token, response):
        """Record user's follow-up response"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Find the follow-up record and determine which user responded
            cursor.execute('''
                SELECT id, user1_id, user2_id, user1_token, user2_token 
                FROM followup_tracking 
                WHERE user1_token = ? OR user2_token = ?
            ''', (token, token))
            
            followup = cursor.fetchone()
            if not followup:
                conn.close()
                return {'success': False, 'error': 'Invalid response token'}
            
            followup_id, user1_id, user2_id, user1_token, user2_token = followup
            
            # Determine which user responded
            if token == user1_token:
                cursor.execute('''
                    UPDATE followup_tracking 
                    SET user1_response = ?, user1_responded_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (response == 'yes', followup_id))
                responding_user_id = user1_id
                other_user_id = user2_id
            else:
                cursor.execute('''
                    UPDATE followup_tracking 
                    SET user2_response = ?, user2_responded_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (response == 'yes', followup_id))
                responding_user_id = user2_id
                other_user_id = user1_id
            
            # Update the user_matches table with the response
            cursor.execute('''
                UPDATE user_matches 
                SET user_would_meet_again = ? 
                WHERE user_id = ? AND matched_user_id = ?
            ''', (response == 'yes', responding_user_id, other_user_id))
            
            # Also update the reverse match
            cursor.execute('''
                UPDATE user_matches 
                SET match_would_meet_again = ? 
                WHERE user_id = ? AND matched_user_id = ?
            ''', (response == 'yes', other_user_id, responding_user_id))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': 'Response recorded successfully'}
            
        except Exception as e:
            print(f"Error recording follow-up response: {e}")
            return {'success': False, 'error': 'Failed to record response'}

# ============================================================================
# MATCHING SYSTEM
# ============================================================================

class MatchingSystem:
    """Advanced friendship compatibility matching system"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.user_auth = UserAuthSystem()
    
    def calculate_distance(self, postcode1: str, postcode2: str) -> float:
        """Calculate distance between two UK postcodes"""
        def get_postcode_coordinates(postcode: str) -> Tuple[Optional[float], Optional[float]]:
            try:
                response = requests.get(f"https://api.postcodes.io/postcodes/{postcode}")
                if response.status_code == 200:
                    data = response.json()
                    return data['result']['latitude'], data['result']['longitude']
            except:
                pass
            return None, None

        def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            R = 3959  # Earth's radius in miles
            
            lat1_rad = math.radians(lat1)
            lat2_rad = math.radians(lat2)
            delta_lat = math.radians(lat2 - lat1)
            delta_lon = math.radians(lon2 - lon1)
            
            a = (math.sin(delta_lat / 2) ** 2 + 
                math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            
            return R * c

        lat1, lon1 = get_postcode_coordinates(postcode1)
        lat2, lon2 = get_postcode_coordinates(postcode2)
        
        if lat1 and lon1 and lat2 and lon2:
            return haversine_distance(lat1, lon1, lat2, lon2)
        
        return 999  # Return high number if geocoding fails
    
    def check_gender_compatibility(self, user1_profile: Dict, user2_profile: Dict) -> bool:
        """Check if users meet each other's gender preferences"""
        user1_gender = user1_profile.get('gender', '')
        user2_gender = user2_profile.get('gender', '')
        user1_preference = user1_profile.get('gender_preference', 'all')
        user2_preference = user2_profile.get('gender_preference', 'all')
        
        # Check mutual compatibility
        user1_compatible = (user1_preference == 'all' or 
                           (user1_preference == 'women' and user2_gender == 'woman') or
                           (user1_preference == 'men' and user2_gender == 'man') or
                           (user1_preference == 'non_binary' and user2_gender == 'non_binary'))
        
        user2_compatible = (user2_preference == 'all' or 
                           (user2_preference == 'women' and user1_gender == 'woman') or
                           (user2_preference == 'men' and user1_gender == 'man') or
                           (user2_preference == 'non_binary' and user1_gender == 'non_binary'))
        
        return user1_compatible and user2_compatible
    
    def is_user_blocked(self, user_id: int, potential_match: Dict[str, Any]) -> bool:
        """Check if a potential match is blocked"""
        blocked = self.user_auth.get_blocked_users(user_id)
        
        # Check email, phone, and name matches
        if potential_match['email'] in blocked['emails']:
            return True
        if potential_match['phone'] and potential_match['phone'] in blocked['phones']:
            return True
        
        user_name = f"{potential_match['first_name']} {potential_match['last_name']}".lower()
        for blocked_name in blocked['names']:
            if blocked_name and blocked_name.lower() in user_name:
                return True
        
        return False
    
    def calculate_compatibility_scores(self, user1_profile: Dict, user2_profile: Dict) -> Dict[str, float]:
        """Calculate all compatibility scores"""
        scores = {}
        
        # Personality compatibility
        scores['personality'] = self._calculate_personality_score(user1_profile, user2_profile)
        
        # Values compatibility  
        scores['values'] = self._calculate_values_score(user1_profile, user2_profile)
        
        # Lifestyle compatibility
        scores['lifestyle'] = self._calculate_lifestyle_score(user1_profile, user2_profile)
        
        # Emotional compatibility
        scores['emotional'] = self._calculate_emotional_score(user1_profile, user2_profile)
        
        # Social boundaries compatibility
        scores['social'] = self._calculate_social_score(user1_profile, user2_profile)
        
        return scores
    
    def _calculate_personality_score(self, user1: Dict, user2: Dict) -> float:
        """Calculate personality compatibility score with safe numeric conversion"""
        
        # Helper function to safely convert to numeric
        def safe_numeric(value, default=5):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        personality_scores = []
        
        # Decision-making compatibility (moderate differences are okay)
        decision_diff = abs(safe_numeric(user1.get('decision_making', 5)) - safe_numeric(user2.get('decision_making', 5)))
        decision_score = max(0, 100 - (decision_diff * 8))
        personality_scores.append(decision_score * 1.2)
        
        # Social energy alignment (should be similar)
        social_diff = abs(safe_numeric(user1.get('social_energy', 5)) - safe_numeric(user2.get('social_energy', 5)))
        social_score = max(0, 100 - (social_diff * 12))
        personality_scores.append(social_score * 1.5)
        
        # Communication depth (should align)
        comm_diff = abs(safe_numeric(user1.get('communication_depth', 5)) - safe_numeric(user2.get('communication_depth', 5)))
        comm_score = max(0, 100 - (comm_diff * 15))
        personality_scores.append(comm_score * 1.8)
        
        # Conflict approach
        conflict_diff = abs(safe_numeric(user1.get('conflict_approach', 5)) - safe_numeric(user2.get('conflict_approach', 5)))
        conflict_score = max(0, 100 - (conflict_diff * 10))
        personality_scores.append(conflict_score * 1.0)
        
        # Life pace
        pace_diff = abs(safe_numeric(user1.get('life_pace', 5)) - safe_numeric(user2.get('life_pace', 5)))
        pace_score = max(0, 100 - (pace_diff * 12))
        personality_scores.append(pace_score * 1.3)
        
        return sum(personality_scores) / len(personality_scores)

    
    def _calculate_values_score(self, user1: Dict, user2: Dict) -> float:
        """Calculate values alignment score with safe numeric conversion"""
        
        def safe_numeric(value, default=5):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        values_scores = []
        
        # Personal growth alignment
        growth_diff = abs(safe_numeric(user1.get('personal_growth', 5)) - safe_numeric(user2.get('personal_growth', 5)))
        growth_score = max(0, 100 - (growth_diff * 10))
        values_scores.append(growth_score)
        
        # Success definition alignment
        success_diff = abs(safe_numeric(user1.get('success_definition', 5)) - safe_numeric(user2.get('success_definition', 5)))
        success_score = max(0, 100 - (success_diff * 12))
        values_scores.append(success_score)
        
        # Community involvement
        community_diff = abs(safe_numeric(user1.get('community_involvement', 5)) - safe_numeric(user2.get('community_involvement', 5)))
        community_score = max(0, 100 - (community_diff * 8))
        values_scores.append(community_score)
        
        # Work-life philosophy
        worklife_diff = abs(safe_numeric(user1.get('work_life_philosophy', 5)) - safe_numeric(user2.get('work_life_philosophy', 5)))
        worklife_score = max(0, 100 - (worklife_diff * 11))
        values_scores.append(worklife_score)
        
        # Future orientation
        future_diff = abs(safe_numeric(user1.get('future_orientation', 5)) - safe_numeric(user2.get('future_orientation', 5)))
        future_score = max(0, 100 - (future_diff * 9))
        values_scores.append(future_score)
        
        return sum(values_scores) / len(values_scores)

    def _calculate_lifestyle_score(self, user1: Dict, user2: Dict) -> float:
        """Calculate lifestyle compatibility score with safe numeric conversion"""
        
        def safe_numeric(value, default=5):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        lifestyle_scores = []
        
        # Energy patterns (important for scheduling)
        energy_diff = abs(safe_numeric(user1.get('energy_patterns', 5)) - safe_numeric(user2.get('energy_patterns', 5)))
        energy_score = max(0, 100 - (energy_diff * 15))
        lifestyle_scores.append(energy_score * 1.4)
        
        # Social setting preference
        setting_diff = abs(safe_numeric(user1.get('social_setting', 5)) - safe_numeric(user2.get('social_setting', 5)))
        setting_score = max(0, 100 - (setting_diff * 8))
        lifestyle_scores.append(setting_score)
        
        # Activity investment
        activity_diff = abs(safe_numeric(user1.get('activity_investment', 5)) - safe_numeric(user2.get('activity_investment', 5)))
        activity_score = max(0, 100 - (activity_diff * 7))
        lifestyle_scores.append(activity_score)
        
        # Physical activity level
        physical_diff = abs(safe_numeric(user1.get('physical_activity', 5)) - safe_numeric(user2.get('physical_activity', 5)))
        physical_score = max(0, 100 - (physical_diff * 10))
        lifestyle_scores.append(physical_score * 1.2)
        
        # Cultural consumption
        cultural_diff = abs(safe_numeric(user1.get('cultural_consumption', 5)) - safe_numeric(user2.get('cultural_consumption', 5)))
        cultural_score = max(0, 100 - (cultural_diff * 6))
        lifestyle_scores.append(cultural_score)
        
        return sum(lifestyle_scores) / len(lifestyle_scores)

    def _calculate_emotional_score(self, user1: Dict, user2: Dict) -> float:
        """Calculate emotional compatibility score with safe numeric conversion"""
        
        def safe_numeric(value, default=5):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        emotional_scores = []
        
        # Stress preference compatibility
        stress1 = user1.get('stress_preference', '')
        stress2 = user2.get('stress_preference', '')
        stress_score = 85 if stress1 == stress2 else 70
        emotional_scores.append(stress_score)
        
        # Processing style compatibility
        process1 = user1.get('processing_style', '')
        process2 = user2.get('processing_style', '')
        process_score = 90 if process1 == process2 else 65
        emotional_scores.append(process_score * 1.3)
        
        # Celebration preference
        celeb_diff = abs(safe_numeric(user1.get('celebration_preference', 5)) - safe_numeric(user2.get('celebration_preference', 5)))
        celeb_score = max(0, 100 - (celeb_diff * 12))
        emotional_scores.append(celeb_score)
        
        return sum(emotional_scores) / len(emotional_scores)

    def _calculate_social_score(self, user1: Dict, user2: Dict) -> float:
        """Calculate social boundaries compatibility score with safe numeric conversion"""
        
        def safe_numeric(value, default=5):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        boundary_scores = []
        
        # Personal sharing alignment
        sharing_diff = abs(safe_numeric(user1.get('personal_sharing', 5)) - safe_numeric(user2.get('personal_sharing', 5)))
        sharing_score = max(0, 100 - (sharing_diff * 14))
        boundary_scores.append(sharing_score * 1.4)
        
        # Social overlap tolerance
        overlap_diff = abs(safe_numeric(user1.get('social_overlap', 5)) - safe_numeric(user2.get('social_overlap', 5)))
        overlap_score = max(0, 100 - (overlap_diff * 8))
        boundary_scores.append(overlap_score)
        
        # Advice-giving style
        advice_diff = abs(safe_numeric(user1.get('advice_giving', 5)) - safe_numeric(user2.get('advice_giving', 5)))
        advice_score = max(0, 100 - (advice_diff * 9))
        boundary_scores.append(advice_score)
        
        # Social commitment level
        commitment_diff = abs(safe_numeric(user1.get('social_commitment', 5)) - safe_numeric(user2.get('social_commitment', 5)))
        commitment_score = max(0, 100 - (commitment_diff * 13))
        boundary_scores.append(commitment_score * 1.3)
        
        return sum(boundary_scores) / len(boundary_scores)
    
    def run_matching(self, user_id: int) -> List[Dict[str, Any]]:
        """Run comprehensive matching for a user"""
        print(f"\n=== Running Advanced Friendship Matching for {user_id} ===")
        
        # Get current user's profile and info
        current_user_profile = self.user_auth.get_user_profile(user_id)
        current_user_info = self.user_auth.get_user_info(user_id)
        
        if not current_user_profile or not current_user_info:
            print("ERROR: Current user profile not found!")
            return []
        
        # Get all other users for matching
        all_users = self.user_auth.get_all_users_for_matching(user_id)
        print(f"Found {len(all_users)} potential matches")
        
        if not all_users:
            print("No other users found for matching")
            return []
        
        matches = []
        
        for potential_match in all_users:
            # Apply filters
            if self.is_user_blocked(user_id, potential_match):
                print(f"Skipping blocked user: {potential_match['first_name']} {potential_match['last_name']}")
                continue
            
            if not self.check_gender_compatibility(current_user_profile, potential_match['profile']):
                print(f"Skipping due to gender preference: {potential_match['first_name']} {potential_match['last_name']}")
                continue
            
            print(f"Analyzing compatibility with {potential_match['first_name']} {potential_match['last_name']}...")
            
            # Calculate detailed compatibility scores
            scores = self.calculate_compatibility_scores(current_user_profile, potential_match['profile'])
            
            # Calculate distance and location score
            distance = 999
            location_score = 50  # Default neutral score
            current_postcode = current_user_profile.get('postcode')
            match_postcode = potential_match['profile'].get('postcode')
            
            if current_postcode and match_postcode:
                distance = self.calculate_distance(current_postcode, match_postcode)
                # Location score based on distance
                if distance <= 5:
                    location_score = 95
                elif distance <= 15:
                    location_score = 85
                elif distance <= 30:
                    location_score = 75
                elif distance <= 50:
                    location_score = 65
                else:
                    location_score = 40
            
            # Calculate weighted overall score
            overall_score = (
                scores['personality'] * 0.25 +
                scores['values'] * 0.20 +
                scores['lifestyle'] * 0.15 +
                scores['emotional'] * 0.20 +
                scores['social'] * 0.10 +
                location_score * 0.10
            )
            
            # Generate AI analysis
            if self.client:
                analysis = self.get_ai_friendship_analysis(current_user_profile, potential_match['profile'])
            else:
                analysis = self.get_fallback_friendship_analysis(current_user_profile, potential_match['profile'])
            
            match_result = {
                'matched_user_id': potential_match['user_id'],
                'matched_user_name': potential_match['first_name'],
                'matched_user_email': potential_match['email'],
                'compatibility_score': round(overall_score),
                'personality_score': round(scores['personality']),
                'values_score': round(scores['values']),
                'lifestyle_score': round(scores['lifestyle']),
                'emotional_score': round(scores['emotional']),
                'social_score': round(scores['social']),
                'location_score': round(location_score),
                'overall_score': round(overall_score),
                'compatibility_analysis': analysis,
                'distance_miles': distance
            }
            
            matches.append(match_result)
        
        # Sort by overall score and filter
        matches.sort(key=lambda x: x['overall_score'], reverse=True)
        matches = [m for m in matches if m['overall_score'] >= 60]
        
        # Save matches to database
        self.user_auth.save_user_matches(user_id, matches)
        
        print(f"✓ Found {len(matches)} compatible friendship matches")
        return matches
    
    def get_ai_friendship_analysis(self, user1_profile: Dict, user2_profile: Dict) -> str:
        """Get AI-powered friendship compatibility analysis"""
        personality_summary = f"""
        User 1: Decision-making ({user1_profile.get('decision_making', 5)}/10), Social energy ({user1_profile.get('social_energy', 5)}/10), Communication depth ({user1_profile.get('communication_depth', 5)}/10)
        User 2: Decision-making ({user2_profile.get('decision_making', 5)}/10), Social energy ({user2_profile.get('social_energy', 5)}/10), Communication depth ({user2_profile.get('communication_depth', 5)}/10)
        
        User 1 friendship superpower: {user1_profile.get('friendship_superpower', 'Not specified')}
        User 2 friendship superpower: {user2_profile.get('friendship_superpower', 'Not specified')}
        
        User 1 ideal friendship: {user1_profile.get('ideal_friendship_description', 'Not specified')}
        User 2 ideal friendship: {user2_profile.get('ideal_friendship_description', 'Not specified')}
        """
        
        prompt = f"""Analyze this friendship compatibility and provide a warm, encouraging 2-3 sentence analysis of why these two people could be great friends.

{personality_summary}

Focus on:
- Complementary or aligned personality traits
- Shared values and interests
- How they might support each other
- What makes this friendship exciting

Keep it positive and specific."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200,
                timeout=30
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            return self.get_fallback_friendship_analysis(user1_profile, user2_profile)
    
    def get_fallback_friendship_analysis(self, user1_profile: Dict, user2_profile: Dict) -> str:
        """Fallback friendship analysis without AI"""
        analyses = [
            "Your complementary communication styles and shared values around personal growth suggest you could build a really meaningful friendship with great conversations and mutual support.",
            "You both seem to value authentic connections and have similar approaches to handling life's challenges, which could form the foundation for a lasting and supportive friendship.",
            "Your different strengths could really complement each other well - one brings energy and planning while the other offers thoughtful listening and emotional support.",
            "You share similar lifestyle rhythms and social preferences, which means you'd likely enjoy spending time together and have compatible friendship expectations.",
            "Both of you value deep, meaningful connections over surface-level interactions, suggesting you could develop the kind of friendship where you really understand and support each other."
        ]
        
        return random.choice(analyses)

# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

def process_matching_background(user_id: int):
    """Background task to process user matching"""
    # Prevent multiple matching processes for same user
    if user_id in processing_status and processing_status[user_id].get('status') == 'processing':
        print(f"Matching already in progress for user {user_id}")
        return
    try:
        processing_status[user_id] = {'status': 'processing', 'progress': 0}
        
        processing_status[user_id]['progress'] = 25
        
        # Run matching against all other users
        matches = enhanced_matching_system.run_matching(user_id)
        processing_status[user_id]['progress'] = 75
        
        print(f"✓ Found {len(matches)} matches")
        processing_status[user_id]['progress'] = 100
        
        # Store results
        processing_status[user_id] = {
            'status': 'completed',
            'matches': matches,
            'progress': 100
        }
        
    except Exception as e:
        print(f"❌ Error in background processing: {e}")
        import traceback
        traceback.print_exc()
        processing_status[user_id] = {
            'status': 'error',
            'error': str(e),
            'progress': 0
        }

# ============================================================================
# TEMPLATE FUNCTIONS
# ============================================================================

def get_base_styles() -> str:
    """Common CSS styles with designer typography and color palette"""
    return '''
    <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=clash-display@400,500,600,700&display=swap" rel="stylesheet">
    <style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    
    :root {
        --color-cream: #f1ece0;
        --color-emerald: #167a60;
        --color-sage: #c6e19b;
        --color-lavender: #c2b7ef;
        --color-charcoal: #2d2d2d;
        --color-white: #ffffff;
        --color-gray-50: #fafafa;
        --color-gray-100: #f5f5f5;
        --color-gray-200: #eeeeee;
        --color-gray-600: #757575;
        --color-gray-800: #424242;
    }
    
    body {
        font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(135deg, var(--color-cream) 0%, var(--color-gray-50) 100%);
        color: var(--color-charcoal);
        line-height: 1.6;
        min-height: 100vh;
        overflow-x: hidden;
    }
    
    /* Typography Scale */
    .text-display {
        font-family: 'Clash Display', 'Satoshi', sans-serif;
        font-size: clamp(2.5rem, 5vw, 4rem);
        font-weight: 600;
        line-height: 1.1;
        letter-spacing: -0.02em;
    }
    
    .text-title {
        font-family: 'Clash Display', 'Satoshi', sans-serif;
        font-size: clamp(1.5rem, 3vw, 2.25rem);
        font-weight: 500;
        line-height: 1.2;
        letter-spacing: -0.01em;
    }
    
    .text-body-lg {
        font-size: 1.125rem;
        line-height: 1.6;
        font-weight: 400;
    }
    
    .text-body {
        font-size: 1rem;
        line-height: 1.5;
        font-weight: 400;
    }
    
    .text-small {
        font-size: 0.875rem;
        line-height: 1.4;
        font-weight: 400;
    }
    
    /* Enhanced Header */
    .header {
        background: var(--color-white);
        padding: 1.5rem 2rem;
        box-shadow: 
            0 1px 3px rgba(0,0,0,0.04),
            0 4px 16px rgba(0,0,0,0.08);
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2rem;
        backdrop-filter: blur(20px);
        border-bottom: 1px solid rgba(0,0,0,0.06);
        position: relative;
    }
    
    .header::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
    }
    
    .logo {
        font-family: 'Clash Display', 'Satoshi', sans-serif;
        font-size: 1.75rem;
        font-weight: 600;
        color: var(--color-charcoal);
        letter-spacing: -0.02em;
        position: relative;
    }
    
    
    .user-info {
        display: flex;
        align-items: center;
        gap: 1rem;
        font-weight: 500;
        color: var(--color-gray-600);
    }
    
    .user-info span {
        font-size: 0.875rem;
        color: var(--color-charcoal);
        font-weight: 500;
    }
    
    /* Enhanced Buttons */
    .btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem 1.5rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        text-align: center;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border: none;
        font-family: 'Satoshi', sans-serif;
        white-space: nowrap;
    }
    
    .btn-primary {
        background: var(--color-emerald);
        color: white;
        box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
    }
    
    .btn-primary:hover {
        background: #0f5942;
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
    }
    
    .btn-secondary {
        background: var(--color-white);
        color: var(--color-gray-600);
        border: 1px solid var(--color-gray-200);
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    
    .btn-secondary:hover {
        background: var(--color-gray-50);
        border-color: var(--color-sage);
        color: var(--color-charcoal);
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }
    
    /* Enhanced Container */
    .container {
        background: var(--color-white);
        border-radius: 24px;
        padding: 3rem 2.5rem;
        max-width: 800px;
        margin: 0 auto;
        box-shadow: 
            0 1px 3px rgba(0,0,0,0.04),
            0 8px 24px rgba(0,0,0,0.08),
            0 24px 48px rgba(0,0,0,0.04);
        position: relative;
        overflow: hidden;
    }
    
    .container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
    }
    
    /* Form Elements */
    input[type="text"],
    input[type="email"],
    input[type="password"],
    input[type="tel"],
    input[type="number"],
    input[type="url"],
    textarea,
    select {
        font-family: 'Satoshi', sans-serif;
        width: 100%;
        padding: 1rem;
        border: 1px solid var(--color-gray-200);
        border-radius: 8px;
        font-size: 1rem;
        background: var(--color-white);
        color: var(--color-charcoal);
        transition: all 0.3s ease;
    }
    
    input[type="text"]:focus,
    input[type="email"]:focus,
    input[type="password"]:focus,
    input[type="tel"]:focus,
    input[type="number"]:focus,
    input[type="url"]:focus,
    textarea:focus,
    select:focus {
        outline: none;
        border-color: var(--color-emerald);
        box-shadow: 0 0 0 3px rgba(22, 122, 96, 0.1);
    }
    
    label {
        display: block;
        margin-bottom: 0.5rem;
        font-weight: 500;
        color: var(--color-charcoal);
        font-size: 0.875rem;
    }
    
    /* Flash Messages */
    .flash-success {
        background: linear-gradient(135deg, var(--color-sage), var(--color-lavender));
        color: var(--color-charcoal);
        padding: 1rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        font-weight: 500;
        border-left: 4px solid var(--color-emerald);
    }
    
    .flash-error {
        background: #fee;
        color: #c53030;
        padding: 1rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        font-weight: 500;
        border-left: 4px solid #fc8181;
    }
    
    /* Cards */
    .card {
        background: var(--color-white);
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        border: 1px solid var(--color-gray-200);
        transition: all 0.3s ease;
    }
    
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(0,0,0,0.12);
    }
    
    /* Notification Badge */
    .notification-badge {
        background: var(--color-emerald);
        color: white;
        border-radius: 50%;
        padding: 0.25rem 0.5rem;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: 0.5rem;
        min-width: 1.25rem;
        height: 1.25rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }
    
    /* Loading States */
    .loading {
        opacity: 0.7;
        pointer-events: none;
    }
    
    .loading-spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 2px solid var(--color-gray-200);
        border-radius: 50%;
        border-top-color: var(--color-emerald);
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* Responsive Design */
    @media (max-width: 768px) {
        .container {
            padding: 2rem 1.5rem;
            margin: 1rem;
            border-radius: 16px;
        }
        
        .header {
            flex-direction: column;
            gap: 1rem;
            text-align: center;
            padding: 1rem 1.5rem;
        }
        
        .user-info {
            flex-wrap: wrap;
            justify-content: center;
            gap: 0.75rem;
        }
        
        .btn {
            padding: 0.875rem 1.25rem;
            font-size: 0.875rem;
        }
        
        .logo {
            font-size: 1.5rem;
        }
    }
    
    @media (max-width: 480px) {
        .container {
            margin: 0.5rem;
            padding: 1.5rem 1rem;
        }
        
        .header {
            margin-bottom: 1rem;
        }
        
        .user-info {
            flex-direction: column;
            gap: 0.5rem;
        }
    }
    </style>
    '''

def render_template_with_header(title: str, content: str, user_info: Dict = None) -> str:
    """Render template with consistent header"""
    # Add notification badge for contact requests (only if logged in)
    notification_badge = ""
    user_nav = ""
    
    # Check if user is actually logged in (has user_id in session)
    if 'user_id' in session:
        user_id = session['user_id']
        pending_requests = user_auth.get_contact_requests(user_id, 'received')
        pending_count = len([r for r in pending_requests if r['status'] == 'pending'])
        if pending_count > 0:
            notification_badge = f'<span style="background: #dc3545; color: white; border-radius: 50%; padding: 4px 8px; font-size: 12px; margin-left: 8px;">{pending_count}</span>'
        
        # Get user info for display name
        if not user_info:
            user_info = user_auth.get_user_info(user_id) or {}
        
        # Logged in user navigation
        user_nav = f'''
            <div class="user-info">
                <span>{user_info.get('first_name', user_info.get('email', 'User'))}</span>
                <a href="/edit-profile" class="btn btn-secondary" style="padding: 8px 16px; font-size: 14px;"> Edit Profile</a>
                <a href="/contact-requests" class="btn btn-secondary">Requests{notification_badge}</a>
                <a href="/logout" class="btn btn-secondary">Logout</a>
            </div>
        '''
    else:
        # Not logged in navigation
        user_nav = '''
            <div class="user-info">
                <a href="/login" class="btn btn-secondary">Login</a>
                <a href="/register" class="btn btn-primary">Sign Up</a>
            </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title} - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{get_base_styles()}</style>
    </head>
    <body>
        <div class="header">
            <div class="logo">Connect</div>
            {user_nav}
        </div>
        {content}
    </body>
    </html>
    '''
# Initialize systems
user_auth = UserAuthSystem()
#matching_system = MatchingSystem(API_KEY)
try:
    enhanced_matching_system, interaction_tracker = integrate_enhanced_matching(app, user_auth, API_KEY)
    enhanced_matching_system.processing_status = processing_status
    print("✓ Enhanced matching system initialized")
except Exception as e:
    from enhanced_matching_system import EnhancedMatchingSystem, InteractionTracker
    enhanced_matching_system = EnhancedMatchingSystem(API_KEY)
    enhanced_matching_system.set_user_auth(user_auth)
    interaction_tracker = InteractionTracker(enhanced_matching_system)
    print("✓ Enhanced matching system created directly")
    
email_followup = EmailFollowupSystem(user_auth)
# ============================================================================
# ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/')
def home():
    """Landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')
    
    content = '''
    <style>
        /* Additional home-specific styles */
        .home-container {
            background: var(--color-white);
            border-radius: 24px;
            padding: 4rem 3rem;
            max-width: 600px;
            width: 100%;
            margin: 2rem auto;
            text-align: center;
            box-shadow: 
                0 1px 3px rgba(0,0,0,0.04),
                0 8px 24px rgba(0,0,0,0.08),
                0 24px 48px rgba(0,0,0,0.04);
            position: relative;
            backdrop-filter: blur(20px);
        }
        
        .home-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
        }
        
        .home-logo {
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: clamp(2.5rem, 5vw, 3.5rem);
            font-weight: 600;
            color: var(--color-charcoal);
            margin-bottom: 0.5rem;
            letter-spacing: -0.02em;
            position: relative;
        }
        
        .home-logo::after {
            content: '';
            position: absolute;
            bottom: -8px;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 4px;
            background: linear-gradient(90deg, var(--color-emerald), var(--color-sage));
            border-radius: 2px;
        }
        
        .subtitle {
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.25rem;
            color: var(--color-gray-600);
            margin-bottom: 3rem;
            font-weight: 500;
        }
        
        .description {
            font-size: 1.125rem;
            color: var(--color-gray-600);
            margin-bottom: 3rem;
            text-align: left;
            line-height: 1.7;
            padding: 2rem;
            background: var(--color-gray-50);
            border-radius: 16px;
            border-left: 4px solid var(--color-sage);
        }
        
        .action-buttons {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-bottom: 2.5rem;
        }
        
        .btn-home-primary {
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            color: white;
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            padding: 1.25rem 2rem;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none;
            font-family: 'Satoshi', sans-serif;
        }
        
        .btn-home-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }
        
        .btn-home-primary::before {
            content: '✨';
            font-size: 1.2rem;
        }
        
        .btn-home-secondary {
            background: var(--color-white);
            color: var(--color-charcoal);
            border: 2px solid var(--color-sage);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            padding: 1.25rem 2rem;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-family: 'Satoshi', sans-serif;
        }
        
        .btn-home-secondary:hover {
            background: var(--color-sage);
            color: var(--color-charcoal);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(198, 225, 155, 0.3);
        }
        
        .btn-home-secondary::before {
            content: '👋';
            font-size: 1.2rem;
        }
        
        .privacy-note {
            background: linear-gradient(135deg, var(--color-lavender), var(--color-sage));
            color: var(--color-charcoal);
            border-radius: 16px;
            padding: 1.5rem 2rem;
            margin: 2rem 0;
            font-size: 0.875rem;
            text-align: left;
            line-height: 1.6;
            position: relative;
            overflow: hidden;
        }
        
        .privacy-note::before {
            content: '🔒';
            position: absolute;
            top: 1rem;
            right: 1.5rem;
            font-size: 1.5rem;
            opacity: 0.7;
        }
        
        .privacy-note strong {
            font-weight: 600;
            display: block;
            margin-bottom: 0.5rem;
        }
        
        @media (max-width: 768px) {
            .home-container {
                padding: 3rem 2rem;
                margin: 1rem;
                border-radius: 20px;
            }
            
            .description {
                text-align: center;
                padding: 1.5rem;
            }
            
            .action-buttons {
                gap: 0.75rem;
            }
        }
        
        @media (max-width: 480px) {
            .home-container {
                padding: 2rem 1.5rem;
            }
        }
    </style>
    
    <div class="home-container">
        <h1 class="home-logo">Connect</h1>
        <div class="subtitle">Skip the small talk</div>
        
        <div class="description">
            Discover meaningful connections based on deep personality compatibility, shared values, and lifestyle alignment. Our advanced neural network analyzes thousands of compatibility factors to help you find people who truly understand you.
        </div>
        
        <div class="action-buttons">
            <a href="/register" class="btn-home-primary">
                Create Account & Start Matching
            </a>
            <a href="/login" class="btn-home-secondary">
                Login to Existing Account
            </a>
        </div>
        
        <div class="privacy-note">
            <strong>Your Privacy is Our Priority</strong>
            We use enterprise-grade security and advanced AI filtering to protect your data while helping you find genuinely compatible matches through intelligent analysis.
        </div>
    </div>
    '''
    return render_template_with_header("Home", content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        # Validation
        existing_user = user_auth.get_user_by_email(email)  # You'll need to add this method
        if existing_user:
            flash('Email already registered. Please login instead.', 'error')
            return redirect('/login')
        if not email or not password:
            flash('Email and password are required', 'error')
        elif not phone:
            flash('Phone number is required for contact requests', 'error')
        elif password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            result = user_auth.create_user(email, password, first_name, last_name, phone)
            
            if result['success']:
                session['user_id'] = result['user_id']
                session['user_email'] = email
                session['user_name'] = first_name
                flash('Account created successfully! Let\'s create your profile.', 'success')
                return redirect('/profile-setup')
            else:
                flash(result['error'], 'error')
    
    # Registration form
    content = '''
    <div class="container" style="max-width: 400px;">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px;">Create Your Account</h1>
        
        <!-- Flash messages -->
        <div id="flash-messages"></div>
        
        <form method="POST">
            <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">First Name</label>
                    <input type="text" name="first_name" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">Last Name</label>
                    <input type="text" name="last_name" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Email Address</label>
                <input type="email" name="email" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Phone Number (Required for contact requests)</label>
                <input type="tel" name="phone" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Password</label>
                <input type="password" name="password" required minlength="6" style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Confirm Password</label>
                <input type="password" name="confirm_password" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <button type="submit" class="btn btn-primary" style="width: 100%; padding: 16px; font-size: 16px; margin-top: 10px;">
                Create Account
            </button>
        </form>
        
        <div style="text-align: center; margin-top: 20px; font-size: 14px;">
            Already have an account? <a href="/login" style="color: #167a60; text-decoration: none;">Login here</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Create Account", content)

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    """User login"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email and password are required', 'error')
        else:
            result = user_auth.authenticate_user(email, password)
            
            if result['success']:
                session['user_id'] = result['user_id']
                session['user_email'] = email
                session['user_name'] = result['first_name']
                flash(f'Welcome back{", " + result["first_name"] if result["first_name"] else ""}!', 'success')
                return redirect('/dashboard')
            else:
                flash(result['error'], 'error')
    
    # Login form
    content = '''
    <div class="container" style="max-width: 400px;">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px;">Login to Your Account</h1>
        
        <form method="POST">
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Email Address</label>
                <input type="email" name="email" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Password</label>
                <input type="password" name="password" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            
            <button type="submit" class="btn btn-primary" style="width: 100%; padding: 16px; font-size: 16px; margin-top: 10px;">
                Login
            </button>
        </form>
        <div style="text-align: center; margin-top: 20px; font-size: 14px;">
            <a href="/forgot-password" style="color: #167a60; text-decoration: none;">Forgot your password?</a>
        </div>
        <div style="text-align: center; margin-top: 20px; font-size: 14px;">
            Don't have an account? <a href="/register" style="color: #167a60; text-decoration: none;">Create one here</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Login", content)

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect('/')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password form and processing"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email address is required', 'error')
        else:
            result = user_auth.create_password_reset_token(email)
            # Always show success message for security (don't reveal if email exists)
            flash('If this email address exists in our system, you will receive a password reset link shortly.', 'success')
            return redirect('/forgot-password')
    
    # Show forgot password form
    content = '''
    <div class="auth-container">
        <div class="auth-header">
            <h1 class="auth-title">Reset Password</h1>
            <p class="auth-subtitle">We'll send you a secure reset link</p>
        </div>
        
        <div class="info-card">
            <div class="info-icon">🔒</div>
            <div class="info-content">
                <strong>Forgot your password?</strong><br>
                Enter your email address and we'll send you a secure link to reset your password.
            </div>
        </div>
        
        <form method="POST" class="auth-form">
            <div class="form-group">
                <label>Email Address</label>
                <input type="email" name="email" required placeholder="Enter your email address" autofocus>
            </div>
            
            <button type="submit" class="btn-submit">
                <span>📧 Send Reset Link</span>
            </button>
        </form>
        
        <div class="auth-links">
            <a href="/login" class="back-link">← Remember your password?</a>
        </div>
        
        <div class="auth-footer">
            Don't have an account? <a href="/register">Create one here</a>
        </div>
    </div>
    
    <style>
        .auth-container {
            max-width: 450px;
            margin: 0 auto;
        }
        
        .auth-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .auth-title {
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 2rem;
            font-weight: 600;
            color: var(--color-charcoal);
            margin-bottom: 0.5rem;
        }
        
        .auth-subtitle {
            color: var(--color-gray-600);
            font-size: 1rem;
            font-weight: 500;
        }
        
        .info-card {
            background: linear-gradient(135deg, var(--color-lavender), var(--color-sage));
            color: var(--color-charcoal);
            padding: 1.5rem;
            border-radius: 16px;
            margin-bottom: 2rem;
            display: flex;
            align-items: flex-start;
            gap: 1rem;
        }
        
        .info-icon {
            font-size: 1.5rem;
            flex-shrink: 0;
        }
        
        .info-content {
            font-size: 0.875rem;
            line-height: 1.5;
        }
        
        .info-content strong {
            display: block;
            margin-bottom: 0.25rem;
            font-weight: 600;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
            color: var(--color-charcoal);
            font-size: 0.875rem;
        }
        
        .form-group input {
            width: 100%;
            padding: 1rem 1.25rem;
            border: 2px solid var(--color-gray-200);
            border-radius: 12px;
            font-size: 1rem;
            font-family: 'Satoshi', sans-serif;
            background: var(--color-white);
            transition: all 0.3s ease;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--color-emerald);
            box-shadow: 0 0 0 3px rgba(22, 122, 96, 0.1);
        }
        
        .btn-submit {
            width: 100%;
            padding: 1.25rem 2rem;
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Satoshi', sans-serif;
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
            margin-bottom: 1.5rem;
        }
        
        .btn-submit:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }
        
        .btn-submit span {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }
        
        .auth-links {
            text-align: center;
            margin-bottom: 1.5rem;
        }
        
        .back-link {
            color: var(--color-emerald);
            text-decoration: none;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        
        .back-link:hover {
            color: var(--color-sage);
        }
        
        .auth-footer {
            text-align: center;
            font-size: 0.875rem;
            color: var(--color-gray-600);
        }
        
        .auth-footer a {
            color: var(--color-emerald);
            text-decoration: none;
            font-weight: 600;
        }
        
        .auth-footer a:hover {
            color: var(--color-sage);
            text-decoration: underline;
        }
    </style>
    '''
    
    return render_template_with_header("Reset Password", content)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Password reset form and processing"""
    # Validate token first
    validation = user_auth.validate_reset_token(token)
    
    if not validation['valid']:
        content = f'''
        <div class="container" style="max-width: 400px; text-align: center;">
            <div style="font-size: 64px; margin-bottom: 20px;">❌</div>
            <h1 style="color: #dc3545; font-size: 24px; margin-bottom: 16px;">Invalid Reset Link</h1>
            <div style="font-size: 16px; color: #666; margin-bottom: 30px;">{validation['error']}</div>
            
            <div style="background: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 6px; margin: 20px 0; color: #721c24;">
                <strong>What can you do?</strong><br>
                • Request a new password reset link<br>
                • Check that you're using the latest email<br>
                • Make sure you haven't already used this link
            </div>
            
            <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 30px;">
                <a href="/forgot-password" class="btn btn-primary">Request New Reset Link</a>
                <a href="/login" class="btn btn-secondary">Back to Login</a>
            </div>
        </div>
        '''
        return render_template_with_header("Invalid Reset Link", content)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not new_password or not confirm_password:
            flash('Both password fields are required', 'error')
        elif new_password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
        else:
            result = user_auth.reset_password_with_token(token, new_password)
            
            if result['success']:
                content = '''
                <div class="container" style="max-width: 400px; text-align: center;">
                    <div style="font-size: 64px; margin-bottom: 20px;">✅</div>
                    <h1 style="color: #28a745; font-size: 24px; margin-bottom: 16px;">Password Reset Successful!</h1>
                    <div style="font-size: 16px; color: #666; margin-bottom: 30px;">Your password has been successfully updated.</div>
                    
                    <div style="background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 6px; margin: 20px 0; color: #155724;">
                        <strong>Security Note:</strong> Your password has been changed. If you didn't make this change, please contact support immediately.
                    </div>
                    
                    <a href="/login" class="btn btn-primary" style="padding: 16px 32px; font-size: 16px;">
                        Login with New Password
                    </a>
                </div>
                '''
                return render_template_with_header("Password Reset Complete", content)
            else:
                flash(result['error'], 'error')
    
    # Show password reset form
    content = f'''
    <div class="container" style="max-width: 400px;">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px;">Set New Password</h1>
        
        <div style="background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 6px; margin: 20px 0; color: #155724; text-align: center;">
            <strong>Reset password for:</strong><br>
            {validation['first_name']} ({validation['email']})
        </div>
        
        <form method="POST">
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">New Password</label>
                <input type="password" name="new_password" required minlength="6" 
                       style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;" 
                       placeholder="Enter your new password">
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Confirm New Password</label>
                <input type="password" name="confirm_password" required minlength="6" 
                       style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;" 
                       placeholder="Confirm your new password">
            </div>
            
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 12px; border-radius: 6px; margin: 20px 0; color: #856404; font-size: 14px;">
                <strong>Password Requirements:</strong><br>
                • At least 6 characters long<br>
                • Choose something secure and unique
            </div>
            
            <button type="submit" class="btn btn-primary" style="width: 100%; padding: 16px; font-size: 16px; margin-top: 10px;">
                Update Password
            </button>
        </form>
        
        <div style="text-align: center; margin-top: 20px; font-size: 14px;">
            <a href="/login" style="color: #167a60; text-decoration: none;">Back to Login</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Set New Password", content)

# ============================================================================
# ROUTES - DASHBOARD & MATCHING
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard - shows existing matches or profile setup option"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if not user_info:
        flash('Account information not found', 'error')
        return redirect('/login')
    
    if user_info['profile_completed']:
        matches = user_auth.get_user_matches(user_id)
        
        # Track dashboard view
        if interaction_tracker:
            interaction_tracker.track_profile_view(user_id, None, 0)
        
        if matches:
            # Show matches
            content = render_matches_dashboard(user_info, matches)
        else:
            # No matches found
            content = render_no_matches_dashboard()
    else:
        # No profile completed yet
        content = render_new_profile_dashboard()
    
    return render_template_with_header("Dashboard", content, user_info)

def render_matches_dashboard(user_info: Dict, matches: List[Dict]) -> str:
    """Render dashboard with designer styling and beautiful typography"""
    user_id = session['user_id']
    matches_html = ""
    
    for i, match in enumerate(matches, 1):
        # Enhanced compatibility badges with new colors
        compatibility_badges = ""
        
        # Neural network confidence badge
        neural_score = match.get('neural_score', 0)
        data_confidence = match.get('data_confidence', 0)
        
        if data_confidence >= 70:
            compatibility_badges += f'<span class="badge badge-ai"> Compatibility: {data_confidence}%</span>'
        
        if neural_score >= 85:
            compatibility_badges += '<span class="badge badge-neural"> High Match</span>'
        
        # Simulation insights
        sim_satisfaction = match.get('simulation_satisfaction', 0)
        if sim_satisfaction >= 80:
            compatibility_badges += '<span class="badge badge-simulation"> Simulation Verified</span>'
        
        # Traditional badges
        if match['personality_score'] >= 85:
            compatibility_badges += '<span class="badge badge-personality">Excellent Personality Match</span>'
        if match['values_score'] >= 85:
            compatibility_badges += '<span class="badge badge-values">Strong Values Alignment</span>'
        
        # Get initials for avatar
        name_parts = match['matched_user_name'].split()
        initials = name_parts[0][0] + (name_parts[-1][0] if len(name_parts) > 1 else '')
        
        # Enhanced contact button logic with new styling
        request_status = user_auth.get_request_status(user_id, match['matched_user_id'])
        if request_status == 'pending':
            contact_button = '<span class="btn btn-pending">📞 Request Pending</span>'
        elif request_status == 'accepted':
            contact_button = f'<a href="tel:{match["matched_user_phone"]}" class="btn btn-success">📞 Call {match["matched_user_phone"]}</a>'
        elif request_status == 'denied':
            contact_button = '<span class="btn btn-declined"> Request Declined</span>'
        else:
            contact_button = f'''
                <a href="/send-contact-request/{match["matched_user_id"]}" 
                   onclick="trackContactIntention({match['matched_user_id']}, {match['overall_score']})"
                   class="btn btn-primary">
                   Connect with {match['matched_user_name']}
                </a>
            '''
        
        # Enhanced scoring display with designer styling
        enhanced_scores_html = ""
        if data_confidence >= 50:
            enhanced_scores_html = f'''
            <div class="ai-scores-grid">
                <div class="ai-score-card">
                    <div class="score-label">Neural AI</div>
                    <div class="score-value">{neural_score}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: {neural_score}%;"></div>
                    </div>
                </div>
                <div class="ai-score-card">
                    <div class="score-label">Simulation</div>
                    <div class="score-value">{sim_satisfaction}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: {sim_satisfaction}%;"></div>
                    </div>
                </div>
                <div class="ai-score-card">
                    <div class="score-label">Confidence</div>
                    <div class="score-value">{data_confidence}</div>
                    <div class="score-bar">
                        <div class="score-fill" style="width: {data_confidence}%;"></div>
                    </div>
                </div>
            </div>
            '''
        
        match_html = f'''
        <div class="match-card" data-match-id="{match['matched_user_id']}" onmouseenter="trackMatchView({match['matched_user_id']})">
            <div class="match-number">{i}</div>
            
            <div class="match-header">
                <div class="avatar">{initials}</div>
                <div class="match-info">
                    <div class="match-name">{match['matched_user_name']}</div>
                    
                </div>
            </div>
            
            <div class="compatibility-score">
                <div class="score-circle">
                    <div class="score-number">{match['overall_score']}%</div>
                    <div class="score-text">Overall Compatibility</div>
                </div>
            </div>
            
            {enhanced_scores_html}
            
            <div class="compatibility-badges">
                {compatibility_badges}
            </div>
            
            <div class="detailed-scores">
                <div class="score-item">
                    <div class="score-category">Personality</div>
                    <div class="score-value-small">{match['personality_score']}</div>
                    <div class="score-bar-small">
                        <div class="score-fill-small" style="width: {match['personality_score']}%;"></div>
                    </div>
                </div>
                <div class="score-item">
                    <div class="score-category">Values</div>
                    <div class="score-value-small">{match.get('values_score', 75)}</div>
                    <div class="score-bar-small">
                        <div class="score-fill-small" style="width: {match.get('values_score', 75)}%;"></div>
                    </div>
                </div>
                <div class="score-item">
                    <div class="score-category">Lifestyle</div>
                    <div class="score-value-small">{match.get('lifestyle_score', 75)}</div>
                    <div class="score-bar-small">
                        <div class="score-fill-small" style="width: {match.get('lifestyle_score', 75)}%;"></div>
                    </div>
                </div>
            </div>
            
            <div class="compatibility-analysis">
                {match['compatibility_analysis']}
            </div>
            
            <div class="match-actions">
                {contact_button}
            </div>
        </div>
        '''
        matches_html += match_html
    
    
    
    matches_count_section = f'''
    <div class="matches-header">
        <h1 class="matches-title">Your Matches</h1>
        <p class="matches-subtitle">We’ve simulated the dinner party for you. Here are your {len(matches)} best fits, as chosen by your agent.</p>
        <div class="profile-updated">Profile updated: {user_info['profile_date'][:10] if user_info['profile_date'] else 'Recently'}</div>
    </div>
    '''
    
    return f'''
    <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=clash-display@400,500,600,700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --color-cream: #f1ece0;
            --color-emerald: #167a60;
            --color-sage: #c6e19b;
            --color-lavender: #c2b7ef;
            --color-charcoal: #2d2d2d;
            --color-white: #ffffff;
            --color-gray-50: #fafafa;
            --color-gray-100: #f5f5f5;
            --color-gray-200: #eeeeee;
            --color-gray-600: #757575;
            --color-gray-800: #424242;
        }}
        
        .dashboard-container {{
            font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 2rem;
            background: linear-gradient(135deg, var(--color-cream) 0%, var(--color-gray-50) 100%);
            min-height: 100vh;
        }}
        
        .system-info-card {{
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            color: white;
            padding: 2rem;
            border-radius: 20px;
            margin-bottom: 3rem;
            position: relative;
            overflow: hidden;
        }}
        
        .system-info-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
            animation: shimmer 3s ease-in-out infinite;
        }}
        
        @keyframes shimmer {{
            0% {{ left: -100%; }}
            50% {{ left: 100%; }}
            100% {{ left: 100%; }}
        }}
        
        .system-info-content h3 {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0 0 0.75rem 0;
            color: white;
        }}
        
        .system-info-content p {{
            margin: 0 0 1.5rem 0;
            opacity: 0.9;
            font-size: 1rem;
            line-height: 1.6;
        }}
        
        .feature-tags {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        
        .feature-tag {{
            background: rgba(255,255,255,0.2);
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.875rem;
            font-weight: 500;
            backdrop-filter: blur(10px);
        }}
        
        .matches-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: var(--color-white);
            border-radius: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            position: relative;
        }}
        
        .matches-header::before {{
            content: '';
            position: absolute;
            top: -0.5rem;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 4px;
            background: linear-gradient(90deg, var(--color-emerald), var(--color-sage));
            border-radius: 2px;
        }}
        
        .matches-title {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: clamp(2rem, 4vw, 3rem);
            font-weight: 600;
            margin: 0 0 1rem 0;
            color: var(--color-charcoal);
            letter-spacing: -0.02em;
            line-height: 1.1;
        }}
        
        .matches-subtitle {{
            font-size: 1.125rem;
            line-height: 1.6;
            color: var(--color-gray-600);
            margin: 0 0 1rem 0;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .profile-updated {{
            font-size: 0.875rem;
            color: var(--color-gray-600);
            font-weight: 500;
        }}
        
        .match-card {{
            background: var(--color-white);
            border-radius: 24px;
            padding: 2.5rem;
            margin: 2rem 0;
            box-shadow: 
                0 1px 3px rgba(0,0,0,0.04),
                0 8px 24px rgba(0,0,0,0.08);
            position: relative;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 4px solid var(--color-sage);
        }}
        
        .match-card:hover {{
            transform: translateY(-4px);
            box-shadow: 
                0 4px 12px rgba(0,0,0,0.08),
                0 16px 48px rgba(0,0,0,0.12);
        }}
        
        .match-number {{
            position: absolute;
            top: -1rem;
            left: 2rem;
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            color: white;
            border-radius: 50%;
            width: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.25rem;
            font-family: 'Clash Display', 'Satoshi', sans-serif;
        }}
        
        .match-header {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
            margin: 1rem 0 2rem 1rem;
        }}
        
        .avatar {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--color-lavender), var(--color-sage));
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--color-charcoal);
            font-size: 2rem;
            font-weight: 700;
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        }}
        
        .match-info {{
            flex: 1;
        }}
        
        .match-name {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            color: var(--color-charcoal);
        }}
        
        .match-subtitle {{
            font-size: 0.875rem;
            color: var(--color-gray-600);
            font-weight: 500;
        }}
        
        .compatibility-score {{
            text-align: center;
            margin: 2rem 0;
        }}
        
        .score-circle {{
            display: inline-block;
            padding: 2rem;
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            border-radius: 20px;
            color: white;
            min-width: 200px;
        }}
        
        .score-number {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 3rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
        }}
        
        .score-text {{
            font-size: 1rem;
            font-weight: 500;
            opacity: 0.9;
        }}
        
        .ai-scores-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
            padding: 2rem;
            background: linear-gradient(135deg, var(--color-charcoal), var(--color-gray-800));
            border-radius: 16px;
        }}
        
        .ai-score-card {{
            text-align: center;
            color: white;
        }}
        
        .score-label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            opacity: 0.8;
            font-weight: 600;
        }}
        
        .score-value {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 0.75rem;
        }}
        
        .score-bar {{
            width: 100%;
            height: 4px;
            background: rgba(255,255,255,0.2);
            border-radius: 2px;
            overflow: hidden;
        }}
        
        .score-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--color-sage), var(--color-lavender));
            border-radius: 2px;
            transition: width 1s ease;
        }}
        
        .compatibility-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin: 2rem 0;
            justify-content: center;
        }}
        
        .badge {{
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .badge-ai {{
            background: var(--color-lavender);
            color: var(--color-charcoal);
        }}
        
        .badge-neural {{
            background: var(--color-emerald);
            color: white;
        }}
        
        .badge-simulation {{
            background: var(--color-sage);
            color: var(--color-charcoal);
        }}
        
        .badge-personality {{
            background: var(--color-cream);
            color: var(--color-charcoal);
            border: 1px solid var(--color-gray-200);
        }}
        
        .badge-values {{
            background: var(--color-cream);
            color: var(--color-charcoal);
            border: 1px solid var(--color-gray-200);
        }}
        
        .detailed-scores {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
            padding: 2rem;
            background: var(--color-gray-50);
            border-radius: 16px;
        }}
        
        .score-item {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        .score-category {{
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--color-charcoal);
            min-width: 80px;
        }}
        
        .score-value-small {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--color-charcoal);
            min-width: 40px;
        }}
        
        .score-bar-small {{
            flex: 1;
            height: 6px;
            background: var(--color-gray-200);
            border-radius: 3px;
            overflow: hidden;
        }}
        
        .score-fill-small {{
            height: 100%;
            background: linear-gradient(90deg, var(--color-emerald), var(--color-sage));
            border-radius: 3px;
            transition: width 1s ease;
        }}
        
        .compatibility-analysis {{
            background: var(--color-white);
            padding: 2rem;
            border-radius: 16px;
            margin: 2rem 0;
            border-left: 4px solid var(--color-emerald);
            font-size: 1rem;
            line-height: 1.6;
            color: var(--color-gray-800);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        
        .match-actions {{
            text-align: center;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid var(--color-gray-200);
        }}
        
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 2rem;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none;
            cursor: pointer;
            font-family: 'Satoshi', sans-serif;
        }}
        
        .btn-primary {{
            background: var(--color-emerald);
            color: white;
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
        }}
        
        .btn-primary:hover {{
            background: #0f5942;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }}
        
        .btn-pending {{
            background: var(--color-lavender);
            color: var(--color-charcoal);
        }}
        
        .btn-success {{
            background: var(--color-sage);
            color: var(--color-charcoal);
            text-decoration: none;
        }}
        
        .btn-success:hover {{
            background: #9ac463;
            transform: translateY(-2px);
        }}
        
        .btn-declined {{
            background: var(--color-gray-200);
            color: var(--color-gray-600);
        }}
        
        @media (max-width: 768px) {{
            .dashboard-container {{
                padding: 1rem;
            }}
            
            .match-card {{
                padding: 2rem 1.5rem;
            }}
            
            .match-header {{
                flex-direction: column;
                text-align: center;
                gap: 1rem;
            }}
            
            .ai-scores-grid {{
                grid-template-columns: 1fr;
            }}
            
            .detailed-scores {{
                grid-template-columns: 1fr;
            }}
            
            .compatibility-badges {{
                justify-content: center;
            }}
        }}
    </style>
    
    <div class="dashboard-container">
        {matches_count_section}
        {matches_html}
        
        <script>
        let viewStartTimes = {{}};
        
        function trackMatchView(matchUserId) {{
            if (!viewStartTimes[matchUserId]) {{
                viewStartTimes[matchUserId] = Date.now();
                
                // Track after 3 seconds of viewing
                setTimeout(() => {{
                    if (viewStartTimes[matchUserId]) {{
                        const timeSpent = (Date.now() - viewStartTimes[matchUserId]) / 1000;
                        fetch('/api/track-interaction', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                interaction_type: 'profile_view',
                                target_user_id: matchUserId,
                                time_spent: timeSpent
                            }})
                        }});
                    }}
                }}, 3000);
            }}
        }}
        
        function trackContactIntention(matchUserId, compatibilityScore) {{
            fetch('/api/track-interaction', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    interaction_type: 'contact_intention',
                    target_user_id: matchUserId,
                    compatibility_score: compatibilityScore
                }})
            }});
        }}
        </script>
    </div>
    '''

def render_no_matches_dashboard() -> str:
    """Render no matches dashboard with designer styling"""
    return '''
    <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=clash-display@400,500,600,700&display=swap" rel="stylesheet">
    <style>
        :root {
            --color-cream: #f1ece0;
            --color-emerald: #167a60;
            --color-sage: #c6e19b;
            --color-lavender: #c2b7ef;
            --color-charcoal: #2d2d2d;
            --color-white: #ffffff;
            --color-gray-50: #fafafa;
            --color-gray-600: #757575;
        }
        
        .no-matches-container {
            font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 2rem;
            text-align: center;
            background: linear-gradient(135deg, var(--color-cream) 0%, var(--color-gray-50) 100%);
            min-height: 80vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        .no-matches-card {
            background: var(--color-white);
            padding: 3rem 2rem;
            border-radius: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        }
        
        .no-matches-icon {
            font-size: 4rem;
            margin-bottom: 2rem;
        }
        
        .no-matches-title {
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 2rem;
            font-weight: 600;
            color: var(--color-emerald);
            margin-bottom: 1.5rem;
        }
        
        .no-matches-text {
            font-size: 1rem;
            line-height: 1.6;
            color: var(--color-gray-600);
            margin-bottom: 2rem;
        }
        
        .reasons-list {
            text-align: left;
            margin: 2rem 0;
            padding: 2rem;
            background: var(--color-gray-50);
            border-radius: 16px;
        }
        
        .reason-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin: 1rem 0;
            font-size: 0.875rem;
            color: var(--color-gray-600);
        }
        
        .reason-bullet {
            width: 8px;
            height: 8px;
            background: var(--color-sage);
            border-radius: 50%;
            flex-shrink: 0;
        }
        
        .btn-update {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--color-emerald);
            color: white;
            padding: 1rem 2rem;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
        }
        
        .btn-update:hover {
            background: #0f5942;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }
    </style>
    
    <div class="no-matches-container">
        <div class="no-matches-card">
            <div class="no-matches-icon">🔍</div>
            <h3 class="no-matches-title">No Matches Found Yet</h3>
            <div class="no-matches-text">
                We couldn't find compatible matches based on your current profile. This might be because:
            </div>
            
            <div class="reasons-list">
                <div class="reason-item">
                    <div class="reason-bullet"></div>
                    <span>There aren't many users in your area yet</span>
                </div>
                <div class="reason-item">
                    <div class="reason-bullet"></div>
                    <span>Your specific preferences are very particular</span>
                </div>
                <div class="reason-item">
                    <div class="reason-bullet"></div>
                    <span>More users need to join the platform</span>
                </div>
            </div>
            
            <div class="no-matches-text">
                Try updating your profile or check back later as more people join!
            </div>
            
            <a href="/profile-setup" class="btn-update">
                 Update Your Profile
            </a>
        </div>
    </div>
    '''

def render_new_profile_dashboard() -> str:
    """Render dashboard for new users without profile"""
    return '''
    <div class="container">
        <div style="text-align: center; margin-bottom: 40px; padding: 30px; background: #f4f2eb; border-radius: 15px; border: 2px solid #167a60;">
            <div style="font-size: 28px; font-weight: bold; margin-bottom: 15px;">Ready to Find Your Perfect Matches?</div>
            <p style="font-size: 18px; margin: 0;">Let's create your profile to start matching.</p>
        </div>
        
        <div style="font-size: 16px; margin-bottom: 32px;">
            We'll ask you about your interests, values, personality, and what you're looking for in a connection. This helps us find people who are truly compatible with you based on shared interests, lifestyle, and relationship goals.
        </div>
        
        <div style="background: #e8f4fd; border-radius: 6px; padding: 16px; margin: 24px 0; font-size: 14px;">
            <strong>Your Privacy is Protected</strong><br>
            All matching is done securely and you have full control over who can see your profile and contact you.
        </div>
        
        <div style="text-align: center;">
            <a href="/profile-setup" class="btn btn-primary" style="padding: 16px 32px; font-size: 16px;">
                Create Your Profile (5 minutes)
            </a>
        </div>
    </div>
    '''

def generate_agents_metadata_for_user(current_user_id):
    """Generate agents metadata with real user data for 3D visualization"""
    agents_metadata = {}
    
    try:
        # Add the current user as the main agent (emerald)
        user_info = user_auth.get_user_info(current_user_id)
        agents_metadata[current_user_id] = {
            'type': 'user',
            'name': user_info.get('first_name', 'You') if user_info else 'You'
        }
        
        # Get other real users from the database
        other_users = user_auth.get_random_users(limit=15, exclude_user_id=current_user_id)
        
        # Add other users as agents (charcoal)
        for user in other_users:
            user_id = user.get('user_id')
            first_name = user.get('first_name', 'Anonymous')
            last_name = user.get('last_name', '')
            
            # Create a display name
            if first_name and last_name:
                name = f"{first_name} {last_name}"
            elif first_name:
                name = first_name
            else:
                name = f"User {user_id}"
            
            agents_metadata[user_id] = {
                'type': 'other',
                'name': name
            }
            
        print(f"Generated {len(agents_metadata)} real agents for user {current_user_id}")
        
    except Exception as e:
        print(f"Error generating agents metadata: {e}")
        
        # Fallback: create some demo agents if database query fails
        for i in range(1, 16):
            if i != current_user_id:
                agents_metadata[i] = {
                    'type': 'other',
                    'name': f'Agent {i}'
                }
    
    return agents_metadata
# ============================================================================
# ROUTES - PROFILE SETUP & ONBOARDING
# ============================================================================

@app.route('/profile-setup')
@login_required 
def profile_setup():
    """Redirect to first step of onboarding"""
    return redirect('/onboarding/step/1')

@app.route('/onboarding/step/<int:step>')
@login_required
def onboarding_step(step):
    """Multi-step onboarding flow"""
    user_id = session['user_id']
    existing_profile = user_auth.get_user_profile(user_id) or {}
    session['onboarding_step'] = step
    
    # Define step configuration
    steps_config = {
        1: {'title': 'Basic Information', 'description': 'Tell us about yourself'},
        2: {'title': 'Core Personality', 'description': 'How you approach life and relationships'},
        3: {'title': 'Social Exchange', 'description': 'How you give and receive in friendships'},
        4: {'title': 'Values & Worldview', 'description': 'What matters most to you'},
        5: {'title': 'Lifestyle & Activities', 'description': 'Your daily rhythms and interests'},
        6: {'title': 'Emotional Intelligence', 'description': 'How you process emotions and stress'},
        7: {'title': 'Social Boundaries', 'description': 'Your interaction style preferences'},
        8: {'title': 'Compatibility Preferences', 'description': 'What you value in friendships'},
        9: {'title': 'Social Context', 'description': 'Your current social situation'},
        10: {'title': 'Final Details', 'description': 'Logistics and personal touches'}
    }
    
    if step not in steps_config:
        return redirect('/onboarding/step/1')
    
    step_content = render_onboarding_step_content(step, existing_profile)
    config = steps_config[step]
    
    return render_onboarding_template(
        step=step,
        total_steps=10,
        step_title=config['title'],
        step_description=config['description'],
        step_content=step_content,
        profile=existing_profile,
        is_last_step=(step == 10)
    )

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Enhanced profile editing with privacy controls"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if request.method == 'POST':
        # Handle form submission
        try:
            # Update basic user info
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            
            # Update user table
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET email = ?, phone = ?, first_name = ?, last_name = ?
                WHERE id = ?
            ''', (email, phone, first_name, last_name, user_id))
            
            # Get existing profile data
            existing_profile = user_auth.get_user_profile(user_id) or {}
            
            # Update profile data
            existing_profile.update({
                'bio': request.form.get('bio', '').strip(),
                'location': request.form.get('location', '').strip(),
                'postcode': request.form.get('postcode', '').strip(),
                'profile_photo_url': request.form.get('profile_photo_url', '').strip(),
                
                # Privacy settings - what sections can be shared
                'privacy_settings': {
                    'share_personality_scores': 'share_personality_scores' in request.form,
                    'share_values_scores': 'share_values_scores' in request.form,
                    'share_lifestyle_info': 'share_lifestyle_info' in request.form,
                    'share_social_preferences': 'share_social_preferences' in request.form,
                    'share_contact_info': 'share_contact_info' in request.form,
                    'share_detailed_analysis': 'share_detailed_analysis' in request.form,
                    'share_bio': 'share_bio' in request.form,
                    'share_photo': 'share_photo' in request.form,
                    'share_exact_location': 'share_exact_location' in request.form,
                    'share_age': 'share_age' in request.form
                }
            })
            
            # Save updated profile
            user_auth.save_user_profile(user_id, existing_profile)
            
            conn.commit()
            conn.close()
            
            flash('Profile updated successfully!', 'success')
            return redirect('/edit-profile')
            
        except Exception as e:
            print(f"Error updating profile: {e}")
            flash('Error updating profile. Please try again.', 'error')
    
    # GET request - show edit form
    existing_profile = user_auth.get_user_profile(user_id) or {}
    privacy_settings = existing_profile.get('privacy_settings', {})
    
    content = f'''
    <div class="container" style="max-width: 800px;">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px;">Edit Your Profile</h1>
        
        <form method="POST" enctype="multipart/form-data">
            <!-- Basic Information Section -->
            <div style="background: #f8f9fa; border-radius: 8px; padding: 25px; margin-bottom: 30px; border-left: 4px solid #167a60;">
                <h3 style="margin-top: 0; color: #167a60;">Basic Information</h3>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 500;">First Name</label>
                        <input type="text" name="first_name" value="{user_info.get('first_name', '')}" required
                               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    </div>
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Last Name</label>
                        <input type="text" name="last_name" value="{user_info.get('last_name', '')}" required
                               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    </div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">Email Address</label>
                    <input type="email" name="email" value="{user_info.get('email', '')}" required
                           style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">Phone Number</label>
                    <input type="tel" name="phone" value="{user_info.get('phone', '')}" required
                           style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    <div style="font-size: 12px; color: #666; margin-top: 4px;">Used for contact requests when matches want to connect</div>
                </div>
                
                <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Location (City/Area)</label>
                        <input type="text" name="location" value="{existing_profile.get('location', '')}" required
                               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    </div>
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Postcode</label>
                        <input type="text" name="postcode" value="{existing_profile.get('postcode', '')}" required
                               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    </div>
                </div>
            </div>
            
            <!-- Bio Section -->
            <div style="background: #f8f9fa; border-radius: 8px; padding: 25px; margin-bottom: 30px; border-left: 4px solid #28a745;">
                <h3 style="margin-top: 0; color: #28a745;">About You</h3>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">Bio / Personal Description</label>
                    <textarea name="bio" rows="4" placeholder="Tell potential matches about yourself, your interests, what you're looking for in a friendship..."
                              style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white; resize: vertical;">{existing_profile.get('bio', '')}</textarea>
                    <div style="font-size: 12px; color: #666; margin-top: 4px;">This helps matches get to know you better before connecting</div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; font-weight: 500;">Profile Photo URL (Optional)</label>
                    <input type="url" name="profile_photo_url" value="{existing_profile.get('profile_photo_url', '')}"
                           placeholder="https://example.com/your-photo.jpg"
                           style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; background: white;">
                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                        Upload your photo to a service like Imgur, Google Drive (public), or use a social media photo URL
                    </div>
                    {render_photo_preview(existing_profile.get('profile_photo_url', ''))}
                </div>
            </div>
            
            
            <!-- Action Buttons -->
            <div style="display: flex; gap: 15px; justify-content: center; margin-top: 40px;">
                <a href="/dashboard" class="btn btn-secondary" style="padding: 16px 32px;">Cancel</a>
                <button type="submit" class="btn btn-primary" style="padding: 16px 32px; font-size: 16px;">
                    Save Changes
                </button>
            </div>
        </form>
        
        <!-- Re-run Matching Section -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 8px; margin-top: 40px; text-align: center;">
            <h3 style="margin-top: 0; color: white;">Want New Matches?</h3>
            <p style="margin-bottom: 20px; opacity: 0.9;">
                If you've made significant changes to your profile, you can re-run the AI matching system to find new compatible users.
            </p>
            
        </div>
    </div>
    
    <script>
        // Photo preview functionality
        function updatePhotoPreview() {{
            const url = document.querySelector('input[name="profile_photo_url"]').value;
            const preview = document.getElementById('photo-preview');
            
            if (url ) {{
                preview.innerHTML = `
                    <div style="margin-top: 10px;">
                        <div style="font-size: 12px; color: #666; margin-bottom: 5px;">Preview:</div>
                        <img src="${{url}}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px; border: 2px solid #ddd;" 
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; padding: 10px; background: #f8d7da; color: #721c24; border-radius: 4px; font-size: 12px;">
                            Could not load image. Please check the URL.
                        </div>
                    </div>
                `;
            }} else if (url) {{
                preview.innerHTML = `
                    <div style="margin-top: 10px; padding: 8px; background: #fff3cd; color: #856404; border-radius: 4px; font-size: 12px;">
                        Please enter a direct image URL (ending in .jpg, .png, etc.)
                    </div>
                `;
            }} else {{
                preview.innerHTML = '';
            }}
        }}
        
        // Add event listener to photo URL input
        document.querySelector('input[name="profile_photo_url"]').addEventListener('input', updatePhotoPreview);
        
        // Initial preview load
        updatePhotoPreview();
    </script>
    '''
    
    return render_template_with_header("Edit Profile", content, user_info)

def render_privacy_checkbox(name: str, label: str, privacy_settings: dict, default: bool = True) -> str:
    """Render a privacy setting checkbox"""
    checked = 'checked' if privacy_settings.get(name, default) else ''
    return f'''
    <div style="display: flex; align-items: center; margin-bottom: 10px;">
        <input type="checkbox" name="{name}" {checked} 
               style="margin-right: 8px; transform: scale(1.2);">
        <label style="margin: 0; font-size: 14px; cursor: pointer; flex: 1;">{label}</label>
    </div>
    '''

def render_photo_preview(photo_url: str) -> str:
    """Render photo preview if URL exists"""
    if photo_url and photo_url.strip():
        return f'''
        <div id="photo-preview" style="margin-top: 10px;">
            <div style="font-size: 12px; color: #666; margin-bottom: 5px;">Current photo:</div>
            <img src="{photo_url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px; border: 2px solid #ddd;" 
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div style="display: none; padding: 10px; background: #f8d7da; color: #721c24; border-radius: 4px; font-size: 12px;">
                Could not load current image.
            </div>
        </div>
        '''
    else:
        return '<div id="photo-preview"></div>'



# Also update the dashboard to show profile photo and respect privacy settings
def render_enhanced_match_card(match: Dict, index: int) -> str:
    """Enhanced match card that respects privacy settings"""
    privacy = match.get('privacy_settings', {})
    
    # Get match's profile data
    match_profile = {}
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT profile_data FROM user_profiles WHERE user_id = ?', (match['matched_user_id'],))
        result = cursor.fetchone()
        if result:
            match_profile = json.loads(result[0])
        conn.close()
    except:
        pass
    
    privacy_settings = match_profile.get('privacy_settings', {})
    
    # Profile photo or initials
    if privacy_settings.get('share_photo', True) and match_profile.get('profile_photo_url'):
        profile_image = f'''
            <img src="{match_profile['profile_photo_url']}" 
                 style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid #167a60;"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div style="display: none; width: 80px; height: 80px; border-radius: 50%; background: linear-gradient(135deg, #167a60, #c6e19b); display: flex; align-items: center; justify-content: center; color: white; font-size: 32px; font-weight: 600;">
                {get_initials(match['matched_user_name'])}
            </div>
        '''
    else:
        profile_image = f'''
            <div style="width: 80px; height: 80px; border-radius: 50%; background: linear-gradient(135deg, #167a60, #c6e19b); display: flex; align-items: center; justify-content: center; color: white; font-size: 32px; font-weight: 600;">
                {get_initials(match['matched_user_name'])}
            </div>
        '''
    
    # Bio section
    bio_section = ""
    if privacy_settings.get('share_bio', True) and match_profile.get('bio'):
        bio_section = f'''
            <div style="background: white; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #28a745;">
                <div style="font-size: 14px; color: #666; margin-bottom: 5px;">About {match['matched_user_name'].split()[0]}:</div>
                <div style="color: #333; line-height: 1.5;">{match_profile['bio']}</div>
            </div>
        '''
    
    # Detailed scores (respect privacy)
    detailed_scores = ""
    if privacy_settings.get('share_personality_scores', True):
        detailed_scores = f'''
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin: 15px 0;">
                <div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 5px;">Personality</div>
                    <div style="font-size: 20px; font-weight: bold; color: #167a60;">{match['personality_score']}</div>
                </div>
                <div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 5px;">Values</div>
                    <div style="font-size: 20px; font-weight: bold; color: #28a745;">{match['values_score']}</div>
                </div>
                <div style="text-align: center; background: white; padding: 15px; border-radius: 8px;">
                    <div style="font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 5px;">Lifestyle</div>
                    <div style="font-size: 20px; font-weight: bold; color: #17a2b8;">{match['lifestyle_score']}</div>
                </div>
            </div>
        '''
    
    return f'''
        <div style="background: #f8f9fa; border-radius: 15px; padding: 30px; margin: 25px 0; border-left: 5px solid #167a60;">
            <div style="display: flex; align-items: center; margin-bottom: 20px; gap: 20px;">
                {profile_image}
                <div>
                    <div style="font-size: 24px; font-weight: bold; margin-bottom: 5px;">{match['matched_user_name']}</div>
                    <div style="font-size: 14px; color: #666;">Compatibility Score: {match['overall_score']}%</div>
                </div>
            </div>
            
            {bio_section}
            {detailed_scores}
            
            <div style="text-align: center; margin-top: 20px;">
                <a href="/send-contact-request/{match['matched_user_id']}" 
                   style="background: #167a60; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">
                   📞 Request Contact
                </a>
            </div>
        </div>
    '''

def get_initials(name: str) -> str:
    """Get initials from name"""
    parts = name.split()
    if len(parts) >= 2:
        return parts[0][0] + parts[-1][0]
    return parts[0][0] if parts else "?"

def render_onboarding_template(step, total_steps, step_title, step_description, step_content, profile, is_last_step):
    """Render onboarding template with navigation"""
    progress_percent = (step / total_steps) * 100
    
    prev_button = f'<button type="submit" name="action" value="previous" class="btn btn-secondary">← Previous</button>' if step > 1 else ''
    
    if is_last_step:
        next_button = '<button type="submit" name="action" value="complete" class="btn" style="background: #28a745; color: white;">Complete Profile & Find Matches</button>'
    else:
        next_button = '<button type="submit" name="action" value="next" class="btn btn-primary">Next →</button>'
    
    content = f'''
    <div class="container">
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 14px; color: #666; margin-bottom: 10px;">Step {step} of {total_steps}</div>
            <h1 style="font-size: 28px; font-weight: 600; margin-bottom: 8px;">{step_title}</h1>
            <div style="font-size: 16px; color: #666; margin-bottom: 20px;">{step_description}</div>
            
            <div style="background: #f2f2f2; border-radius: 10px; height: 8px; margin: 20px 0; overflow: hidden;">
                <div style="background: linear-gradient(90deg, #167a60, #a29bfe); height: 100%; border-radius: 10px; width: {progress_percent}%;"></div>
            </div>
        </div>
        
        <form method="POST" action="/onboarding/save-step">
            <div style="margin: 30px 0;">
                {step_content}
            </div>
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;">
                <div>{prev_button}</div>
                <div>{next_button}</div>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header(f"Step {step}: {step_title}", content)

def render_onboarding_step_content(step: int, profile: Dict) -> str:
    """Render content for specific onboarding step"""
    if step == 1:
        return render_step_1_content(profile)
    elif step == 2:
        return render_step_2_content(profile)
    elif step == 3:
        return render_step_3_content(profile)
    elif step == 4:
        return render_step_4_content(profile)
    elif step == 5:
        return render_step_5_content(profile)
    elif step == 6:
        return render_step_6_content(profile)
    elif step == 7:
        return render_step_7_content(profile)
    elif step == 8:
        return render_step_8_content(profile)
    elif step == 9:
        return render_step_9_content(profile)
    elif step == 10:
        return render_step_10_content(profile)
    else:
        return '<div>Invalid step</div>'

def render_step_1_content(profile: Dict) -> str:
    """Basic Information step"""
    return f'''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Let's start with the basics!</strong><br>
        This information helps us find people in your area and ensures you're matched with the right people.
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Age</label>
        <input type="number" name="age" required min="18" max="100" 
               value="{profile.get('age', '')}" placeholder="Enter your age"
               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Gender</label>
        <select name="gender" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="">Select your gender</option>
            <option value="woman" {"selected" if profile.get('gender') == 'woman' else ""}>Woman</option>
            <option value="man" {"selected" if profile.get('gender') == 'man' else ""}>Man</option>
            <option value="non_binary" {"selected" if profile.get('gender') == 'non_binary' else ""}>Non-binary</option>
            <option value="prefer_not_to_say" {"selected" if profile.get('gender') == 'prefer_not_to_say' else ""}>Prefer not to say</option>
        </select>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Looking to connect with</label>
        <select name="gender_preference" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="">Select preference</option>
            <option value="women" {"selected" if profile.get('gender_preference') == 'women' else ""}>Women</option>
            <option value="men" {"selected" if profile.get('gender_preference') == 'men' else ""}>Men</option>
            <option value="non_binary" {"selected" if profile.get('gender_preference') == 'non_binary' else ""}>Non-binary people</option>
            <option value="all" {"selected" if profile.get('gender_preference') == 'all' else ""}>All genders</option>
        </select>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Location (City/Area)</label>
        <input type="text" name="location" required
               value="{profile.get('location', '')}"
               placeholder="e.g., London, Manchester, Brighton"
               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Postcode (for distance calculations)</label>
        <input type="text" name="postcode" required
               value="{profile.get('postcode', '')}"
               placeholder="e.g., SW3 4HN"
               style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
    </div>
    '''

def render_slider_component(label: str, name: str, left_label: str, right_label: str, value: int = 5) -> str:
    """Render a slider component"""
    return f'''
    <style>
        input[type=range] {{
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: linear-gradient(to right, #167a60 0%, #167a60 {(value-1)*11}% , #ddd {(value-1)*11}%, #ddd 100%);
            outline: none;
        }}
        input[type=range]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #167a60; /* Pont green thumb */
            cursor: pointer;
            border: none;
            margin-top: -6px; /* align thumb with track */
        }}
        input[type=range]::-moz-range-thumb {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #167a60; /* Pont green thumb */
            cursor: pointer;
            border: none;
        }}
    </style>

    <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;">
        <div style="font-weight: 500; margin-bottom: 15px;">{label}</div>
        <div style="position: relative; margin: 20px 0;">
            <input type="range" min="1" max="10" value="{value}" name="{name}" 
                   oninput="this.style.background = 
                       'linear-gradient(to right, #167a60 0%, #167a60 ' + 
                       ((this.value-1)*11) + '%, #ddd ' + 
                       ((this.value-1)*11) + '%, #ddd 100%)'">
            <div style="display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: #2d2d2d;">
                <span>{left_label}</span>
                <span>{right_label}</span>
            </div>
        </div>
    </div>
    '''

def render_step_2_content(profile: Dict) -> str:
    """Core Personality step"""
    content = '''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Core Personality Architecture</strong><br>
        These unique psychological dimensions help us understand your friendship compatibility style.
    </div>
    '''
    
    sliders = [
        ('Decision-making style', 'decision_making', 'Logic-driven', 'Emotion-driven'),
        ('Social energy preference', 'social_energy', 'Intimate connections', 'Wide social circles'),
        ('Communication depth', 'communication_depth', 'Surface-level fun', 'Deep conversations'),
        ('Conflict approach', 'conflict_approach', 'Direct confrontation', 'Gentle discussion'),
        ('Life pace preference', 'life_pace', 'Structured routine', 'Spontaneous flow')
    ]
    
    for label, name, left, right in sliders:
        value = profile.get(name, 5)
        content += render_slider_component(label, name, left, right, value)
    
    return content

def render_step_3_content(profile: Dict) -> str:
    """Social Exchange step"""
    return f'''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Social Exchange Patterns</strong><br>
        Understanding how you give and receive in friendships helps us find complementary matches.
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Your friendship superpower (Choose one)</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_radio_options("friendship_superpower", [
                ("making_people_laugh", "Making people laugh"),
                ("giving_thoughtful_advice", "Giving thoughtful advice"),
                ("planning_amazing_experiences", "Planning amazing experiences"),
                ("being_reliable_listener", "Being a reliable listener"),
                ("bringing_diverse_perspectives", "Bringing diverse perspectives"),
                ("creating_safe_emotional_space", "Creating safe emotional space")
            ], profile.get('friendship_superpower', ''))}
        </div>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">When friends are struggling, you typically:</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_radio_options("friend_support_style", [
                ("offer_practical_solutions", "Offer practical solutions"),
                ("provide_emotional_support", "Provide emotional support"),
                ("give_space_to_process", "Give them space to process"),
                ("distract_with_fun", "Distract them with fun activities"),
                ("share_similar_experiences", "Share similar experiences"),
                ("connect_with_resources", "Connect them with resources")
            ], profile.get('friend_support_style', ''))}
        </div>
    </div>
    
    {render_slider_component("Friend maintenance energy", "friend_maintenance", "High-touch regular contact", "Low-key periodic connection", profile.get('friend_maintenance', 5))}
    '''

def render_radio_options(name: str, options: List[Tuple[str, str]], selected: str = '') -> str:
    """Render radio button options"""
    html = ""
    for value, label in options:
        checked = 'checked' if value == selected else ''
        html += f'''
        <div style="display: flex; align-items: center; padding: 12px; background: white; border-radius: 4px; border: 1px solid #ddd;">
            <input type="radio" name="{name}" value="{value}" {checked} style="margin-right: 10px;">
            <label style="cursor: pointer; flex: 1; margin: 0;">{label}</label>
        </div>
        '''
    return html

# Continue with steps 4-10 content functions
def render_step_4_content(profile: Dict) -> str:
    """Values & Worldview step"""
    content = '''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Values & Worldview Alignment</strong><br>
        Understanding what drives you helps us find friends who share your fundamental outlook.
    </div>
    '''
    
    sliders = [
        ('Personal growth priority', 'personal_growth', 'Self-improvement', 'Self-acceptance'),
        ('Success definition', 'success_definition', 'External achievements', 'Internal fulfillment'),
        ('Community involvement', 'community_involvement', 'Highly engaged locally', 'Globally minded'),
        ('Work-life philosophy', 'work_life_philosophy', 'Career-focused', 'Life-balance focused'),
        ('Future orientation', 'future_orientation', 'Detailed planning', 'Present-moment living')
    ]
    
    for label, name, left, right in sliders:
        value = profile.get(name, 5)
        content += render_slider_component(label, name, left, right, value)
    
    return content

def render_step_5_content(profile: Dict) -> str:
    """Lifestyle & Activities step"""
    content = '''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Activity & Lifestyle Synchronization</strong><br>
        Your daily rhythms and activity preferences help us find friends you'll actually enjoy spending time with.
    </div>
    '''
    
    sliders = [
        ('Energy patterns', 'energy_patterns', 'Early morning active', 'Night owl active'),
        ('Social setting preference', 'social_setting', 'Home-based hangouts', 'Out-and-about adventures'),
        ('Activity investment', 'activity_investment', 'Few deep interests', 'Many varied interests'),
        ('Physical activity level', 'physical_activity', 'Low/sedentary', 'High/athletic'),
        ('Cultural consumption', 'cultural_consumption', 'Mainstream popular', 'Niche alternative')
    ]
    
    for label, name, left, right in sliders:
        value = profile.get(name, 5)
        content += render_slider_component(label, name, left, right, value)
    
    return content

def render_step_6_content(profile: Dict) -> str:
    """Emotional Intelligence step"""
    return f'''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Emotional Intelligence Mapping</strong><br>
        How you process emotions and handle stress is crucial for friendship compatibility.
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">When you're stressed, you prefer friends who:</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_radio_options("stress_preference", [
                ("give_space_until_ready", "Give you space until you're ready"),
                ("check_in_regularly_gently", "Check in regularly but gently"),
                ("actively_help_problem_solve", "Actively help problem-solve"),
                ("provide_distraction_lightness", "Provide distraction and lightness"),
                ("match_emotional_energy", "Match your emotional energy"),
                ("stay_calm_grounding", "Stay calm and grounding")
            ], profile.get('stress_preference', ''))}
        </div>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Your emotional processing style:</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_radio_options("processing_style", [
                ("think_internally_then_share", "Think through internally first, then share"),
                ("talk_through_as_they_come", "Talk through feelings as they come up"),
                ("need_time_alone_before_discussing", "Need time alone before discussing"),
                ("process_through_activities_together", "Process best through activities together"),
                ("prefer_written_text_communication", "Prefer written/text communication"),
                ("work_through_via_shared_experiences", "Work through emotions via shared experiences")
            ], profile.get('processing_style', ''))}
        </div>
    </div>
    
    {render_slider_component("Celebration preference", "celebration_preference", "Quiet acknowledgment", "Big enthusiastic celebrations", profile.get('celebration_preference', 5))}
    '''

def render_step_7_content(profile: Dict) -> str:
    """Social Boundaries step"""
    content = '''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Social Boundaries & Compatibility</strong><br>
        Understanding your comfort zones helps us match you with people who respect your style.
    </div>
    '''
    
    sliders = [
        ('Personal sharing comfort', 'personal_sharing', 'Private person', 'Open book'),
        ('Social overlap tolerance', 'social_overlap', 'Separate friend groups', 'Integrated social circles'),
        ('Advice-giving style', 'advice_giving', 'Direct honest feedback', 'Supportive validation'),
        ('Social commitment level', 'social_commitment', 'Flexible casual plans', 'Firm scheduled commitments')
    ]
    
    for label, name, left, right in sliders:
        value = profile.get(name, 5)
        content += render_slider_component(label, name, left, right, value)
    
    return content

def render_step_8_content(profile: Dict) -> str:
    """Compatibility Preferences step"""
    return f'''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Compatibility Preferences & Deal-breakers</strong><br>
        Help us understand what matters most to you in friendships and what to avoid.
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Most important friendship foundation (Rank 1-5, with 1 being most important)</label>
        <div style="margin: 20px 0;">
            {render_ranking_items([
                ("rank_shared_values", "Shared core values"),
                ("rank_lifestyle_rhythms", "Similar lifestyle rhythms"),
                ("rank_complementary_strengths", "Complementary strengths"),
                ("rank_emotional_compatibility", "Emotional compatibility"),
                ("rank_activity_overlap", "Activity/interest overlap")
            ], profile)}
        </div>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Friendship red flags (Select up to 3)</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_checkbox_options("red_flags", [
                ("consistently_self_centered", "Consistently self-centered conversations"),
                ("frequent_plan_cancellations", "Frequent plan cancellations"),
                ("gossiping_about_friends", "Gossiping about other friends"),
                ("pressuring_uncomfortable_things", "Pressuring to try things you're uncomfortable with"),
                ("making_feel_judged", "Making you feel judged for your choices"),
                ("competing_rather_celebrating", "Competing rather than celebrating your successes"),
                ("emotional_volatility_without_awareness", "Emotional volatility without self-awareness"),
                ("pushing_political_religious_views", "Pushing political/religious views")
            ], profile.get('red_flags', []))}
        </div>
    </div>
    '''

def render_ranking_items(items: List[Tuple[str, str]], profile: Dict) -> str:
    """Render ranking dropdown items"""
    html = ""
    for name, label in items:
        selected_value = profile.get(name, '')
        options = ""
        for i in range(1, 6):
            selected = 'selected' if str(i) == selected_value else ''
            options += f'<option value="{i}" {selected}>{i}</option>'
        
        html += f'''
        <div style="display: flex; align-items: center; padding: 12px; background: white; border-radius: 4px; border: 1px solid #ddd; margin: 8px 0;">
            <select name="{name}" required style="width: 60px; margin-right: 15px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="">#</option>
                {options}
            </select>
            <label style="flex: 1; margin: 0;">{label}</label>
        </div>
        '''
    return html

def render_checkbox_options(name: str, options: List[Tuple[str, str]], selected: List[str] = []) -> str:
    """Render checkbox options"""
    html = ""
    for value, label in options:
        checked = 'checked' if value in selected else ''
        html += f'''
        <div style="display: flex; align-items: center; padding: 12px; background: white; border-radius: 4px; border: 1px solid #ddd;">
            <input type="checkbox" name="{name}" value="{value}" {checked} style="margin-right: 10px;">
            <label style="cursor: pointer; flex: 1; margin: 0;">{label}</label>
        </div>
        '''
    return html

def render_step_9_content(profile: Dict) -> str:
    """Social Context step"""
    content = '''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Social Context & Goals</strong><br>
        Understanding your current social situation helps us find the right type of connections.
    </div>
    '''
    
    content += render_slider_component("Current social satisfaction", "social_satisfaction", "Very lonely", "Socially fulfilled", profile.get('social_satisfaction', 5))
    
    content += f'''
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">New friend motivation (Choose primary reason)</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_radio_options("friend_motivation", [
                ("recently_moved", "Recently moved to new area"),
                ("life_transition", "Life transition changed social needs"),
                ("activity_companions", "Want activity-specific companions"),
                ("deeper_connections", "Seeking deeper emotional connections"),
                ("friends_unavailable", "Current friends unavailable/busy"),
                ("diverse_perspectives", "Want more diverse perspectives"),
                ("outgrew_social_circle", "Outgrew current social circle")
            ], profile.get('friend_motivation', ''))}
        </div>
    </div>
    '''
    
    content += render_slider_component("Ideal friendship development", "friendship_development", "Fast deep connection", "Gradual trust building", profile.get('friendship_development', 5))
    content += render_slider_component("Social risk tolerance", "social_risk_tolerance", "Prefer safe known experiences", "Love trying new things together", profile.get('social_risk_tolerance', 5))
    
    return content

def render_step_10_content(profile: Dict) -> str:
    """Final Details step"""
    return f'''
    <div style="background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 25px; border-left: 4px solid #167a60;">
        <strong>Final Details</strong><br>
        Last step! Help us understand your practical needs and add some personal touches.
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Weekly social availability</label>
        <select name="weekly_availability" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="">Select your availability</option>
            <option value="1-2 hours" {"selected" if profile.get('weekly_availability') == '1-2 hours' else ""}>1-2 hours</option>
            <option value="3-5 hours" {"selected" if profile.get('weekly_availability') == '3-5 hours' else ""}>3-5 hours</option>
            <option value="6-10 hours" {"selected" if profile.get('weekly_availability') == '6-10 hours' else ""}>6-10 hours</option>
            <option value="10+ hours" {"selected" if profile.get('weekly_availability') == '10+ hours' else ""}>10+ hours</option>
        </select>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Transportation (Select all that apply)</label>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px;">
            {render_checkbox_options("transportation", [
                ("walk_bike", "Walk/bike"),
                ("car", "Car"),
                ("public_transit", "Public transit"),
                ("flexible", "Flexible")
            ], profile.get('transportation', []))}
        </div>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Describe your ideal friendship in one sentence:</label>
        <textarea name="ideal_friendship_description" required
                  placeholder="What would your perfect friendship look like?"
                  style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 80px; resize: vertical;">{profile.get('ideal_friendship_description', '')}</textarea>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">What's a unique interest or hobby you'd love to share with someone?</label>
        <textarea name="unique_interest" required
                  placeholder="Something special you're passionate about..."
                  style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 80px; resize: vertical;">{profile.get('unique_interest', '')}</textarea>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">What life experience has most shaped how you approach friendships?</label>
        <textarea name="life_experience_impact" required
                  placeholder="A moment or period that changed your perspective..."
                  style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 80px; resize: vertical;">{profile.get('life_experience_impact', '')}</textarea>
    </div>
    
    <div style="margin-bottom: 20px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 500;">Complete this: 'I feel most energized around people who...'</label>
        <textarea name="energized_by" required
                  placeholder="Finish this sentence..."
                  style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 80px; resize: vertical;">{profile.get('energized_by', '')}</textarea>
    </div>
    '''

@app.route('/onboarding/save-step', methods=['POST'])
@login_required
def save_onboarding_step():
    """Save current step data and redirect to next step with proper numeric conversion"""
    user_id = session['user_id']
    current_step = session.get('onboarding_step', 1)
    
    # Get existing profile data or create new
    profile_data = user_auth.get_user_profile(user_id) or {}
    
    # Define which fields should be converted to integers
    INTEGER_FIELDS = {
        'age', 'social_energy', 'decision_making', 'communication_depth',
        'personal_growth', 'social_satisfaction', 'success_definition',
        'energy_patterns', 'activity_investment', 'time_allocation',
        'relationship_priorities', 'conflict_resolution', 'emotional_support',
        'friend_maintenance', 'community_involvement', 'work_life_philosophy',
        'future_orientation', 'social_setting', 'physical_activity',
        'cultural_consumption', 'celebration_preference', 'personal_sharing',
        'social_overlap', 'advice_giving', 'social_commitment',
        'friendship_development', 'social_risk_tolerance',
        'conflict_approach', 'life_pace',
        # Ranking fields
        'rank_shared_values', 'rank_lifestyle_rhythms', 'rank_complementary_strengths',
        'rank_emotional_compatibility', 'rank_activity_overlap'
    }
    
    # Define which fields should be converted to floats (if any)
    FLOAT_FIELDS = {
        'latitude', 'longitude'  # example location fields if you add them
    }
    
    def convert_form_data(form_data):
        """Convert form data to appropriate numeric types"""
        converted_data = {}
        
        for key, value in form_data.items():
            if key.startswith('csrf_') or key in ['action']:
                continue
            elif key in INTEGER_FIELDS:
                try:
                    converted_data[key] = int(value) if value else 5  # default to 5
                except (ValueError, TypeError):
                    converted_data[key] = 5  # fallback default
            elif key in FLOAT_FIELDS:
                try:
                    converted_data[key] = float(value) if value else 0.0
                except (ValueError, TypeError):
                    converted_data[key] = 0.0
            else:
                # Keep as string for text fields
                converted_data[key] = value
        
        return converted_data
    
    # Update profile with converted form data from current step
    for key, value in request.form.items():
        if key.startswith('csrf_') or key in ['action']:
            continue
        if key in ['interests', 'personality_traits', 'red_flags', 'transportation']:
            profile_data[key] = request.form.getlist(key)
        else:
            # Convert to appropriate type
            if key in INTEGER_FIELDS:
                try:
                    profile_data[key] = int(value) if value else 5
                except (ValueError, TypeError):
                    profile_data[key] = 5
            elif key in FLOAT_FIELDS:
                try:
                    profile_data[key] = float(value) if value else 0.0
                except (ValueError, TypeError):
                    profile_data[key] = 0.0
            else:
                profile_data[key] = value
    
    # Save updated profile
    user_auth.save_user_profile(user_id, profile_data)
    
    # Handle navigation
    action = request.form.get('action', 'next')
    
    if action == 'next':
        next_step = current_step + 1
        if next_step > 10:  # Last step
            return redirect('/onboarding/complete')
        return redirect(f'/onboarding/step/{next_step}')
    elif action == 'previous':
        prev_step = max(1, current_step - 1)
        return redirect(f'/onboarding/step/{prev_step}')
    elif action == 'complete':
        return redirect('/onboarding/complete')
    
    return redirect(f'/onboarding/step/{current_step}')

@app.route('/onboarding/complete', methods=['GET', 'POST'])
@login_required
def complete_onboarding_enhanced():
    """Enhanced onboarding completion"""
    user_id = session['user_id']
    
    if request.method == 'POST':
        # Process final submission and blocked users (same as before)
        blocked_emails = request.form.get('blocked_emails', '')
        blocked_names = request.form.get('blocked_names', '')  
        blocked_phones = request.form.get('blocked_phones', '')
        
        # Clear existing blocked users
        user_auth.clear_blocked_users(user_id)
        
        # Add new blocked users and track blocking interactions
        if blocked_emails:
            for email in [e.strip() for e in blocked_emails.split(',') if e.strip()]:
                user_auth.add_blocked_user(user_id, blocked_email=email)
                # Note: We can't get user_id from email easily, so this tracking is limited
        
        if blocked_names:
            for name in [n.strip() for n in blocked_names.split(',') if n.strip()]:
                user_auth.add_blocked_user(user_id, blocked_name=name)
        
        if blocked_phones:
            for phone in [p.strip() for p in blocked_phones.split(',') if p.strip()]:
                user_auth.add_blocked_user(user_id, blocked_phone=phone)
        
        # Start enhanced background matching
        thread = threading.Thread(target=process_matching_background, args=(user_id,))
        thread.daemon = True
        thread.start()
        
        # Clear onboarding session data
        session.pop('onboarding_step', None)
        
        return redirect('/processing')
    
    # Show completion page (enhanced version)
    content = '''
    <div class="container" style="max-width: 600px; text-align: center;">
        <div style="font-size: 64px; margin-bottom: 20px;">🎉</div>
        <h1 style="font-size: 32px; font-weight: 600; color: #28a745; margin-bottom: 16px;">Profile Complete!</h1>
        <div style="font-size: 18px; color: #666; margin-bottom: 30px;">Ready for AI-powered matching</div>
        
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <h3 style="margin-bottom: 10px; color: white;">🤖 Enhanced AI Matching</h3>
            <p style="margin: 0; opacity: 0.9;">Your profile will be analyzed using neural networks and agent-based social simulation for the most accurate matches!</p>
        </div>
        
        <div style="font-size: 16px; color: #333; margin-bottom: 40px; text-align: left; background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745;">
            <strong>What happens next:</strong><br>
            •  Neural network analyzes your personality patterns<br>
            •  Social simulation finds your natural cluster<br>
            •  AI learns from community interactions<br>
            •  You get scientifically-backed compatibility matches<br>
            •  System improves with every interaction
        </div>
        
        <form method="POST">
            <div style="background: #f8f9fa; padding: 30px; border-radius: 8px; margin: 30px 0; text-align: left;">
                <h3 style="font-size: 18px; font-weight: 600; color: black; margin-bottom: 15px;">Block List (Optional)</h3>
                <div style="font-size: 14px; color: #666; margin-bottom: 20px;">
                    Exclude specific people from matching. This data is kept completely private and helps improve AI accuracy.
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; color: black; margin-bottom: 8px; font-weight: 500; font-size: 14px;">Email addresses to exclude</label>
                    <textarea name="blocked_emails"
                              placeholder="Enter email addresses separated by commas"
                              style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 60px; resize: vertical; background: white;"></textarea>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; color: black; margin-bottom: 8px; font-weight: 500; font-size: 14px;">Names to exclude</label>
                    <textarea name="blocked_names"
                              placeholder="Enter full names separated by commas"
                              style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 60px; resize: vertical; background: white;"></textarea>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; color: black; margin-bottom: 8px; font-weight: 500; font-size: 14px;">Phone numbers to exclude</label>
                    <textarea name="blocked_phones"
                              placeholder="Enter phone numbers separated by commas"
                              style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 60px; resize: vertical; background: white;"></textarea>
                </div>
            </div>
            
            <button type="submit" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 18px 36px; border-radius: 8px; font-size: 18px; font-weight: 600; cursor: pointer; margin-top: 20px;">
                🚀 Launch AI Matching
            </button>
        </form>
    </div>
    '''
    
    return render_template_with_header("Complete Profile", content)

# ============================================================================
# ROUTES - PROCESSING & RESULTS
# ============================================================================

@app.route('/processing')
@login_required
def processing():
    """Start matching and redirect to live visualization"""
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')
    
    # Start background matching with real-time updates
    thread = threading.Thread(target=process_matching_background, args=(user_id,))
    thread.daemon = True
    thread.start()
    
    return redirect(f'/live-matching/{user_id}')

@app.route('/live-matching/<int:user_id>')
@login_required
def live_matching(user_id):
    """3D neural network matching visualization"""
    if session.get('user_id') != user_id:
        return redirect('/login')
    
    # Get user info for any needed data
    user_info = user_auth.get_user_info(user_id)
    
    # The 3D matching HTML - replace the old live_matching_html variable
    live_matching_html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>3D Live Agent Simulation - Connect</title>
        <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=clash-display@400,500,600,700&display=swap" rel="stylesheet">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            :root {{
                --color-cream: #f1ece0;
                --color-emerald: #167a60;
                --color-sage: #c6e19b;
                --color-lavender: #c2b7ef;
                --color-charcoal: #2d2d2d;
                --color-white: #ffffff;
            }}
            
            body {{
                font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
                background: var(--color-cream);
                color: var(--color-charcoal);
                min-height: 100vh;
                overflow: hidden;
                cursor: move;
            }}
            
            #threejs-container {{
                width: 100vw;
                height: 100vh;
                position: relative;
                overflow: hidden;
            }}
            
            /* Status */
            .status {{
                position: absolute;
                top: 2rem;
                left: 50%;
                transform: translateX(-50%);
                z-index: 1000;
                color: var(--color-charcoal);
                font-size: 0.875rem;
                font-weight: 500;
                background: rgba(255, 255, 255, 0.9);
                padding: 0.75rem 1.25rem;
                border-radius: 8px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0,0,0,0.1);
                box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            }}
            
            /* Results Modal */
            .results-modal {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(20px);
                border-radius: 16px;
                padding: 2rem;
                max-width: 400px;
                width: 90vw;
                border: 1px solid rgba(0,0,0,0.1);
                box-shadow: 0 24px 48px rgba(0,0,0,0.2);
                display: none;
                color: var(--color-charcoal);
            }}
            
            .results-modal.visible {{
                display: block;
                animation: modalSlideIn 0.6s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            @keyframes modalSlideIn {{
                from {{ opacity: 0; transform: translate(-50%, -40%); }}
                to {{ opacity: 1; transform: translate(-50%, -50%); }}
            }}
            
            .complete-message {{
                text-align: center;
                padding: 2rem 1rem;
                color: var(--color-charcoal);
            }}
            
            .complete-message h3 {{
                font-size: 1.25rem;
                font-weight: 600;
                margin-bottom: 1rem;
            }}
            
            .complete-message p {{
                margin-bottom: 1.5rem;
                opacity: 0.8;
            }}
            
            .dashboard-link {{
                display: inline-block;
                background: var(--color-emerald);
                color: white;
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            
            .dashboard-link:hover {{
                background: #0f5942;
                transform: translateY(-1px);
            }}
            
            /* Loading */
            .loading {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: var(--color-charcoal);
                font-size: 0.875rem;
                opacity: 0.8;
                z-index: 10;
                text-align: center;
            }}
            
            .loading-spinner {{
                width: 32px;
                height: 32px;
                border: 2px solid rgba(0,0,0,0.1);
                border-radius: 50%;
                border-top-color: var(--color-emerald);
                animation: spin 1s ease-in-out infinite;
                margin: 0 auto 1rem;
            }}
            
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
            
            /* Responsive */
            @media (max-width: 768px) {{
                .status {{
                    top: 1rem;
                    font-size: 0.8rem;
                    padding: 0.5rem 1rem;
                }}
                
                .results-modal {{
                    padding: 1.5rem;
                    max-width: 350px;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Status -->
        <div class="status" id="status">
            Analyzing neural patterns...
        </div>
        
        <!-- 3D Canvas -->
        <div id="threejs-container">
            <div class="loading" id="loading">
                <div class="loading-spinner"></div>
                Initializing 3D neural space...
            </div>
        </div>
        
        <!-- Results Modal -->
        <div class="results-modal" id="resultsModal">
            <div class="complete-message">
                <h3>Neural Analysis Complete</h3>
                <p>Your matches have been calculated and are ready for review.</p>
                <a href="/dashboard" class="dashboard-link">Go to Dashboard</a>
            </div>
        </div>

        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script>
            let scene, camera, renderer, controls;
            let agents = new Map();
            let connections = [];
            let boxHelper;
            let agentsMetadata = {{}};
            let simulationCompleted = false;
            let updateInterval;
            
            const BOX_SIZE = 400;
            const USER_ID = {user_id}; // Your actual user ID
            
            // Colors from your palette
            const COLORS = {{
                user: 0x167a60,      // emerald - your agent
                other: 0x2d2d2d,     // charcoal - other agents  
                line: 0x2d2d2d,      // charcoal - connection lines (stronger)
                box: 0x757575        // gray - container box
            }};
            
            function initThreeJS() {{
                const container = document.getElementById('threejs-container');
                
                // Scene
                scene = new THREE.Scene();
                scene.background = new THREE.Color(0xf1ece0); // cream background
                
                // Camera
                camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 2000);
                camera.position.set(600, 400, 600);
                
                // Renderer
                renderer = new THREE.WebGLRenderer({{ antialias: true }});
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                container.appendChild(renderer.domElement);
                
                // Lighting
                const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
                scene.add(ambientLight);
                
                const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
                directionalLight.position.set(100, 100, 50);
                scene.add(directionalLight);
                
                // Create container box (wireframe)
                createContainerBox();
                
                // Mouse controls
                setupControls();
                
                // Hide loading
                document.getElementById('loading').style.display = 'none';
                
                // Start animation
                animate();
            }}
            
            function createContainerBox() {{
                const boxGeometry = new THREE.BoxGeometry(BOX_SIZE, BOX_SIZE, BOX_SIZE);
                const boxMaterial = new THREE.MeshBasicMaterial({{ 
                    color: COLORS.box,
                    wireframe: true,
                    transparent: true,
                    opacity: 0.2
                }});
                
                const box = new THREE.Mesh(boxGeometry, boxMaterial);
                scene.add(box);
                
                // Add wireframe helper for cleaner lines
                boxHelper = new THREE.BoxHelper(box, COLORS.box);
                boxHelper.material.transparent = true;
                boxHelper.material.opacity = 0.3;
                scene.add(boxHelper);
            }}
            
            function setupControls() {{
                let isMouseDown = false;
                let mouseX = 0, mouseY = 0;
                let targetRotationX = 0, targetRotationY = 0;
                let currentRotationX = 0, currentRotationY = 0;
                
                renderer.domElement.addEventListener('mousedown', onMouseDown);
                renderer.domElement.addEventListener('mousemove', onMouseMove);
                renderer.domElement.addEventListener('mouseup', onMouseUp);
                renderer.domElement.addEventListener('wheel', onMouseWheel);
                
                function onMouseDown(event) {{
                    isMouseDown = true;
                    mouseX = event.clientX;
                    mouseY = event.clientY;
                }}
                
                function onMouseMove(event) {{
                    if (!isMouseDown) return;
                    
                    const deltaX = event.clientX - mouseX;
                    const deltaY = event.clientY - mouseY;
                    
                    targetRotationY += deltaX * 0.01;
                    targetRotationX += deltaY * 0.01;
                    
                    mouseX = event.clientX;
                    mouseY = event.clientY;
                }}
                
                function onMouseUp() {{
                    isMouseDown = false;
                }}
                
                function onMouseWheel(event) {{
                    const zoomSpeed = 10;
                    camera.position.multiplyScalar(1 + event.deltaY * 0.001 * zoomSpeed);
                    camera.position.clampLength(200, 1500);
                }}
                
                // Smooth camera rotation in animate loop
                function updateCamera() {{
                    currentRotationX += (targetRotationX - currentRotationX) * 0.1;
                    currentRotationY += (targetRotationY - currentRotationY) * 0.1;
                    
                    const distance = camera.position.length();
                    camera.position.x = Math.cos(currentRotationY) * Math.cos(currentRotationX) * distance;
                    camera.position.y = Math.sin(currentRotationX) * distance;
                    camera.position.z = Math.sin(currentRotationY) * Math.cos(currentRotationX) * distance;
                    
                    camera.lookAt(0, 0, 0);
                }}
                
                // Store update function for animate loop
                this.updateCamera = updateCamera;
            }}
            
            function createAgent(agentId, metadata) {{
                const isUser = metadata.type === 'user';
                
                // Create sphere geometry - bigger dots
                const geometry = new THREE.SphereGeometry(isUser ? 12 : 8, 16, 16);
                
                // Create material
                let color = isUser ? COLORS.user : COLORS.other;
                const material = new THREE.MeshLambertMaterial({{
                    color: color,
                    transparent: true,
                    opacity: 0.9
                }});
                
                const sphere = new THREE.Mesh(geometry, material);
                
                // Random position within the box
                sphere.position.set(
                    (Math.random() - 0.5) * BOX_SIZE * 0.8,
                    (Math.random() - 0.5) * BOX_SIZE * 0.8,
                    (Math.random() - 0.5) * BOX_SIZE * 0.8
                );
                
                // Store metadata
                sphere.userData = {{ 
                    agentId, 
                    metadata, 
                    isUser,
                    targetPosition: sphere.position.clone(),
                    velocity: new THREE.Vector3(
                        (Math.random() - 0.5) * 2,
                        (Math.random() - 0.5) * 2,
                        (Math.random() - 0.5) * 2
                    )
                }};
                
                scene.add(sphere);
                agents.set(agentId, sphere);
                
                return sphere;
            }}
            
            function createConnection(agent1, agent2) {{
                const points = [];
                points.push(agent1.position.clone());
                points.push(agent2.position.clone());
                
                const geometry = new THREE.BufferGeometry().setFromPoints(points);
                const material = new THREE.LineBasicMaterial({{
                    color: COLORS.line,
                    transparent: true,
                    opacity: 0.8,
                    linewidth: 4
                }});
                
                const line = new THREE.Line(geometry, material);
                scene.add(line);
                
                const connection = {{
                    line: line,
                    agent1: agent1,
                    agent2: agent2,
                    createdTime: Date.now()
                }};
                
                connections.push(connection);
                
                // Fade out connection after some time
                setTimeout(() => {{
                    connection.fadeOut = true;
                }}, 4000);
                
                return line;
            }}
            
            function updateConnections() {{
                connections = connections.filter(connection => {{
                    const {{ line, agent1, agent2, fadeOut, createdTime }} = connection;
                    
                    if (fadeOut) {{
                        const age = Date.now() - createdTime;
                        const maxAge = 6000;
                        const opacity = Math.max(0, 1 - (age - 4000) / 2000);
                        
                        if (opacity <= 0) {{
                            scene.remove(line);
                            return false;
                        }}
                        
                        line.material.opacity = opacity * 0.8;
                    }}
                    
                    // Update line positions
                    const positions = line.geometry.attributes.position.array;
                    positions[0] = agent1.position.x;
                    positions[1] = agent1.position.y;
                    positions[2] = agent1.position.z;
                    positions[3] = agent2.position.x;
                    positions[4] = agent2.position.y;
                    positions[5] = agent2.position.z;
                    line.geometry.attributes.position.needsUpdate = true;
                    
                    return true;
                }});
            }}
            
            function updateAgentMovement() {{
                agents.forEach(agent => {{
                    // Move towards target position
                    agent.position.lerp(agent.userData.targetPosition, 0.02);
                    
                    // Add continuous movement within the box
                    const velocity = agent.userData.velocity;
                    agent.position.add(velocity);
                    
                    // Bounce off walls
                    const halfBox = BOX_SIZE * 0.4;
                    if (Math.abs(agent.position.x) > halfBox) {{
                        velocity.x *= -1;
                        agent.position.x = Math.sign(agent.position.x) * halfBox;
                    }}
                    if (Math.abs(agent.position.y) > halfBox) {{
                        velocity.y *= -1;
                        agent.position.y = Math.sign(agent.position.y) * halfBox;
                    }}
                    if (Math.abs(agent.position.z) > halfBox) {{
                        velocity.z *= -1;
                        agent.position.z = Math.sign(agent.position.z) * halfBox;
                    }}
                    
                    // Update target position for natural movement
                    agent.userData.targetPosition.copy(agent.position);
                    
                    // Check for interactions with other agents
                    agents.forEach(otherAgent => {{
                        if (agent !== otherAgent) {{
                            const distance = agent.position.distanceTo(otherAgent.position);
                            if (distance < 50 && Math.random() < 0.01) {{ // Random interaction
                                createConnection(agent, otherAgent);
                            }}
                        }}
                    }});
                }});
            }}
            
            function animate() {{
                requestAnimationFrame(animate);
                
                // Update camera rotation
                if (this.updateCamera) {{
                    this.updateCamera();
                }}
                
                // Update agent movement
                updateAgentMovement();
                
                // Update connections
                updateConnections();
                
                renderer.render(scene, camera);
            }}
            
            // Real simulation logic - replace with your actual API calls
            function startRealTimeUpdates() {{
                updateInterval = setInterval(fetchLiveStatus, 1000);
                fetchLiveStatus();
            }}
            
            function fetchLiveStatus() {{
                // Replace this with your actual API endpoint
                fetch(`/api/processing-status/${{USER_ID}}`)
                    .then(response => response.json())
                    .then(data => {{
                        updateVisualization(data);
                    }})
                    .catch(error => {{
                        console.error('Real simulation error:', error);
                        // Fallback to demo mode after some time
                        setTimeout(() => {{
                            const demoData = {{
                                status: 'completed',
                                agents_metadata: generateDemoAgents()
                            }};
                            updateVisualization(demoData);
                        }}, 10000);
                    }});
            }}
            
            function generateDemoAgents() {{
                if (Object.keys(agentsMetadata).length > 0) return agentsMetadata;
                
                const dummy = {{
                    [USER_ID]: {{ type: 'user', name: 'You' }}
                }};
                
                for (let i = 1; i <= 15; i++) {{
                    if (i !== USER_ID) {{
                        dummy[i] = {{ 
                            type: 'other', 
                            name: `Agent ${{i}}` 
                        }};
                    }}
                }}
                
                return dummy;
            }}
            
            function updateVisualization(data) {{
                // Update status
                document.getElementById('status').textContent = 
                    data.status === 'completed' ? 'Analysis complete' : 'Analyzing neural patterns...';
                
                // Initialize agents
                if (data.agents_metadata && Object.keys(agentsMetadata).length === 0) {{
                    agentsMetadata = data.agents_metadata;
                    Object.entries(agentsMetadata).forEach(([agentId, metadata]) => {{
                        createAgent(parseInt(agentId), metadata);
                    }});
                }}
                
                // Handle completion
                if (data.status === 'completed' && !simulationCompleted) {{
                    simulationCompleted = true;
                    clearInterval(updateInterval); // Stop updates when complete
                    setTimeout(showResults, 2000);
                }}
            }}
            
            function showResults() {{
                // Just show the completion modal
                document.getElementById('resultsModal').classList.add('visible');
            }}
            
            // Handle window resize
            function onWindowResize() {{
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            }}
            
            window.addEventListener('resize', onWindowResize);
            
            // Initialize
            document.addEventListener('DOMContentLoaded', () => {{
                initThreeJS();
                startRealTimeUpdates();
            }});
            
            // Cleanup
            window.addEventListener('beforeunload', () => {{
                if (updateInterval) clearInterval(updateInterval);
                if (renderer) renderer.dispose();
            }});
            
            // Close modal
            document.getElementById('resultsModal').addEventListener('click', (e) => {{
                if (e.target.id === 'resultsModal') {{
                    e.target.classList.remove('visible');
                }}
            }});
        </script>
    </body>
    </html>
    '''
    
    return live_matching_html

@app.route('/api/processing-status/<int:user_id>')
def processing_status_api(user_id):
    """Enhanced API endpoint for real processing status"""
    # Verify this is the logged-in user
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Check both local and enhanced matching system status
    local_status = processing_status.get(user_id, {})
    enhanced_status = enhanced_matching_system.processing_status.get(user_id, {})
    
    # Merge statuses (enhanced takes priority)
    final_status = {**local_status, **enhanced_status}
    
    if not final_status:
        final_status = {'status': 'processing', 'progress': 0}
    
    # Ensure we always have the required fields for the frontend
    final_status.setdefault('phase', 'initializing')
    final_status.setdefault('simulation_step', 0)
    final_status.setdefault('agents_moved', 0)
    final_status.setdefault('avg_satisfaction', 0)
    final_status.setdefault('agents_positions', {})
    
    # FIX: Generate agents_metadata with real user data
    if 'agents_metadata' not in final_status or not final_status['agents_metadata']:
        final_status['agents_metadata'] = generate_agents_metadata_for_user(user_id)
    
    return jsonify(final_status)
# ============================================================================
# ROUTES - PROFILE UPDATES
# ============================================================================

@app.route('/update-profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    """Update existing user profile"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if not user_info or not user_info['profile_completed']:
        return redirect('/profile-setup')
    
    if request.method == 'POST':
        # Process the profile update
        profile_data = {}
        for key in request.form.keys():
            if key in ['interests', 'personality_traits', 'red_flags', 'transportation']:
                profile_data[key] = request.form.getlist(key)
            else:
                profile_data[key] = request.form.get(key)
        
        print(f"✓ Updating profile for user {user_id}")
        
        # Clear existing blocked users and save updated profile
        user_auth.clear_blocked_users(user_id)
        user_auth.save_user_profile(user_id, profile_data)
        
        # Process blocked users
        for field in ['blocked_emails', 'blocked_names', 'blocked_phones']:
            blocked_list = profile_data.get(field, '')
            if blocked_list:
                items = [item.strip() for item in blocked_list.split(',') if item.strip()]
                for item in items:
                    if field == 'blocked_emails':
                        user_auth.add_blocked_user(user_id, blocked_email=item)
                    elif field == 'blocked_names':
                        user_auth.add_blocked_user(user_id, blocked_name=item)
                    elif field == 'blocked_phones':
                        user_auth.add_blocked_user(user_id, blocked_phone=item)
        
        # Start background re-matching
        thread = threading.Thread(target=process_matching_background, args=(user_id,))
        thread.daemon = True
        thread.start()
        
        flash('Profile updated successfully! Finding new matches...', 'success')
        return redirect('/processing')
    
    # GET request - show the update form
    existing_profile = user_auth.get_user_profile(user_id)
    existing_blocked = user_auth.get_blocked_users(user_id)
    
    # Render update form (simplified version)
    content = '''
    <div class="container">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px; color: #28a745;">Update Your Profile</h1>
        
        <form method="POST">
            <!-- Add simplified form fields here -->
            <div style="text-align: center; margin-top: 30px;">
                <button type="submit" class="btn" style="background: #28a745; color: white; padding: 16px 32px; font-size: 16px;">
                    Update Profile & Re-run Matching
                </button>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header("Update Profile", content, user_info)

@app.route('/send-contact-request/<int:requested_id>', methods=['GET', 'POST'])
@login_required
def send_contact_request_with_tracking(requested_id):
    """Enhanced contact request with interaction tracking"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    requested_user_info = user_auth.get_user_info(requested_id)
    
    if not requested_user_info:
        flash('User not found', 'error')
        return redirect('/dashboard')
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        
        # Get compatibility score for tracking
        user_matches = user_auth.get_user_matches(user_id)
        compatibility_score = 0
        for match in user_matches:
            if match['matched_user_id'] == requested_id:
                compatibility_score = match['overall_score']
                break
        
        result = user_auth.send_contact_request(user_id, requested_id, message)
        
        if result['success']:
            # Track successful contact request
            interaction_tracker.track_contact_request(user_id, requested_id, compatibility_score)
            flash(f'Contact request sent to {requested_user_info["first_name"]}!', 'success')
            return redirect('/dashboard')
        else:
            flash(result['error'], 'error')
    
    # Show contact request form (same as before)
    content = f'''
    <div class="container" style="max-width: 600px;">
        <h1 style="font-size: 28px; text-align: center; margin-bottom: 32px;">Request Contact Information</h1>
        
        <div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 30px; text-align: center;">
            <div style="font-size: 20px; font-weight: bold; margin-bottom: 10px;">{requested_user_info['first_name']} {requested_user_info['last_name']}</div>
            <div style="font-size: 14px; color: #666;">You'd like to connect with this person</div>
        </div>
        
        <form method="POST">
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 500;">Optional message:</label>
                <textarea name="message" 
                          placeholder="Hi! I saw we're a great match and would love to chat!"
                          style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; height: 100px;"></textarea>
            </div>
            
            <div style="display: flex; gap: 15px; justify-content: center; margin-top: 30px;">
                <a href="/dashboard" class="btn btn-secondary">Cancel</a>
                <button type="submit" class="btn btn-primary">Send Request</button>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header("Send Contact Request", content, user_info)

@app.route('/contact-requests')
@login_required 
def contact_requests_route():
    """View and manage contact requests with beautiful design"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    received_requests = user_auth.get_contact_requests(user_id, 'received')
    sent_requests = user_auth.get_contact_requests(user_id, 'sent')
    
    # Build received requests HTML with new design
    received_html = ""
    pending_received = [r for r in received_requests if r['status'] == 'pending']
    
    if pending_received:
        for req in pending_received:
            # Get initials for avatar
            name_parts = req['other_user_name'].split()
            initials = name_parts[0][0] + (name_parts[-1][0] if len(name_parts) > 1 else '')
            
            received_html += f'''
            <div class="request-card">
                <div class="request-header">
                    <div class="avatar">{initials}</div>
                    <div class="request-info">
                        <div class="request-name">{req['other_user_name']}</div>
                        <div class="request-date">{req['created_at'][:10]}</div>
                    </div>
                    <div class="request-actions">
                        <a href="/respond-contact-request/{req['id']}/accept" class="btn btn-accept">
                            Accept
                        </a>
                        <a href="/respond-contact-request/{req['id']}/deny" class="btn btn-decline">
                            Decline
                        </a>
                    </div>
                </div>
                
                {f'<div class="request-message">"{req["message"]}"</div>' if req['message'] else ''}
                
                <div class="privacy-notice">
                    <div class="privacy-icon">🔒</div>
                    <div class="privacy-text">
                        <strong>If you accept:</strong> {req['other_user_name']} will receive your phone number: <strong>{user_info['phone']}</strong>
                    </div>
                </div>
            </div>
            '''
    else:
        received_html = '''
        <div class="empty-state">
            <div class="empty-title">No Pending Requests</div>
            <div class="empty-text">When someone wants to connect with you, their requests will appear here.</div>
        </div>
        '''
    
    # Build sent requests HTML with new design
    sent_html = ""
    if sent_requests:
        for req in sent_requests:
            # Get initials for avatar
            name_parts = req['other_user_name'].split()
            initials = name_parts[0][0] + (name_parts[-1][0] if len(name_parts) > 1 else '')
            
            # Status styling with your color palette
            status_config = {
                'pending': {'color': 'var(--color-charcoal)', 'bg': 'var(--color-sage)', 'icon': '⏳', 'text': 'Pending'},
                'accepted': {'color': 'var(--color-white)', 'bg': 'var(--color-emerald)', 'icon': '✅', 'text': 'Accepted'},
                'denied': {'color': 'var(--color-white)', 'bg': 'var(--color-gray-600)', 'icon': '❌', 'text': 'Declined'}
            }
            
            config = status_config.get(req['status'], status_config['pending'])
            
            # Phone number display for accepted requests
            contact_section = ""
            if req['status'] == 'accepted':
                contact_section = f'''
                <div class="contact-info">
                    <div class="contact-header">
                        <div class="contact-icon">📞</div>
                        <div class="contact-label">Contact Information Available</div>
                    </div>
                    <div class="contact-actions">
                        <a href="tel:{req['other_user_phone']}" class="btn btn-call">
                            Call {req['other_user_phone']}
                        </a>
                        <div class="contact-note">You can now contact each other!</div>
                    </div>
                </div>
                '''
            
            sent_html += f'''
            <div class="request-card">
                <div class="request-header">
                    <div class="avatar">{initials}</div>
                    <div class="request-info">
                        <div class="request-name">{req['other_user_name']}</div>
                        <div class="request-date">{req['created_at'][:10]}</div>
                    </div>
                    <div class="status-badge" style="background: {config['bg']}; color: {config['color']};">
                        <span class="status-icon">{config['icon']}</span>
                        <span class="status-text">{config['text']}</span>
                    </div>
                </div>
                
                {f'<div class="request-message sent"><strong>Your message:</strong> "{req["message"]}"</div>' if req['message'] else ''}
                {contact_section}
            </div>
            '''
    else:
        sent_html = '''
        <div class="empty-state">
            <div class="empty-title">No Requests Sent</div>
            <div class="empty-text">When you request someone's contact information, it will appear here.</div>
        </div>
        '''
    
    # Build the complete HTML content with enhanced styling
    content = f'''
    <style>
        .requests-container {{
            font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .requests-title {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: clamp(2rem, 4vw, 2.5rem);
            font-weight: 600;
            text-align: center;
            margin-bottom: 3rem;
            color: var(--color-charcoal);
            letter-spacing: -0.02em;
        }}
        
        .requests-section {{
            margin-bottom: 3rem;
        }}
        
        .section-header {{
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding: 0 0.5rem;
        }}
        
        .section-title {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--color-emerald);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            letter-spacing: -0.01em;
        }}
        
        .notification-badge {{
            background: var(--color-emerald);
            color: white;
            border-radius: 50%;
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            min-width: 1.25rem;
            height: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .requests-container-inner {{
            background: var(--color-white);
            border-radius: 20px;
            padding: 2rem;
            box-shadow: 
                0 1px 3px rgba(0,0,0,0.04),
                0 8px 24px rgba(0,0,0,0.08);
            position: relative;
        }}
        
        .requests-container-inner::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
        }}
        
        .request-card {{
            background: var(--color-gray-50);
            border-radius: 16px;
            padding: 2rem;
            margin: 1.5rem 0;
            border-left: 4px solid var(--color-sage);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .request-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        }}
        
        .request-header {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        
        .avatar {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--color-lavender), var(--color-sage));
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--color-charcoal);
            font-size: 1.5rem;
            font-weight: 700;
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        }}
        
        .request-info {{
            flex: 1;
        }}
        
        .request-name {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--color-charcoal);
            margin-bottom: 0.25rem;
        }}
        
        .request-date {{
            font-size: 0.875rem;
            color: var(--color-gray-600);
            font-weight: 500;
        }}
        
        .request-actions {{
            display: flex;
            gap: 0.75rem;
        }}
        
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.25rem;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none;
            cursor: pointer;
            font-family: 'Satoshi', sans-serif;
            white-space: nowrap;
        }}
        
        .btn-accept {{
            background: var(--color-emerald);
            color: white;
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
        }}
        
        .btn-accept:hover {{
            background: #0f5942;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }}
        
        .btn-decline {{
            background: var(--color-gray-600);
            color: white;
            box-shadow: 0 4px 16px rgba(117, 117, 117, 0.2);
        }}
        
        .btn-decline:hover {{
            background: #616161;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(117, 117, 117, 0.3);
        }}
        
        .btn-call {{
            background: var(--color-sage);
            color: var(--color-charcoal);
            box-shadow: 0 4px 16px rgba(198, 225, 155, 0.2);
        }}
        
        .btn-call:hover {{
            background: #9ac463;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(198, 225, 155, 0.3);
        }}
        
        .status-badge {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.25rem;
            border-radius: 50px;
            font-size: 0.875rem;
            font-weight: 600;
            white-space: nowrap;
        }}
        
        .status-icon {{
            font-size: 1rem;
        }}
        
        .request-message {{
            background: var(--color-white);
            padding: 1.5rem;
            border-radius: 12px;
            margin: 1.5rem 0;
            border-left: 4px solid var(--color-emerald);
            font-style: italic;
            color: var(--color-gray-800);
            line-height: 1.6;
        }}
        
        .request-message.sent {{
            border-left-color: var(--color-sage);
        }}
        
        .privacy-notice {{
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            padding: 1.5rem;
            background: linear-gradient(135deg, var(--color-lavender), var(--color-sage));
            border-radius: 12px;
            margin-top: 1.5rem;
        }}
        
        .privacy-icon {{
            font-size: 1.25rem;
            flex-shrink: 0;
        }}
        
        .privacy-text {{
            font-size: 0.875rem;
            line-height: 1.5;
            color: var(--color-charcoal);
        }}
        
        .privacy-text strong {{
            font-weight: 600;
        }}
        
        .contact-info {{
            background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
            color: white;
            padding: 1.5rem;
            border-radius: 12px;
            margin-top: 1.5rem;
        }}
        
        .contact-header {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        
        .contact-icon {{
            font-size: 1.25rem;
        }}
        
        .contact-label {{
            font-weight: 600;
            font-size: 0.875rem;
        }}
        
        .contact-actions {{
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        
        .contact-note {{
            font-size: 0.875rem;
            opacity: 0.9;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 3rem 2rem;
            color: var(--color-gray-600);
            background: var(--color-white);
            border-radius: 16px;
            border: 2px dashed var(--color-gray-200);
        }}
        
        .empty-icon {{
            font-size: 3rem;
            margin-bottom: 1rem;
        }}
        
        .empty-title {{
            font-family: 'Clash Display', 'Satoshi', sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: var(--color-charcoal);
        }}
        
        .empty-text {{
            font-size: 0.875rem;
            line-height: 1.5;
        }}
        
        .back-to-dashboard {{
            text-align: center;
            margin-top: 3rem;
        }}
        
        .btn-back {{
            background: var(--color-emerald);
            color: white;
            padding: 1rem 2rem;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.875rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 16px rgba(22, 122, 96, 0.2);
        }}
        
        .btn-back:hover {{
            background: #0f5942;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }}
        
        @media (max-width: 768px) {{
            .requests-container {{
                padding: 1rem;
            }}
            
            .request-card {{
                padding: 1.5rem;
            }}
            
            .request-header {{
                flex-direction: column;
                text-align: center;
                gap: 1rem;
            }}
            
            .request-actions {{
                justify-content: center;
            }}
            
            .contact-actions {{
                flex-direction: column;
                align-items: flex-start;
            }}
        }}
    </style>
    
    <div class="requests-container">
        <h1 class="requests-title">Contact Requests</h1>
        
        <div class="requests-section">
            <div class="section-header">
                <h2 class="section-title">
                    Requests Received
                    {f'<span class="notification-badge">{len(pending_received)}</span>' if pending_received else ''}
                </h2>
            </div>
            <div class="requests-container-inner">
                {received_html}
            </div>
        </div>
        
        <div class="requests-section">
            <div class="section-header">
                <h2 class="section-title">Requests Sent</h2>
            </div>
            <div class="requests-container-inner">
                {sent_html}
            </div>
        </div>
        
        <div class="back-to-dashboard">
            <a href="/dashboard" class="btn-back">
                ← Back to Matches
            </a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Contact Requests", content, user_info)

@app.route('/respond-contact-request/<int:request_id>/<response>')
@login_required
def respond_contact_request_with_tracking(request_id, response):
    """Enhanced contact request response with tracking"""
    user_id = session['user_id']
    
    if response not in ['accept', 'deny']:
        flash('Invalid response', 'error')
        return redirect('/contact-requests')
    
    # Get request details for tracking
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT requester_id FROM contact_requests WHERE id = ? AND requested_id = ?', 
                      (request_id, user_id))
        result = cursor.fetchone()
        conn.close()
        
        requester_id = result[0] if result else None
    except:
        requester_id = None
    
    result = user_auth.respond_to_contact_request(request_id, user_id, response + 'ed')
    
    if result['success']:
        # Track the response
        if requester_id:
            interaction_tracker.track_contact_response(user_id, requester_id, response == 'accept')
        
        if response == 'accept':
            flash('Contact request accepted!', 'success')
        else:
            flash('Contact request declined.', 'success')
    else:
        flash(result['error'], 'error')
    
    return redirect('/contact-requests')

# ============================================================================
# ROUTES - EMAIL FOLLOW-UP
# ============================================================================


@app.route('/followup-response/<token>/<response>')
def followup_response_with_tracking(token, response):
    """Enhanced follow-up response with tracking"""
    if response not in ['yes', 'no']:
        return render_template_with_header("Invalid Response", 
            '<div class="container"><h1>Invalid Response</h1><p>Invalid response type.</p></div>')
    
    # Get user details from token for tracking
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user1_id, user2_id, user1_token, user2_token 
            FROM followup_tracking 
            WHERE user1_token = ? OR user2_token = ?
        ''', (token, token))
        
        followup = cursor.fetchone()
        conn.close()
        
        if followup:
            user1_id, user2_id, user1_token, user2_token = followup
            
            # Determine which user responded
            if token == user1_token:
                responding_user_id = user1_id
                other_user_id = user2_id
            else:
                responding_user_id = user2_id
                other_user_id = user1_id
            
            # Track the email response
            interaction_tracker.track_email_response(responding_user_id, other_user_id, response == 'yes')
    except Exception as e:
        print(f"Error tracking email response: {e}")
    
    # Process the response (same as before)
    result = email_followup.record_followup_response(token, response)
    
    if result['success']:
        response_text = "Yes, I'd meet them again!" if response == 'yes' else "No, not a good match"
        content = f'''
        <div class="container" style="text-align: center; max-width: 500px;">
            <div style="font-size: 64px; margin-bottom: 20px;">{"✅" if response == 'yes' else "❌"}</div>
            <h1 style="color: {"#28a745" if response == "yes" else "#dc3545"};">Response Recorded</h1>
            <div style="font-size: 18px; margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                Your response: <strong>{response_text}</strong>
            </div>
            <p>Thank you for your feedback! This helps our AI learn and improve future matches.</p>
            <div style="margin-top: 30px;">
                <a href="/dashboard" class="btn btn-primary">Back to Dashboard</a>
            </div>
        </div>
        '''
    else:
        content = f'''
        <div class="container" style="text-align: center;">
            <h1 style="color: #dc3545;">Error</h1>
            <p>{result['error']}</p>
            <div style="margin-top: 30px;">
                <a href="/" class="btn btn-primary">Go Home</a>
            </div>
        </div>
        '''
    
    return render_template_with_header("Follow-up Response", content)

@app.route('/api/followup-stats/<int:user_id>')
@login_required
def followup_stats(user_id):
    """Get follow-up statistics for a user"""
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Get follow-up responses for this user's matches
        cursor.execute('''
            SELECT 
                COUNT(*) as total_followups,
                SUM(CASE WHEN user1_response = 1 OR user2_response = 1 THEN 1 ELSE 0 END) as positive_responses,
                SUM(CASE WHEN user1_response = 0 OR user2_response = 0 THEN 1 ELSE 0 END) as negative_responses,
                SUM(CASE WHEN user1_response IS NULL AND user2_response IS NULL THEN 1 ELSE 0 END) as pending_responses
            FROM followup_tracking 
            WHERE user1_id = ? OR user2_id = ?
            AND email_sent_at IS NOT NULL
        ''', (user_id, user_id))
        
        stats = cursor.fetchone()
        conn.close()
        
        return jsonify({
            'total_followups': stats[0] or 0,
            'positive_responses': stats[1] or 0,
            'negative_responses': stats[2] or 0,
            'pending_responses': stats[3] or 0,
            'success_rate': round((stats[1] or 0) / max(1, stats[0] or 1) * 100, 1)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/user/<int:user_id>/matches')
def api_user_matches(user_id):
    """API endpoint to get matches for a user"""
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        matches = user_auth.get_user_matches(user_id)
        
        if matches:
            return jsonify({
                'user_id': user_id,
                'matches': matches,
                'total_matches': len(matches)
            })
        else:
            return jsonify({'error': 'No matches found for this user'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check for deployment monitoring"""
    return jsonify({
        'status': 'healthy',
        'service': 'user-matching-platform',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/track-interaction', methods=['POST'])
@login_required
def track_interaction():
    """API endpoint to track user interactions"""
    try:
        user_id = session['user_id']
        data = request.json
        
        interaction_tracker.track_profile_view(
            user_id,
            data.get('target_user_id'),
            data.get('time_spent', 0)
        )
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/neural-network-status')
@login_required
def neural_network_status():
    """Get neural network training status and performance"""
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Get latest model performance
        cursor.execute('''
            SELECT model_version, accuracy, training_data_size, created_at
            FROM model_performance
            ORDER BY created_at DESC
            LIMIT 1
        ''')
        latest_model = cursor.fetchone()
        
        # Get total interaction count
        cursor.execute('SELECT COUNT(*) FROM user_interactions WHERE outcome IS NOT NULL')
        total_interactions = cursor.fetchone()[0]
        
        conn.close()
        
        status = {
            'is_trained': enhanced_matching_system.neural_predictor.is_trained,
            'total_interactions': total_interactions,
            'min_required': enhanced_matching_system.min_neural_data,
            'latest_model': {
                'version': latest_model[0] if latest_model else None,
                'accuracy': latest_model[1] if latest_model else None,
                'data_size': latest_model[2] if latest_model else None,
                'created_at': latest_model[3] if latest_model else None
            } if latest_model else None
        }
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

@app.after_request
def after_request(response):
    """Add CORS headers"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def init_database():
    """Initialize the database"""
    user_auth.init_user_database()
    print("✓ Database initialized")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

@app.route('/test-live-matching/<int:user_id>')
@login_required  
def test_live_matching(user_id):
    """Designer-quality live matching with beautiful typography and colors"""
    if session.get('user_id') != user_id:
        return redirect('/login')
    
    live_matching_html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Agent Simulation</title>
        <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=clash-display@400,500,600,700&display=swap" rel="stylesheet">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            :root {{
                --color-cream: #f1ece0;
                --color-emerald: #167a60;
                --color-sage: #c6e19b;
                --color-lavender: #c2b7ef;
                --color-charcoal: #2d2d2d;
                --color-white: #ffffff;
                --color-gray-50: #fafafa;
                --color-gray-100: #f5f5f5;
                --color-gray-200: #eeeeee;
                --color-gray-600: #757575;
                --color-gray-800: #424242;
            }}
            
            body {{
                font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
                background: linear-gradient(135deg, var(--color-cream) 0%, var(--color-gray-50) 100%);
                color: var(--color-charcoal);
                min-height: 100vh;
                overflow-x: hidden;
            }}
            
            /* Typography Scale */
            .text-display {{
                font-family: 'Clash Display', 'Satoshi', sans-serif;
                font-size: clamp(2.5rem, 5vw, 4rem);
                font-weight: 600;
                line-height: 1.1;
                letter-spacing: -0.02em;
            }}
            
            .text-title {{
                font-family: 'Clash Display', 'Satoshi', sans-serif;
                font-size: clamp(1.5rem, 3vw, 2.25rem);
                font-weight: 500;
                line-height: 1.2;
                letter-spacing: -0.01em;
            }}
            
            .text-body-lg {{
                font-size: 1.125rem;
                line-height: 1.6;
                font-weight: 400;
            }}
            
            .text-body {{
                font-size: 1rem;
                line-height: 1.5;
                font-weight: 400;
            }}
            
            .text-small {{
                font-size: 0.875rem;
                line-height: 1.4;
                font-weight: 400;
            }}
            
            .text-micro {{
                font-size: 0.75rem;
                line-height: 1.3;
                font-weight: 500;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }}
            
            /* Layout */
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
            }}
            
            .header {{
                text-align: center;
                margin-bottom: 3rem;
                position: relative;
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: -1rem;
                left: 50%;
                transform: translateX(-50%);
                width: 60px;
                height: 4px;
                background: linear-gradient(90deg, var(--color-emerald), var(--color-sage));
                border-radius: 2px;
            }}
            
            .test-badge {{
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                background: var(--color-lavender);
                color: var(--color-charcoal);
                padding: 0.5rem 1rem;
                border-radius: 50px;
                font-weight: 600;
                margin-top: 1rem;
                font-size: 0.875rem;
            }}
            
            .test-badge::before {{
                content: '✦';
                font-size: 1rem;
            }}
            
            /* Simulation Container */
            .simulation-container {{
                background: var(--color-white);
                border-radius: 24px;
                padding: 2rem;
                box-shadow: 
                    0 1px 3px rgba(0,0,0,0.04),
                    0 8px 24px rgba(0,0,0,0.08),
                    0 24px 48px rgba(0,0,0,0.04);
                backdrop-filter: blur(20px);
                position: relative;
                overflow: hidden;
            }}
            
            .simulation-container::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 1px;
                background: linear-gradient(90deg, transparent, var(--color-sage), transparent);
            }}
            
            /* Phase Indicator */
            .phase {{
                text-align: center;
                padding: 1.5rem 2rem;
                background: linear-gradient(135deg, var(--color-emerald), var(--color-sage));
                color: white;
                border-radius: 16px;
                margin-bottom: 2rem;
                font-weight: 500;
                font-size: 1.125rem;
                position: relative;
                overflow: hidden;
            }}
            
            .phase::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
                animation: shimmer 3s ease-in-out infinite;
            }}
            
            @keyframes shimmer {{
                0% {{ left: -100%; }}
                50% {{ left: 100%; }}
                100% {{ left: 100%; }}
            }}
            
            /* Legend */
            .legend {{
                display: flex;
                justify-content: center;
                gap: 2rem;
                margin: 2rem 0;
                flex-wrap: wrap;
            }}
            
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.75rem 1.25rem;
                background: var(--color-gray-50);
                border-radius: 50px;
                font-weight: 500;
                font-size: 0.875rem;
                color: var(--color-gray-800);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .legend-item:hover {{
                background: var(--color-gray-100);
                transform: translateY(-2px);
            }}
            
            .legend-dot {{
                width: 14px;
                height: 14px;
                border-radius: 50%;
                border: 2px solid rgba(255,255,255,0.8);
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            }}
            
            /* Simulation Area */
            .simulation-area {{
                width: 100%;
                height: 600px;
                background: var(--color-cream);
                border-radius: 16px;
                position: relative;
                overflow: hidden;
                border: 1px solid rgba(0,0,0,0.06);
                box-shadow: inset 0 2px 8px rgba(0,0,0,0.04);
            }}
            
            /* Enhanced Dots */
            .dot {{
                position: absolute;
                border-radius: 50%;
                transition: all 1.8s cubic-bezier(0.25, 0.46, 0.45, 0.94);
                cursor: pointer;
                z-index: 10;
            }}
            
            .dot.you {{
                width: 16px;
                height: 16px;
                background: radial-gradient(circle at 30% 30%, var(--color-charcoal), #1a1a1a);
                border: 3px solid var(--color-white);
                box-shadow: 
                    0 0 0 2px var(--color-charcoal),
                    0 4px 12px rgba(45, 45, 45, 0.4),
                    0 0 24px rgba(45, 45, 45, 0.2);
                z-index: 20;
            }}
            
            .dot.other {{
                width: 10px;
                height: 10px;
                background: radial-gradient(circle at 30% 30%, var(--color-emerald), #0f5942);
                border: 2px solid rgba(255, 255, 255, 0.6);
                box-shadow: 
                    0 2px 8px rgba(22, 122, 96, 0.3),
                    0 0 16px rgba(22, 122, 96, 0.1);
            }}
            
            .dot:hover {{
                transform: scale(1.4);
                z-index: 30;
            }}
            
            .dot.you:hover {{
                box-shadow: 
                    0 0 0 2px var(--color-charcoal),
                    0 6px 20px rgba(45, 45, 45, 0.5),
                    0 0 32px rgba(45, 45, 45, 0.3);
            }}
            
            /* Stats Panel */
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 1.5rem;
                margin: 2rem 0;
            }}
            
            .stat {{
                text-align: center;
                padding: 1.5rem 1rem;
                background: linear-gradient(135deg, var(--color-gray-50), var(--color-white));
                border-radius: 16px;
                border: 1px solid rgba(0,0,0,0.04);
                position: relative;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .stat:hover {{
                transform: translateY(-4px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            }}
            
            .stat-value {{
                font-family: 'Clash Display', 'Satoshi', sans-serif;
                font-size: 2rem;
                font-weight: 600;
                color: var(--color-charcoal);
                margin-bottom: 0.25rem;
                line-height: 1;
            }}
            
            .stat-label {{
                font-size: 0.75rem;
                font-weight: 600;
                color: var(--color-gray-600);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            
            /* Navigation */
            .back-nav {{
                position: fixed;
                top: 2rem;
                left: 2rem;
                z-index: 1000;
            }}
            
            .back-btn {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                background: var(--color-white);
                color: var(--color-charcoal);
                padding: 0.75rem 1.25rem;
                border-radius: 50px;
                text-decoration: none;
                font-weight: 500;
                font-size: 0.875rem;
                box-shadow: 
                    0 1px 3px rgba(0,0,0,0.04),
                    0 4px 16px rgba(0,0,0,0.08);
                backdrop-filter: blur(20px);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                border: 1px solid rgba(0,0,0,0.06);
            }}
            
            .back-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 
                    0 2px 8px rgba(0,0,0,0.08),
                    0 8px 24px rgba(0,0,0,0.12);
            }}
            
            /* Completion Message */
            .completion-message {{
                background: linear-gradient(135deg, var(--color-sage), var(--color-lavender));
                color: var(--color-charcoal);
                padding: 2.5rem 2rem;
                border-radius: 20px;
                text-align: center;
                margin-top: 2rem;
                display: none;
                position: relative;
                overflow: hidden;
            }}
            
            .completion-message.visible {{
                display: block;
                animation: slideUp 0.6s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            @keyframes slideUp {{
                from {{
                    opacity: 0;
                    transform: translateY(20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .completion-message h3 {{
                font-family: 'Clash Display', 'Satoshi', sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 0.75rem;
            }}
            
            .completion-message p {{
                font-size: 1rem;
                line-height: 1.6;
                margin-bottom: 2rem;
                opacity: 0.9;
            }}
            
            .completion-buttons {{
                display: flex;
                gap: 1rem;
                justify-content: center;
                flex-wrap: wrap;
            }}
            
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.875rem 1.5rem;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 0.875rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                white-space: nowrap;
            }}
            
            .btn-primary {{
                background: var(--color-charcoal);
                color: var(--color-white);
                box-shadow: 0 4px 16px rgba(45, 45, 45, 0.2);
            }}
            
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 24px rgba(45, 45, 45, 0.3);
            }}
            
            .btn-secondary {{
                background: var(--color-white);
                color: var(--color-charcoal);
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
            }}
            
            .btn-secondary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15);
            }}
            
            /* Responsive Design */
            @media (max-width: 768px) {{
                .container {{
                    padding: 1rem;
                }}
                
                .simulation-container {{
                    padding: 1.5rem;
                }}
                
                .simulation-area {{
                    height: 400px;
                }}
                
                .legend {{
                    gap: 1rem;
                }}
                
                .stats {{
                    grid-template-columns: repeat(2, 1fr);
                    gap: 1rem;
                }}
                
                .completion-buttons {{
                    flex-direction: column;
                    align-items: center;
                }}
            }}
            
            /* Loading States */
            .loading-pulse {{
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }}
            
            @keyframes pulse {{
                0%, 100% {{
                    opacity: 1;
                }}
                50% {{
                    opacity: 0.7;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="back-nav">
            <a href="/dashboard" class="back-btn">
                ← Back to Dashboard
            </a>
        </div>
        
        <div class="container">
            <header class="header">
                <h1 class="text-display">Live Agent Matching</h1>
                <p class="text-body-lg" style="color: var(--color-gray-600); margin-top: 1rem;">
                    Watch intelligent agents discover perfect compatibility clusters
                </p>
                <div class="test-badge">
                    Test Simulation Mode
                </div>
            </header>
            
            <div class="simulation-container">
                <div class="phase loading-pulse" id="phaseIndicator">
                    Initializing intelligent agents...
                </div>
                
                <div class="legend">
                    <div class="legend-item">
                        <div class="legend-dot" style="background: radial-gradient(circle at 30% 30%, var(--color-charcoal), #1a1a1a);"></div>
                        <span>Your Agent</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot" style="background: radial-gradient(circle at 30% 30%, var(--color-emerald), #0f5942);"></div>
                        <span>Other Agents</span>
                    </div>
                </div>
                
                <div class="simulation-area" id="simulationArea">
                    <!-- Beautiful dots will appear here -->
                </div>
                
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value" id="simulationStep">0</div>
                        <div class="stat-label">Simulation Step</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="agentsMoved">0</div>
                        <div class="stat-label">Agents Moved</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="avgSatisfaction">0%</div>
                        <div class="stat-label">Cluster Satisfaction</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="totalAgents">0</div>
                        <div class="stat-label">Total Agents</div>
                    </div>
                </div>
                
                <div class="completion-message" id="completionMessage">
                    <h3>🎉 Perfect Clusters Discovered!</h3>
                    <p>Your intelligent agent has successfully identified its ideal compatibility cluster through advanced social simulation.</p>
                    <div class="completion-buttons">
                        <a href="/test-matching" class="btn btn-primary">
                            ↻ Run Simulation Again
                        </a>
                        <a href="/dashboard" class="btn btn-secondary">
                            → View Dashboard
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const USER_ID = {user_id};
            let dots = new Map();
            let updateInterval;
            let agentsMetadata = {{}};
            
            const phaseMessages = {{
                'data_collection': '📊 Analyzing user personality profiles...',
                'filtering_users': '🎯 Identifying compatible candidates...',
                'initializing_simulation': '🤖 Spawning intelligent agents...',
                'running_simulation': '✨ Agents discovering optimal clusters...',
                'generating_matches': '🔬 Calculating compatibility matrices...'
            }};
            
            function startRealTimeUpdates() {{
                updateInterval = setInterval(fetchLiveStatus, 1000);
                fetchLiveStatus();
            }}
            
            function fetchLiveStatus() {{
                fetch(`/api/test-processing-status/${{USER_ID}}`)
                    .then(response => response.json())
                    .then(data => {{
                        updateVisualization(data);
                    }})
                    .catch(error => {{
                        console.error('Simulation error:', error);
                    }});
            }}
            
            function updateVisualization(data) {{
                // Update phase with smooth transitions
                const phase = data.phase || 'initializing';
                const phaseEl = document.getElementById('phaseIndicator');
                phaseEl.textContent = phaseMessages[phase] || 'Processing simulation...';
                
                // Remove loading pulse when simulation starts
                if (phase === 'running_simulation') {{
                    phaseEl.classList.remove('loading-pulse');
                }}
                
                // Update stats with smooth counting animation
                animateValue('simulationStep', data.simulation_step || 0);
                animateValue('agentsMoved', data.agents_moved || 0);
                animateValue('avgSatisfaction', data.avg_satisfaction || 0, '%');
                
                // Initialize beautiful dots
                if (data.agents_metadata && Object.keys(agentsMetadata).length === 0) {{
                    console.log('🎨 Creating beautiful agent visualization...');
                    agentsMetadata = data.agents_metadata;
                    initializeDesignerDots();
                    document.getElementById('totalAgents').textContent = Object.keys(agentsMetadata).length;
                }}
                
                // Smooth dot position updates
                if (data.agents_positions) {{
                    updateDotPositions(data.agents_positions);
                }}
                
                // Elegant completion
                if (data.status === 'completed') {{
                    showCompletion();
                }}
            }}
            
            function animateValue(elementId, targetValue, suffix = '') {{
                const element = document.getElementById(elementId);
                const currentValue = parseInt(element.textContent) || 0;
                
                if (currentValue !== targetValue) {{
                    const increment = (targetValue - currentValue) / 10;
                    let current = currentValue;
                    
                    const timer = setInterval(() => {{
                        current += increment;
                        if ((increment > 0 && current >= targetValue) || 
                            (increment < 0 && current <= targetValue)) {{
                            current = targetValue;
                            clearInterval(timer);
                        }}
                        element.textContent = Math.round(current) + suffix;
                    }}, 50);
                }}
            }}
            
            function initializeDesignerDots() {{
                const area = document.getElementById('simulationArea');
                area.innerHTML = '';
                dots.clear();
                
                Object.entries(agentsMetadata).forEach(([agentId, metadata]) => {{
                    const dot = document.createElement('div');
                    dot.className = `dot ${{metadata.type === 'user' ? 'you' : 'other'}}`;
                    dot.id = `dot-${{agentId}}`;
                    dot.title = metadata.type === 'user' ? 'Your Intelligent Agent' : `Agent: ${{metadata.name}}`;
                    
                    // Start in center with stagger effect
                    const delay = Math.random() * 200;
                    dot.style.transitionDelay = delay + 'ms';
                    dot.style.left = '400px';
                    dot.style.top = '300px';
                    
                    area.appendChild(dot);
                    dots.set(parseInt(agentId), dot);
                }});
                
                console.log('✨ Created', dots.size, 'beautiful agent dots');
            }}
            
            function updateDotPositions(positions) {{
                Object.entries(positions).forEach(([agentId, posData]) => {{
                    const dot = dots.get(parseInt(agentId));
                    if (dot) {{
                        const x = Math.max(8, Math.min(792, posData.x));
                        const y = Math.max(8, Math.min(592, posData.y));
                        
                        dot.style.left = x + 'px';
                        dot.style.top = y + 'px';
                    }}
                }});
            }}
            
            function showCompletion() {{
                clearInterval(updateInterval);
                document.getElementById('phaseIndicator').textContent = '🎉 Simulation complete! Perfect clusters discovered.';
                document.getElementById('phaseIndicator').classList.remove('loading-pulse');
                document.getElementById('completionMessage').classList.add('visible');
                
                console.log('🎊 Beautiful simulation completed!');
            }}
            
            // Initialize when page loads
            document.addEventListener('DOMContentLoaded', () => {{
                console.log('🚀 Starting designer simulation...');
                startRealTimeUpdates();
            }});
            
            // Cleanup
            window.addEventListener('beforeunload', () => {{
                if (updateInterval) clearInterval(updateInterval);
            }});
        </script>
    </body>
    </html>
    '''
    
    return render_template_string(live_matching_html, user_id=user_id)



if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Create necessary directories
    os.makedirs('data', exist_ok=True)
    
    print("\n" + "="*60)
    print("💜 USER MATCHING PLATFORM")
    print("="*60)
    print("🌐 URL: http://localhost:8050")
    print("📝 Features: User profiles + AI matching + Block lists")
    print("🔒 Security: Full authentication + privacy controls")
    print("📊 Database: users.db")
    print("🎯 Matching: User-to-user compatibility")
    print("="*60 + "\n")
    
    # Run the app
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=True)