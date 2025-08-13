import math
import requests
from flask import send_from_directory, abort
    
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from dataclasses import dataclass
from typing import List, Dict, Tuple
import random

from flask import Flask, render_template_string, request, redirect, session, jsonify, flash, url_for
from flask_cors import CORS
import hashlib
import json
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import re
import secrets
from openai import OpenAI
import threading
import time
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
import string

load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'pont-matching-secret-key-change-in-production'
CORS(app, origins="*", supports_credentials=True)

# Configuration
API_KEY = os.environ.get('OPENAI_API_KEY')

# User authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated_function

class UserAuthSystem:
    """User authentication and account management"""
    
    def __init__(self):
        self.init_user_database()
    
    def init_user_database(self):
        """Initialize user accounts database"""
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                matched_user_id INTEGER NOT NULL,
                matched_user_name TEXT NOT NULL,
                matched_user_email TEXT,
                compatibility_score INTEGER,
                personality_score INTEGER,
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
        
        conn.commit()
        conn.close()
        print("✓ User authentication database initialized")
    
    def create_user(self, email, password, first_name=None, last_name=None, phone=None):
        """Create new user account"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                conn.close()
                return {'success': False, 'error': 'Email already registered'}
            
            # Create password hash
            password_hash = generate_password_hash(password)
            
            # Insert new user
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
    
    def authenticate_user(self, email, password):
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
    
    def get_user_info(self, user_id):
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
    
    def save_user_profile(self, user_id, profile_data):
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
    
    def get_user_profile(self, user_id):
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
    
    def save_user_matches(self, user_id, matches):
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
                    (user_id, matched_user_id, matched_user_name, matched_user_email,
                     compatibility_score, personality_score, communication_score, 
                     location_score, overall_score, compatibility_analysis, distance_miles)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    match['matched_user_id'],
                    match['matched_user_name'],
                    match.get('matched_user_email', ''),
                    match['compatibility_score'],
                    match['personality_score'],
                    match['communication_score'],
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
    
    def get_user_matches(self, user_id):
        """Get saved user matches"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT matched_user_id, matched_user_name, matched_user_email,
                       compatibility_score, personality_score, communication_score,
                       location_score, overall_score, compatibility_analysis, distance_miles
                FROM user_matches 
                WHERE user_id = ? AND is_active = 1
                ORDER BY overall_score DESC
            ''', (user_id,))
            
            matches = cursor.fetchall()
            conn.close()
            
            results = []
            for match in matches:
                results.append({
                    'matched_user_id': match[0],
                    'matched_user_name': match[1],
                    'matched_user_email': match[2],
                    'compatibility_score': match[3],
                    'personality_score': match[4],
                    'communication_score': match[5],
                    'location_score': match[6],
                    'overall_score': match[7],
                    'compatibility_analysis': match[8],
                    'distance_miles': match[9]
                })
            
            return results
            
        except Exception as e:
            print(f"Error getting matches: {e}")
            return []
    
    def add_blocked_user(self, user_id, blocked_email=None, blocked_phone=None, blocked_name=None, reason=None):
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
    
    def get_blocked_users(self, user_id):
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
    
    def clear_blocked_users(self, user_id):
        """Clear all blocked users for a user (used during profile updates)"""
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

    def get_all_users_for_matching(self, exclude_user_id):
        """Get all users with completed profiles for matching (excluding current user)"""
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

class MatchingSystem:
    """User-to-user matching system"""
    
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.user_auth = UserAuthSystem()
    
    def calculate_distance(self, postcode1, postcode2):
        """Calculate distance between two UK postcodes"""
        def get_postcode_coordinates(postcode):
            try:
                response = requests.get(f"https://api.postcodes.io/postcodes/{postcode}")
                if response.status_code == 200:
                    data = response.json()
                    return data['result']['latitude'], data['result']['longitude']
            except:
                pass
            return None, None

        def haversine_distance(lat1, lon1, lat2, lon2):
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
    
    def is_user_blocked(self, user_id, potential_match):
        """Check if a potential match is in the user's block list"""
        blocked = self.user_auth.get_blocked_users(user_id)
        
        # Check if any of the blocked criteria match
        if potential_match['email'] in blocked['emails']:
            return True
        if potential_match['phone'] and potential_match['phone'] in blocked['phones']:
            return True
        
        # Check name matches (fuzzy matching)
        user_name = f"{potential_match['first_name']} {potential_match['last_name']}".lower()
        for blocked_name in blocked['names']:
            if blocked_name and blocked_name.lower() in user_name:
                return True
        
        return False
    
    def run_matching(self, user_id):
        """Run matching for a user against all other users"""
        print(f"\n=== Running User-to-User Matching for {user_id} ===")
        
        # Get current user's profile
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
            # Check if user is blocked
            if self.is_user_blocked(user_id, potential_match):
                print(f"Skipping blocked user: {potential_match['first_name']} {potential_match['last_name']}")
                continue
            
            print(f"Analyzing match with {potential_match['first_name']} {potential_match['last_name']}...")
            
            # Calculate compatibility
            scores, analysis = self.calculate_compatibility(current_user_profile, potential_match['profile'])
            
            # Calculate distance if both have postcodes
            distance = 999
            current_postcode = current_user_profile.get('postcode')
            match_postcode = potential_match['profile'].get('postcode')
            
            if current_postcode and match_postcode:
                distance = self.calculate_distance(current_postcode, match_postcode)
            
            match_result = {
                'matched_user_id': potential_match['user_id'],
                'matched_user_name': f"{potential_match['first_name']} {potential_match['last_name']}",
                'matched_user_email': potential_match['email'],
                'compatibility_score': scores['compatibility'],
                'personality_score': scores['personality'],
                'communication_score': scores['communication'],
                'location_score': scores['location'],
                'overall_score': scores['overall'],
                'compatibility_analysis': analysis,
                'distance_miles': distance
            }
            
            matches.append(match_result)
        
        # Sort by overall score
        matches.sort(key=lambda x: x['overall_score'], reverse=True)
        
        # Save matches to database
        self.user_auth.save_user_matches(user_id, matches)
        
        print(f"✓ Found {len(matches)} compatible matches")
        return matches
    
    def calculate_compatibility(self, user1_profile, user2_profile):
        """Calculate compatibility between two users"""
        # Get compatibility analysis from AI or use fallback
        if self.client:
            scores, analysis = self.get_ai_compatibility_analysis(user1_profile, user2_profile)
        else:
            scores, analysis = self.get_fallback_compatibility_analysis(user1_profile, user2_profile)
        
        return scores, analysis
    
    def get_ai_compatibility_analysis(self, user1_profile, user2_profile):
        """Get AI-powered compatibility analysis"""
        prompt = f"""Analyze compatibility between these two users for a social/dating platform. Provide structured response:

SCORES (0-100):
Compatibility: [number]
Personality: [number]
Communication: [number]
Location: [number]
Overall: [number]

ANALYSIS:
[2-3 sentences explaining why they might be compatible, focusing on shared interests, values, lifestyle, and communication styles]

User 1:
- Age: {user1_profile.get('age', 'Not specified')}
- Location: {user1_profile.get('location', 'Not specified')}
- Interests: {user1_profile.get('interests', 'Not specified')}
- Personality: {user1_profile.get('personality_traits', 'Not specified')}
- Looking for: {user1_profile.get('looking_for', 'Not specified')}
- Values: {user1_profile.get('values', 'Not specified')}
- Lifestyle: {user1_profile.get('lifestyle', 'Not specified')}

User 2:
- Age: {user2_profile.get('age', 'Not specified')}
- Location: {user2_profile.get('location', 'Not specified')}
- Interests: {user2_profile.get('interests', 'Not specified')}
- Personality: {user2_profile.get('personality_traits', 'Not specified')}
- Looking for: {user2_profile.get('looking_for', 'Not specified')}
- Values: {user2_profile.get('values', 'Not specified')}
- Lifestyle: {user2_profile.get('lifestyle', 'Not specified')}"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400,
                timeout=30
            )
            
            result = response.choices[0].message.content
            
            # Parse scores
            scores = {
                'compatibility': 75,
                'personality': 75,
                'communication': 75,
                'location': 75,
                'overall': 75
            }
            
            if "SCORES:" in result:
                scores_section = result.split("SCORES:")[1].split("ANALYSIS:")[0] if "ANALYSIS:" in result else result.split("SCORES:")[1]
                numbers = re.findall(r'\d+', scores_section)
                if len(numbers) >= 5:
                    scores = {
                        'compatibility': int(numbers[0]),
                        'personality': int(numbers[1]),
                        'communication': int(numbers[2]),
                        'location': int(numbers[3]),
                        'overall': int(numbers[4])
                    }
            
            analysis = result.split("ANALYSIS:")[1].strip() if "ANALYSIS:" in result else result
            
            return scores, analysis
            
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            return self.get_fallback_compatibility_analysis(user1_profile, user2_profile)
    
    def get_fallback_compatibility_analysis(self, user1_profile, user2_profile):
        """Fallback compatibility calculation without AI"""
        scores = {
            'compatibility': random.randint(60, 90),
            'personality': random.randint(60, 90),
            'communication': random.randint(60, 90),
            'location': random.randint(50, 95),
            'overall': random.randint(65, 88)
        }
        
        analysis = "Based on your profiles, you share several common interests and values that suggest good compatibility. Your communication styles appear complementary, and you both seem to be looking for similar things in a connection."
        
        return scores, analysis

# Initialize systems
user_auth = UserAuthSystem()
matching_system = MatchingSystem(API_KEY)

# Store processing status
processing_status = {}

def process_matching_background(user_id):
    """Background task to process user matching"""
    try:
        processing_status[user_id] = {'status': 'processing', 'progress': 0}
        
        processing_status[user_id]['progress'] = 25
        
        # Run matching against all other users
        matches = matching_system.run_matching(user_id)
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

# Routes
@app.route('/')
def home():
    """Landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Find Your Perfect Match - Social Platform</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 60px 40px;
                max-width: 500px;
                width: 100%;
                text-align: center;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .logo {
                font-size: 32px;
                font-weight: 600;
                color: black;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
            }
            .subtitle {
                font-size: 16px;
                color: black;
                margin-bottom: 40px;
                font-weight: 400;
            }
            .description {
                font-size: 16px;
                color: #666;
                margin-bottom: 40px;
                text-align: left;
                line-height: 1.6;
            }
            .action-buttons {
                display: flex;
                flex-direction: column;
                gap: 15px;
                margin-bottom: 30px;
            }
            .btn {
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: all 0.2s ease;
                border: none;
            }
            .btn-primary {
                background: #6c5ce7;
                color: white;
            }
            .btn-primary:hover {
                background: #5a4fcf;
                transform: translateY(-2px);
            }
            .btn-secondary {
                background: white;
                color: #6c5ce7;
                border: 2px solid #6c5ce7;
            }
            .btn-secondary:hover {
                background: #6c5ce7;
                color: white;
            }
            .privacy-note {
                background: #f8f9fa;
                border-radius: 6px;
                padding: 16px;
                margin: 24px 0;
                font-size: 14px;
                color: #666;
                text-align: left;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 40px 24px;
                    margin: 16px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="logo">💜 Connect</h1>
            <div class="subtitle">Find Your Perfect Match</div>
            
            <div class="description">
                Discover meaningful connections based on personality compatibility, shared interests, and values. Our AI-powered matching system helps you find people who truly understand you.
            </div>
            
            <div class="action-buttons">
                <a href="/register" class="btn btn-primary">
                    Create Account & Start Matching
                </a>
                <a href="/login" class="btn btn-secondary">
                    Login to Existing Account
                </a>
            </div>
            
            <div class="privacy-note">
                <strong>Your Privacy Matters</strong><br>
                We use secure authentication and advanced filtering to protect your data while helping you find compatible matches.
            </div>
        </div>
    </body>
    </html>
    ''')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        # Validation
        if not email or not password:
            flash('Email and password are required', 'error')
        elif password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            # Create user account
            result = user_auth.create_user(email, password, first_name, last_name, phone)
            
            if result['success']:
                # Auto-login after registration
                session['user_id'] = result['user_id']
                session['user_email'] = email
                session['user_name'] = first_name
                flash('Account created successfully! Let\'s create your profile.', 'success')
                return redirect('/profile-setup')
            else:
                flash(result['error'], 'error')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Create Account - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .logo {
                font-size: 28px;
                font-weight: 600;
                color: black;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
                text-align: center;
            }
            .subtitle {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
                text-align: center;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                color: black;
                margin-bottom: 8px;
                font-weight: 500;
                font-size: 14px;
            }
            .form-group input {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease;
            }
            .form-group input:focus {
                border-color: #6c5ce7;
                outline: none;
            }
            .form-row {
                display: flex;
                gap: 15px;
            }
            .form-row .form-group {
                flex: 1;
            }
            .submit-btn {
                background: #6c5ce7;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s ease;
                margin-top: 10px;
            }
            .submit-btn:hover {
                background: #5a4fcf;
            }
            .login-link {
                text-align: center;
                margin-top: 20px;
                font-size: 14px;
            }
            .login-link a {
                color: #6c5ce7;
                text-decoration: none;
            }
            .login-link a:hover {
                text-decoration: underline;
            }
            .flash-messages {
                margin-bottom: 20px;
            }
            .flash-message {
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            .flash-message.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .flash-message.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="logo">💜 Connect</h1>
            <div class="subtitle">Create Your Account</div>
            
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-message {{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            
            <form method="POST">
                <div class="form-row">
                    <div class="form-group">
                        <label for="first_name">First Name</label>
                        <input type="text" id="first_name" name="first_name" required>
                    </div>
                    <div class="form-group">
                        <label for="last_name">Last Name</label>
                        <input type="text" id="last_name" name="last_name" required>
                    </div>
                </div>
                
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                </div>
                
                <div class="form-group">
                    <label for="phone">Phone Number (Optional)</label>
                    <input type="tel" id="phone" name="phone">
                </div>
                
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required minlength="6">
                </div>
                
                <div class="form-group">
                    <label for="confirm_password">Confirm Password</label>
                    <input type="password" id="confirm_password" name="confirm_password" required>
                </div>
                
                <button type="submit" class="submit-btn">Create Account</button>
            </form>
            
            <div class="login-link">
                Already have an account? <a href="/login">Login here</a>
            </div>
        </div>
    </body>
    </html>
    ''')

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
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .logo {
                font-size: 28px;
                font-weight: 600;
                color: black;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
                text-align: center;
            }
            .subtitle {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
                text-align: center;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                color: black;
                margin-bottom: 8px;
                font-weight: 500;
                font-size: 14px;
            }
            .form-group input {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease;
            }
            .form-group input:focus {
                border-color: #6c5ce7;
                outline: none;
            }
            .submit-btn {
                background: #6c5ce7;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s ease;
                margin-top: 10px;
            }
            .submit-btn:hover {
                background: #5a4fcf;
            }
            .register-link {
                text-align: center;
                margin-top: 20px;
                font-size: 14px;
            }
            .register-link a {
                color: #6c5ce7;
                text-decoration: none;
            }
            .register-link a:hover {
                text-decoration: underline;
            }
            .flash-messages {
                margin-bottom: 20px;
            }
            .flash-message {
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            .flash-message.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .flash-message.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="logo">💜 Connect</h1>
            <div class="subtitle">Login to Your Account</div>
            
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-message {{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                </div>
                
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                
                <button type="submit" class="submit-btn">Login</button>
            </form>
            
            <div class="register-link">
                Don't have an account? <a href="/register">Create one here</a>
            </div>
        </div>
    </body>
    </html>
    ''')

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect('/')

@app.route('/profile-setup')
@login_required
def profile_setup():
    """Profile setup form"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Create Your Profile - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                padding: 20px;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                border-radius: 8px;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .logout-btn {
                color: #666;
                text-decoration: none;
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
                transition: all 0.2s ease;
            }
            .logout-btn:hover {
                background: #f8f9fa;
                border-color: #6c5ce7;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 40px;
                max-width: 700px;
                margin: 0 auto;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .profile-header {
                text-align: center;
                margin-bottom: 40px;
            }
            .profile-logo {
                font-size: 28px;
                font-weight: 600;
                color: black;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
            }
            .subtitle {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
            }
            .progress-bar {
                width: 100%;
                height: 4px;
                background: #f2f2eb;
                border-radius: 2px;
                margin-bottom: 40px;
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                background: #6c5ce7;
                width: 0%;
                transition: width 0.3s ease;
            }
            .section {
                margin-bottom: 32px;
                padding: 24px;
                background: #f4f2eb;
                border-radius: 6px;
                border-left: 3px solid #6c5ce7;
            }
            .section-title {
                font-size: 18px;
                font-weight: 600;
                color: black;
                margin-bottom: 20px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                color: black;
                margin-bottom: 8px;
                font-weight: 500;
                font-size: 14px;
            }
            .form-group input, .form-group textarea, .form-group select {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease;
                background: white;
            }
            .form-group input:focus, .form-group textarea:focus, .form-group select:focus {
                border-color: #6c5ce7;
                outline: none;
            }
            .form-group textarea {
                height: 100px;
                resize: vertical;
            }
            .checkbox-group {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin-top: 8px;
            }
            .checkbox-item {
                display: flex;
                align-items: center;
                padding: 8px;
                background: white;
                border-radius: 4px;
                border: 1px solid #ddd;
                transition: border-color 0.2s ease;
            }
            .checkbox-item:hover {
                border-color: #6c5ce7;
            }
            .checkbox-item input[type="checkbox"] {
                margin-right: 8px;
                width: auto;
                accent-color: #6c5ce7;
            }
            .checkbox-item label {
                margin: 0;
                font-size: 13px;
                cursor: pointer;
                flex: 1;
            }
            .submit-btn {
                background: #6c5ce7;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s ease;
                margin-top: 20px;
            }
            .submit-btn:hover {
                background: #5a4fcf;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 24px 20px;
                    margin: 10px;
                }
                .section {
                    padding: 20px;
                }
                .checkbox-group {
                    grid-template-columns: 1fr;
                }
                .header {
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                }
                .user-info {
                    flex-direction: column;
                    gap: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>{{ session.user_name or session.user_email }}</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="profile-header">
                <h1 class="profile-logo">Create Your Profile</h1>
                <div class="subtitle">Help us find your perfect matches</div>
                
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
            </div>
            
            <form method="POST" action="/submit-profile" id="profileForm">
                <div class="section">
                    <h3 class="section-title">Basic Information</h3>
                    
                    <div class="form-group">
                        <label for="age">Age</label>
                        <select id="age" name="age" required>
                            <option value="">Select your age</option>
                            <option value="18-25">18-25</option>
                            <option value="26-35">26-35</option>
                            <option value="36-45">36-45</option>
                            <option value="46-55">46-55</option>
                            <option value="56-65">56-65</option>
                            <option value="65+">65+</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="location">Location (City/Area)</label>
                        <input type="text" id="location" name="location" required
                               placeholder="e.g., London, Manchester, Brighton">
                    </div>
                    
                    <div class="form-group">
                        <label for="postcode">Postcode (for distance calculations)</label>
                        <input type="text" id="postcode" name="postcode" required
                               placeholder="e.g., SW3 4HN"
                               pattern="^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]? [0-9][ABD-HJLNP-UW-Zabd-hjlnp-uw-z]{2}$"
                               title="Please enter a valid UK postcode">
                    </div>
                    
                    <div class="form-group">
                        <label for="occupation">Occupation</label>
                        <input type="text" id="occupation" name="occupation" required
                               placeholder="What do you do for work?">
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Interests & Hobbies</h3>
                    
                    <div class="form-group">
                        <label>What are your main interests? (Select all that apply)</label>
                        <div class="checkbox-group">
                            <div class="checkbox-item">
                                <input type="checkbox" id="travel" name="interests" value="travel">
                                <label for="travel">Travel</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="fitness" name="interests" value="fitness">
                                <label for="fitness">Fitness & Health</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="music" name="interests" value="music">
                                <label for="music">Music</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="cooking" name="interests" value="cooking">
                                <label for="cooking">Cooking</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="reading" name="interests" value="reading">
                                <label for="reading">Reading</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="outdoors" name="interests" value="outdoors">
                                <label for="outdoors">Outdoor Activities</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="arts" name="interests" value="arts">
                                <label for="arts">Arts & Culture</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="technology" name="interests" value="technology">
                                <label for="technology">Technology</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="sports" name="interests" value="sports">
                                <label for="sports">Sports</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="photography" name="interests" value="photography">
                                <label for="photography">Photography</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="hobbies_description">Tell us more about your hobbies and interests</label>
                        <textarea id="hobbies_description" name="hobbies_description"
                                  placeholder="What do you love doing in your free time? What makes you excited?"></textarea>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Personality & Values</h3>
                    
                    <div class="form-group">
                        <label>Which personality traits best describe you? (Select all that apply)</label>
                        <div class="checkbox-group">
                            <div class="checkbox-item">
                                <input type="checkbox" id="outgoing" name="personality_traits" value="outgoing">
                                <label for="outgoing">Outgoing</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="introverted" name="personality_traits" value="introverted">
                                <label for="introverted">Introverted</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="adventurous" name="personality_traits" value="adventurous">
                                <label for="adventurous">Adventurous</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="calm" name="personality_traits" value="calm">
                                <label for="calm">Calm & Peaceful</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="funny" name="personality_traits" value="funny">
                                <label for="funny">Funny</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="thoughtful" name="personality_traits" value="thoughtful">
                                <label for="thoughtful">Thoughtful</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="ambitious" name="personality_traits" value="ambitious">
                                <label for="ambitious">Ambitious</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="creative" name="personality_traits" value="creative">
                                <label for="creative">Creative</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="values">What values are most important to you?</label>
                        <textarea id="values" name="values" required
                                  placeholder="e.g., Honesty, Family, Adventure, Personal Growth, Kindness..."></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="lifestyle">How would you describe your lifestyle?</label>
                        <select id="lifestyle" name="lifestyle" required>
                            <option value="">Select your lifestyle</option>
                            <option value="active_social">Very active and social</option>
                            <option value="balanced">Balanced work and social life</option>
                            <option value="career_focused">Career-focused</option>
                            <option value="laid_back">Laid back and relaxed</option>
                            <option value="family_oriented">Family-oriented</option>
                            <option value="adventurous">Always seeking new experiences</option>
                        </select>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">What You're Looking For</h3>
                    
                    <div class="form-group">
                        <label for="looking_for">What type of connection are you seeking?</label>
                        <select id="looking_for" name="looking_for" required>
                            <option value="">Select what you're looking for</option>
                            <option value="serious_relationship">Serious relationship</option>
                            <option value="casual_dating">Casual dating</option>
                            <option value="friendship">New friendships</option>
                            <option value="activity_partner">Activity partner</option>
                            <option value="open_to_see">Open to see what happens</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="ideal_match">Describe your ideal match</label>
                        <textarea id="ideal_match" name="ideal_match" required
                                  placeholder="What qualities are you looking for in a connection? What would make someone a great match for you?"></textarea>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Block List (Optional)</h3>
                    <p style="color: #666; margin-bottom: 20px; font-size: 14px;">
                        If there are specific people you don't want to be matched with, you can add them here. 
                        This information is kept completely private.
                    </p>
                    
                    <div class="form-group">
                        <label for="blocked_emails">Email addresses to exclude</label>
                        <textarea id="blocked_emails" name="blocked_emails"
                                  placeholder="Enter email addresses separated by commas (e.g., person1@email.com, person2@email.com)"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="blocked_names">Names to exclude</label>
                        <textarea id="blocked_names" name="blocked_names"
                                  placeholder="Enter full names separated by commas (e.g., John Smith, Jane Doe)"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="blocked_phones">Phone numbers to exclude</label>
                        <textarea id="blocked_phones" name="blocked_phones"
                                  placeholder="Enter phone numbers separated by commas"></textarea>
                    </div>
                </div>
                
                <button type="submit" class="submit-btn">
                    Create Profile & Find Matches
                </button>
            </form>
        </div>
        
        <script>
            function updateProgress() {
                const form = document.getElementById('profileForm');
                const requiredFields = form.querySelectorAll('input[required], textarea[required], select[required]');
                
                let filledFields = 0;
                requiredFields.forEach(field => {
                    if (field.value.trim() !== '') {
                        filledFields++;
                    }
                });
                
                // Check if at least one interest and personality trait is selected
                const interestsChecked = form.querySelectorAll('input[name="interests"]:checked').length > 0;
                const traitsChecked = form.querySelectorAll('input[name="personality_traits"]:checked').length > 0;
                
                if (interestsChecked) filledFields += 0.5;
                if (traitsChecked) filledFields += 0.5;
                
                const totalFields = requiredFields.length + 1; // +1 for the checkbox groups
                const progress = (filledFields / totalFields) * 100;
                document.getElementById('progressFill').style.width = Math.min(progress, 100) + '%';
            }
            
            document.querySelectorAll('input, textarea, select').forEach(field => {
                field.addEventListener('input', updateProgress);
                field.addEventListener('change', updateProgress);
            });
            
            updateProgress();
        </script>
    </body>
    </html>
    ''')

@app.route('/submit-profile', methods=['POST'])
@login_required
def submit_profile():
    """Process profile submission for authenticated user"""
    user_id = session['user_id']
    
    # Collect form data
    profile_data = {}
    for key in request.form.keys():
        if key in ['interests', 'personality_traits']:
            # Handle multiple checkbox values
            profile_data[key] = request.form.getlist(key)
        else:
            profile_data[key] = request.form.get(key)
    
    print(f"✓ Processing profile submission for user {user_id}")
    
    # Save profile to database
    user_auth.save_user_profile(user_id, profile_data)
    
    # Process blocked users if any
    blocked_emails = profile_data.get('blocked_emails', '')
    blocked_names = profile_data.get('blocked_names', '')
    blocked_phones = profile_data.get('blocked_phones', '')
    
    if blocked_emails:
        for email in [e.strip() for e in blocked_emails.split(',') if e.strip()]:
            user_auth.add_blocked_user(user_id, blocked_email=email)
    
    if blocked_names:
        for name in [n.strip() for n in blocked_names.split(',') if n.strip()]:
            user_auth.add_blocked_user(user_id, blocked_name=name)
    
    if blocked_phones:
        for phone in [p.strip() for p in blocked_phones.split(',') if p.strip()]:
            user_auth.add_blocked_user(user_id, blocked_phone=phone)
    
    # Store user_id in session for processing page
    session['processing_user_id'] = user_id
    
    # Start background processing
    thread = threading.Thread(target=process_matching_background, args=(user_id,))
    thread.daemon = True
    thread.start()
    
    return redirect('/processing')

@app.route('/processing')
@login_required
def processing():
    """Loading screen while matching runs"""
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Finding Your Matches</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .loading-container {
                background: white;
                border-radius: 8px;
                padding: 60px 40px;
                max-width: 500px;
                width: 100%;
                text-align: center;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
                margin: 0 auto;
            }
            .loading-spinner {
                width: 60px;
                height: 60px;
                border: 4px solid #f0f0f0;
                border-top: 4px solid #6c5ce7;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .loading-text {
                font-size: 18px;
                color: black;
                margin: 20px 0;
                font-weight: 500;
            }
            .status-text {
                font-size: 14px;
                color: #666;
                margin: 10px 0;
            }
            .progress-bar {
                width: 100%;
                height: 8px;
                background: #f0f0f0;
                border-radius: 4px;
                margin: 20px 0;
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #6c5ce7, #a29bfe);
                border-radius: 4px;
                width: 0%;
                transition: width 0.5s ease;
                animation: pulse 2s ease-in-out infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            .time-estimate {
                font-size: 16px;
                color: #6c5ce7;
                margin: 20px 0;
                font-weight: 500;
            }
            .steps {
                text-align: left;
                margin: 30px 0;
                padding: 20px;
                background: #f9f9f9;
                border-radius: 6px;
            }
            .step {
                display: flex;
                align-items: center;
                margin: 10px 0;
                font-size: 14px;
            }
            .step-icon {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                margin-right: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                font-weight: bold;
            }
            .step-complete {
                background: #28a745;
                color: white;
            }
            .step-active {
                background: #6c5ce7;
                color: white;
                animation: pulse 1.5s ease-in-out infinite;
            }
            .step-pending {
                background: #e9ecef;
                color: #6c757d;
            }
            @media (max-width: 600px) {
                .loading-container {
                    padding: 40px 24px;
                    margin: 16px;
                }
                .header {
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>{{ session.user_name or session.user_email }}</span>
            </div>
        </div>
        
        <div class="loading-container">
            <h1 class="loading-title" style="font-size: 28px; margin-bottom: 10px;">Finding Your Matches</h1>
            <div class="subtitle" style="margin-bottom: 30px;">Analyzing your profile and matching with compatible users</div>
            
            <div class="loading-spinner"></div>
            
            <div class="loading-text" id="loadingText">Processing your profile...</div>
            
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            
            <div class="time-estimate">
                Your results should be ready in about 30 seconds
            </div>
            
            <div class="steps">
                <div class="step">
                    <div class="step-icon step-complete" id="step1">✓</div>
                    <span>Profile completed</span>
                </div>
                <div class="step">
                    <div class="step-icon step-active" id="step2">2</div>
                    <span id="step2Text">Processing your preferences</span>
                </div>
                <div class="step">
                    <div class="step-icon step-pending" id="step3">3</div>
                    <span>Finding compatible users</span>
                </div>
                <div class="step">
                    <div class="step-icon step-pending" id="step4">4</div>
                    <span>Calculating compatibility scores</span>
                </div>
                <div class="step">
                    <div class="step-icon step-pending" id="step5">5</div>
                    <span>Saving to your account</span>
                </div>
            </div>
            
            <div class="status-text" id="statusText">
                Our AI is carefully analyzing your profile to find the most compatible matches for you.
            </div>
        </div>
        
        <script>
            let progress = 0;
            let currentStep = 2;
            let startTime = Date.now();
            
            const steps = [
                { text: "Processing your preferences", duration: 3000 },
                { text: "Finding compatible users", duration: 8000 },
                { text: "Calculating compatibility scores", duration: 12000 },
                { text: "Saving to your account", duration: 5000 }
            ];
            
            const statusMessages = [
                "Our AI is carefully analyzing your profile to find the most compatible matches for you.",
                "Comparing your interests, values, and personality with other users...",
                "Running compatibility analysis using advanced matching algorithms...",
                "Generating personalized compatibility scores and recommendations...",
                "Almost ready! Saving your matches to your secure account..."
            ];
            
            function updateProgress() {
                const elapsed = Date.now() - startTime;
                const totalDuration = 28000; // 28 seconds total
                progress = Math.min((elapsed / totalDuration) * 100, 95);
                
                document.getElementById('progressFill').style.width = progress + '%';
                
                // Update steps
                let stepIndex = Math.floor(progress / 20); // 5 steps, so every 20%
                if (stepIndex >= 4) stepIndex = 3; // Don't advance past step 4 until complete
                
                if (stepIndex + 2 !== currentStep && stepIndex + 2 <= 5) {
                    // Mark previous step complete
                    if (currentStep <= 5) {
                        document.getElementById('step' + currentStep).className = 'step-icon step-complete';
                        document.getElementById('step' + currentStep).innerHTML = '✓';
                    }
                    
                    // Activate new step
                    currentStep = stepIndex + 2;
                    if (currentStep <= 5) {
                        document.getElementById('step' + currentStep).className = 'step-icon step-active';
                        document.getElementById('step' + currentStep).innerHTML = currentStep;
                        
                        // Update loading text
                        if (currentStep <= 5) {
                            document.getElementById('loadingText').textContent = steps[currentStep - 2].text;
                        }
                        
                        // Update status message
                        document.getElementById('statusText').textContent = statusMessages[currentStep - 2];
                    }
                }
            }
            
            // Check for completion
            function checkCompletion() {
                fetch('/api/processing-status/{{ user_id }}')
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'completed') {
                            // Mark all steps complete
                            for (let i = 2; i <= 5; i++) {
                                document.getElementById('step' + i).className = 'step-icon step-complete';
                                document.getElementById('step' + i).innerHTML = '✓';
                            }
                            
                            document.getElementById('progressFill').style.width = '100%';
                            document.getElementById('loadingText').textContent = 'Complete! Redirecting to your results...';
                            document.getElementById('statusText').textContent = 'Your personalized matches have been saved to your account!';
                            
                            // Redirect after short delay
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1500);
                        } else if (data.status === 'error') {
                            document.getElementById('loadingText').textContent = 'Processing complete! Redirecting...';
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 2000);
                        }
                    })
                    .catch(error => {
                        console.log('Status check failed, will redirect soon...');
                    });
            }
            
            // Update progress every 200ms
            const progressInterval = setInterval(updateProgress, 200);
            
            // Check completion every 2 seconds
            const completionInterval = setInterval(checkCompletion, 2000);
            
            // Fallback redirect after 35 seconds
            setTimeout(() => {
                clearInterval(progressInterval);
                clearInterval(completionInterval);
                window.location.href = '/dashboard';
            }, 35000);
        </script>
    </body>
    </html>
    ''', user_id=user_id)

@app.route('/api/processing-status/<int:user_id>')
def processing_status_api(user_id):
    """Check processing status for authenticated user"""
    # Verify this is the logged-in user
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    status = processing_status.get(user_id, {'status': 'processing', 'progress': 0})
    return jsonify(status)

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard - shows existing matches or profile setup option"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if not user_info:
        flash('Account information not found', 'error')
        return redirect('/login')
    
    # Check if user has completed profile and has matches
    if user_info['profile_completed']:
        matches = user_auth.get_user_matches(user_id)
        
        if matches:
            # Parse analysis for each match
            for match in matches:
                match['parsed_analysis'] = parse_compatibility_analysis(match['compatibility_analysis'])
            
            return render_template_string(dashboard_with_matches_template(), 
                                        user_info=user_info, matches=matches)
        else:
            # Profile completed but no matches - rare case
            return render_template_string(dashboard_no_matches_template(), user_info=user_info)
    else:
        # No profile completed yet
        return render_template_string(dashboard_new_profile_template(), user_info=user_info)

@app.route('/update-profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    """Update existing user profile"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if not user_info or not user_info['profile_completed']:
        # If no profile exists, redirect to initial setup
        return redirect('/profile-setup')
    
    if request.method == 'POST':
        # Process the profile update
        profile_data = {}
        for key in request.form.keys():
            if key in ['interests', 'personality_traits']:
                profile_data[key] = request.form.getlist(key)
            else:
                profile_data[key] = request.form.get(key)
        
        print(f"✓ Updating profile for user {user_id}")
        
        # Clear existing blocked users for this update
        user_auth.clear_blocked_users(user_id)
        
        # Save updated profile
        user_auth.save_user_profile(user_id, profile_data)
        
        # Process blocked users
        blocked_emails = profile_data.get('blocked_emails', '')
        blocked_names = profile_data.get('blocked_names', '')
        blocked_phones = profile_data.get('blocked_phones', '')
        
        if blocked_emails:
            for email in [e.strip() for e in blocked_emails.split(',') if e.strip()]:
                user_auth.add_blocked_user(user_id, blocked_email=email)
        
        if blocked_names:
            for name in [n.strip() for n in blocked_names.split(',') if n.strip()]:
                user_auth.add_blocked_user(user_id, blocked_name=name)
        
        if blocked_phones:
            for phone in [p.strip() for p in blocked_phones.split(',') if p.strip()]:
                user_auth.add_blocked_user(user_id, blocked_phone=phone)
        
        # Start background re-matching
        thread = threading.Thread(target=process_matching_background, args=(user_id,))
        thread.daemon = True
        thread.start()
        
        flash('Profile updated successfully! Finding new matches...', 'success')
        return redirect('/processing')
    
    # GET request - show the update form with existing data
    existing_profile = user_auth.get_user_profile(user_id)
    existing_blocked = user_auth.get_blocked_users(user_id)
    
    return render_template_string(update_profile_template(), 
                                user_info=user_info, 
                                profile=existing_profile,
                                blocked=existing_blocked)



def dashboard_new_profile_template():
    """Template for dashboard when no profile completed"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .logout-btn {
                color: #666;
                text-decoration: none;
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
                transition: all 0.2s ease;
            }
            .logout-btn:hover {
                background: #f8f9fa;
                border-color: #6c5ce7;
            }
            .container {
                max-width: 800px;
                margin: 40px auto;
                padding: 40px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .welcome-section {
                text-align: center;
                margin-bottom: 40px;
                padding: 30px;
                background: #f4f2eb;
                border-radius: 15px;
                border: 2px solid #6c5ce7;
            }
            .welcome-title {
                color: black;
                font-size: 28px;
                margin-bottom: 15px;
                font-weight: bold;
            }
            .description {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
                text-align: left;
            }
            .start-btn {
                background: #6c5ce7;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: background 0.2s ease;
            }
            .start-btn:hover {
                background: #5a4fcf;
            }
            .privacy-note {
                background: #e8f4fd;
                border-radius: 6px;
                padding: 16px;
                margin: 24px 0;
                font-size: 14px;
                color: black;
                text-align: left;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>Welcome, {{ user_info.first_name or user_info.email }}!</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="welcome-section">
                <div class="welcome-title">Ready to Find Your Perfect Matches?</div>
                <p style="color: #2d2d2d; font-size: 18px; margin: 0;">
                    Let's create your profile to start matching.
                </p>
            </div>
            
            <div class="description">
                We'll ask you about your interests, values, personality, and what you're looking for in a connection. This helps us find people who are truly compatible with you based on shared interests, lifestyle, and relationship goals.
            </div>
            
            <div class="privacy-note">
                <strong>Your Privacy is Protected</strong><br>
                All matching is done securely and you have full control over who can see your profile and contact you.
            </div>
            
            <div style="text-align: center;">
                <a href="/profile-setup" class="start-btn">
                    Create Your Profile (5 minutes)
                </a>
            </div>
        </div>
    </body>
    </html>
    '''

def dashboard_with_matches_template():
    """Template for dashboard with existing matches"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Your Matches - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .logout-btn, .retake-btn {
                color: #666;
                text-decoration: none;
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
                transition: all 0.2s ease;
            }
            .logout-btn:hover, .retake-btn:hover {
                background: #f8f9fa;
                border-color: #6c5ce7;
            }
            .retake-btn {
                color: #6c5ce7;
                border-color: #6c5ce7;
            }
            .results-container {
                max-width: 1000px;
                margin: 20px auto;
                padding: 40px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .success-header {
                text-align: center;
                margin-bottom: 40px;
                padding: 30px;
                background: #f4f2eb;
                border-radius: 15px;
                border: 2px solid #6c5ce7;
            }
            .success-title {
                color: black;
                font-size: 28px;
                margin-bottom: 15px;
                font-weight: bold;
            }
            .match-card {
                background: #f8f9fa;
                border-radius: 15px;
                padding: 30px;
                margin: 25px 0;
                border-left: 5px solid #6c5ce7;
                transition: all 0.3s ease;
                position: relative;
            }
            .match-card:hover {
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                transform: translateY(-3px);
            }
            .match-rank {
                position: absolute;
                top: -15px;
                left: 30px;
                background: #6c5ce7;
                color: white;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 18px;
                box-shadow: 0 4px 10px rgba(108, 92, 231, 0.3);
                z-index: 10;
            }
            
            .match-header {
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                margin-left: 30px;
                gap: 20px;
            }
            
            .match-avatar {
                width: 80px;
                height: 80px;
                border-radius: 50%;
                background: linear-gradient(135deg, #6c5ce7, #a29bfe);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 32px;
                font-weight: 600;
                border: 3px solid white;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            
            .match-info {
                flex: 1;
            }
            
            .match-name {
                font-size: 24px;
                font-weight: bold;
                color: black;
                margin-bottom: 5px;
            }
            
            .match-distance {
                font-size: 14px;
                color: #666;
                font-style: italic;
            }
            
            .score-section {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                margin: 20px 0;
                padding: 20px;
                background: white;
                border-radius: 12px;
                border: 1px solid #e9ecef;
            }
            .score-item {
                text-align: center;
                padding: 15px;
                border-radius: 8px;
                background: #f8f9fa;
            }
            .score-label {
                font-size: 12px;
                color: black;
                text-transform: uppercase;
                margin-bottom: 8px;
                font-weight: 600;
            }
            .score-value {
                font-size: 24px;
                font-weight: bold;
                color: black;
                margin-bottom: 5px;
            }
            .score-bar {
                width: 100%;
                height: 6px;
                background: #e9ecef;
                border-radius: 3px;
                overflow: hidden;
                margin-top: 8px;
            }
            .score-fill {
                height: 100%;
                background: linear-gradient(90deg, #6c5ce7, #a29bfe);
                border-radius: 3px;
                transition: width 0.8s ease;
            }
            .analysis-section {
                background: white;
                padding: 20px;
                border-radius: 12px;
                margin: 20px 0;
                border-left: 4px solid #6c5ce7;
            }
            .analysis-text {
                color: #333;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 20px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 8px;
            }
            
            .contact-section {
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                text-align: center;
            }
            
            .contact-btn {
                background: #28a745;
                color: white;
                padding: 12px 24px;
                border-radius: 6px;
                text-decoration: none;
                display: inline-block;
                font-weight: 500;
                transition: background 0.2s ease;
                margin: 0 10px;
            }
            
            .contact-btn:hover {
                background: #218838;
                color: white;
                text-decoration: none;
            }
            
            .contact-btn.secondary {
                background: #6c5ce7;
            }
            
            .contact-btn.secondary:hover {
                background: #5a4fcf;
            }
            
            @media (max-width: 768px) {
                .results-container {
                    padding: 30px 20px;
                    margin: 10px;
                }
                .match-card {
                    padding: 25px 20px;
                }
                .match-header {
                    flex-direction: column;
                    text-align: center;
                    margin-left: 0;
                    gap: 15px;
                }
                .match-avatar {
                    width: 100px;
                    height: 100px;
                }
                .match-name {
                    font-size: 20px;
                }
                .score-section {
                    grid-template-columns: 1fr 1fr;
                    gap: 15px;
                }
                .header {
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                }
                .user-info {
                    flex-direction: column;
                    gap: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>Welcome back, {{ user_info.first_name or user_info.email }}!</span>
                <a href="/update-profile" class="retake-btn">Update Profile</a>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="results-container">
            <div class="success-header">
                <div class="success-title">Your Compatible Matches</div>
                <p style="color: #2d2d2d; font-size: 18px; margin: 0;">
                    Here are your {{ matches|length }} most compatible matches based on your profile.
                </p>
                <p style="color: black; font-size: 14px; margin: 10px 0 0 0;">
                    Profile updated: {{ user_info.profile_date[:10] if user_info.profile_date else 'Recently' }}
                </p>
            </div>
            
            {% for match in matches %}
            <div class="match-card">
                <div class="match-rank">{{ loop.index }}</div>
                
                <div class="match-header">
                    <div class="match-avatar">
                        {{ match.matched_user_name.split()[0][0] }}{{ match.matched_user_name.split()[-1][0] if match.matched_user_name.split()|length > 1 else '' }}
                    </div>
                    
                    <div class="match-info">
                        <div class="match-name">{{ match.matched_user_name }}</div>
                        {% if match.distance_miles and match.distance_miles < 500 %}
                            <div class="match-distance">{{ "%.1f"|format(match.distance_miles) }} miles away</div>
                        {% endif %}
                    </div>
                </div>
                
                <div class="score-section">
                    <div class="score-item">
                        <div class="score-label">Compatibility</div>
                        <div class="score-value">{{ match.compatibility_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.compatibility_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Personality</div>
                        <div class="score-value">{{ match.personality_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.personality_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Communication</div>
                        <div class="score-value">{{ match.communication_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.communication_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Overall Match</div>
                        <div class="score-value">{{ match.overall_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.overall_score }}%"></div>
                        </div>
                    </div>
                </div>
                
                <div class="analysis-section">
                    <div class="analysis-text">{{ match.compatibility_analysis }}</div>
                </div>
                
                <div class="contact-section">
                    <a href="mailto:{{ match.matched_user_email }}?subject=Hi from Connect - We're a match!" 
                       class="contact-btn">
                        📧 Send Message
                    </a>
                    <a href="#" onclick="showContactInfo({{ loop.index0 }})" 
                       class="contact-btn secondary">
                        📱 View Contact Info
                    </a>
                    
                    <div id="contact-info-{{ loop.index0 }}" style="display: none; margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 6px;">
                        <p style="color: #666; margin-bottom: 10px;">
                            <strong>Contact Information:</strong>
                        </p>
                        <p style="color: #666; font-size: 14px;">
                            Email: {{ match.matched_user_email }}
                        </p>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <script>
            // Animate score bars on page load
            setTimeout(() => {
                document.querySelectorAll('.score-fill').forEach(bar => {
                    const width = bar.style.width;
                    bar.style.width = '0%';
                    setTimeout(() => {
                        bar.style.width = width;
                    }, 100);
                });
            }, 500);
            
            function showContactInfo(index) {
                const contactDiv = document.getElementById('contact-info-' + index);
                if (contactDiv.style.display === 'none') {
                    contactDiv.style.display = 'block';
                } else {
                    contactDiv.style.display = 'none';
                }
            }
        </script>
    </body>
    </html>
    '''

def dashboard_no_matches_template():
    """Template for dashboard when profile completed but no matches"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                min-height: 100vh;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .logout-btn, .retake-btn {
                color: #666;
                text-decoration: none;
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
                transition: all 0.2s ease;
            }
            .logout-btn:hover, .retake-btn:hover {
                background: #f8f9fa;
                border-color: #6c5ce7;
            }
            .retake-btn {
                color: #6c5ce7;
                border-color: #6c5ce7;
            }
            .container {
                max-width: 800px;
                margin: 40px auto;
                padding: 40px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
                text-align: center;
            }
            .no-matches-title {
                color: #6c5ce7;
                font-size: 24px;
                margin-bottom: 20px;
            }
            .description {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
            }
            .update-profile-btn {
                background: #6c5ce7;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: background 0.2s ease;
            }
            .update-profile-btn:hover {
                background: #5a4fcf;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>Welcome, {{ user_info.first_name or user_info.email }}!</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <h3 class="no-matches-title">No Matches Found Yet</h3>
            <div class="description">
                We couldn't find compatible matches based on your current profile. This might be because:
                <br><br>
                • There aren't many users in your area yet
                • Your specific preferences are very particular
                • More users need to join the platform
                <br><br>
                Try updating your profile or check back later as more people join!
            </div>
            <a href="/profile-setup" class="update-profile-btn">Update Your Profile</a>
        </div>
    </body>
    </html>
    '''

def update_profile_template():
    """Template for updating existing profile"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Update Your Profile - Connect</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* Same styles as profile-setup, but with different colors for update theme */
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #f4f2eb;
                color: black;
                line-height: 1.6;
                padding: 20px;
            }
            .header {
                background: white;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                border-radius: 8px;
            }
            .logo {
                font-size: 24px;
                font-weight: 600;
                color: black;
                letter-spacing: -0.5px;
            }
            .user-info {
                display: flex;
                align-items: center;
                gap: 20px;
            }
            .logout-btn, .cancel-btn {
                color: #666;
                text-decoration: none;
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
                transition: all 0.2s ease;
            }
            .logout-btn:hover, .cancel-btn:hover {
                background: #f8f9fa;
                border-color: #6c5ce7;
            }
            .container {
                background: white;
                border-radius: 8px;
                padding: 40px;
                max-width: 700px;
                margin: 0 auto;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .profile-header {
                text-align: center;
                margin-bottom: 40px;
            }
            .profile-logo {
                font-size: 28px;
                font-weight: 600;
                color: #28a745; /* Green for update */
                margin-bottom: 8px;
                letter-spacing: -0.5px;
            }
            .subtitle {
                font-size: 16px;
                color: black;
                margin-bottom: 32px;
            }
            .last-updated {
                font-size: 14px;
                color: #666;
                background: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 20px;
            }
            .section {
                margin-bottom: 32px;
                padding: 24px;
                background: #f4f2eb;
                border-radius: 6px;
                border-left: 3px solid #28a745; /* Green for update */
            }
            .section-title {
                font-size: 18px;
                font-weight: 600;
                color: black;
                margin-bottom: 20px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                color: black;
                margin-bottom: 8px;
                font-weight: 500;
                font-size: 14px;
            }
            .form-group input, .form-group textarea, .form-group select {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease;
                background: white;
            }
            .form-group input:focus, .form-group textarea:focus, .form-group select:focus {
                border-color: #28a745;
                outline: none;
            }
            .form-group textarea {
                height: 100px;
                resize: vertical;
            }
            .checkbox-group {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin-top: 8px;
            }
            .checkbox-item {
                display: flex;
                align-items: center;
                padding: 8px;
                background: white;
                border-radius: 4px;
                border: 1px solid #ddd;
                transition: border-color 0.2s ease;
            }
            .checkbox-item:hover {
                border-color: #28a745;
            }
            .checkbox-item input[type="checkbox"] {
                margin-right: 8px;
                width: auto;
                accent-color: #28a745;
            }
            .checkbox-item label {
                margin: 0;
                font-size: 13px;
                cursor: pointer;
                flex: 1;
            }
            .button-group {
                display: flex;
                gap: 15px;
                margin-top: 30px;
            }
            .submit-btn {
                background: #28a745;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                flex: 1;
                transition: background 0.2s ease;
            }
            .submit-btn:hover {
                background: #218838;
            }
            .cancel-btn-form {
                background: #6c757d;
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 6px;
                font-size: 16px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: background 0.2s ease;
                text-align: center;
            }
            .cancel-btn-form:hover {
                background: #5a6268;
                color: white;
                text-decoration: none;
            }
            .flash-messages {
                margin-bottom: 20px;
            }
            .flash-message {
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            .flash-message.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .flash-message.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 24px 20px;
                    margin: 10px;
                }
                .section {
                    padding: 20px;
                }
                .checkbox-group {
                    grid-template-columns: 1fr;
                }
                .header {
                    flex-direction: column;
                    gap: 15px;
                    text-align: center;
                }
                .user-info {
                    flex-direction: column;
                    gap: 10px;
                }
                .button-group {
                    flex-direction: column;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">💜 Connect</div>
            <div class="user-info">
                <span>{{ user_info.first_name or user_info.email }}</span>
                <a href="/dashboard" class="cancel-btn">Back to Dashboard</a>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="profile-header">
                <h1 class="profile-logo">Update Your Profile</h1>
                <div class="subtitle">Modify your information to get better matches</div>
                
                {% if user_info.profile_date %}
                <div class="last-updated">
                    Last updated: {{ user_info.profile_date[:10] }}
                </div>
                {% endif %}
            </div>
            
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="flash-message {{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            
            <form method="POST" id="updateProfileForm">
                <div class="section">
                    <h3 class="section-title">Basic Information</h3>
                    
                    <div class="form-group">
                        <label for="age">Age</label>
                        <select id="age" name="age" required>
                            <option value="">Select your age</option>
                            <option value="18-25" {{ 'selected' if profile and profile.age == '18-25' else '' }}>18-25</option>
                            <option value="26-35" {{ 'selected' if profile and profile.age == '26-35' else '' }}>26-35</option>
                            <option value="36-45" {{ 'selected' if profile and profile.age == '36-45' else '' }}>36-45</option>
                            <option value="46-55" {{ 'selected' if profile and profile.age == '46-55' else '' }}>46-55</option>
                            <option value="56-65" {{ 'selected' if profile and profile.age == '56-65' else '' }}>56-65</option>
                            <option value="65+" {{ 'selected' if profile and profile.age == '65+' else '' }}>65+</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="location">Location (City/Area)</label>
                        <input type="text" id="location" name="location" required
                               value="{{ profile.location if profile else '' }}"
                               placeholder="e.g., London, Manchester, Brighton">
                    </div>
                    
                    <div class="form-group">
                        <label for="postcode">Postcode</label>
                        <input type="text" id="postcode" name="postcode" required
                               value="{{ profile.postcode if profile else '' }}"
                               placeholder="e.g., SW3 4HN"
                               pattern="^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]? [0-9][ABD-HJLNP-UW-Zabd-hjlnp-uw-z]{2}$">
                    </div>
                    
                    <div class="form-group">
                        <label for="occupation">Occupation</label>
                        <input type="text" id="occupation" name="occupation" required
                               value="{{ profile.occupation if profile else '' }}"
                               placeholder="What do you do for work?">
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Interests & Hobbies</h3>
                    
                    <div class="form-group">
                        <label>What are your main interests? (Select all that apply)</label>
                        <div class="checkbox-group">
                            {% set current_interests = profile.interests if profile else [] %}
                            <div class="checkbox-item">
                                <input type="checkbox" id="travel" name="interests" value="travel" 
                                       {{ 'checked' if 'travel' in current_interests else '' }}>
                                <label for="travel">Travel</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="fitness" name="interests" value="fitness"
                                       {{ 'checked' if 'fitness' in current_interests else '' }}>
                                <label for="fitness">Fitness & Health</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="music" name="interests" value="music"
                                       {{ 'checked' if 'music' in current_interests else '' }}>
                                <label for="music">Music</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="cooking" name="interests" value="cooking"
                                       {{ 'checked' if 'cooking' in current_interests else '' }}>
                                <label for="cooking">Cooking</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="reading" name="interests" value="reading"
                                       {{ 'checked' if 'reading' in current_interests else '' }}>
                                <label for="reading">Reading</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="outdoors" name="interests" value="outdoors"
                                       {{ 'checked' if 'outdoors' in current_interests else '' }}>
                                <label for="outdoors">Outdoor Activities</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="arts" name="interests" value="arts"
                                       {{ 'checked' if 'arts' in current_interests else '' }}>
                                <label for="arts">Arts & Culture</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="technology" name="interests" value="technology"
                                       {{ 'checked' if 'technology' in current_interests else '' }}>
                                <label for="technology">Technology</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="sports" name="interests" value="sports"
                                       {{ 'checked' if 'sports' in current_interests else '' }}>
                                <label for="sports">Sports</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="photography" name="interests" value="photography"
                                       {{ 'checked' if 'photography' in current_interests else '' }}>
                                <label for="photography">Photography</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="hobbies_description">Tell us more about your hobbies and interests</label>
                        <textarea id="hobbies_description" name="hobbies_description"
                                  placeholder="What do you love doing in your free time?">{{ profile.hobbies_description if profile else '' }}</textarea>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Personality & Values</h3>
                    
                    <div class="form-group">
                        <label>Which personality traits best describe you? (Select all that apply)</label>
                        <div class="checkbox-group">
                            {% set current_traits = profile.personality_traits if profile else [] %}
                            <div class="checkbox-item">
                                <input type="checkbox" id="outgoing" name="personality_traits" value="outgoing"
                                       {{ 'checked' if 'outgoing' in current_traits else '' }}>
                                <label for="outgoing">Outgoing</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="introverted" name="personality_traits" value="introverted"
                                       {{ 'checked' if 'introverted' in current_traits else '' }}>
                                <label for="introverted">Introverted</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="adventurous" name="personality_traits" value="adventurous"
                                       {{ 'checked' if 'adventurous' in current_traits else '' }}>
                                <label for="adventurous">Adventurous</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="calm" name="personality_traits" value="calm"
                                       {{ 'checked' if 'calm' in current_traits else '' }}>
                                <label for="calm">Calm & Peaceful</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="funny" name="personality_traits" value="funny"
                                       {{ 'checked' if 'funny' in current_traits else '' }}>
                                <label for="funny">Funny</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="thoughtful" name="personality_traits" value="thoughtful"
                                       {{ 'checked' if 'thoughtful' in current_traits else '' }}>
                                <label for="thoughtful">Thoughtful</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="ambitious" name="personality_traits" value="ambitious"
                                       {{ 'checked' if 'ambitious' in current_traits else '' }}>
                                <label for="ambitious">Ambitious</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="creative" name="personality_traits" value="creative"
                                       {{ 'checked' if 'creative' in current_traits else '' }}>
                                <label for="creative">Creative</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="values">What values are most important to you?</label>
                        <textarea id="values" name="values" required
                                  placeholder="e.g., Honesty, Family, Adventure, Personal Growth, Kindness...">{{ profile.values if profile else '' }}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="lifestyle">How would you describe your lifestyle?</label>
                        <select id="lifestyle" name="lifestyle" required>
                            <option value="">Select your lifestyle</option>
                            <option value="active_social" {{ 'selected' if profile and profile.lifestyle == 'active_social' else '' }}>Very active and social</option>
                            <option value="balanced" {{ 'selected' if profile and profile.lifestyle == 'balanced' else '' }}>Balanced work and social life</option>
                            <option value="career_focused" {{ 'selected' if profile and profile.lifestyle == 'career_focused' else '' }}>Career-focused</option>
                            <option value="laid_back" {{ 'selected' if profile and profile.lifestyle == 'laid_back' else '' }}>Laid back and relaxed</option>
                            <option value="family_oriented" {{ 'selected' if profile and profile.lifestyle == 'family_oriented' else '' }}>Family-oriented</option>
                            <option value="adventurous" {{ 'selected' if profile and profile.lifestyle == 'adventurous' else '' }}>Always seeking new experiences</option>
                        </select>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">What You're Looking For</h3>
                    
                    <div class="form-group">
                        <label for="looking_for">What type of connection are you seeking?</label>
                        <select id="looking_for" name="looking_for" required>
                            <option value="">Select what you're looking for</option>
                            <option value="serious_relationship" {{ 'selected' if profile and profile.looking_for == 'serious_relationship' else '' }}>Serious relationship</option>
                            <option value="casual_dating" {{ 'selected' if profile and profile.looking_for == 'casual_dating' else '' }}>Casual dating</option>
                            <option value="friendship" {{ 'selected' if profile and profile.looking_for == 'friendship' else '' }}>New friendships</option>
                            <option value="activity_partner" {{ 'selected' if profile and profile.looking_for == 'activity_partner' else '' }}>Activity partner</option>
                            <option value="open_to_see" {{ 'selected' if profile and profile.looking_for == 'open_to_see' else '' }}>Open to see what happens</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="ideal_match">Describe your ideal match</label>
                        <textarea id="ideal_match" name="ideal_match" required
                                  placeholder="What qualities are you looking for in a connection?">{{ profile.ideal_match if profile else '' }}</textarea>
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">Block List (Optional)</h3>
                    <p style="color: #666; margin-bottom: 20px; font-size: 14px;">
                        Update who you don't want to be matched with. This information is kept completely private.
                    </p>
                    
                    <div class="form-group">
                        <label for="blocked_emails">Email addresses to exclude</label>
                        <textarea id="blocked_emails" name="blocked_emails"
                                  placeholder="Enter email addresses separated by commas">{{ blocked.emails|join(', ') if blocked else '' }}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="blocked_names">Names to exclude</label>
                        <textarea id="blocked_names" name="blocked_names"
                                  placeholder="Enter full names separated by commas">{{ blocked.names|join(', ') if blocked else '' }}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="blocked_phones">Phone numbers to exclude</label>
                        <textarea id="blocked_phones" name="blocked_phones"
                                  placeholder="Enter phone numbers separated by commas">{{ blocked.phones|join(', ') if blocked else '' }}</textarea>
                    </div>
                </div>
                
                <div class="button-group">
                    <button type="submit" class="submit-btn">
                        Update Profile & Re-run Matching
                    </button>
                    <a href="/dashboard" class="cancel-btn-form">
                        Cancel Changes
                    </a>
                </div>
            </form>
        </div>
    </body>
    </html>
    '''

def parse_compatibility_analysis(analysis_text):
    """Parse the compatibility analysis text"""
    try:
        return {
            'overview': analysis_text,
            'pros': [],
            'cons': []
        }
    except Exception as e:
        print(f"Error parsing analysis: {e}")
        return {
            'overview': analysis_text,
            'pros': [],
            'cons': []
        }



# CORS and security headers
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# API endpoints
@app.route('/api/user/<int:user_id>/matches')
def api_user_matches(user_id):
    """API endpoint to get matches for a user"""
    # Verify this is the logged-in user
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

def init_database():
    """Initialize the database"""
    user_auth.init_user_database()
    print("✓ Database initialized")

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
                    
   