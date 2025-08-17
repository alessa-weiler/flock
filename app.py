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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = True  # Only if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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
        """Get saved user matches with new score fields"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT matched_user_id, matched_user_name, matched_user_email,
                    compatibility_score, personality_score, communication_score,
                    location_score, overall_score, compatibility_analysis, distance_miles,
                    values_score, lifestyle_score, emotional_score, social_score
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
                    'communication_score': match[5],  # Legacy field
                    'location_score': match[6],
                    'overall_score': match[7],
                    'compatibility_analysis': match[8],
                    'distance_miles': match[9],
                    'values_score': match[10] or 75,  # Default if None
                    'lifestyle_score': match[11] or 75,
                    'emotional_score': match[12] or 75,
                    'social_score': match[13] or 75
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
    """user-to-user matching system for friendship compatibility"""
    
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
    
    def check_gender_compatibility(self, user1_profile, user2_profile):
        """Check if users meet each other's gender preferences"""
        user1_gender = user1_profile.get('gender', '')
        user2_gender = user2_profile.get('gender', '')
        user1_preference = user1_profile.get('gender_preference', 'all')
        user2_preference = user2_profile.get('gender_preference', 'all')
        
        # Check if user1 wants to connect with user2's gender
        user1_compatible = (user1_preference == 'all' or 
                           (user1_preference == 'women' and user2_gender == 'woman') or
                           (user1_preference == 'men' and user2_gender == 'man') or
                           (user1_preference == 'non_binary' and user2_gender == 'non_binary'))
        
        # Check if user2 wants to connect with user1's gender
        user2_compatible = (user2_preference == 'all' or 
                           (user2_preference == 'women' and user1_gender == 'woman') or
                           (user2_preference == 'men' and user1_gender == 'man') or
                           (user2_preference == 'non_binary' and user1_gender == 'non_binary'))
        
        return user1_compatible and user2_compatible
    
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
    
    def calculate_personality_compatibility_score(self, user1_profile, user2_profile):
        """Calculate detailed personality compatibility using the new assessment dimensions"""
        
        # Core personality dimensions (weighted heavily)
        personality_scores = []
        
        # Decision-making compatibility (opposites can complement)
        decision_diff = abs(user1_profile.get('decision_making', 5) - user2_profile.get('decision_making', 5))
        decision_score = max(0, 100 - (decision_diff * 8))  # Moderate differences are okay
        personality_scores.append(decision_score * 1.2)
        
        # Social energy alignment (should be similar)
        social_diff = abs(user1_profile.get('social_energy', 5) - user2_profile.get('social_energy', 5))
        social_score = max(0, 100 - (social_diff * 12))  # Strong preference for similarity
        personality_scores.append(social_score * 1.5)
        
        # Communication depth (should align)
        comm_diff = abs(user1_profile.get('communication_depth', 5) - user2_profile.get('communication_depth', 5))
        comm_score = max(0, 100 - (comm_diff * 15))  # Very important to align
        personality_scores.append(comm_score * 1.8)
        
        # Conflict approach (some difference okay)
        conflict_diff = abs(user1_profile.get('conflict_approach', 5) - user2_profile.get('conflict_approach', 5))
        conflict_score = max(0, 100 - (conflict_diff * 10))
        personality_scores.append(conflict_score * 1.0)
        
        # Life pace (should be somewhat similar)
        pace_diff = abs(user1_profile.get('life_pace', 5) - user2_profile.get('life_pace', 5))
        pace_score = max(0, 100 - (pace_diff * 12))
        personality_scores.append(pace_score * 1.3)
        
        return sum(personality_scores) / len(personality_scores)
    
    def calculate_values_compatibility_score(self, user1_profile, user2_profile):
        """Calculate values and worldview alignment score"""
        
        values_scores = []
        
        # Personal growth alignment
        growth_diff = abs(user1_profile.get('personal_growth', 5) - user2_profile.get('personal_growth', 5))
        growth_score = max(0, 100 - (growth_diff * 10))
        values_scores.append(growth_score)
        
        # Success definition alignment
        success_diff = abs(user1_profile.get('success_definition', 5) - user2_profile.get('success_definition', 5))
        success_score = max(0, 100 - (success_diff * 12))
        values_scores.append(success_score)
        
        # Community involvement (some difference can be enriching)
        community_diff = abs(user1_profile.get('community_involvement', 5) - user2_profile.get('community_involvement', 5))
        community_score = max(0, 100 - (community_diff * 8))
        values_scores.append(community_score)
        
        # Work-life philosophy alignment
        worklife_diff = abs(user1_profile.get('work_life_philosophy', 5) - user2_profile.get('work_life_philosophy', 5))
        worklife_score = max(0, 100 - (worklife_diff * 11))
        values_scores.append(worklife_score)
        
        # Future orientation
        future_diff = abs(user1_profile.get('future_orientation', 5) - user2_profile.get('future_orientation', 5))
        future_score = max(0, 100 - (future_diff * 9))
        values_scores.append(future_score)
        
        return sum(values_scores) / len(values_scores)
    
    def calculate_lifestyle_compatibility_score(self, user1_profile, user2_profile):
        """Calculate lifestyle synchronization score"""
        
        lifestyle_scores = []
        
        # Energy patterns (should align for hanging out)
        energy_diff = abs(user1_profile.get('energy_patterns', 5) - user2_profile.get('energy_patterns', 5))
        energy_score = max(0, 100 - (energy_diff * 15))  # Important for scheduling
        lifestyle_scores.append(energy_score * 1.4)
        
        # Social setting preference (some variety can be good)
        setting_diff = abs(user1_profile.get('social_setting', 5) - user2_profile.get('social_setting', 5))
        setting_score = max(0, 100 - (setting_diff * 8))
        lifestyle_scores.append(setting_score)
        
        # Activity investment (complementary can work)
        activity_diff = abs(user1_profile.get('activity_investment', 5) - user2_profile.get('activity_investment', 5))
        activity_score = max(0, 100 - (activity_diff * 7))
        lifestyle_scores.append(activity_score)
        
        # Physical activity level (should be somewhat aligned)
        physical_diff = abs(user1_profile.get('physical_activity', 5) - user2_profile.get('physical_activity', 5))
        physical_score = max(0, 100 - (physical_diff * 10))
        lifestyle_scores.append(physical_score * 1.2)
        
        # Cultural consumption (difference can be enriching)
        cultural_diff = abs(user1_profile.get('cultural_consumption', 5) - user2_profile.get('cultural_consumption', 5))
        cultural_score = max(0, 100 - (cultural_diff * 6))
        lifestyle_scores.append(cultural_score)
        
        return sum(lifestyle_scores) / len(lifestyle_scores)
    
    def calculate_emotional_compatibility_score(self, user1_profile, user2_profile):
        """Calculate emotional intelligence and processing compatibility"""
        
        emotional_scores = []
        
        # Stress preference compatibility (should complement)
        stress1 = user1_profile.get('stress_preference', '')
        stress2 = user2_profile.get('stress_preference', '')
        stress_score = 85 if stress1 == stress2 else 70  # Similar styles work well
        emotional_scores.append(stress_score)
        
        # Processing style compatibility
        process1 = user1_profile.get('processing_style', '')
        process2 = user2_profile.get('processing_style', '')
        process_score = 90 if process1 == process2 else 65  # Similar processing helps
        emotional_scores.append(process_score * 1.3)
        
        # Celebration preference (should align somewhat)
        celeb_diff = abs(user1_profile.get('celebration_preference', 5) - user2_profile.get('celebration_preference', 5))
        celeb_score = max(0, 100 - (celeb_diff * 12))
        emotional_scores.append(celeb_score)
        
        return sum(emotional_scores) / len(emotional_scores)
    
    def calculate_social_boundaries_score(self, user1_profile, user2_profile):
        """Calculate social boundaries and interaction style compatibility"""
        
        boundary_scores = []
        
        # Personal sharing alignment (should be similar)
        sharing_diff = abs(user1_profile.get('personal_sharing', 5) - user2_profile.get('personal_sharing', 5))
        sharing_score = max(0, 100 - (sharing_diff * 14))
        boundary_scores.append(sharing_score * 1.4)
        
        # Social overlap tolerance
        overlap_diff = abs(user1_profile.get('social_overlap', 5) - user2_profile.get('social_overlap', 5))
        overlap_score = max(0, 100 - (overlap_diff * 8))
        boundary_scores.append(overlap_score)
        
        # Advice-giving style (complementary can work)
        advice_diff = abs(user1_profile.get('advice_giving', 5) - user2_profile.get('advice_giving', 5))
        advice_score = max(0, 100 - (advice_diff * 9))
        boundary_scores.append(advice_score)
        
        # Social commitment level (should align)
        commitment_diff = abs(user1_profile.get('social_commitment', 5) - user2_profile.get('social_commitment', 5))
        commitment_score = max(0, 100 - (commitment_diff * 13))
        boundary_scores.append(commitment_score * 1.3)
        
        return sum(boundary_scores) / len(boundary_scores)
    
    def check_red_flags_compatibility(self, user1_profile, user2_profile):
        """Check for deal-breaker red flags - returns penalty score"""
        
        # This is simplified - in reality you'd need to analyze behavioral patterns
        # For now, we'll assume no major red flags and return a neutral score
        return 85  # Base score assuming no major red flags detected
    
    def calculate_tolerance_score(self, user1_profile, user2_profile):
        """Calculate how well users tolerate differences"""
        
        # Average tolerance levels
        user1_avg_tolerance = (
            user1_profile.get('tolerance_political', 5) +
            user1_profile.get('tolerance_life_stages', 5) +
            user1_profile.get('tolerance_economic', 5) +
            user1_profile.get('tolerance_cultural', 5)
        ) / 4
        
        user2_avg_tolerance = (
            user2_profile.get('tolerance_political', 5) +
            user2_profile.get('tolerance_life_stages', 5) +
            user2_profile.get('tolerance_economic', 5) +
            user2_profile.get('tolerance_cultural', 5)
        ) / 4
        
        # Higher tolerance generally means better compatibility
        combined_tolerance = (user1_avg_tolerance + user2_avg_tolerance) / 2
        return min(100, combined_tolerance * 10)  # Scale to 0-100
    
    def run_matching(self, user_id):
        """Run comprehensive matching for a user against all other users"""
        print(f"\n=== Running Advanced Friendship Matching for {user_id} ===")
        
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
            
            # Check gender compatibility
            if not self.check_gender_compatibility(current_user_profile, potential_match['profile']):
                print(f"Skipping due to gender preference: {potential_match['first_name']} {potential_match['last_name']}")
                continue
            
            print(f"Analyzing compatibility with {potential_match['first_name']} {potential_match['last_name']}...")
            
            # Calculate detailed compatibility scores
            personality_score = self.calculate_personality_compatibility_score(current_user_profile, potential_match['profile'])
            values_score = self.calculate_values_compatibility_score(current_user_profile, potential_match['profile'])
            lifestyle_score = self.calculate_lifestyle_compatibility_score(current_user_profile, potential_match['profile'])
            emotional_score = self.calculate_emotional_compatibility_score(current_user_profile, potential_match['profile'])
            social_score = self.calculate_social_boundaries_score(current_user_profile, potential_match['profile'])
            red_flags_score = self.check_red_flags_compatibility(current_user_profile, potential_match['profile'])
            tolerance_score = self.calculate_tolerance_score(current_user_profile, potential_match['profile'])
            
            # Calculate distance if both have postcodes
            distance = 999
            location_score = 50  # Default neutral score
            current_postcode = current_user_profile.get('postcode')
            match_postcode = potential_match['profile'].get('postcode')
            
            if current_postcode and match_postcode:
                distance = self.calculate_distance(current_postcode, match_postcode)
                # Location score based on distance (closer is better)
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
                personality_score * 0.25 +
                values_score * 0.20 +
                lifestyle_score * 0.15 +
                emotional_score * 0.20 +
                social_score * 0.10 +
                red_flags_score * 0.05 +
                tolerance_score * 0.05
            )
            
            # Generate AI analysis if available
            if self.client:
                analysis = self.get_ai_friendship_analysis(current_user_profile, potential_match['profile'])
            else:
                analysis = self.get_fallback_friendship_analysis(current_user_profile, potential_match['profile'])
            
            match_result = {
                'matched_user_id': potential_match['user_id'],
                'matched_user_name': potential_match['first_name'],
                'matched_user_email': potential_match['email'],
                'compatibility_score': round(overall_score),
                'personality_score': round(personality_score),
                'values_score': round(values_score),
                'lifestyle_score': round(lifestyle_score),
                'emotional_score': round(emotional_score),
                'social_score': round(social_score),
                'location_score': round(location_score),
                'overall_score': round(overall_score),
                'compatibility_analysis': analysis,
                'distance_miles': distance
            }
            
            matches.append(match_result)
        
        # Sort by overall score
        matches.sort(key=lambda x: x['overall_score'], reverse=True)
        
        # Only keep matches with reasonable compatibility (60%+)
        matches = [m for m in matches if m['overall_score'] >= 60]
        
        # Save matches to database
        self.user_auth.save_user_matches(user_id, matches)
        
        print(f"✓ Found {len(matches)} compatible friendship matches")
        return matches
    
    def get_ai_friendship_analysis(self, user1_profile, user2_profile):
        """Get AI-powered friendship compatibility analysis"""
        
        # Create a summary of key compatibility factors
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
    
    def get_fallback_friendship_analysis(self, user1_profile, user2_profile):
        """Fallback friendship analysis without AI"""
        
        analyses = [
            "Your complementary communication styles and shared values around personal growth suggest you could build a really meaningful friendship with great conversations and mutual support.",
            "You both seem to value authentic connections and have similar approaches to handling life's challenges, which could form the foundation for a lasting and supportive friendship.",
            "Your different strengths could really complement each other well - one brings energy and planning while the other offers thoughtful listening and emotional support.",
            "You share similar lifestyle rhythms and social preferences, which means you'd likely enjoy spending time together and have compatible friendship expectations.",
            "Both of you value deep, meaningful connections over surface-level interactions, suggesting you could develop the kind of friendship where you really understand and support each other."
        ]
        
        return random.choice(analyses)

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
            <h1 class="logo"> Connect</h1>
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
            <h1 class="logo"> Connect</h1>
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
            <h1 class="logo"> Connect</h1>
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
    """Redirect to first step of onboarding"""
    return redirect('/onboarding/step/1')

@app.route('/onboarding/step/<int:step>')
@login_required
def onboarding_step(step):
    """Multi-step onboarding flow"""
    user_id = session['user_id']
    
    # Get existing profile data if updating
    existing_profile = user_auth.get_user_profile(user_id) or {}
    
    # Store current step in session
    session['onboarding_step'] = step
    
    # Define step configuration
    steps = {
        1: {
            'title': 'Basic Information',
            'description': 'Tell us about yourself',
            'template': render_step_1_template()
        },
        2: {
            'title': 'Core Personality',
            'description': 'How you approach life and relationships',
            'template': render_step_2_template()
        },
        3: {
            'title': 'Social Exchange',
            'description': 'How you give and receive in friendships',
            'template': render_step_3_template()
        },
        4: {
            'title': 'Values & Worldview',
            'description': 'What matters most to you',
            'template': render_step_4_template()
        },
        5: {
            'title': 'Lifestyle & Activities',
            'description': 'Your daily rhythms and interests',
            'template': render_step_5_template()
        },
        6: {
            'title': 'Emotional Intelligence',
            'description': 'How you process emotions and stress',
            'template': render_step_6_template()
        },
        7: {
            'title': 'Social Boundaries',
            'description': 'Your interaction style preferences',
            'template': render_step_7_template()
        },
        8: {
            'title': 'Compatibility Preferences',
            'description': 'What you value in friendships',
            'template': render_step_8_template()
        },
        9: {
            'title': 'Social Context',
            'description': 'Your current social situation',
            'template': render_step_9_template()
        },
        10: {
            'title': 'Final Details',
            'description': 'Logistics and personal touches',
            'template': render_step_10_template()
        }
    }
    
    if step not in steps:
        return redirect('/onboarding/step/1')
    
    total_steps = len(steps)
    progress_percent = (step / total_steps) * 100
    
    step_config = steps[step]
    
    return render_template_string(
        onboarding_wrapper_template(),
        step=step,
        total_steps=total_steps,
        progress_percent=progress_percent,
        step_title=step_config['title'],
        step_description=step_config['description'],
        step_content=step_config['template'],
        profile=existing_profile,
        is_last_step=(step == total_steps)
    )

@app.route('/onboarding/save-step', methods=['POST'])
@login_required
def save_onboarding_step():
    """Save current step data and redirect to next step"""
    user_id = session['user_id']
    current_step = session.get('onboarding_step', 1)
    
    # Get existing profile data or create new
    profile_data = user_auth.get_user_profile(user_id) or {}
    
    # Update profile with form data from current step
    for key, value in request.form.items():
        if key.startswith('csrf_') or key in ['action']:
            continue
        if key in ['interests', 'personality_traits', 'red_flags', 'transportation']:
            profile_data[key] = request.form.getlist(key)
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

@app.route('/onboarding/auto-save', methods=['POST'])
@login_required
def auto_save_onboarding():
    """Auto-save onboarding progress"""
    user_id = session['user_id']
    
    try:
        # Get existing profile data
        profile_data = user_auth.get_user_profile(user_id) or {}
        
        # Update with new data
        for key, value in request.json.items():
            profile_data[key] = value
        
        # Save to database
        user_auth.save_user_profile(user_id, profile_data)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/onboarding/navigation', methods=['POST'])
@login_required
def onboarding_navigation():
    """Handle step navigation with validation"""
    current_step = request.json.get('current_step')
    action = request.json.get('action')  # 'next', 'previous', 'jump'
    target_step = request.json.get('target_step')
    form_data = request.json.get('form_data', {})
    
    # Validate current step if moving forward
    if action == 'next':
        missing_fields = validate_step_data(current_step, form_data)
        if missing_fields:
            return jsonify({
                'success': False, 
                'errors': missing_fields,
                'message': 'Please complete all required fields'
            })
    
    # Auto-save current step
    user_id = session['user_id']
    profile_data = user_auth.get_user_profile(user_id) or {}
    profile_data.update(form_data)
    user_auth.save_user_profile(user_id, profile_data)
    
    # Determine next step
    if action == 'next':
        next_step = min(current_step + 1, 10)
    elif action == 'previous':
        next_step = max(current_step - 1, 1)
    elif action == 'jump' and target_step:
        next_step = max(1, min(target_step, 10))
    else:
        next_step = current_step
    
    return jsonify({
        'success': True,
        'next_step': next_step,
        'redirect_url': f'/onboarding/step/{next_step}'
    })

@app.route('/onboarding/progress')
@login_required
def onboarding_progress():
    """Get onboarding progress for user"""
    user_id = session['user_id']
    profile_data = user_auth.get_user_profile(user_id) or {}
    
    # Calculate completion percentage for each step
    step_completion = {}
    total_fields = 0
    completed_fields = 0
    
    required_fields = {
        1: ['age', 'gender', 'gender_preference', 'location', 'postcode'],
        2: ['decision_making', 'social_energy', 'communication_depth', 'conflict_approach', 'life_pace'],
        3: ['friendship_superpower', 'friend_support_style', 'friend_maintenance'],
        4: ['personal_growth', 'success_definition', 'community_involvement', 'work_life_philosophy', 'future_orientation'],
        5: ['energy_patterns', 'social_setting', 'activity_investment', 'physical_activity', 'cultural_consumption'],
        6: ['stress_preference', 'processing_style', 'celebration_preference'],
        7: ['personal_sharing', 'social_overlap', 'advice_giving', 'social_commitment'],
        8: ['rank_shared_values', 'rank_lifestyle_rhythms', 'rank_complementary_strengths', 'rank_emotional_compatibility', 'rank_activity_overlap'],
        9: ['social_satisfaction', 'friend_motivation', 'friendship_development', 'social_risk_tolerance'],
        10: ['weekly_availability', 'ideal_friendship_description', 'unique_interest', 'life_experience_impact', 'energized_by']
    }
    
    for step, fields in required_fields.items():
        step_total = len(fields)
        step_completed = sum(1 for field in fields if profile_data.get(field))
        step_completion[step] = {
            'completed': step_completed,
            'total': step_total,
            'percentage': (step_completed / step_total) * 100
        }
        total_fields += step_total
        completed_fields += step_completed
    
    overall_percentage = (completed_fields / total_fields) * 100
    
    return jsonify({
        'overall_percentage': overall_percentage,
        'step_completion': step_completion,
        'current_step': session.get('onboarding_step', 1)
    })

@app.route('/onboarding/complete', methods=['GET', 'POST'])
@login_required
def complete_onboarding():
    """Complete onboarding and start matching"""
    user_id = session['user_id']
    
    if request.method == 'POST':
        # Process final submission and blocked users
        profile_data = user_auth.get_user_profile(user_id) or {}
        
        # Process blocked users from final step
        blocked_emails = request.form.get('blocked_emails', '')
        blocked_names = request.form.get('blocked_names', '')  
        blocked_phones = request.form.get('blocked_phones', '')
        
        # Clear existing blocked users
        user_auth.clear_blocked_users(user_id)
        
        # Add new blocked users
        if blocked_emails:
            for email in [e.strip() for e in blocked_emails.split(',') if e.strip()]:
                user_auth.add_blocked_user(user_id, blocked_email=email)
        
        if blocked_names:
            for name in [n.strip() for n in blocked_names.split(',') if n.strip()]:
                user_auth.add_blocked_user(user_id, blocked_name=name)
        
        if blocked_phones:
            for phone in [p.strip() for p in blocked_phones.split(',') if p.strip()]:
                user_auth.add_blocked_user(user_id, blocked_phone=phone)
        
        # Start background matching
        thread = threading.Thread(target=process_matching_background, args=(user_id,))
        thread.daemon = True
        thread.start()
        
        # Clear onboarding session data
        session.pop('onboarding_step', None)
        
        return redirect('/processing')
    
    # Show completion page
    return render_template_string(completion_template())



@app.route('/submit-profile', methods=['POST'])
@login_required
def submit_profile():
    """Legacy route - redirect to new onboarding flow"""
    return redirect('/onboarding/step/1')


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
            <div class="logo"> Connect</div>
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
            <div class="logo"> Connect</div>
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
    """Updated template for dashboard with friendship matches"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Your Friendship Matches - Connect</title>
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
            
            .overall-compatibility {
                text-align: center;
                margin: 20px 0;
                padding: 20px;
                background: linear-gradient(135deg, #6c5ce7, #a29bfe);
                border-radius: 12px;
                color: white;
            }
            
            .overall-score {
                font-size: 48px;
                font-weight: bold;
                margin-bottom: 5px;
            }
            
            .overall-label {
                font-size: 16px;
                opacity: 0.9;
            }
            
            .score-section {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 15px;
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
                font-size: 11px;
                color: black;
                text-transform: uppercase;
                margin-bottom: 8px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            .score-value {
                font-size: 20px;
                font-weight: bold;
                color: black;
                margin-bottom: 5px;
            }
            .score-bar {
                width: 100%;
                height: 4px;
                background: #e9ecef;
                border-radius: 2px;
                overflow: hidden;
                margin-top: 6px;
            }
            .score-fill {
                height: 100%;
                background: linear-gradient(90deg, #6c5ce7, #a29bfe);
                border-radius: 2px;
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
            
            .compatibility-badges {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin: 15px 0;
            }
            
            .badge {
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
                color: white;
            }
            
            .badge-excellent {
                background: #28a745;
            }
            
            .badge-good {
                background: #6c5ce7;
            }
            
            .badge-fair {
                background: #ffc107;
                color: #333;
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
                    grid-template-columns: repeat(2, 1fr);
                    gap: 12px;
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
                .overall-score {
                    font-size: 36px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo"> Connect</div>
            <div class="user-info">
                <span>Welcome back, {{ user_info.first_name or user_info.email }}!</span>
                <a href="/update-profile" class="retake-btn">Update Profile</a>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="results-container">
            <div class="success-header">
                <div class="success-title">Your Friendship Compatibility Matches</div>
                <p style="color: #2d2d2d; font-size: 18px; margin: 0;">
                    Here are your {{ matches|length }} most compatible friendship matches based on your comprehensive profile.
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
                
                <div class="overall-compatibility">
                    <div class="overall-score">{{ match.overall_score }}%</div>
                    <div class="overall-label">Overall Friendship Compatibility</div>
                </div>
                
                <div class="compatibility-badges">
                    {% if match.personality_score >= 85 %}
                        <span class="badge badge-excellent">Excellent Personality Match</span>
                    {% elif match.personality_score >= 70 %}
                        <span class="badge badge-good">Good Personality Match</span>
                    {% endif %}
                    
                    {% if match.values_score >= 85 %}
                        <span class="badge badge-excellent">Strong Values Alignment</span>
                    {% elif match.values_score >= 70 %}
                        <span class="badge badge-good">Values Compatibility</span>
                    {% endif %}
                    
                    {% if match.emotional_score >= 85 %}
                        <span class="badge badge-excellent">Emotional Harmony</span>
                    {% elif match.emotional_score >= 70 %}
                        <span class="badge badge-good">Emotional Compatibility</span>
                    {% endif %}
                    
                    {% if match.lifestyle_score >= 85 %}
                        <span class="badge badge-excellent">Lifestyle Sync</span>
                    {% elif match.lifestyle_score >= 70 %}
                        <span class="badge badge-good">Lifestyle Match</span>
                    {% endif %}
                    
                    {% if match.distance_miles and match.distance_miles <= 15 %}
                        <span class="badge badge-good">Close Distance</span>
                    {% endif %}
                </div>
                
                <div class="score-section">
                    <div class="score-item">
                        <div class="score-label">Personality</div>
                        <div class="score-value">{{ match.personality_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.personality_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Values</div>
                        <div class="score-value">{{ match.values_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.values_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Lifestyle</div>
                        <div class="score-value">{{ match.lifestyle_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.lifestyle_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Emotional</div>
                        <div class="score-value">{{ match.emotional_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.emotional_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Social Style</div>
                        <div class="score-value">{{ match.social_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.social_score }}%"></div>
                        </div>
                    </div>
                    <div class="score-item">
                        <div class="score-label">Location</div>
                        <div class="score-value">{{ match.location_score }}</div>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ match.location_score }}%"></div>
                        </div>
                    </div>
                </div>
                
                <div class="analysis-section">
                    <div class="analysis-text">{{ match.compatibility_analysis }}</div>
                </div>
                
                <div class="contact-section">
                    <a href="mailto:{{ match.matched_user_email }}?subject=Hi from Connect - We're a friendship match!" 
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
            
            {% if matches|length == 0 %}
            <div style="text-align: center; padding: 40px; color: #666;">
                <h3>No Compatible Matches Found</h3>
                <p style="margin: 20px 0;">We couldn't find friendship matches that meet your compatibility criteria yet. This could be because:</p>
                <ul style="text-align: left; max-width: 400px; margin: 0 auto;">
                    <li>There aren't many users in your area yet</li>
                    <li>Your preferences are very specific</li>
                    <li>More users need to join the platform</li>
                </ul>
                <p style="margin: 20px 0;">Try updating your profile or check back as more people join!</p>
                <a href="/update-profile" class="contact-btn">Update Your Profile</a>
            </div>
            {% endif %}
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
            <div class="logo"> Connect</div>
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
            <div class="logo"> Connect</div>
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

def update_user_matches_table():
    """Update the user_matches table to include new score fields"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Add new columns if they don't exist
    new_columns = [
        'values_score INTEGER',
        'lifestyle_score INTEGER', 
        'emotional_score INTEGER',
        'social_score INTEGER'
    ]
    
    for column in new_columns:
        try:
            cursor.execute(f'ALTER TABLE user_matches ADD COLUMN {column}')
            print(f"✓ Added column: {column}")
        except sqlite3.OperationalError:
            # Column already exists
            pass
    
    conn.commit()
    conn.close()

def onboarding_wrapper_template():
    """Main wrapper template for all onboarding steps"""
    return '''
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
                max-width: 800px;
                margin: 0 auto 40px auto;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
            }
            .onboarding-header {
                text-align: center;
                margin-bottom: 30px;
            }
            .step-indicator {
                font-size: 14px;
                color: #666;
                margin-bottom: 10px;
            }
            .step-title {
                font-size: 28px;
                font-weight: 600;
                color: black;
                margin-bottom: 8px;
            }
            .step-description {
                font-size: 16px;
                color: #666;
                margin-bottom: 20px;
            }
            .progress-container {
                background: #f2f2f2;
                border-radius: 10px;
                height: 8px;
                margin: 20px 0;
                overflow: hidden;
            }
            .progress-bar {
                background: linear-gradient(90deg, #6c5ce7, #a29bfe);
                height: 100%;
                border-radius: 10px;
                transition: width 0.5s ease;
                width: {{ progress_percent }}%;
            }
            .form-content {
                margin: 30px 0;
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
                height: 80px;
                resize: vertical;
            }
            .slider-group {
                margin: 20px 0;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
            .slider-label {
                font-weight: 500;
                margin-bottom: 15px;
                color: black;
            }
            .slider-container {
                position: relative;
                margin: 20px 0;
            }
            .slider {
                width: 100%;
                height: 6px;
                border-radius: 3px;
                background: #ddd;
                outline: none;
                -webkit-appearance: none;
                appearance: none;
            }
            .slider::-webkit-slider-thumb {
                appearance: none;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: #6c5ce7;
                cursor: pointer;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            }
            .slider::-moz-range-thumb {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: #6c5ce7;
                cursor: pointer;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            }
            .slider-labels {
                display: flex;
                justify-content: space-between;
                margin-top: 8px;
                font-size: 12px;
                color: #666;
            }
            .checkbox-group {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 10px;
                margin-top: 8px;
            }
            .checkbox-item {
                display: flex;
                align-items: center;
                padding: 12px;
                background: white;
                border-radius: 4px;
                border: 1px solid #ddd;
                transition: border-color 0.2s ease;
            }
            .checkbox-item:hover {
                border-color: #6c5ce7;
            }
            .checkbox-item input[type="checkbox"], .checkbox-item input[type="radio"] {
                margin-right: 10px;
                width: auto;
                accent-color: #6c5ce7;
            }
            .checkbox-item label {
                margin: 0;
                font-size: 14px;
                cursor: pointer;
                flex: 1;
            }
            .navigation-buttons {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #eee;
            }
            .btn {
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: all 0.2s ease;
                border: none;
                text-align: center;
            }
            .btn-primary {
                background: #6c5ce7;
                color: white;
            }
            .btn-primary:hover {
                background: #5a4fcf;
            }
            .btn-secondary {
                background: #f8f9fa;
                color: #666;
                border: 1px solid #ddd;
            }
            .btn-secondary:hover {
                background: #e9ecef;
                border-color: #6c5ce7;
            }
            .btn-success {
                background: #28a745;
                color: white;
            }
            .btn-success:hover {
                background: #218838;
            }
            .btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            .step-info {
                background: #f8f9fa;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 25px;
                border-left: 4px solid #6c5ce7;
            }
            .ranking-group {
                margin: 20px 0;
            }
            .ranking-item {
                display: flex;
                align-items: center;
                padding: 12px;
                background: white;
                border-radius: 4px;
                border: 1px solid #ddd;
                margin: 8px 0;
            }
            .ranking-item select {
                width: 60px;
                margin-right: 15px;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 24px 20px;
                    margin: 10px auto 20px auto;
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
                .navigation-buttons {
                    flex-direction: column;
                    gap: 15px;
                }
                .btn {
                    width: 100%;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo"> Connect</div>
            <div class="user-info">
                <span>{{ session.user_name or session.user_email }}</span>
                <a href="/logout" class="logout-btn">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="onboarding-header">
                <div class="step-indicator">Step {{ step }} of {{ total_steps }}</div>
                <h1 class="step-title">{{ step_title }}</h1>
                <div class="step-description">{{ step_description }}</div>
                
                <div class="progress-container">
                    <div class="progress-bar"></div>
                </div>
            </div>
            
            <form method="POST" action="/onboarding/save-step" id="stepForm">
                <div class="form-content">
                    {{ step_content|safe }}
                </div>
                
                <div class="navigation-buttons">
                    <div>
                        {% if step > 1 %}
                        <button type="submit" name="action" value="previous" class="btn btn-secondary">
                            ← Previous
                        </button>
                        {% endif %}
                    </div>
                    
                    <div>
                        {% if is_last_step %}
                        <button type="submit" name="action" value="complete" class="btn btn-success">
                            Complete Profile & Find Matches
                        </button>
                        {% else %}
                        <button type="submit" name="action" value="next" class="btn btn-primary">
                            Next →
                        </button>
                        {% endif %}
                    </div>
                </div>
            </form>
        </div>
        
        <script>
            // Enhanced JavaScript functionality
            class OnboardingManager {
                constructor() {
                    this.currentStep = {{ step }};
                    this.autoSaveDelay = 2000;
                    this.autoSaveTimer = null;
                    this.init();
                }
                
                init() {
                    this.setupFormValidation();
                    this.setupAutoSave();
                    this.setupKeyboardNavigation();
                    this.setupProgressTracking();
                }
                
                setupFormValidation() {
                    const form = document.getElementById('stepForm');
                    const inputs = form.querySelectorAll('input, textarea, select');
                    
                    inputs.forEach(input => {
                        input.addEventListener('blur', (e) => {
                            this.validateField(e.target);
                        });
                        
                        input.addEventListener('input', (e) => {
                            this.clearFieldError(e.target);
                            this.scheduleAutoSave();
                        });
                    });
                }
                
                validateField(field) {
                    if (field.hasAttribute('required') && !field.value.trim()) {
                        this.showFieldError(field, 'This field is required');
                        return false;
                    }
                    
                    // Postcode validation
                    if (field.name === 'postcode') {
                        const postcodeRegex = /^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]? [0-9][ABD-HJLNP-UW-Zabd-hjlnp-uw-z]{2}$/;
                        if (field.value && !postcodeRegex.test(field.value)) {
                            this.showFieldError(field, 'Please enter a valid UK postcode');
                            return false;
                        }
                    }
                    
                    // Red flags validation
                    if (field.name === 'red_flags') {
                        const checkedFlags = document.querySelectorAll('input[name="red_flags"]:checked');
                        if (checkedFlags.length > 3) {
                            this.showFieldError(field, 'Please select maximum 3 red flags');
                            return false;
                        }
                    }
                    
                    this.clearFieldError(field);
                    return true;
                }
                
                showFieldError(field, message) {
                    field.style.borderColor = '#dc3545';
                    
                    // Remove existing error message
                    const existingError = field.parentNode.querySelector('.field-error');
                    if (existingError) {
                        existingError.remove();
                    }
                    
                    // Add error message
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'field-error';
                    errorDiv.style.color = '#dc3545';
                    errorDiv.style.fontSize = '12px';
                    errorDiv.style.marginTop = '4px';
                    errorDiv.textContent = message;
                    field.parentNode.appendChild(errorDiv);
                }
                
                clearFieldError(field) {
                    field.style.borderColor = '#ddd';
                    const errorDiv = field.parentNode.querySelector('.field-error');
                    if (errorDiv) {
                        errorDiv.remove();
                    }
                }
                
                scheduleAutoSave() {
                    clearTimeout(this.autoSaveTimer);
                    this.autoSaveTimer = setTimeout(() => {
                        this.autoSave();
                    }, this.autoSaveDelay);
                }
                
                autoSave() {
                    const formData = new FormData(document.getElementById('stepForm'));
                    const data = {};
                    
                    for (let [key, value] of formData.entries()) {
                        if (data[key]) {
                            if (Array.isArray(data[key])) {
                                data[key].push(value);
                            } else {
                                data[key] = [data[key], value];
                            }
                        } else {
                            data[key] = value;
                        }
                    }
                    
                    fetch('/onboarding/auto-save', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(data)
                    }).then(response => response.json())
                      .then(data => {
                          if (data.success) {
                              this.showAutoSaveIndicator();
                          }
                      }).catch(error => {
                          console.log('Auto-save failed:', error);
                      });
                }
                
                showAutoSaveIndicator() {
                    const indicator = document.getElementById('autoSaveIndicator');
                    if (!indicator) {
                        const div = document.createElement('div');
                        div.id = 'autoSaveIndicator';
                        div.style.position = 'fixed';
                        div.style.top = '20px';
                        div.style.right = '20px';
                        div.style.background = '#28a745';
                        div.style.color = 'white';
                        div.style.padding = '8px 16px';
                        div.style.borderRadius = '4px';
                        div.style.fontSize = '14px';
                        div.style.zIndex = '1000';
                        div.style.opacity = '0';
                        div.style.transition = 'opacity 0.3s ease';
                        div.textContent = '✓ Saved';
                        document.body.appendChild(div);
                        
                        setTimeout(() => {
                            div.style.opacity = '1';
                            setTimeout(() => {
                                div.style.opacity = '0';
                                setTimeout(() => {
                                    if (div.parentNode) {
                                        div.parentNode.removeChild(div);
                                    }
                                }, 300);
                            }, 1500);
                        }, 100);
                    }
                }
                
                setupKeyboardNavigation() {
                    document.addEventListener('keydown', (e) => {
                        if (e.ctrlKey || e.metaKey) {
                            if (e.key === 'ArrowLeft') {
                                e.preventDefault();
                                this.goToPreviousStep();
                            } else if (e.key === 'ArrowRight') {
                                e.preventDefault();
                                this.goToNextStep();
                            }
                        }
                    });
                }
                
                setupProgressTracking() {
                    this.updateProgress();
                }
                
                updateProgress() {
                    fetch('/onboarding/progress')
                        .then(response => response.json())
                        .then(data => {
                            const progressBar = document.querySelector('.progress-bar');
                            if (progressBar) {
                                progressBar.style.width = data.overall_percentage + '%';
                            }
                        })
                        .catch(error => {
                            console.log('Progress update failed:', error);
                        });
                }
                
                goToNextStep() {
                    const nextBtn = document.querySelector('button[value="next"]');
                    if (nextBtn) {
                        nextBtn.click();
                    }
                }
                
                goToPreviousStep() {
                    const prevBtn = document.querySelector('button[value="previous"]');
                    if (prevBtn) {
                        prevBtn.click();
                    }
                }
            }
            
            // Initialize when DOM is loaded
            document.addEventListener('DOMContentLoaded', () => {
                new OnboardingManager();
            });
        </script>
    </body>
    </html>
    '''


def render_step_1_template():
    """Step 1: Basic Information"""
    return '''
    <div class="step-info">
        <strong>Let's start with the basics!</strong><br>
        This information helps us find people in your area and ensures you're matched with the right people.
    </div>
    
    <div class="form-group">
        <label for="age">Age</label>
        <input type="number" id="age" name="age" required min="18" max="100" 
               value="{{ profile.age if profile else '' }}" placeholder="Enter your age">
    </div>
    
    <div class="form-group">
        <label for="gender">Gender</label>
        <select id="gender" name="gender" required>
            <option value="">Select your gender</option>
            <option value="woman" {{ 'selected' if profile and profile.gender == 'woman' else '' }}>Woman</option>
            <option value="man" {{ 'selected' if profile and profile.gender == 'man' else '' }}>Man</option>
            <option value="non_binary" {{ 'selected' if profile and profile.gender == 'non_binary' else '' }}>Non-binary</option>
            <option value="prefer_not_to_say" {{ 'selected' if profile and profile.gender == 'prefer_not_to_say' else '' }}>Prefer not to say</option>
        </select>
    </div>
    
    <div class="form-group">
        <label for="gender_preference">Looking to connect with</label>
        <select id="gender_preference" name="gender_preference" required>
            <option value="">Select preference</option>
            <option value="women" {{ 'selected' if profile and profile.gender_preference == 'women' else '' }}>Women</option>
            <option value="men" {{ 'selected' if profile and profile.gender_preference == 'men' else '' }}>Men</option>
            <option value="non_binary" {{ 'selected' if profile and profile.gender_preference == 'non_binary' else '' }}>Non-binary people</option>
            <option value="all" {{ 'selected' if profile and profile.gender_preference == 'all' else '' }}>All genders</option>
        </select>
    </div>
    
    <div class="form-group">
        <label for="location">Location (City/Area)</label>
        <input type="text" id="location" name="location" required
               value="{{ profile.location if profile else '' }}"
               placeholder="e.g., London, Manchester, Brighton">
    </div>
    
    <div class="form-group">
        <label for="postcode">Postcode (for distance calculations)</label>
        <input type="text" id="postcode" name="postcode" required
               value="{{ profile.postcode if profile else '' }}"
               placeholder="e.g., SW3 4HN"
               pattern="^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]? [0-9][ABD-HJLNP-UW-Zabd-hjlnp-uw-z]{2}$"
               title="Please enter a valid UK postcode">
    </div>
    '''


def render_step_2_template():
    """Step 2: Core Personality Architecture"""
    return '''
    <div class="step-info">
        <strong>Core Personality Architecture</strong><br>
        These unique psychological dimensions help us understand your friendship compatibility style.
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Decision-making style</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.decision_making if profile else 5 }}" 
                   class="slider" id="decision_making" name="decision_making">
            <div class="slider-labels">
                <span>Logic-driven</span>
                <span>Emotion-driven</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Social energy preference</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_energy if profile else 5 }}" 
                   class="slider" id="social_energy" name="social_energy">
            <div class="slider-labels">
                <span>Intimate connections</span>
                <span>Wide social circles</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Communication depth</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.communication_depth if profile else 5 }}" 
                   class="slider" id="communication_depth" name="communication_depth">
            <div class="slider-labels">
                <span>Surface-level fun</span>
                <span>Deep conversations</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Conflict approach</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.conflict_approach if profile else 5 }}" 
                   class="slider" id="conflict_approach" name="conflict_approach">
            <div class="slider-labels">
                <span>Direct confrontation</span>
                <span>Gentle discussion</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Life pace preference</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.life_pace if profile else 5 }}" 
                   class="slider" id="life_pace" name="life_pace">
            <div class="slider-labels">
                <span>Structured routine</span>
                <span>Spontaneous flow</span>
            </div>
        </div>
    </div>
    '''


def render_step_3_template():
    """Step 3: Social Exchange Patterns"""
    return '''
    <div class="step-info">
        <strong>Social Exchange Patterns</strong><br>
        Understanding how you give and receive in friendships helps us find complementary matches.
    </div>
    
    <div class="form-group">
        <label>Your friendship superpower (Choose one)</label>
        <div class="checkbox-group">
            {% set current_superpower = profile.friendship_superpower if profile else '' %}
            <div class="checkbox-item">
                <input type="radio" id="superpower_laugh" name="friendship_superpower" value="making_people_laugh"
                       {{ 'checked' if current_superpower == 'making_people_laugh' else '' }}>
                <label for="superpower_laugh">Making people laugh</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="superpower_advice" name="friendship_superpower" value="giving_thoughtful_advice"
                       {{ 'checked' if current_superpower == 'giving_thoughtful_advice' else '' }}>
                <label for="superpower_advice">Giving thoughtful advice</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="superpower_planning" name="friendship_superpower" value="planning_amazing_experiences"
                       {{ 'checked' if current_superpower == 'planning_amazing_experiences' else '' }}>
                <label for="superpower_planning">Planning amazing experiences</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="superpower_listening" name="friendship_superpower" value="being_reliable_listener"
                       {{ 'checked' if current_superpower == 'being_reliable_listener' else '' }}>
                <label for="superpower_listening">Being a reliable listener</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="superpower_perspectives" name="friendship_superpower" value="bringing_diverse_perspectives"
                       {{ 'checked' if current_superpower == 'bringing_diverse_perspectives' else '' }}>
                <label for="superpower_perspectives">Bringing diverse perspectives</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="superpower_safe_space" name="friendship_superpower" value="creating_safe_emotional_space"
                       {{ 'checked' if current_superpower == 'creating_safe_emotional_space' else '' }}>
                <label for="superpower_safe_space">Creating safe emotional space</label>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label>When friends are struggling, you typically:</label>
        <div class="checkbox-group">
            {% set current_support = profile.friend_support_style if profile else '' %}
            <div class="checkbox-item">
                <input type="radio" id="struggle_solutions" name="friend_support_style" value="offer_practical_solutions"
                       {{ 'checked' if current_support == 'offer_practical_solutions' else '' }}>
                <label for="struggle_solutions">Offer practical solutions</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="struggle_emotional" name="friend_support_style" value="provide_emotional_support"
                       {{ 'checked' if current_support == 'provide_emotional_support' else '' }}>
                <label for="struggle_emotional">Provide emotional support</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="struggle_space" name="friend_support_style" value="give_space_to_process"
                       {{ 'checked' if current_support == 'give_space_to_process' else '' }}>
                <label for="struggle_space">Give them space to process</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="struggle_distract" name="friend_support_style" value="distract_with_fun"
                       {{ 'checked' if current_support == 'distract_with_fun' else '' }}>
                <label for="struggle_distract">Distract them with fun activities</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="struggle_share" name="friend_support_style" value="share_similar_experiences"
                       {{ 'checked' if current_support == 'share_similar_experiences' else '' }}>
                <label for="struggle_share">Share similar experiences</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="struggle_resources" name="friend_support_style" value="connect_with_resources"
                       {{ 'checked' if current_support == 'connect_with_resources' else '' }}>
                <label for="struggle_resources">Connect them with resources</label>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Friend maintenance energy</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.friend_maintenance if profile else 5 }}" 
                   class="slider" id="friend_maintenance" name="friend_maintenance">
            <div class="slider-labels">
                <span>High-touch regular contact</span>
                <span>Low-key periodic connection</span>
            </div>
        </div>
    </div>
    '''


def render_step_4_template():
    """Step 4: Values & Worldview Alignment"""
    return '''
    <div class="step-info">
        <strong>Values & Worldview Alignment</strong><br>
        Understanding what drives you helps us find friends who share your fundamental outlook.
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Personal growth priority</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.personal_growth if profile else 5 }}" 
                   class="slider" id="personal_growth" name="personal_growth">
            <div class="slider-labels">
                <span>Self-improvement</span>
                <span>Self-acceptance</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Success definition</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.success_definition if profile else 5 }}" 
                   class="slider" id="success_definition" name="success_definition">
            <div class="slider-labels">
                <span>External achievements</span>
                <span>Internal fulfillment</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Community involvement</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.community_involvement if profile else 5 }}" 
                   class="slider" id="community_involvement" name="community_involvement">
            <div class="slider-labels">
                <span>Highly engaged locally</span>
                <span>Globally minded</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Work-life philosophy</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.work_life_philosophy if profile else 5 }}" 
                   class="slider" id="work_life_philosophy" name="work_life_philosophy">
            <div class="slider-labels">
                <span>Career-focused</span>
                <span>Life-balance focused</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Future orientation</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.future_orientation if profile else 5 }}" 
                   class="slider" id="future_orientation" name="future_orientation">
            <div class="slider-labels">
                <span>Detailed planning</span>
                <span>Present-moment living</span>
            </div>
        </div>
    </div>
    '''


def render_step_5_template():
    """Step 5: Activity & Lifestyle Synchronization"""
    return '''
    <div class="step-info">
        <strong>Activity & Lifestyle Synchronization</strong><br>
        Your daily rhythms and activity preferences help us find friends you'll actually enjoy spending time with.
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Energy patterns</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.energy_patterns if profile else 5 }}" 
                   class="slider" id="energy_patterns" name="energy_patterns">
            <div class="slider-labels">
                <span>Early morning active</span>
                <span>Night owl active</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Social setting preference</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_setting if profile else 5 }}" 
                   class="slider" id="social_setting" name="social_setting">
            <div class="slider-labels">
                <span>Home-based hangouts</span>
                <span>Out-and-about adventures</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Activity investment</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.activity_investment if profile else 5 }}" 
                   class="slider" id="activity_investment" name="activity_investment">
            <div class="slider-labels">
                <span>Few deep interests</span>
                <span>Many varied interests</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Physical activity level</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.physical_activity if profile else 5 }}" 
                   class="slider" id="physical_activity" name="physical_activity">
            <div class="slider-labels">
                <span>Low/sedentary</span>
                <span>High/athletic</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Cultural consumption</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.cultural_consumption if profile else 5 }}" 
                   class="slider" id="cultural_consumption" name="cultural_consumption">
            <div class="slider-labels">
                <span>Mainstream popular</span>
                <span>Niche alternative</span>
            </div>
        </div>
    </div>
    '''


def render_step_6_template():
    """Step 6: Emotional Intelligence Mapping"""
    return '''
    <div class="step-info">
        <strong>Emotional Intelligence Mapping</strong><br>
        How you process emotions and handle stress is crucial for friendship compatibility.
    </div>
    
    <div class="form-group">
        <label>When you're stressed, you prefer friends who:</label>
        <div class="checkbox-group">
            {% set current_stress = profile.stress_preference if profile else '' %}
            <div class="checkbox-item">
                <input type="radio" id="stress_space" name="stress_preference" value="give_space_until_ready"
                       {{ 'checked' if current_stress == 'give_space_until_ready' else '' }}>
                <label for="stress_space">Give you space until you're ready</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="stress_check_in" name="stress_preference" value="check_in_regularly_gently"
                       {{ 'checked' if current_stress == 'check_in_regularly_gently' else '' }}>
                <label for="stress_check_in">Check in regularly but gently</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="stress_problem_solve" name="stress_preference" value="actively_help_problem_solve"
                       {{ 'checked' if current_stress == 'actively_help_problem_solve' else '' }}>
                <label for="stress_problem_solve">Actively help problem-solve</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="stress_distraction" name="stress_preference" value="provide_distraction_lightness"
                       {{ 'checked' if current_stress == 'provide_distraction_lightness' else '' }}>
                <label for="stress_distraction">Provide distraction and lightness</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="stress_match_energy" name="stress_preference" value="match_emotional_energy"
                       {{ 'checked' if current_stress == 'match_emotional_energy' else '' }}>
                <label for="stress_match_energy">Match your emotional energy</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="stress_calm" name="stress_preference" value="stay_calm_grounding"
                       {{ 'checked' if current_stress == 'stay_calm_grounding' else '' }}>
                <label for="stress_calm">Stay calm and grounding</label>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label>Your emotional processing style:</label>
        <div class="checkbox-group">
            {% set current_processing = profile.processing_style if profile else '' %}
            <div class="checkbox-item">
                <input type="radio" id="process_internal_first" name="processing_style" value="think_internally_then_share"
                       {{ 'checked' if current_processing == 'think_internally_then_share' else '' }}>
                <label for="process_internal_first">Think through internally first, then share</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="process_talk_through" name="processing_style" value="talk_through_as_they_come"
                       {{ 'checked' if current_processing == 'talk_through_as_they_come' else '' }}>
                <label for="process_talk_through">Talk through feelings as they come up</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="process_time_alone" name="processing_style" value="need_time_alone_before_discussing"
                       {{ 'checked' if current_processing == 'need_time_alone_before_discussing' else '' }}>
                <label for="process_time_alone">Need time alone before discussing</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="process_activities" name="processing_style" value="process_through_activities_together"
                       {{ 'checked' if current_processing == 'process_through_activities_together' else '' }}>
                <label for="process_activities">Process best through activities together</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="process_written" name="processing_style" value="prefer_written_text_communication"
                       {{ 'checked' if current_processing == 'prefer_written_text_communication' else '' }}>
                <label for="process_written">Prefer written/text communication</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="process_shared_experiences" name="processing_style" value="work_through_via_shared_experiences"
                       {{ 'checked' if current_processing == 'work_through_via_shared_experiences' else '' }}>
                <label for="process_shared_experiences">Work through emotions via shared experiences</label>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Celebration preference</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.celebration_preference if profile else 5 }}" 
                   class="slider" id="celebration_preference" name="celebration_preference">
            <div class="slider-labels">
                <span>Quiet acknowledgment</span>
                <span>Big enthusiastic celebrations</span>
            </div>
        </div>
    </div>
    '''


def render_step_7_template():
    """Step 7: Social Boundaries & Compatibility"""
    return '''
    <div class="step-info">
        <strong>Social Boundaries & Compatibility</strong><br>
        Understanding your comfort zones helps us match you with people who respect your style.
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Personal sharing comfort</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.personal_sharing if profile else 5 }}" 
                   class="slider" id="personal_sharing" name="personal_sharing">
            <div class="slider-labels">
                <span>Private person</span>
                <span>Open book</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Social overlap tolerance</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_overlap if profile else 5 }}" 
                   class="slider" id="social_overlap" name="social_overlap">
            <div class="slider-labels">
                <span>Separate friend groups</span>
                <span>Integrated social circles</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Advice-giving style</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.advice_giving if profile else 5 }}" 
                   class="slider" id="advice_giving" name="advice_giving">
            <div class="slider-labels">
                <span>Direct honest feedback</span>
                <span>Supportive validation</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Social commitment level</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_commitment if profile else 5 }}" 
                   class="slider" id="social_commitment" name="social_commitment">
            <div class="slider-labels">
                <span>Flexible casual plans</span>
                <span>Firm scheduled commitments</span>
            </div>
        </div>
    </div>
    '''


def render_step_8_template():
    """Step 8: Compatibility Preferences & Deal-breakers"""
    return '''
    <div class="step-info">
        <strong>Compatibility Preferences & Deal-breakers</strong><br>
        Help us understand what matters most to you in friendships and what to avoid.
    </div>
    
    <div class="form-group">
        <label>Most important friendship foundation (Rank 1-5, with 1 being most important)</label>
        <div class="ranking-group">
            <div class="ranking-item">
                <select name="rank_shared_values" required>
                    <option value="">Rank</option>
                    <option value="1" {{ 'selected' if profile and profile.rank_shared_values == '1' else '' }}>1</option>
                    <option value="2" {{ 'selected' if profile and profile.rank_shared_values == '2' else '' }}>2</option>
                    <option value="3" {{ 'selected' if profile and profile.rank_shared_values == '3' else '' }}>3</option>
                    <option value="4" {{ 'selected' if profile and profile.rank_shared_values == '4' else '' }}>4</option>
                    <option value="5" {{ 'selected' if profile and profile.rank_shared_values == '5' else '' }}>5</option>
                </select>
                <label>Shared core values</label>
            </div>
            <div class="ranking-item">
                <select name="rank_lifestyle_rhythms" required>
                    <option value="">Rank</option>
                    <option value="1" {{ 'selected' if profile and profile.rank_lifestyle_rhythms == '1' else '' }}>1</option>
                    <option value="2" {{ 'selected' if profile and profile.rank_lifestyle_rhythms == '2' else '' }}>2</option>
                    <option value="3" {{ 'selected' if profile and profile.rank_lifestyle_rhythms == '3' else '' }}>3</option>
                    <option value="4" {{ 'selected' if profile and profile.rank_lifestyle_rhythms == '4' else '' }}>4</option>
                    <option value="5" {{ 'selected' if profile and profile.rank_lifestyle_rhythms == '5' else '' }}>5</option>
                </select>
                <label>Similar lifestyle rhythms</label>
            </div>
            <div class="ranking-item">
                <select name="rank_complementary_strengths" required>
                    <option value="">Rank</option>
                    <option value="1" {{ 'selected' if profile and profile.rank_complementary_strengths == '1' else '' }}>1</option>
                    <option value="2" {{ 'selected' if profile and profile.rank_complementary_strengths == '2' else '' }}>2</option>
                    <option value="3" {{ 'selected' if profile and profile.rank_complementary_strengths == '3' else '' }}>3</option>
                    <option value="4" {{ 'selected' if profile and profile.rank_complementary_strengths == '4' else '' }}>4</option>
                    <option value="5" {{ 'selected' if profile and profile.rank_complementary_strengths == '5' else '' }}>5</option>
                </select>
                <label>Complementary strengths</label>
            </div>
            <div class="ranking-item">
                <select name="rank_emotional_compatibility" required>
                    <option value="">Rank</option>
                    <option value="1" {{ 'selected' if profile and profile.rank_emotional_compatibility == '1' else '' }}>1</option>
                    <option value="2" {{ 'selected' if profile and profile.rank_emotional_compatibility == '2' else '' }}>2</option>
                    <option value="3" {{ 'selected' if profile and profile.rank_emotional_compatibility == '3' else '' }}>3</option>
                    <option value="4" {{ 'selected' if profile and profile.rank_emotional_compatibility == '4' else '' }}>4</option>
                    <option value="5" {{ 'selected' if profile and profile.rank_emotional_compatibility == '5' else '' }}>5</option>
                </select>
                <label>Emotional compatibility</label>
            </div>
            <div class="ranking-item">
                <select name="rank_activity_overlap" required>
                    <option value="">Rank</option>
                    <option value="1" {{ 'selected' if profile and profile.rank_activity_overlap == '1' else '' }}>1</option>
                    <option value="2" {{ 'selected' if profile and profile.rank_activity_overlap == '2' else '' }}>2</option>
                    <option value="3" {{ 'selected' if profile and profile.rank_activity_overlap == '3' else '' }}>3</option>
                    <option value="4" {{ 'selected' if profile and profile.rank_activity_overlap == '4' else '' }}>4</option>
                    <option value="5" {{ 'selected' if profile and profile.rank_activity_overlap == '5' else '' }}>5</option>
                </select>
                <label>Activity/interest overlap</label>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label>Friendship red flags (Select up to 3)</label>
        <div class="checkbox-group">
            {% set current_flags = profile.red_flags if profile else [] %}
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_selfcentered" name="red_flags" value="consistently_self_centered"
                       {{ 'checked' if 'consistently_self_centered' in current_flags else '' }}>
                <label for="redflag_selfcentered">Consistently self-centered conversations</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_cancellations" name="red_flags" value="frequent_plan_cancellations"
                       {{ 'checked' if 'frequent_plan_cancellations' in current_flags else '' }}>
                <label for="redflag_cancellations">Frequent plan cancellations</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_gossiping" name="red_flags" value="gossiping_about_friends"
                       {{ 'checked' if 'gossiping_about_friends' in current_flags else '' }}>
                <label for="redflag_gossiping">Gossiping about other friends</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_pressuring" name="red_flags" value="pressuring_uncomfortable_things"
                       {{ 'checked' if 'pressuring_uncomfortable_things' in current_flags else '' }}>
                <label for="redflag_pressuring">Pressuring to try things you're uncomfortable with</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_judging" name="red_flags" value="making_feel_judged"
                       {{ 'checked' if 'making_feel_judged' in current_flags else '' }}>
                <label for="redflag_judging">Making you feel judged for your choices</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_competing" name="red_flags" value="competing_rather_celebrating"
                       {{ 'checked' if 'competing_rather_celebrating' in current_flags else '' }}>
                <label for="redflag_competing">Competing rather than celebrating your successes</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_volatility" name="red_flags" value="emotional_volatility_without_awareness"
                       {{ 'checked' if 'emotional_volatility_without_awareness' in current_flags else '' }}>
                <label for="redflag_volatility">Emotional volatility without self-awareness</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="redflag_pushing_views" name="red_flags" value="pushing_political_religious_views"
                       {{ 'checked' if 'pushing_political_religious_views' in current_flags else '' }}>
                <label for="redflag_pushing_views">Pushing political/religious views</label>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label>Difference tolerance: How comfortable are you with friends who have:</label>
        
        <div class="slider-group">
            <div class="slider-label">Very different political views</div>
            <div class="slider-container">
                <input type="range" min="1" max="10" value="{{ profile.tolerance_political if profile else 5 }}" 
                       class="slider" id="tolerance_political" name="tolerance_political">
                <div class="slider-labels">
                    <span>Uncomfortable</span>
                    <span>Energizing</span>
                </div>
            </div>
        </div>
        
        <div class="slider-group">
            <div class="slider-label">Different life stages</div>
            <div class="slider-container">
                <input type="range" min="1" max="10" value="{{ profile.tolerance_life_stages if profile else 5 }}" 
                       class="slider" id="tolerance_life_stages" name="tolerance_life_stages">
                <div class="slider-labels">
                    <span>Uncomfortable</span>
                    <span>Energizing</span>
                </div>
            </div>
        </div>
        
        <div class="slider-group">
            <div class="slider-label">Different economic backgrounds</div>
            <div class="slider-container">
                <input type="range" min="1" max="10" value="{{ profile.tolerance_economic if profile else 5 }}" 
                       class="slider" id="tolerance_economic" name="tolerance_economic">
                <div class="slider-labels">
                    <span>Uncomfortable</span>
                    <span>Energizing</span>
                </div>
            </div>
        </div>
        
        <div class="slider-group">
            <div class="slider-label">Different cultural backgrounds</div>
            <div class="slider-container">
                <input type="range" min="1" max="10" value="{{ profile.tolerance_cultural if profile else 5 }}" 
                       class="slider" id="tolerance_cultural" name="tolerance_cultural">
                <div class="slider-labels">
                    <span>Uncomfortable</span>
                    <span>Energizing</span>
                </div>
            </div>
        </div>
    </div>
    '''


def render_step_9_template():
    """Step 9: Social Context & Goals"""
    return '''
    <div class="step-info">
        <strong>Social Context & Goals</strong><br>
        Understanding your current social situation helps us find the right type of connections.
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Current social satisfaction</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_satisfaction if profile else 5 }}" 
                   class="slider" id="social_satisfaction" name="social_satisfaction">
            <div class="slider-labels">
                <span>Very lonely</span>
                <span>Socially fulfilled</span>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label>New friend motivation (Choose primary reason)</label>
        <div class="checkbox-group">
            {% set current_motivation = profile.friend_motivation if profile else '' %}
            <div class="checkbox-item">
                <input type="radio" id="motivation_moved" name="friend_motivation" value="recently_moved"
                       {{ 'checked' if current_motivation == 'recently_moved' else '' }}>
                <label for="motivation_moved">Recently moved to new area</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_transition" name="friend_motivation" value="life_transition"
                       {{ 'checked' if current_motivation == 'life_transition' else '' }}>
                <label for="motivation_transition">Life transition changed social needs</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_activity" name="friend_motivation" value="activity_companions"
                       {{ 'checked' if current_motivation == 'activity_companions' else '' }}>
                <label for="motivation_activity">Want activity-specific companions</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_deeper" name="friend_motivation" value="deeper_connections"
                       {{ 'checked' if current_motivation == 'deeper_connections' else '' }}>
                <label for="motivation_deeper">Seeking deeper emotional connections</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_unavailable" name="friend_motivation" value="friends_unavailable"
                       {{ 'checked' if current_motivation == 'friends_unavailable' else '' }}>
                <label for="motivation_unavailable">Current friends unavailable/busy</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_diverse" name="friend_motivation" value="diverse_perspectives"
                       {{ 'checked' if current_motivation == 'diverse_perspectives' else '' }}>
                <label for="motivation_diverse">Want more diverse perspectives</label>
            </div>
            <div class="checkbox-item">
                <input type="radio" id="motivation_outgrew" name="friend_motivation" value="outgrew_social_circle"
                       {{ 'checked' if current_motivation == 'outgrew_social_circle' else '' }}>
                <label for="motivation_outgrew">Outgrew current social circle</label>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Ideal friendship development</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.friendship_development if profile else 5 }}" 
                   class="slider" id="friendship_development" name="friendship_development">
            <div class="slider-labels">
                <span>Fast deep connection</span>
                <span>Gradual trust building</span>
            </div>
        </div>
    </div>
    
    <div class="slider-group">
        <div class="slider-label">Social risk tolerance</div>
        <div class="slider-container">
            <input type="range" min="1" max="10" value="{{ profile.social_risk_tolerance if profile else 5 }}" 
                   class="slider" id="social_risk_tolerance" name="social_risk_tolerance">
            <div class="slider-labels">
                <span>Prefer safe known experiences</span>
                <span>Love trying new things together</span>
            </div>
        </div>
    </div>
    '''


def render_step_10_template():
    """Step 10: Final Details"""
    return '''
    <div class="step-info">
        <strong>Final Details</strong><br>
        Last step! Help us understand your practical needs and add some personal touches.
    </div>
    
    <div class="form-group">
        <label for="weekly_availability">Weekly social availability</label>
        <select id="weekly_availability" name="weekly_availability" required>
            <option value="">Select your availability</option>
            <option value="1-2 hours" {{ 'selected' if profile and profile.weekly_availability == '1-2 hours' else '' }}>1-2 hours</option>
            <option value="3-5 hours" {{ 'selected' if profile and profile.weekly_availability == '3-5 hours' else '' }}>3-5 hours</option>
            <option value="6-10 hours" {{ 'selected' if profile and profile.weekly_availability == '6-10 hours' else '' }}>6-10 hours</option>
            <option value="10+ hours" {{ 'selected' if profile and profile.weekly_availability == '10+ hours' else '' }}>10+ hours</option>
        </select>
    </div>
    
    <div class="form-group">
        <label>Transportation (Select all that apply)</label>
        <div class="checkbox-group">
            {% set current_transport = profile.transportation if profile else [] %}
            <div class="checkbox-item">
                <input type="checkbox" id="transport_walk" name="transportation" value="walk_bike"
                       {{ 'checked' if 'walk_bike' in current_transport else '' }}>
                <label for="transport_walk">Walk/bike</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="transport_car" name="transportation" value="car"
                       {{ 'checked' if 'car' in current_transport else '' }}>
                <label for="transport_car">Car</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="transport_public" name="transportation" value="public_transit"
                       {{ 'checked' if 'public_transit' in current_transport else '' }}>
                <label for="transport_public">Public transit</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="transport_flexible" name="transportation" value="flexible"
                       {{ 'checked' if 'flexible' in current_transport else '' }}>
                <label for="transport_flexible">Flexible</label>
            </div>
        </div>
    </div>
    
    <div class="form-group">
        <label for="ideal_friendship_description">Describe your ideal friendship in one sentence:</label>
        <textarea id="ideal_friendship_description" name="ideal_friendship_description" required
                  placeholder="What would your perfect friendship look like?">{{ profile.ideal_friendship_description if profile else '' }}</textarea>
    </div>
    
    <div class="form-group">
        <label for="unique_interest">What's a unique interest or hobby you'd love to share with someone?</label>
        <textarea id="unique_interest" name="unique_interest" required
                  placeholder="Something special you're passionate about...">{{ profile.unique_interest if profile else '' }}</textarea>
    </div>
    
    <div class="form-group">
        <label for="life_experience_impact">What life experience has most shaped how you approach friendships?</label>
        <textarea id="life_experience_impact" name="life_experience_impact" required
                  placeholder="A moment or period that changed your perspective...">{{ profile.life_experience_impact if profile else '' }}</textarea>
    </div>
    
    <div class="form-group">
        <label for="energized_by">Complete this: 'I feel most energized around people who...'</label>
        <textarea id="energized_by" name="energized_by" required
                  placeholder="Finish this sentence...">{{ profile.energized_by if profile else '' }}</textarea>
    </div>
    '''


def completion_template():
    """Completion page template"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Complete Your Profile - Connect</title>
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
            .container {
                background: white;
                border-radius: 8px;
                padding: 60px 40px;
                max-width: 600px;
                margin: 0 auto;
                box-shadow: 0 2px 20px rgba(0,0,0,0.05);
                text-align: center;
            }
            .completion-icon {
                font-size: 64px;
                margin-bottom: 20px;
            }
            .completion-title {
                font-size: 32px;
                font-weight: 600;
                color: #28a745;
                margin-bottom: 16px;
            }
            .completion-subtitle {
                font-size: 18px;
                color: #666;
                margin-bottom: 30px;
            }
            .completion-description {
                font-size: 16px;
                color: #333;
                margin-bottom: 40px;
                text-align: left;
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #28a745;
            }
            .block-list-section {
                background: #f8f9fa;
                padding: 30px;
                border-radius: 8px;
                margin: 30px 0;
                text-align: left;
            }
            .block-list-title {
                font-size: 18px;
                font-weight: 600;
                color: black;
                margin-bottom: 15px;
            }
            .block-list-description {
                font-size: 14px;
                color: #666;
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
            .form-group textarea {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-family: inherit;
                height: 60px;
                resize: vertical;
                background: white;
            }
            .form-group textarea:focus {
                border-color: #28a745;
                outline: none;
            }
            .complete-btn {
                background: #28a745;
                color: white;
                border: none;
                padding: 18px 36px;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s ease;
                margin-top: 20px;
            }
            .complete-btn:hover {
                background: #218838;
            }
            .progress-summary {
                background: linear-gradient(135deg, #6c5ce7, #a29bfe);
                color: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 30px;
            }
            .progress-summary h3 {
                margin-bottom: 10px;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 40px 24px;
                    margin: 16px;
                }
                .completion-title {
                    font-size: 28px;
                }
                .completion-icon {
                    font-size: 48px;
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo"> Connect</div>
            <div class="user-info">
                <span>{{ session.user_name or session.user_email }}</span>
            </div>
        </div>
        
        <div class="container">
            <div class="completion-icon">🎉</div>
            <h1 class="completion-title">Profile Almost Complete!</h1>
            <div class="completion-subtitle">One final optional step before we find your matches</div>
            
            <div class="progress-summary">
                <h3>✓ Profile Complete</h3>
                <p>You've completed all 10 sections of your comprehensive friendship profile. Our AI is ready to find your most compatible matches!</p>
            </div>
            
            <div class="completion-description">
                <strong>What happens next:</strong><br>
                • Our AI will analyze your responses across all personality dimensions<br>
                • We'll compare you with other users to find the best friendship matches<br>
                • You'll get detailed compatibility scores and explanations<br>
                • You can contact your matches directly through the platform
            </div>
            
            <form method="POST">
                <div class="block-list-section">
                    <h3 class="block-list-title">Block List (Optional)</h3>
                    <div class="block-list-description">
                        If there are specific people you don't want to be matched with, you can add them here. 
                        This information is kept completely private and secure.
                    </div>
                    
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
                
                <button type="submit" class="complete-btn">
                    🚀 Complete Profile & Find My Matches
                </button>
            </form>
        </div>
    </body>
    </html>
    '''

def validate_step_data(step, form_data):
    """Validate data for specific step"""
    required_fields = {
        1: ['age', 'gender', 'gender_preference', 'location', 'postcode'],
        2: ['decision_making', 'social_energy', 'communication_depth', 'conflict_approach', 'life_pace'],
        3: ['friendship_superpower', 'friend_support_style', 'friend_maintenance'],
        4: ['personal_growth', 'success_definition', 'community_involvement', 'work_life_philosophy', 'future_orientation'],
        5: ['energy_patterns', 'social_setting', 'activity_investment', 'physical_activity', 'cultural_consumption'],
        6: ['stress_preference', 'processing_style', 'celebration_preference'],
        7: ['personal_sharing', 'social_overlap', 'advice_giving', 'social_commitment'],
        8: ['rank_shared_values', 'rank_lifestyle_rhythms', 'rank_complementary_strengths', 'rank_emotional_compatibility', 'rank_activity_overlap'],
        9: ['social_satisfaction', 'friend_motivation', 'friendship_development', 'social_risk_tolerance'],
        10: ['weekly_availability', 'ideal_friendship_description', 'unique_interest', 'life_experience_impact', 'energized_by']
    }
    
    step_required = required_fields.get(step, [])
    missing_fields = []
    
    for field in step_required:
        if field not in form_data or not form_data[field]:
            missing_fields.append(field)
    
    # Special validation for rankings - must be unique
    if step == 8:
        ranking_fields = ['rank_shared_values', 'rank_lifestyle_rhythms', 'rank_complementary_strengths', 
                         'rank_emotional_compatibility', 'rank_activity_overlap']
        ranking_values = [form_data.get(field) for field in ranking_fields if form_data.get(field)]
        if len(ranking_values) != len(set(ranking_values)):
            missing_fields.append('unique_rankings')
    
    # Special validation for red flags - max 3
    if step == 8:
        red_flags = form_data.getlist('red_flags')
        if len(red_flags) > 3:
            missing_fields.append('too_many_red_flags')
    
    return missing_fields

def get_enhanced_onboarding_js():
    """Enhanced JavaScript for better UX"""
    return '''
    <script>
        class OnboardingManager {
            constructor() {
                this.currentStep = {{ step }};
                this.autoSaveDelay = 2000; // 2 seconds
                this.autoSaveTimer = null;
                this.init();
            }
            
            init() {
                this.setupFormValidation();
                this.setupAutoSave();
                this.setupKeyboardNavigation();
                this.setupProgressTracking();
            }
            
            setupFormValidation() {
                const form = document.getElementById('stepForm');
                const inputs = form.querySelectorAll('input, textarea, select');
                
                inputs.forEach(input => {
                    input.addEventListener('blur', (e) => {
                        this.validateField(e.target);
                    });
                    
                    input.addEventListener('input', (e) => {
                        this.clearFieldError(e.target);
                        this.scheduleAutoSave();
                    });
                });
            }
            
            validateField(field) {
                if (field.hasAttribute('required') && !field.value.trim()) {
                    this.showFieldError(field, 'This field is required');
                    return false;
                }
                
                // Special validations
                if (field.name === 'postcode') {
                    const postcodeRegex = /^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]? [0-9][ABD-HJLNP-UW-Zabd-hjlnp-uw-z]{2}$/;
                    if (field.value && !postcodeRegex.test(field.value)) {
                        this.showFieldError(field, 'Please enter a valid UK postcode');
                        return false;
                    }
                }
                
                if (field.name === 'red_flags') {
                    const checkedFlags = document.querySelectorAll('input[name="red_flags"]:checked');
                    if (checkedFlags.length > 3) {
                        this.showFieldError(field, 'Please select maximum 3 red flags');
                        return false;
                    }
                }
                
                this.clearFieldError(field);
                return true;
            }
            
            showFieldError(field, message) {
                field.style.borderColor = '#dc3545';
                
                // Remove existing error message
                const existingError = field.parentNode.querySelector('.field-error');
                if (existingError) {
                    existingError.remove();
                }
                
                // Add error message
                const errorDiv = document.createElement('div');
                errorDiv.className = 'field-error';
                errorDiv.style.color = '#dc3545';
                errorDiv.style.fontSize = '12px';
                errorDiv.style.marginTop = '4px';
                errorDiv.textContent = message;
                field.parentNode.appendChild(errorDiv);
            }
            
            clearFieldError(field) {
                field.style.borderColor = '#ddd';
                const errorDiv = field.parentNode.querySelector('.field-error');
                if (errorDiv) {
                    errorDiv.remove();
                }
            }
            
            setupAutoSave() {
                // Auto-save functionality
            }
            
            scheduleAutoSave() {
                clearTimeout(this.autoSaveTimer);
                this.autoSaveTimer = setTimeout(() => {
                    this.autoSave();
                }, this.autoSaveDelay);
            }
            
            autoSave() {
                const formData = new FormData(document.getElementById('stepForm'));
                const data = {};
                
                for (let [key, value] of formData.entries()) {
                    if (data[key]) {
                        if (Array.isArray(data[key])) {
                            data[key].push(value);
                        } else {
                            data[key] = [data[key], value];
                        }
                    } else {
                        data[key] = value;
                    }
                }
                
                fetch('/onboarding/auto-save', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          this.showAutoSaveIndicator();
                      }
                  });
            }
            
            showAutoSaveIndicator() {
                const indicator = document.getElementById('autoSaveIndicator');
                if (!indicator) {
                    const div = document.createElement('div');
                    div.id = 'autoSaveIndicator';
                    div.style.position = 'fixed';
                    div.style.top = '20px';
                    div.style.right = '20px';
                    div.style.background = '#28a745';
                    div.style.color = 'white';
                    div.style.padding = '8px 16px';
                    div.style.borderRadius = '4px';
                    div.style.fontSize = '14px';
                    div.style.zIndex = '1000';
                    div.style.opacity = '0';
                    div.style.transition = 'opacity 0.3s ease';
                    div.textContent = '✓ Saved';
                    document.body.appendChild(div);
                    
                    setTimeout(() => {
                        div.style.opacity = '1';
                        setTimeout(() => {
                            div.style.opacity = '0';
                            setTimeout(() => {
                                if (div.parentNode) {
                                    div.parentNode.removeChild(div);
                                }
                            }, 300);
                        }, 1500);
                    }, 100);
                }
            }
            
            setupKeyboardNavigation() {
                document.addEventListener('keydown', (e) => {
                    if (e.ctrlKey || e.metaKey) {
                        if (e.key === 'ArrowLeft') {
                            e.preventDefault();
                            this.goToPreviousStep();
                        } else if (e.key === 'ArrowRight') {
                            e.preventDefault();
                            this.goToNextStep();
                        }
                    }
                });
            }
            
            setupProgressTracking() {
                this.updateProgress();
            }
            
            updateProgress() {
                fetch('/onboarding/progress')
                    .then(response => response.json())
                    .then(data => {
                        const progressBar = document.querySelector('.progress-bar');
                        if (progressBar) {
                            progressBar.style.width = data.overall_percentage + '%';
                        }
                    });
            }
            
            goToNextStep() {
                const nextBtn = document.querySelector('button[value="next"]');
                if (nextBtn) {
                    nextBtn.click();
                }
            }
            
            goToPreviousStep() {
                const prevBtn = document.querySelector('button[value="previous"]');
                if (prevBtn) {
                    prevBtn.click();
                }
            }
        }
        
        // Initialize when DOM is loaded
        document.addEventListener('DOMContentLoaded', () => {
            new OnboardingManager();
        });
    </script>
    '''


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
                    
   