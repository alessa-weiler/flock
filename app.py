import os
import warnings

# Standard library imports
import base64
import hashlib
import json
import logging
import math
import random
import re
import secrets
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

# Third-party imports
import psycopg2
import requests
import stripe
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
from flask import (Flask, abort, flash, get_flashed_messages, jsonify, redirect,
                   render_template_string, request, send_from_directory, session, url_for)
from flask_cors import CORS
from openai import OpenAI
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash

# Local imports
from enhanced_matching_system import (EnhancedMatchingSystem, InteractionTracker,
                                       MatchingDataCollector, MatchingSystem,
                                       integrate_enhanced_matching)
from payment import SubscriptionManager

# Load environment variables
load_dotenv()

# Suppress protobuf warnings
warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================================
# APP CONFIGURATION
# ============================================================================

app = Flask(__name__)
app.secret_key = 'pont-matching-secret-key-change-in-production'
CORS(app, origins="*", supports_credentials=True)

# Configuration
API_KEY = os.environ.get('OPENAI_API_KEY')
if API_KEY:
    print(f"✓ OpenAI API Key loaded: {API_KEY[:8]}...{API_KEY[-4:]}")
else:
    print("⚠️  WARNING: OPENAI_API_KEY not found in environment variables!")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_FROM = os.environ.get('EMAIL_FROM', EMAIL_USER)

FRESH_API_KEY = os.environ.get('FRESH_API_KEY')

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
# CONNECTING TO POSTGRESQL DATABASE
# ============================================================================

def get_db_connection():
    """Get PostgreSQL database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable not set")
    
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


# ============================================================================
# USER AUTHENTICATION SYSTEM + ANONYMIZATION + COMPLIANCE
# ============================================================================

class UserAuthSystem:
    """Handles user authentication and account management"""
    
    def __init__(self):
        self.init_user_database()
        self.encryption = data_encryption
    
    def init_user_database(self):
        """Initialize user accounts database with PostgreSQL"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Enhanced users table with encryption
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                anonymous_id TEXT UNIQUE NOT NULL,
                email_hash TEXT UNIQUE NOT NULL,
                email_encrypted TEXT NOT NULL,
                email TEXT,  -- Keep for backward compatibility during migration
                password_hash TEXT NOT NULL,
                first_name_encrypted TEXT,
                last_name_encrypted TEXT,
                first_name TEXT,  -- Keep for backward compatibility
                last_name TEXT,   -- Keep for backward compatibility
                phone_encrypted TEXT,
                phone_hash TEXT,
                phone TEXT,  -- Keep for backward compatibility
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                profile_completed BOOLEAN DEFAULT FALSE,
                profile_date TIMESTAMP,
                data_consent BOOLEAN DEFAULT FALSE,
                data_consent_date TIMESTAMP,
                min_age INTEGER DEFAULT 18,
                max_age INTEGER DEFAULT 65,
                bio TEXT,
                profile_photo_url TEXT
            )
        ''')

        # Data processing log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_processing_log (
                id SERIAL PRIMARY KEY,
                anonymous_id TEXT NOT NULL,
                action TEXT NOT NULL,
                purpose TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_hash TEXT,
                user_agent_hash TEXT
            )
        ''')

        # Add new columns if they don't exist (PostgreSQL way)
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS min_age INTEGER DEFAULT 18')
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS max_age INTEGER DEFAULT 65')
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT')
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_url TEXT')
            print("✓ Added new columns to users table")
        except psycopg2.Error as e:
            print(f"Column addition info: {e}")
        
        # Create profile privacy settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profile_privacy (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                share_personality_scores BOOLEAN DEFAULT TRUE,
                share_values_scores BOOLEAN DEFAULT TRUE,
                share_lifestyle_info BOOLEAN DEFAULT TRUE,
                share_social_preferences BOOLEAN DEFAULT TRUE,
                share_contact_info BOOLEAN DEFAULT TRUE,
                share_detailed_analysis BOOLEAN DEFAULT TRUE,
                share_bio BOOLEAN DEFAULT TRUE,
                share_photo BOOLEAN DEFAULT TRUE,
                share_exact_location BOOLEAN DEFAULT FALSE,
                share_age BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
        ''')
        
        # User profiles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS anonymous_profiles (
                id SERIAL PRIMARY KEY,
                anonymous_id TEXT NOT NULL,
                profile_data_encrypted TEXT NOT NULL,
                profile_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (anonymous_id) REFERENCES users (anonymous_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                profile_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
        ''')
        
        # User matches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_matches (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                matched_user_id INTEGER NOT NULL,
                matched_user_name TEXT NOT NULL,
                matched_user_email TEXT,
                matched_user_phone TEXT,
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
                is_active BOOLEAN DEFAULT TRUE,
                user_would_meet_again BOOLEAN,
                match_would_meet_again BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (matched_user_id) REFERENCES users (id)
            )
        ''')
            
        # Blocked users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_users (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Follow-up tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS followup_tracking (
                id SERIAL PRIMARY KEY,
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
        #tracking user interactions for ML
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_interactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                target_user_id INTEGER,
                context_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                outcome TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS social_clusters (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                cluster_snapshot TEXT NOT NULL,
                cluster_metrics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_data (
                id SERIAL PRIMARY KEY,
                feature_vector TEXT NOT NULL,
                target_outcome REAL NOT NULL,
                interaction_context TEXT,
                user_pair TEXT,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_performance (
                id SERIAL PRIMARY KEY,
                model_version TEXT NOT NULL,
                accuracy REAL,
                precision_score REAL,
                recall_score REAL,
                training_data_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        #Stripe payment tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                stripe_customer_id TEXT UNIQUE,
                stripe_subscription_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'inactive',
                plan_id TEXT,
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matching_usage (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                matching_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_free_run BOOLEAN DEFAULT FALSE,
                subscription_active BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Add subscription columns to users table
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS free_matches_used INTEGER DEFAULT 0')
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_free_match_date TIMESTAMP')
            print("✓ Added subscription columns to users table")
        except Exception as e:
            print(f"Subscription columns may already exist: {e}")
        
        try:
            cursor.execute('ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP')
            cursor.execute('ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN DEFAULT FALSE')
            print("✓ Updated subscription table schema")
        except Exception as e:
            print(f"Schema update error: {e}")
        
        #Add linkedin URL
        try:
            cursor.execute('ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS linkedin_url TEXT')
            print("✓ Added linkedin_url column to user_profiles table")
        except psycopg2.Error as e:
            print(f"LinkedIn URL column may already exist: {e}")

        # Add V2 mode setting to users table
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS matching_mode TEXT DEFAULT \'individual\'')
            print("✓ Added matching_mode column to users table")
        except psycopg2.Error as e:
            print(f"Matching mode column may already exist: {e}")

        # Create V2 network tables
        self.create_v2_tables(cursor)

        conn.commit()
        conn.close()

    def create_v2_tables(self, cursor):
        """Create tables for V2 network functionality"""

        # Networks table - stores network groups created by users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS networks (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (owner_id) REFERENCES users (id)
            )
        ''')

        # Network people - stores individuals in a network with their LinkedIn data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_people (
                id SERIAL PRIMARY KEY,
                network_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                linkedin_url TEXT,
                linkedin_data_encrypted TEXT,
                profile_summary TEXT,
                skills TEXT,
                experience_years INTEGER,
                industry TEXT,
                location TEXT,
                education TEXT,
                mutual_connections INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (network_id) REFERENCES networks (id) ON DELETE CASCADE
            )
        ''')

        # Network relationships - stores compatibility scores and manual adjustments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_relationships (
                id SERIAL PRIMARY KEY,
                network_id INTEGER NOT NULL,
                person1_id INTEGER NOT NULL,
                person2_id INTEGER NOT NULL,
                compatibility_score DECIMAL(3,2) DEFAULT 0.0,
                manual_score DECIMAL(3,2),
                ai_reasoning TEXT,
                manual_note TEXT,
                relationship_strength DECIMAL(3,2) DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (network_id) REFERENCES networks (id) ON DELETE CASCADE,
                FOREIGN KEY (person1_id) REFERENCES network_people (id) ON DELETE CASCADE,
                FOREIGN KEY (person2_id) REFERENCES network_people (id) ON DELETE CASCADE,
                UNIQUE(person1_id, person2_id)
            )
        ''')

        # Network visualization settings - stores user preferences for graph layout
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_viz_settings (
                id SERIAL PRIMARY KEY,
                network_id INTEGER NOT NULL,
                layout_data TEXT,
                node_positions TEXT,
                view_settings TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (network_id) REFERENCES networks (id) ON DELETE CASCADE,
                UNIQUE(network_id)
            )
        ''')

        # Organizations table - stores business/team organizations for simulation
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS organizations (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER NOT NULL,
                invite_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')

        # Organization members - junction table linking users to organizations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS organization_members (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE(organization_id, user_id)
            )
        ''')

        # Simulations table - stores each scenario simulation run
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS simulations (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                scenario_text TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                completed_at TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')

        # Simulation responses - stores AI-generated responses for each user
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS simulation_responses (
                id SERIAL PRIMARY KEY,
                simulation_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                response_json TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (simulation_id) REFERENCES simulations (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                UNIQUE(simulation_id, user_id)
            )
        ''')

        # Embed configurations - settings for embeddable widgets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embed_configurations (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                embed_token TEXT UNIQUE NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('party', 'simulation')),
                person_specification TEXT,
                use_linkedin BOOLEAN DEFAULT FALSE,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users (id),
                UNIQUE(organization_id)
            )
        ''')

        # Migration: Add use_linkedin column if it doesn't exist
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'embed_configurations'
                    AND column_name = 'use_linkedin'
                ) THEN
                    ALTER TABLE embed_configurations ADD COLUMN use_linkedin BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        ''')

        # Embed sessions - tracks anonymous widget usage
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embed_sessions (
                id SERIAL PRIMARY KEY,
                embed_config_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                onboarding_data TEXT NOT NULL,
                results_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (embed_config_id) REFERENCES embed_configurations (id) ON DELETE CASCADE
            )
        ''')

        # Applicants table - tracks candidates who apply via widget
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS applicants (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                embed_session_id INTEGER,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                linkedin_url TEXT,
                application_token TEXT UNIQUE NOT NULL,
                onboarding_data TEXT NOT NULL,
                compatibility_results TEXT,
                behavioral_fit_analysis TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
                FOREIGN KEY (embed_session_id) REFERENCES embed_sessions (id) ON DELETE SET NULL
            )
        ''')

        # Events table - stores upcoming events for matching
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                venue_name VARCHAR(255),
                venue_address TEXT,
                date_time TIMESTAMPTZ NOT NULL,
                capacity INTEGER DEFAULT 50,
                current_attendees INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')

        # Event registrations - tracks who is attending which event
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_registrations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                registered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                attended BOOLEAN DEFAULT FALSE,
                feedback_submitted BOOLEAN DEFAULT FALSE,
                UNIQUE(user_id, event_id)
            )
        ''')

        # Event feedback - post-event feedback for gating access to next events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_feedback (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                matched_users INTEGER[] DEFAULT '{}',
                no_show BOOLEAN DEFAULT FALSE,
                feedback_text TEXT,
                submitted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, user_id)
            )
        ''')

        print("✓ Created V2 network and events tables")

    def create_user(self, email: str, password: str, first_name: str = None, 
               last_name: str = None, phone: str = None, min_age: int = 18, 
               max_age: int = 100, data_consent: bool = True) -> Dict[str, Any]:
        """Create user with encryption and anonymization"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Create hashes for duplicate checking
            email_hash = self.encryption.hash_for_matching(email.lower().strip())
            phone_hash = self.encryption.hash_for_matching(phone) if phone else None
            
            # Check if email/phone already exists
            cursor.execute('SELECT id FROM users WHERE email_hash = %s OR phone_hash = %s', 
                        (email_hash, phone_hash))
            if cursor.fetchone():
                conn.close()
                return {'success': False, 'error': 'Email or phone already registered'}
            
            # Generate anonymous ID
            anonymous_id = self.encryption.generate_anonymous_id()
            
            # Encrypt sensitive data
            email_encrypted = self.encryption.encrypt_sensitive_data(email)
            first_name_encrypted = self.encryption.encrypt_sensitive_data(first_name) if first_name else None
            last_name_encrypted = self.encryption.encrypt_sensitive_data(last_name) if last_name else None
            phone_encrypted = self.encryption.encrypt_sensitive_data(phone) if phone else None
            
            # Create password hash
            password_hash = generate_password_hash(password)
            
            # Insert user (Note: PostgreSQL uses RETURNING instead of lastrowid)
            cursor.execute('''
                INSERT INTO users (
                    anonymous_id, email_hash, email_encrypted, password_hash,
                    first_name_encrypted, last_name_encrypted, phone_encrypted, phone_hash,
                    min_age, max_age, data_consent, data_consent_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            ''', (
                anonymous_id, email_hash, email_encrypted, password_hash,
                first_name_encrypted, last_name_encrypted, phone_encrypted, phone_hash,
                min_age, max_age, data_consent
            ))
            
            user_id = cursor.fetchone()['id']
            
            # Log data processing
            self._log_data_processing(cursor, anonymous_id, 'user_creation', 'account_setup')
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'user_id': user_id, 'anonymous_id': anonymous_id}
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return {'success': False, 'error': 'Account creation failed'}     
    
    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user login"""
        try:
            print(f"LOGIN: Starting for email: {email}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Hash the email for lookup
            email_clean = email.lower().strip()
            email_hash = self.encryption.hash_for_matching(email_clean)
            
            print(f"Email clean: '{email_clean}'")
            print(f"Generated hash: {email_hash}")
            
            cursor.execute('''
                SELECT id, password_hash, first_name_encrypted, last_name_encrypted, profile_completed
                FROM users WHERE email_hash = %s AND is_active = TRUE
            ''', (email_hash,))
            
            user = cursor.fetchone()
            print(f"User found: {user is not None}")
            
            if user:
                print(f"User ID: {user['id']}")
                
                password_valid = check_password_hash(user['password_hash'], password)
                print(f"Password valid: {password_valid}")
                
                if password_valid:
                    # Decrypt names
                    first_name = self.encryption.decrypt_sensitive_data(user['first_name_encrypted']) if user['first_name_encrypted'] else None
                    last_name = self.encryption.decrypt_sensitive_data(user['last_name_encrypted']) if user['last_name_encrypted'] else None
                    
                    # Update last login
                    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s', (user['id'],))
                    conn.commit()
                    conn.close()
                    
                    print("Login successful!")
                    return {
                        'success': True,
                        'user_id': user['id'],
                        'first_name': first_name,
                        'last_name': last_name,
                        'profile_completed': bool(user['profile_completed'])
                    }
                else:
                    print("Password check failed")
            else:
                print("No user found with generated hash")
            
            conn.close()
            return {'success': False, 'error': 'Invalid email or password'}
            
        except Exception as e:
            print(f"Authentication error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': 'Authentication failed'}

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT email_encrypted, first_name_encrypted, last_name_encrypted,
                    phone_encrypted, profile_completed, profile_date,
                    email, first_name, last_name, phone
                FROM users WHERE id = %s
            ''', (user_id,))

            user = cursor.fetchone()
            conn.close()

            if user:
                # Decrypt encrypted fields, with fallback to plain text fields
                email_decrypted = self.encryption.decrypt_sensitive_data(user['email_encrypted']) if user['email_encrypted'] else None
                first_name_decrypted = self.encryption.decrypt_sensitive_data(user['first_name_encrypted']) if user['first_name_encrypted'] else None
                last_name_decrypted = self.encryption.decrypt_sensitive_data(user['last_name_encrypted']) if user['last_name_encrypted'] else None
                phone_decrypted = self.encryption.decrypt_sensitive_data(user['phone_encrypted']) if user['phone_encrypted'] else None

                return {
                    'email': email_decrypted or user.get('email'),
                    'first_name': first_name_decrypted or user.get('first_name') or '',
                    'last_name': last_name_decrypted or user.get('last_name') or '',
                    'phone': phone_decrypted or user.get('phone'),
                    'profile_completed': bool(user['profile_completed']) if user['profile_completed'] is not None else False,
                    'profile_date': user['profile_date']
                }
            return None

        except Exception as e:
            print(f"Error getting user info: {e}")
            return None

    def get_user_by_email(self, email: str):
        """Get user by email"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, email, first_name, last_name 
                FROM users 
                WHERE LOWER(email) = LOWER(%s)
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
    def get_user_by_phone(self, phone: str):
        """Get user by phone number"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, email, first_name, last_name, phone 
                FROM users 
                WHERE phone = %s
            ''', (phone,))
            
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return {
                    'id': user[0],
                    'email': user[1],
                    'first_name': user[2],
                    'last_name': user[3],
                    'phone': user[4]
                }
            return None
            
        except Exception as e:
            print(f"Error getting user by phone: {e}")
            return None
    
    def save_user_profile(self, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """Save profile data to both encrypted and plain tables"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get anonymous ID
            cursor.execute('SELECT anonymous_id FROM users WHERE id = %s', (user_id,))
            result = cursor.fetchone()
            if not result:
                print(f"❌ User {user_id} not found")
                conn.close()
                return False
            
            anonymous_id = result['anonymous_id']
            
            # Save to user_profiles (plain) for matching system
            # Check if profile exists
            cursor.execute('SELECT id FROM user_profiles WHERE user_id = %s', (user_id,))
            if cursor.fetchone():
                # Update existing
                cursor.execute('''
                    UPDATE user_profiles 
                    SET profile_data = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                ''', (json.dumps(profile_data), user_id))
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO user_profiles (user_id, profile_data, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                ''', (user_id, json.dumps(profile_data)))
            
            # Update user record
            cursor.execute('''
                UPDATE users 
                SET profile_completed = TRUE, profile_date = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_id,))
            
            conn.commit()
            conn.close()
            print(f"✅ Profile saved successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving profile for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _anonymize_profile_data(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or hash identifying information from profile data"""
        anonymized = profile_data.copy()
        
        # Remove direct identifiers
        anonymized.pop('full_name', None)
        anonymized.pop('email', None)
        anonymized.pop('phone', None)
        
        # Generalize location data
        if 'postcode' in anonymized:
            # Keep only first part of postcode (e.g., "SW3" from "SW3 4HN")
            postcode = anonymized['postcode']
            if len(postcode) > 3:
                anonymized['postcode_area'] = postcode[:3]
            anonymized.pop('postcode', None)
        
        # Hash any remaining potentially identifying data
        if 'unique_interest' in anonymized:
            # Keep the data but flag it as sensitive
            anonymized['unique_interest_hash'] = self.encryption.hash_for_matching(anonymized['unique_interest'])
        
        return anonymized
    
    def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile data"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT profile_data FROM user_profiles WHERE user_id = %s
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return json.loads(result['profile_data'])
            return None
            
        except Exception as e:
            print(f"Error getting profile for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _log_data_processing(self, cursor, anonymous_id: str, action: str, purpose: str):
        """Log data processing activities for compliance"""
        cursor.execute('''
            INSERT INTO data_processing_log (anonymous_id, action, purpose)
            VALUES (%s, %s, %s)
        ''', (anonymous_id, action, purpose))
    def save_user_matches(self, user_id: int, matches: List[Dict[str, Any]]) -> bool:
        """Save user matches to database"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Clear existing matches
            cursor.execute('DELETE FROM user_matches WHERE user_id = %s', (user_id,))
            
            # Save new matches
            for match in matches:
                cursor.execute('''
                    INSERT INTO user_matches 
                    (user_id, matched_user_id, matched_user_name, matched_user_email, matched_user_phone,
                    compatibility_score, personality_score, values_score, lifestyle_score,
                    emotional_score, social_score, communication_score, location_score, 
                    overall_score, compatibility_analysis, distance_miles)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    um.matched_user_id, um.matched_user_name, um.matched_user_email, um.matched_user_phone,
                    um.compatibility_score, um.personality_score, um.values_score, um.lifestyle_score,
                    um.emotional_score, um.social_score, um.communication_score, um.location_score,
                    um.overall_score, um.compatibility_analysis, um.distance_miles,
                    um.user_would_meet_again, um.match_would_meet_again
                FROM user_matches um
                WHERE um.user_id = %s AND um.is_active = TRUE
                ORDER BY um.overall_score DESC
            ''', (user_id,))
            
            matches = cursor.fetchall()
            conn.close()
            
            results = []
            for match in matches:
                results.append({
                    'matched_user_id': match['matched_user_id'],
                    'matched_user_name': match['matched_user_name'],
                    'matched_user_email': match['matched_user_email'],
                    'matched_user_phone': match['matched_user_phone'],
                    'compatibility_score': match['compatibility_score'],
                    'personality_score': match['personality_score'],
                    'values_score': match['values_score'] or 75,
                    'lifestyle_score': match['lifestyle_score'] or 75,
                    'emotional_score': match['emotional_score'] or 75,
                    'social_score': match['social_score'] or 75,
                    'communication_score': match['communication_score'] or 75,
                    'location_score': match['location_score'],
                    'overall_score': match['overall_score'],
                    'compatibility_analysis': match['compatibility_analysis'],
                    'distance_miles': match['distance_miles'],
                    'user_would_meet_again': match['user_would_meet_again'],
                    'match_would_meet_again': match['match_would_meet_again']
                })
            
            return results
            
        except Exception as e:
            print(f"Error getting matches: {e}")
            return []

    def get_all_users_for_matching(self, exclude_user_id: int) -> List[Dict[str, Any]]:
        """Get all users with completed profiles for matching"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.email_encrypted, u.first_name_encrypted, u.last_name_encrypted, 
                    u.phone_encrypted, up.profile_data
                FROM users u
                JOIN user_profiles up ON u.id = up.user_id
                WHERE u.id != %s AND u.is_active = TRUE AND u.profile_completed = TRUE
            ''', (exclude_user_id,))
            
            users = cursor.fetchall()
            conn.close()
            
            results = []
            for user in users:
                try:
                    profile_data = json.loads(user['profile_data']) if user['profile_data'] else {}
                    results.append({
                        'user_id': user['id'],
                        'email': self.encryption.decrypt_sensitive_data(user['email_encrypted']) if user['email_encrypted'] else None,
                        'first_name': self.encryption.decrypt_sensitive_data(user['first_name_encrypted']) if user['first_name_encrypted'] else None,
                        'last_name': self.encryption.decrypt_sensitive_data(user['last_name_encrypted']) if user['last_name_encrypted'] else None,
                        'phone': self.encryption.decrypt_sensitive_data(user['phone_encrypted']) if user['phone_encrypted'] else None,
                        'profile': profile_data
                    })
                except json.JSONDecodeError:
                    continue
            
            return results
            
        except Exception as e:
            print(f"Error getting users for matching: {e}")
            return []

    def get_age_filtered_users(self, user_id: int) -> List[Dict[str, Any]]:
        """Get users filtered by mutual age compatibility"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current user's age preferences
            cursor.execute('SELECT min_age, max_age FROM users WHERE id = %s', (user_id,))
            user_prefs = cursor.fetchone()
            if not user_prefs:
                return []
            
            user_min_age, user_max_age = user_prefs['min_age'], user_prefs['max_age']
            
            # Get current user's age
            cursor.execute('SELECT (profile_data::json->>\'age\')::integer as age FROM user_profiles WHERE user_id = %s', (user_id,))
            current_user_age_result = cursor.fetchone()
            if not current_user_age_result:
                return []
            
            current_user_age = current_user_age_result['age']
            
            # Get users who fit mutual age requirements
            cursor.execute('''
                SELECT u.id, u.email_encrypted, u.first_name_encrypted, u.last_name_encrypted, 
                    u.phone_encrypted, up.profile_data
                FROM users u
                JOIN user_profiles up ON u.id = up.user_id
                WHERE u.id != %s 
                AND u.is_active = TRUE 
                AND u.profile_completed = TRUE
                AND (up.profile_data::json->>\'age\')::integer BETWEEN %s AND %s
                AND %s BETWEEN u.min_age AND u.max_age
            ''', (user_id, user_min_age, user_max_age, current_user_age))
            
            users = cursor.fetchall()
            conn.close()
            
            results = []
            for user in users:
                try:
                    profile_data = json.loads(user['profile_data']) if user['profile_data'] else {}
                    results.append({
                        'user_id': user['id'],
                        'email': self.encryption.decrypt_sensitive_data(user['email_encrypted']) if user['email_encrypted'] else None,
                        'first_name': self.encryption.decrypt_sensitive_data(user['first_name_encrypted']) if user['first_name_encrypted'] else None,
                        'last_name': self.encryption.decrypt_sensitive_data(user['last_name_encrypted']) if user['last_name_encrypted'] else None, 
                        'phone': self.encryption.decrypt_sensitive_data(user['phone_encrypted']) if user['phone_encrypted'] else None,
                        'profile': profile_data
                    })
                except json.JSONDecodeError:
                    continue
            
            return results
            
        except Exception as e:
            print(f"Error getting age-filtered users: {e}")
            return []

    def get_random_users(self, limit=15, exclude_user_id=None):
        """Get random users for visualization"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if exclude_user_id:
                cursor.execute('''
                    SELECT id, first_name_encrypted, last_name_encrypted, email_encrypted 
                    FROM users 
                    WHERE id != %s AND is_active = TRUE
                    ORDER BY RANDOM() 
                    LIMIT %s
                ''', (exclude_user_id, limit))
            else:
                cursor.execute('''
                    SELECT id, first_name_encrypted, last_name_encrypted, email_encrypted 
                    FROM users 
                    WHERE is_active = TRUE
                    ORDER BY RANDOM() 
                    LIMIT %s
                ''', (limit,))
            
            rows = cursor.fetchall()
            users = []
            
            for row in rows:
                first_name = self.encryption.decrypt_sensitive_data(row['first_name_encrypted']) if row['first_name_encrypted'] else 'Anonymous'
                last_name = self.encryption.decrypt_sensitive_data(row['last_name_encrypted']) if row['last_name_encrypted'] else ''
                email = self.encryption.decrypt_sensitive_data(row['email_encrypted']) if row['email_encrypted'] else ''
                
                users.append({
                    'user_id': row['id'],
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO blocked_users (user_id, blocked_email, blocked_phone, blocked_name, reason)
                VALUES (%s, %s, %s, %s, %s)
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT blocked_email, blocked_phone, blocked_name
                FROM blocked_users WHERE user_id = %s
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM blocked_users WHERE user_id = %s', (user_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error clearing blocked users: {e}")
            return False
    
    def send_contact_request(self, requester_id: int, requested_id: int, message: str = '') -> Dict[str, Any]:
        """Send a contact request"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            print(f"DEBUG: Getting requester info for user {requester_id}")
            
            # Get requester info - Use encrypted columns and handle both old and new schema
            cursor.execute('''
                SELECT first_name_encrypted, last_name_encrypted, phone_encrypted,
                    first_name, last_name, phone 
                FROM users WHERE id = %s
            ''', (requester_id,))
            requester = cursor.fetchone()
            
            print(f"DEBUG: Getting requested user info for user {requested_id}")
            
            # Get requested user info
            cursor.execute('''
                SELECT first_name_encrypted, last_name_encrypted, phone_encrypted,
                    first_name, last_name, phone 
                FROM users WHERE id = %s
            ''', (requested_id,))
            requested = cursor.fetchone()
            
            if not requester or not requested:
                print(f"DEBUG: User not found - requester: {requester is not None}, requested: {requested is not None}")
                conn.close()
                return {'success': False, 'error': 'User not found'}
            
            print(f"DEBUG: Processing user data")
            
            # Try to get names from encrypted columns first, fall back to unencrypted
            try:
                if requester['first_name_encrypted']:
                    requester_first = self.encryption.decrypt_sensitive_data(requester['first_name_encrypted'])
                    requester_last = self.encryption.decrypt_sensitive_data(requester['last_name_encrypted']) if requester['last_name_encrypted'] else ''
                    requester_phone = self.encryption.decrypt_sensitive_data(requester['phone_encrypted']) if requester['phone_encrypted'] else ''
                else:
                    # Fallback to unencrypted columns
                    requester_first = requester['first_name'] or ''
                    requester_last = requester['last_name'] or ''
                    requester_phone = requester['phone'] or ''
                    
                if requested['first_name_encrypted']:
                    requested_first = self.encryption.decrypt_sensitive_data(requested['first_name_encrypted'])
                    requested_last = self.encryption.decrypt_sensitive_data(requested['last_name_encrypted']) if requested['last_name_encrypted'] else ''
                    requested_phone = self.encryption.decrypt_sensitive_data(requested['phone_encrypted']) if requested['phone_encrypted'] else ''
                else:
                    # Fallback to unencrypted columns
                    requested_first = requested['first_name'] or ''
                    requested_last = requested['last_name'] or ''
                    requested_phone = requested['phone'] or ''
                    
            except Exception as decrypt_error:
                print(f"DEBUG: Decryption error: {decrypt_error}")
                # Use unencrypted columns as fallback
                requester_first = requester['first_name'] or 'User'
                requester_last = requester['last_name'] or ''
                requester_phone = requester['phone'] or ''
                requested_first = requested['first_name'] or 'User'
                requested_last = requested['last_name'] or ''
                requested_phone = requested['phone'] or ''
            
            print(f"DEBUG: Checking for existing requests")
            
            # Check if request already exists
            cursor.execute('SELECT id, status FROM contact_requests WHERE requester_id = %s AND requested_id = %s', (requester_id, requested_id))
            existing = cursor.fetchone()
            
            if existing:
                conn.close()
                if existing['status'] == 'pending':
                    return {'success': False, 'error': 'Request already pending'}
                else:
                    return {'success': False, 'error': f'Previous request was {existing["status"]}'}
            
            print(f"DEBUG: Creating contact request")
            print(f"DEBUG: Data - requester: '{requester_first} {requester_last}' ({requester_phone})")
            print(f"DEBUG: Data - requested: '{requested_first} {requested_last}' ({requested_phone})")
            
            # Create contact request
            cursor.execute('''
                INSERT INTO contact_requests
                (requester_id, requested_id, requester_name, requested_name,
                requester_phone, requested_phone, message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                requester_id, requested_id,
                f"{requester_first} {requester_last}".strip(),
                f"{requested_first} {requested_last}".strip(),
                requester_phone, requested_phone, message
            ))

            # Get the contact request ID
            contact_request_id = cursor.fetchone()[0]

            print(f"DEBUG: Insert completed, committing transaction")

            conn.commit()
            conn.close()

            print(f"DEBUG: Contact request created successfully")

            # Send email notification to the requested user
            try:
                email_followup.send_contact_request_notification(
                    contact_request_id, requester_id, requested_id, message
                )
                print(f"DEBUG: Email notification sent for contact request {contact_request_id}")
            except Exception as email_error:
                print(f"WARNING: Failed to send email notification: {email_error}")
                # Don't let email errors break the contact request flow

            return {'success': True, 'message': 'Contact request sent successfully'}
            
        except Exception as e:
            print(f"ERROR in send_contact_request: {e}")
            import traceback
            traceback.print_exc()
            if 'conn' in locals():
                try:
                    conn.rollback()
                    conn.close()
                except:
                    pass
            return {'success': False, 'error': f'Failed to send request: {str(e)}'}
    def get_contact_requests(self, user_id: int, request_type: str = 'received') -> List[Dict[str, Any]]:
        """Get contact requests for a user (received or sent)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            print(f"DEBUG: Getting {request_type} contact requests for user {user_id}")
            
            if request_type == 'received':
                cursor.execute('''
                    SELECT id, requester_id, requester_name, requester_phone, message, status, created_at
                    FROM contact_requests WHERE requested_id = %s ORDER BY created_at DESC
                ''', (user_id,))
            else:  # sent
                cursor.execute('''
                    SELECT id, requested_id, requested_name, requested_phone, message, status, created_at
                    FROM contact_requests WHERE requester_id = %s ORDER BY created_at DESC
                ''', (user_id,))
            
            requests = cursor.fetchall()
            conn.close()
            
            print(f"DEBUG: Found {len(requests)} {request_type} requests")
            
            results = []
            for req in requests:
                try:
                    request_dict = {
                        'id': req['id'],
                        'other_user_id': req['requester_id'] if request_type == 'received' else req['requested_id'],
                        'other_user_name': req['requester_name'] if request_type == 'received' else req['requested_name'],
                        'other_user_phone': req['requester_phone'] if request_type == 'received' else req['requested_phone'],
                        'message': req['message'],
                        'status': req['status'],
                        'created_at': req['created_at']
                    }
                    results.append(request_dict)
                    print(f"DEBUG: Added request - {request_dict['other_user_name']} ({request_dict['status']})")
                except Exception as req_error:
                    print(f"DEBUG: Error processing request {req['id']}: {req_error}")
                    continue
            
            print(f"DEBUG: Returning {len(results)} processed requests")
            return results
            
        except Exception as e:
            print(f"ERROR in get_contact_requests: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def respond_to_contact_request(self, request_id: int, user_id: int, response: str) -> Dict[str, Any]:
        """Respond to a contact request (accept/deny)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            print(f"DEBUG: Processing response '{response}' for request {request_id} by user {user_id}")
            
            # Verify this request belongs to the user
            cursor.execute('SELECT requester_id, requested_id, status FROM contact_requests WHERE id = %s', (request_id,))
            result = cursor.fetchone()
            
            print(f"DEBUG: Found request - {result}")
            
            if not result or result['requested_id'] != user_id:
                conn.close()
                print(f"DEBUG: Request not found or unauthorized - result: {result}, user_id: {user_id}")
                return {'success': False, 'error': 'Request not found or unauthorized'}
            
            if result['status'] != 'pending':
                conn.close()
                print(f"DEBUG: Request already responded to - status: {result['status']}")
                return {'success': False, 'error': 'Request already responded to'}
            
            requester_id = result['requester_id']
            requested_id = result['requested_id']
            
            print(f"DEBUG: Updating request status to '{response}'")
            
            # Update request status
            cursor.execute('''
                UPDATE contact_requests SET status = %s, responded_at = CURRENT_TIMESTAMP WHERE id = %s
            ''', (response, request_id))
            
            print(f"DEBUG: Updated {cursor.rowcount} rows")
            
            conn.commit()
            conn.close()
            
            # If accepted, schedule follow-up email
            if response == 'accepted':
                try:
                    print(f"DEBUG: Scheduling follow-up email for request {request_id}")
                    email_followup.schedule_followup_email(request_id, requester_id, requested_id)
                    print(f"DEBUG: Follow-up email scheduled successfully")
                except Exception as email_error:
                    print(f"WARNING: Failed to schedule follow-up email: {email_error}")
                    # Don't let email scheduling errors break the main flow
            
            print(f"DEBUG: Contact request response completed successfully")
            return {'success': True, 'message': f'Request {response} successfully'}
            
        except Exception as e:
            print(f"ERROR in respond_to_contact_request: {e}")
            import traceback
            traceback.print_exc()
            if 'conn' in locals():
                try:
                    conn.rollback()
                    conn.close()
                except:
                    pass
            return {'success': False, 'error': f'Failed to respond to request: {str(e)}'}

    def get_request_status(self, requester_id: int, requested_id: int) -> Optional[str]:
        """Get status of contact request between two users"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM contact_requests WHERE requester_id = %s AND requested_id = %s', (requester_id, requested_id))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            return None

    def create_password_reset_token(self, email: str) -> Dict[str, Any]:
        """Create a password reset token for a user"""
        print(f"🔑 CREATE TOKEN: Starting for email: {email}")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Create email hash for lookup (same as registration process)
            email_hash = self.encryption.hash_for_matching(email.lower().strip())
            print(f"🔍 Looking for email hash: {email_hash[:16]}...")
            
            # Check if user exists using email_hash
            cursor.execute('SELECT id, first_name_encrypted FROM users WHERE email_hash = %s AND is_active = TRUE', (email_hash,))
            user = cursor.fetchone()
            
            if not user:
                print(f"❌ User not found for email: {email}")
                conn.close()
                return {'success': True, 'message': 'If this email exists, a reset link has been sent'}
            
            user_id = user['id']
            first_name_encrypted = user['first_name_encrypted']
            
            # Decrypt the first name
            first_name = self.encryption.decrypt_sensitive_data(first_name_encrypted) if first_name_encrypted else 'User'
            print(f"✅ User found: ID={user_id}, Name={first_name}")
            
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=1)
            print(f"🎫 Generated token: {token[:8]}... (expires: {expires_at})")
            
            # Store token in database
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
            ''', (user_id, token, expires_at))
            
            conn.commit()
            conn.close()
            print(f"💾 Token stored in database")
            
            # Send reset email
            print(f"📧 Calling send_password_reset_email...")
            email_sent = self.send_password_reset_email(email, first_name, token)
            print(f"📬 Email send result: {email_sent}")
            
            return {'success': True, 'message': 'If this email exists, a reset link has been sent'}
            
        except Exception as e:
            print(f"❌ ERROR in create_password_reset_token: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': 'Failed to process reset request'}

    def send_password_reset_email(self, to_email: str, first_name: str, token: str):
        """Send password reset email"""
        try:
            
            base_url = 'https://pont.world' if os.environ.get('FLASK_ENV') == 'production' else 'http://localhost:8080'
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
                    .header {{ background: white; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .button {{ display: inline-block; padding: 15px 30px; margin: 10px; text-decoration: none; border-radius: 6px; font-weight: bold; text-align: center; background: white; color: white; }}
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
                        <p>If you have any questions, please contact us at admin@pont.world</p>
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT prt.user_id, prt.expires_at, prt.used, u.email_encrypted, u.first_name_encrypted
                FROM password_reset_tokens prt
                JOIN users u ON prt.user_id = u.id
                WHERE prt.token = %s
            ''', (token,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return {'valid': False, 'error': 'Invalid reset token'}
            
            user_id = result['user_id']
            expires_at = result['expires_at']
            used = result['used']
            email_encrypted = result['email_encrypted']
            first_name_encrypted = result['first_name_encrypted']
            
            # Check if token is used
            if used:
                return {'valid': False, 'error': 'This reset link has already been used'}
            
            # Check if token is expired (expires_at is already a datetime object in PostgreSQL)
            if datetime.now() > expires_at:
                return {'valid': False, 'error': 'This reset link has expired. Please request a new one.'}
            
            # Decrypt user data
            email = self.encryption.decrypt_sensitive_data(email_encrypted) if email_encrypted else None
            first_name = self.encryption.decrypt_sensitive_data(first_name_encrypted) if first_name_encrypted else 'User'
            
            return {
                'valid': True,
                'user_id': user_id,
                'email': email,
                'first_name': first_name
            }
            
        except Exception as e:
            print(f"Error validating reset token: {e}")
            import traceback
            traceback.print_exc()
            return {'valid': False, 'error': 'Invalid reset token'}

    def reset_password_with_token(self, token: str, new_password: str) -> Dict[str, Any]:
        """Reset password using a valid token"""
        try:
            # First validate the token
            validation = self.validate_reset_token(token)
            if not validation['valid']:
                return {'success': False, 'error': validation['error']}
            
            user_id = validation['user_id']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update password
            password_hash = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password_hash = %s WHERE id = %s', (password_hash, user_id))
            
            # Mark token as used
            cursor.execute('UPDATE password_reset_tokens SET used = TRUE WHERE token = %s', (token,))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': 'Password reset successfully'}
            
        except Exception as e:
            print(f"Error resetting password: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': 'Failed to reset password'}

    def cleanup_expired_tokens(self):
        """Clean up expired password reset tokens (call this periodically)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM password_reset_tokens WHERE expires_at < %s', (datetime.now(),))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                print(f"✓ Cleaned up {deleted_count} expired password reset tokens")
            
        except Exception as e:
            print(f"Error cleaning up expired tokens: {e}")



# ============================================================================
# IDENTITY VERIFICATION SYSTEM
# ============================================================================


class IdentityVerificationSystem:
    """Handles identity verification with photo ID uploads via email"""
    
    def __init__(self, user_auth_system):
        self.user_auth = user_auth_system
        self.init_verification_database()
    
    def init_verification_database(self):
        """Initialize identity verification tables"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Identity verification requests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identity_verification_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                verification_token TEXT UNIQUE NOT NULL,
                email_sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                photo_received BOOLEAN DEFAULT FALSE,
                photo_received_at TIMESTAMP,
                verification_status TEXT DEFAULT 'pending', -- pending, approved, rejected, expired
                verified_at TIMESTAMP,
                verified_by TEXT, -- admin email who approved
                rejection_reason TEXT,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id) -- Only one active verification per user
            )
        ''')
        
        # Add verification status to users table
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE')
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP')
            print("✓ Added verification columns to users table")
        except Exception as e:
            print(f"Verification columns may already exist: {e}")
        
        # Verification admin settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_admin_settings (
                id SERIAL PRIMARY KEY,
                admin_email TEXT NOT NULL,
                verification_email TEXT NOT NULL,
                instructions TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default admin settings if none exist
        cursor.execute('SELECT COUNT(*) as count FROM verification_admin_settings')
        result = cursor.fetchone()
        if result['count'] == 0:
            cursor.execute('''
                INSERT INTO verification_admin_settings 
                (admin_email, verification_email, instructions)
                VALUES (%s, %s, %s)
            ''', (
                'admin@pont.world',
                'verify@pont.world', 
                '''Please send a clear photo containing:
1. Your government-issued photo ID (passport, driving licence, or national ID)
2. A selfie of you holding the same ID next to your face
3. A piece of paper with your verification code written on it

All three items must be clearly visible in the photo(s).'''
            ))
        
        conn.commit()
        conn.close()
        print("✓ Identity verification database initialized")
    
    def request_verification(self, user_id: int) -> Dict[str, Any]:
        """Initiate identity verification process for a user"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if user already has a pending/approved verification
            cursor.execute('''
                SELECT verification_status, expires_at FROM identity_verification_requests 
                WHERE user_id = %s AND verification_status IN ('pending', 'approved')
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            
            existing = cursor.fetchone()
            if existing:
                if existing['verification_status'] == 'approved':
                    conn.close()
                    return {'success': False, 'error': 'You are already verified'}
                elif existing['verification_status'] == 'pending' and existing['expires_at'] > datetime.now():
                    conn.close()
                    return {'success': False, 'error': 'Verification request already pending'}
            
            # Generate unique verification token
            verification_token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days to submit
            
            # Delete any old requests for this user
            cursor.execute('DELETE FROM identity_verification_requests WHERE user_id = %s', (user_id,))
            
            # Create new verification request
            cursor.execute('''
                INSERT INTO identity_verification_requests 
                (user_id, verification_token, expires_at)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (user_id, verification_token, expires_at))
            
            request_id = cursor.fetchone()['id']
            
            # Send verification instructions email
            user_info = self.user_auth.get_user_info(user_id)
            email_sent = self.send_verification_instructions_email(
                user_info['email'], 
                user_info['first_name'] or 'User', 
                verification_token
            )
            
            if email_sent:
                conn.commit()
                conn.close()
                return {
                    'success': True, 
                    'message': 'Verification instructions sent to your email',
                    'token': verification_token,
                    'expires_at': expires_at.isoformat()
                }
            else:
                conn.rollback()
                conn.close()
                return {'success': False, 'error': 'Failed to send verification email'}
            
        except Exception as e:
            print(f"Error requesting verification: {e}")
            return {'success': False, 'error': 'Failed to process verification request'}
    
    def send_verification_instructions_email(self, to_email: str, first_name: str, verification_token: str) -> bool:
        """Send detailed verification instructions to user"""
        try:
            # Get admin settings
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT verification_email, instructions FROM verification_admin_settings ORDER BY id DESC LIMIT 1')
            settings = cursor.fetchone()
            conn.close()
            
            verification_email = settings['verification_email'] if settings else 'verify@pont.world'
            instructions = settings['instructions'] if settings else 'Send your ID verification photos.'
            
            subject = "Connect Identity Verification - Action Required"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Inter', sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: white; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .verification-code {{ background: #f5f5f5; border: 2px dashed black; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px; }}
                    .code {{ font-family: monospace; font-size: 24px; font-weight: bold; color: black; letter-spacing: 3px; }}
                    .instructions {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 6px; margin: 20px 0; }}
                    .step {{ margin: 15px 0; padding: 10px; border-left: 4px solid black; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }}
                    .warning {{ background: #ffe6e6; border: 1px solid #ffb3b3; padding: 15px; border-radius: 6px; margin: 20px 0; color: #d63384; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 24px;">Identity Verification</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">Get your blue verified badge</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {first_name}!</h2>
                        
                        <p>You've requested identity verification for your Connect account. Once verified, you'll receive a blue verified badge that shows you're a real person, increasing trust and improving your match success rate.</p>
                        
                        <div class="verification-code">
                            <strong>Your Verification Code:</strong><br>
                            <div class="code">{verification_token[:8].upper()}</div>
                            <small>Include this code in your verification photo</small>
                        </div>
                        
                        <div class="instructions">
                            <strong>🔐 Verification Requirements:</strong><br>
                            {instructions.replace(chr(10), '<br>')}
                        </div>
                        
                        <div style="margin: 30px 0;">
                            <div class="step">
                                <strong>Step 1:</strong> Take a clear photo of your government-issued ID (passport, driving licence, or national ID card)
                            </div>
                            <div class="step">
                                <strong>Step 2:</strong> Take a selfie holding the same ID next to your face
                            </div>
                            <div class="step">
                                <strong>Step 3:</strong> Write your verification code <strong>{verification_token[:8].upper()}</strong> on paper and include it in the photo
                            </div>
                            <div class="step">
                                <strong>Step 4:</strong> Email all photos to: <strong>{verification_email}</strong>
                            </div>
                        </div>
                        
                        <div class="warning">
                            <strong>Important Security Notes:</strong><br>
                            • You can blur sensitive details like ID numbers (but keep your photo and name visible)<br>
                            • We only verify your identity - we don't store your ID details<br>
                            • This process typically takes 1-2 business days<br>
                            • Your verification code expires in 7 days
                        </div>
                        
                        <p><strong>What happens next?</strong></p>
                        <ol>
                            <li>Send your verification photos to <strong>{verification_email}</strong></li>
                            <li>Our team will review within 1-2 business days</li>
                            <li>You'll receive confirmation once approved</li>
                            <li>Your profile will display a blue verified badge</li>
                            <li>Your match-to-meet rate will improve significantly</li>
                        </ol>
                        
                        <p>Questions? Reply to this email or contact support.</p>
                        
                        <p>Best regards,<br>The Connect Verification Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>This verification request expires in 7 days. You can request a new code anytime from your profile settings.</p>
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
                
            print(f"✓ Verification instructions sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"Error sending verification email to {to_email}: {e}")
            return False
    
    def mark_photo_received(self, verification_token: str) -> Dict[str, Any]:
        """Mark that verification photos have been received (called by admin)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE identity_verification_requests 
                SET photo_received = TRUE, photo_received_at = CURRENT_TIMESTAMP
                WHERE verification_token = %s AND expires_at > CURRENT_TIMESTAMP
                RETURNING user_id
            ''', (verification_token,))
            
            result = cursor.fetchone()
            
            if result:
                conn.commit()
                conn.close()
                return {'success': True, 'user_id': result['user_id']}
            else:
                conn.close()
                return {'success': False, 'error': 'Invalid or expired verification token'}
                
        except Exception as e:
            print(f"Error marking photo received: {e}")
            return {'success': False, 'error': 'Database error'}
    
    def approve_verification(self, verification_token: str, admin_email: str) -> Dict[str, Any]:
        """Approve a verification request"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update verification request
            cursor.execute('''
                UPDATE identity_verification_requests 
                SET verification_status = 'approved', verified_at = CURRENT_TIMESTAMP, verified_by = %s
                WHERE verification_token = %s AND expires_at > CURRENT_TIMESTAMP
                RETURNING user_id
            ''', (admin_email, verification_token))
            
            result = cursor.fetchone()
            
            if result:
                user_id = result['user_id']
                
                # Update user as verified
                cursor.execute('''
                    UPDATE users 
                    SET is_verified = TRUE, verified_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (user_id,))
                
                # Send confirmation email
                user_info = self.user_auth.get_user_info(user_id)
                if user_info:
                    self.send_verification_approved_email(
                        user_info['email'], 
                        user_info['first_name'] or 'User'
                    )
                
                conn.commit()
                conn.close()
                
                return {'success': True, 'user_id': user_id, 'message': 'Verification approved'}
            else:
                conn.close()
                return {'success': False, 'error': 'Invalid or expired verification token'}
                
        except Exception as e:
            print(f"Error approving verification: {e}")
            return {'success': False, 'error': 'Database error'}
    
    def reject_verification(self, verification_token: str, admin_email: str, reason: str) -> Dict[str, Any]:
        """Reject a verification request"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update verification request
            cursor.execute('''
                UPDATE identity_verification_requests 
                SET verification_status = 'rejected', verified_at = CURRENT_TIMESTAMP, 
                    verified_by = %s, rejection_reason = %s
                WHERE verification_token = %s AND expires_at > CURRENT_TIMESTAMP
                RETURNING user_id
            ''', (admin_email, reason, verification_token))
            
            result = cursor.fetchone()
            
            if result:
                user_id = result['user_id']
                
                # Send rejection email
                user_info = self.user_auth.get_user_info(user_id)
                if user_info:
                    self.send_verification_rejected_email(
                        user_info['email'], 
                        user_info['first_name'] or 'User',
                        reason
                    )
                
                conn.commit()
                conn.close()
                
                return {'success': True, 'user_id': user_id, 'message': 'Verification rejected'}
            else:
                conn.close()
                return {'success': False, 'error': 'Invalid or expired verification token'}
                
        except Exception as e:
            print(f"Error rejecting verification: {e}")
            return {'success': False, 'error': 'Database error'}
    
    def send_verification_approved_email(self, to_email: str, first_name: str) -> bool:
        """Send verification approved confirmation email"""
        try:
            subject = "Your Connect Account is Now Verified!"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Inter', sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: white; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .badge-preview {{ background: #f5f5f5; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0; }}
                    .verified-badge {{ display: inline-flex; align-items: center; gap: 8px; background: white; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }}
                    .benefits {{ background: #e8f4fd; padding: 20px; border-radius: 6px; margin: 20px 0; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 28px;">You're Verified!</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">Your identity has been confirmed</p>
                    </div>
                    
                    <div class="content">
                        <h2>Congratulations {first_name}!</h2>
                        
                        <p>Your identity verification has been approved. Your Connect profile now displays a verified badge, showing other users that you're a real, trustworthy person.</p>
                        
                        <div class="badge-preview">
                            <strong>Your new verified badge:</strong><br><br>
                            <div class="verified-badge">
                                Verified
                            </div>
                        </div>
                        
                        <div class="benefits">
                            <strong> Benefits of being verified:</strong><br>
                            • Higher match-to-meet conversion rates<br>
                            • Increased trust from other users<br>
                            • Priority in matching algorithms<br>
                            • Blue verified badge on your profile<br>
                            • Enhanced safety for all users
                        </div>
                        
                        <p>Thank you for helping make Connect a safer, more trusted community. Your verification helps other users feel confident about connecting with real people.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="/dashboard" style="background: white; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                View Your Verified Profile
                            </a>
                        </div>
                        
                        <p>Best regards,<br>The Connect Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>Your verified status is permanent and will be displayed on your profile.</p>
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
                
            print(f"✓ Verification approved email sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"Error sending approval email to {to_email}: {e}")
            return False
    
    def send_verification_rejected_email(self, to_email: str, first_name: str, reason: str) -> bool:
        """Send verification rejection email"""
        try:
            subject = "Connect Verification Update - Action Needed"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Inter', sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #dc3545; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: white; padding: 30px; border: 1px solid #ddd; }}
                    .reason {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 6px; margin: 20px 0; }}
                    .next-steps {{ background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; border-radius: 6px; margin: 20px 0; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 24px;">Verification Needs Attention</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">We couldn't complete your verification</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {first_name},</h2>
                        
                        <p>We've reviewed your identity verification submission, but unfortunately we couldn't approve it at this time.</p>
                        
                        <div class="reason">
                            <strong>Reason:</strong><br>
                            {reason}
                        </div>
                        
                        <div class="next-steps">
                            <strong>📋 Next Steps:</strong><br>
                            • Review the reason above<br>
                            • Take new photos following our guidelines<br>
                            • Request a new verification code from your profile<br>
                            • Submit clearer photos that meet all requirements
                        </div>
                        
                        <p>Don't worry - you can try again anytime! Most verification issues are resolved with clearer photos or including all required elements.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="/profile-settings" style="background: white; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                Try Verification Again
                            </a>
                        </div>
                        
                        <p>If you have questions about the verification process, please reply to this email.</p>
                        
                        <p>Best regards,<br>The Connect Verification Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>We're here to help! Contact us if you need assistance with the verification process.</p>
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
                
            print(f"✓ Verification rejected email sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"Error sending rejection email to {to_email}: {e}")
            return False
    
    def get_verification_status(self, user_id: int) -> Dict[str, Any]:
        """Get current verification status for a user"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check user verification status
            cursor.execute('SELECT is_verified, verified_at FROM users WHERE id = %s', (user_id,))
            user_result = cursor.fetchone()
            
            if not user_result:
                conn.close()
                return {'error': 'User not found'}
            
            # Check for any pending/recent verification requests
            cursor.execute('''
                SELECT verification_status, created_at, expires_at, photo_received, rejection_reason
                FROM identity_verification_requests 
                WHERE user_id = %s 
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            
            request_result = cursor.fetchone()
            conn.close()
            
            status = {
                'is_verified': bool(user_result['is_verified']),
                'verified_at': user_result['verified_at'].isoformat() if user_result['verified_at'] else None,
                'can_request_verification': True,
                'pending_request': None
            }
            
            if request_result and request_result['expires_at'] > datetime.now():
                status['can_request_verification'] = False
                status['pending_request'] = {
                    'status': request_result['verification_status'],
                    'created_at': request_result['created_at'].isoformat(),
                    'expires_at': request_result['expires_at'].isoformat(),
                    'photo_received': bool(request_result['photo_received']),
                    'rejection_reason': request_result['rejection_reason']
                }
            
            return status
            
        except Exception as e:
            print(f"Error getting verification status: {e}")
            return {'error': 'Database error'}
    
    def cleanup_expired_requests(self):
        """Clean up expired verification requests (run periodically)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE identity_verification_requests 
                SET verification_status = 'expired' 
                WHERE expires_at < CURRENT_TIMESTAMP AND verification_status = 'pending'
            ''')
            
            expired_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if expired_count > 0:
                print(f"✓ Marked {expired_count} verification requests as expired")
                
        except Exception as e:
            print(f"Error cleaning up expired verification requests: {e}")


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

def process_event_matching_background(user_id: int, event_id: int):
    """Background task to process event-based matching"""
    # Prevent multiple matching processes for same user
    if user_id in processing_status and processing_status[user_id].get('status') == 'processing':
        print(f"Event matching already in progress for user {user_id}")
        return
    try:
        processing_status[user_id] = {'status': 'processing', 'progress': 0}

        processing_status[user_id]['progress'] = 25

        # Run event-based matching only against other attendees
        matches = enhanced_matching_system.run_event_matching(user_id, event_id)
        processing_status[user_id]['progress'] = 75

        print(f"✓ Found {len(matches)} event matches")
        processing_status[user_id]['progress'] = 100

        # Store results
        processing_status[user_id] = {
            'status': 'completed',
            'matches': matches,
            'progress': 100
        }

    except Exception as e:
        print(f"❌ Error in event matching: {e}")
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
    <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap" rel="stylesheet">
    <style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    
    :root {
        --color-cream: #ffffff;
        --color-emerald: #000000;
        --color-sage: #ffffff;
        --color-lavender: #c2b7ef;
        --color-charcoal: #000000;
        --color-white: #ffffff;
        --color-gray-50: #fafafa;
        --color-gray-100: #f5f5f5;
        --color-gray-200: #eeeeee;
        --color-gray-600: #757575;
        --color-gray-800: #424242;
    }
    
    body {
        font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
        background: white;
        color: black;
        line-height: 1.6;
        min-height: 100vh;
        overflow-x: hidden;
    }
    
    /* Typography Scale */
    .text-display {
        font-family: 'Sentient', 'Satoshi', sans-serif;
        font-size: clamp(2.5rem, 5vw, 4rem);
        font-weight: 600;
        line-height: 1.1;
        letter-spacing: -0.02em;
    }
    
    .text-title {
        font-family: 'Sentient', 'Satoshi', sans-serif;
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
        font-family: 'Sentient', 'Satoshi', sans-serif;
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
        background: black;
        color: white;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    
    .btn-primary:hover {
        background: #333;
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
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
        background: white;
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
        background: white;
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

def render_template_with_header(title: str, content: str, user_info: Dict = None, minimal_nav: bool = False) -> str:
    """Enhanced render template with transition support"""

    user_nav = ""
    
    # Check if user is actually logged in (has user_id in session)
    if 'user_id' in session:
        user_id = session['user_id']
        
        # Get user info for display name
        if not user_info:
            user_info = user_auth.get_user_info(user_id) or {}
        
        if minimal_nav:
            # Minimal navigation for onboarding - just logout
            user_nav = f'''
                <div class="user-info">
                    <span>{user_info.get('first_name', user_info.get('email', 'User'))}</span>
                    <a href="/logout" class="btn btn-secondary no-transition">Logout</a>
                </div>
            '''
        else:
            # Full navigation for completed profiles
            user_nav = f'''
                <div class="user-info">
                    <a href="/dashboard" class="btn btn-secondary">Dashboard</a>
                    <a href="/profile-settings" class="btn btn-secondary">Settings</a>
                    <a href="/logout" class="btn btn-secondary no-transition">Logout</a>
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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        {get_base_styles()}
        
        <!-- Transition Styles -->
        <style>
            /* Page transition overlay */
            .page-transition-overlay {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: radial-gradient(circle at center, rgba(22, 122, 96, 0.1), rgba(22, 122, 96, 0.3));
                backdrop-filter: blur(10px);
                z-index: 9999;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .page-transition-overlay.active {{
                opacity: 1;
                pointer-events: all;
            }}
            
            /* Glow effect */
            .page-transition-glow {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 200px;
                height: 200px;
                background: radial-gradient(circle, rgba(22, 122, 96, 0.8), rgba(22, 122, 96, 0.4), transparent);
                border-radius: 50%;
                animation: pulse-glow 1.5s ease-in-out infinite;
            }}
            
            @keyframes pulse-glow {{
                0%, 100% {{
                    transform: translate(-50%, -50%) scale(1);
                    opacity: 0.8;
                }}
                50% {{
                    transform: translate(-50%, -50%) scale(1.2);
                    opacity: 1;
                }}
            }}
            
            /* Content fade animation */
            .page-content {{
                opacity: 0;
                transform: translateY(20px);
                animation: fadeInUp 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
                animation-delay: 0.2s;
            }}
            
            @keyframes fadeInUp {{
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            /* Enhanced navigation links */
            a:not(.no-transition) {{
                position: relative;
                transition: all 0.3s ease;
            }}
            
            a:not(.no-transition):hover {{
                text-shadow: 0 0 10px rgba(22, 122, 96, 0.5);
            }}
        </style>
    </head>
    <body>
        <!-- Transition overlay -->
        <div class="page-transition-overlay" id="transitionOverlay">
            <div class="page-transition-glow"></div>
        </div>
        
        <!-- Page content -->
        <div class="page-content">
            <div class="header">
                <div class="logo">
                    <a href="{'/' if not user_info else '/dashboard'}" style="color: inherit; text-decoration: none;">Connect</a>
                </div>
                {user_nav}
            </div>
            
            <main>
                {content}
            </main>
        </div>
        
        <!-- Transition JavaScript -->
        <script>
            class PageTransition {{
                constructor() {{
                    this.overlay = document.getElementById('transitionOverlay');
                    this.isTransitioning = false;
                    this.init();
                }}
                
                init() {{
                    // Add transition to all navigation links
                    document.addEventListener('click', (e) => {{
                        const link = e.target.closest('a');
                        if (link && !link.classList.contains('no-transition') && 
                            !link.href.startsWith('mailto:') && 
                            !link.href.startsWith('tel:') &&
                            link.hostname === window.location.hostname) {{
                            e.preventDefault();
                            this.navigate(link.href);
                        }}
                    }});
                    
                    // Handle browser back/forward
                    window.addEventListener('popstate', () => {{
                        this.navigate(window.location.href, false);
                    }});
                }}
                
                async navigate(url, pushState = true) {{
                    if (this.isTransitioning) return;
                    
                    this.isTransitioning = true;
                    
                    // Show transition overlay with glow
                    this.overlay.classList.add('active');
                    
                    try {{
                        // Wait for transition effect
                        await new Promise(resolve => setTimeout(resolve, 400));
                        
                        // Fetch new page content
                        const response = await fetch(url, {{
                            headers: {{ 'X-Requested-With': 'XMLHttpRequest' }}
                        }});
                        
                        if (response.ok) {{
                            const html = await response.text();
                            
                            // Update page content
                            document.documentElement.innerHTML = html;
                            
                            // Update URL if needed
                            if (pushState) {{
                                history.pushState(null, '', url);
                            }}
                            
                            // Reinitialize transition system
                            new PageTransition();
                            
                            // Hide overlay
                            setTimeout(() => {{
                                const newOverlay = document.getElementById('transitionOverlay');
                                if (newOverlay) {{
                                    newOverlay.classList.remove('active');
                                }}
                            }}, 100);
                            
                        }} else {{
                            // Fallback to normal navigation
                            window.location.href = url;
                        }}
                    }} catch (error) {{
                        console.error('Transition error:', error);
                        window.location.href = url;
                    }}
                    
                    this.isTransitioning = false;
                }}
            }}
            
            // Initialize page transitions
            document.addEventListener('DOMContentLoaded', () => {{
                new PageTransition();
            }});
        </script>
    </body>
    </html>
    '''

def render_matches_dashboard(user_info: Dict, matches: List[Dict]) -> str:
    """
    Unified dashboard function that includes:
    - Interactive 3D cube visualization
    - Verification status and badges
    - Subscription status banners
    - Enhanced compatibility scoring
    - Proper date formatting
    - Flash message handling
    - Tracking analytics
    """
    user_id = session['user_id']
    
    # Get flash messages and convert to HTML
    flash_html = ""
    messages = get_flashed_messages(with_categories=True)
    if messages:
        flash_html = '<div class="flash-messages">'
        for category, message in messages:
            flash_html += f'<div class="flash-{category}">{message}</div>'
        flash_html += '</div>'
    
    # Get user's verification status
    user_verification = verification_system.get_verification_status(user_id)
    user_verified_badge = ''
    if user_verification.get('is_verified'):
        user_verified_badge = '''
        <div style="text-align: center; margin: 1rem 0;">
            <div style="display: inline-flex; align-items: center; gap: 0.5rem; background: black; color: white; padding: 0.5rem 1rem; border-radius: 20px; font-weight: 600; font-size: 0.875rem;">
                ✓ Your Profile is Verified
            </div>
        </div>
        '''
    
    # Get subscription status
    subscription_status = subscription_manager.get_user_subscription_status(user_id)
    subscription_banner = ""
    if subscription_status['is_subscribed']:
        subscription_banner = '''
        <div style="background: black; color: white; padding: 1rem; border-radius: 12px; text-align: center; margin-bottom: 2rem;">
            ✓ Premium Member - Unlimited matching available
        </div>
        '''
    else:
        remaining = subscription_status['free_matches_remaining']
        subscription_banner = f'''
        <div style="background: linear-gradient(135deg, white, #e8dce2); color: black; padding: 1rem; border-radius: 12px; text-align: center; margin-bottom: 2rem;">
            Free Plan - {remaining} free match{"" if remaining == 1 else "es"} remaining this month
            <div style="margin-top: 0.5rem;">
                <a href="/subscription/plans" style="color: black; font-weight: 600; text-decoration: none;">
                    Upgrade to Premium for unlimited matching →
                </a>
            </div>
        </div>
        '''
    
    # Process matches with enhanced features
    matches_html = ""
    
    for i, match in enumerate(matches, 1):
        # Check if the matched user is verified
        matched_user_verified = False
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT is_verified FROM users WHERE id = %s', (match['matched_user_id'],))
            result = cursor.fetchone()
            if result:
                matched_user_verified = bool(result['is_verified'])
            conn.close()
        except:
            pass
        
        # Verification badge for matched user
        verification_badge = ""
        if matched_user_verified:
            verification_badge = '''
            <div style="display: inline-flex; align-items: center; gap: 0.25rem; background: black; color: white; padding: 0.25rem 0.75rem; border-radius: 15px; font-size: 0.75rem; font-weight: 600; margin-left: 0.5rem;">
                Verified
            </div>
            '''
        
        # Enhanced compatibility badges
        compatibility_badges = ""
        
        # Verification trust badge
        if matched_user_verified:
            compatibility_badges += '<span class="badge badge-verified">Identity Verified</span>'
        
        # Neural network confidence badge
        neural_score = match.get('neural_score', 0)
        data_confidence = match.get('data_confidence', 0)
        
        if data_confidence >= 70:
            compatibility_badges += f'<span class="badge badge-ai">ML Confidence: {data_confidence}%</span>'
        
        if neural_score >= 85:
            compatibility_badges += '<span class="badge badge-neural">High ML Match</span>'
        
        # Simulation insights
        sim_satisfaction = match.get('simulation_satisfaction', 0)
        if sim_satisfaction >= 80:
            compatibility_badges += '<span class="badge badge-simulation">Simulation Verified</span>'
        
        # Traditional badges
        if match['personality_score'] >= 85:
            compatibility_badges += '<span class="badge badge-personality">Excellent Personality Match</span>'
        if match.get('values_score', 75) >= 85:
            compatibility_badges += '<span class="badge badge-values">Strong Values Alignment</span>'
        
        # Get initials for avatar
        name_parts = match['matched_user_name'].split()
        initials = name_parts[0][0] + (name_parts[-1][0] if len(name_parts) > 1 else '')
        
        # Enhanced contact button logic with verification boost messaging
        request_status = user_auth.get_request_status(user_id, match['matched_user_id'])
        if request_status == 'pending':
            contact_button = '<span class="btn btn-pending">Request Pending</span>'
        elif request_status == 'accepted':
            contact_button = f'<a href="tel:{match["matched_user_phone"]}" class="btn btn-success">Call {match["matched_user_phone"]}</a>'
        elif request_status == 'denied':
            contact_button = '<span class="btn btn-declined">Request Declined</span>'
        else:
            verification_boost_text = ""
            if matched_user_verified:
                verification_boost_text = " (Verified users have 40% higher response rates!)"
            
            contact_button = f'''
                <div>
                    <a href="/send-contact-request/{match["matched_user_id"]}" 
                       onclick="trackContactIntention({match['matched_user_id']}, {match['overall_score']})"
                       class="btn btn-primary">
                       Connect with {match['matched_user_name']}
                    </a>
                    {f'<div style="font-size: 0.75rem; color: #007bff; margin-top: 0.5rem; text-align: center;">{verification_boost_text}</div>' if verification_boost_text else ''}
                </div>
            '''
        
        # Enhanced scoring display for AI-powered matches
        enhanced_scores_html = ""
        if data_confidence >= 50:
            enhanced_scores_html = f'''
            <div class="ai-scores-grid">
                <div class="ai-score-card">
                    <div class="score-label">ML Score</div>
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
                    <div class="match-name">
                        {match['matched_user_name']}
                        {verification_badge}
                    </div>
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
            
            
            <div class="compatibility-analysis">
                {match['compatibility_analysis']}
            </div>
            
            <div class="match-actions">
                {contact_button}
            </div>
        </div>
        '''
        matches_html += match_html
    
    # Safe date formatting
    def safe_format_date(date_obj):
        """Safely format date object to string"""
        if not date_obj:
            return 'Recently'
        
        if isinstance(date_obj, str):
            # Already a string, try to extract date part
            return date_obj[:10] if len(date_obj) >= 10 else date_obj
        
        if hasattr(date_obj, 'strftime'):
            # It's a datetime object
            return date_obj.strftime('%Y-%m-%d')
        
        return 'Recently'
    
    profile_date = safe_format_date(user_info.get('profile_date'))
    
    matches_count_section = f'''
    <div class="canvas-container">
        <canvas id="cube-canvas"></canvas>
    </div>
    
    <div class="matches-header">
        <h1 class="matches-title">Your Matches</h1>
        <p class="matches-subtitle">Your agent found {len(matches)} perfect connections</p>
        {user_verified_badge}
        <div class="profile-updated">Profile updated: {profile_date}</div>
    </div>
    '''
    
    return f'''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        body {{
            background-color: white;
            color: black;
            font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
        }}
        
        .dashboard-container {{
            max-width: 1000px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .canvas-container {{
            width: 200px;
            height: 200px;
            margin: 3rem auto 2rem auto;
            z-index: 2;
        }}
        
        #cube-canvas {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}
        
        #cube-canvas:active {{
            cursor: grabbing;
        }}
        
        .matches-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .matches-title {{
            font-family: "Sentient", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: black;
            letter-spacing: -0.02em;
            background: white;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .matches-subtitle {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            line-height: 1.6;
            color: black;
            margin: 0 0 1rem 0;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .profile-updated {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
            color: rgba(107, 155, 153, 0.8);
            font-weight: 500;
        }}
        
        .match-card {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            margin: 2rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            transition: all 0.3s ease;
        }}
        
        .match-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(0, 0, 0, 0.3);
        }}
        
        .match-number {{
            position: absolute;
            top: -1rem;
            left: 2rem;
            background: black;
            color: white;
            border-radius: 50%;
            width: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Satoshi", sans-serif;
            font-weight: 700;
            font-size: 1.25rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
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
            background: white;
            display: flex;
            align-items: center;
            justify-content: center;
            color: black;
            font-family: "Sentient", sans-serif;
            font-size: 2rem;
            font-weight: 700;
        }}
        
        .match-info {{
            flex: 1;
        }}
        
        .match-name {{
            font-family: "Sentient", sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            color: black;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .compatibility-score {{
            text-align: center;
            margin: 2rem 0;
        }}
        
        .score-circle {{
            display: inline-block;
            padding: 2rem;
            background: white;
            border-radius: 20px;
            color: black;
            min-width: 200px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }}
        
        .score-number {{
            font-family: "Sentient", sans-serif;
            font-size: 3rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
        }}
        
        .score-text {{
            font-family: "Satoshi", sans-serif;
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
            background: rgba(45, 45, 45, 0.9);
            border-radius: 16px;
        }}
        
        .ai-score-card {{
            text-align: center;
            color: white;
        }}
        
        .score-label {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            opacity: 0.8;
            font-weight: 600;
        }}
        
        .score-value {{
            font-family: "Sentient", sans-serif;
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
            background: black;
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
            font-family: "Satoshi", sans-serif;
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .badge-verified {{
            background: #007bff;
            color: white;
            border: 1px solid #0056b3;
        }}
        
        .badge-verified::before {{
            content: '✓ ';
            font-weight: bold;
        }}
        
        .badge-ai {{
            background: rgba(255, 149, 0, 0.8);
            color: white;
        }}
        
        .badge-neural {{
            background: white;
            color: white;
        }}
        
        .badge-simulation {{
            background: rgba(107, 155, 153, 0.8);
            color: white;
        }}
        
        .badge-personality {{
            background: rgba(255, 255, 255, 0.8);
            color: black;
        }}
        
        .badge-values {{
            background: rgba(255, 255, 255, 0.8);
            color: black;
        }}
        
        .detailed-scores {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 16px;
        }}
        
        .score-item {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        .score-category {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
            font-weight: 600;
            color: black;
            min-width: 80px;
        }}
        
        .score-value-small {{
            font-family: "Sentient", sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            color: black;
            min-width: 40px;
        }}
        
        .score-bar-small {{
            flex: 1;
            height: 6px;
            background: rgba(107, 155, 153, 0.2);
            border-radius: 3px;
            overflow: hidden;
        }}
        
        .score-fill-small {{
            height: 100%;
            background: white;
            border-radius: 3px;
            transition: width 1s ease;
        }}
        
        .compatibility-analysis {{
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 16px;
            margin: 2rem 0;
            border-left: 4px solid black;
            font-family: "Satoshi", sans-serif;
            font-size: 1rem;
            line-height: 1.6;
            color: black;
        }}
        
        .match-actions {{
            text-align: center;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid rgba(107, 155, 153, 0.2);
        }}
        
        .btn {{
            font-family: "Satoshi", sans-serif;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
            backdrop-filter: blur(10px);
        }}
        
        .btn-primary {{
            background: black;
            color: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }}
        
        .btn-primary:hover {{
            background: #333;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        
        .btn-pending {{
            background: rgba(255, 149, 0, 0.8);
            color: white;
            border: 1px solid rgba(255, 149, 0, 0.5);
        }}
        
        .btn-success {{
            background: rgba(107, 155, 153, 0.8);
            color: white;
            text-decoration: none;
            border: 1px solid rgba(107, 155, 153, 0.5);
        }}
        
        .btn-success:hover {{
            transform: translateY(-2px);
            background: white;
        }}
        
        .btn-declined {{
            background: rgba(255, 255, 255, 0.5);
            color: rgba(45, 45, 45, 0.6);
            border: 1px solid rgba(45, 45, 45, 0.2);
        }}
        
        /* Flash message styling */
        .flash-messages {{
            margin-bottom: 2rem;
        }}
        
        .flash-error {{
            background: rgba(255, 149, 0, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 149, 0, 0.5);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
        }}
        
        .flash-success {{
            background: rgba(107, 155, 153, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(107, 155, 153, 0.5);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
        }}
        
        /* Responsive design */
        @media (max-width: 768px) {{
            .canvas-container {{
                width: 150px;
                height: 150px;
            }}
            
            .matches-header {{
                padding: 1.5rem 1rem;
            }}
            
            .match-card {{
                padding: 1.5rem;
            }}
            
            .match-name {{
                font-size: 1.5rem;
            }}
            
            .ai-scores-grid {{
                grid-template-columns: 1fr;
                padding: 1rem;
            }}
            
            .detailed-scores {{
                grid-template-columns: 1fr;
                padding: 1rem;
            }}
        }}
    </style>
    
    <!-- Include required libraries -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    
    <div class="dashboard-container">
        {flash_html}
        {subscription_banner}
        {matches_count_section}
        {matches_html}
        <!-- Re-matching Section -->
            <div class="rematching-section">
                <h3 class="rematching-title">Want Fresh Matches?</h3>
                <p class="rematching-description">
                    If you've made significant changes to your profile, you can re-run the AI matching system 
                    to discover new compatible connections based on your updated preferences.
                </p>
                <a href="/choose-agent" class="btn btn-rematch">
                    Find New Matches
                </a>
            </div>
        <script>
        let viewStartTimes = {{}};
        
        function trackMatchView(matchUserId) {{
            if (!viewStartTimes[matchUserId]) {{
                viewStartTimes[matchUserId] = Date.now();
                
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
        
        // Three.js scene setup
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        camera.position.z = 3;

        const canvas = document.querySelector("#cube-canvas");
        const renderer = new THREE.WebGLRenderer({{
            canvas: canvas,
            antialias: true,
            alpha: true
        }});
        renderer.setSize(200, 200);
        renderer.setPixelRatio(window.devicePixelRatio);

        // Create cube with teal wireframe
        const cubeGeometry = new THREE.BoxGeometry(1.5, 1.5, 1.5);
        const cubeMaterial = new THREE.MeshBasicMaterial({{ 
            color: 0x000000, 
            transparent: true, 
            opacity: 0 
        }});
        const cube = new THREE.Mesh(cubeGeometry, cubeMaterial);

        // Add wireframe edges
        const edges = new THREE.EdgesGeometry(cubeGeometry);
        const lineMaterial = new THREE.LineBasicMaterial({{ 
            color: 0x6b9b99,
            linewidth: 2
        }});
        const wireframe = new THREE.LineSegments(edges, lineMaterial);
        cube.add(wireframe);

        // Create user's orange sphere (centered)
        const userSphereGeometry = new THREE.SphereGeometry(0.15, 16, 16);
        const userSphereMaterial = new THREE.MeshPhongMaterial({{ 
            color: 0xff9500,
            shininess: 30
        }});
        const userSphere = new THREE.Mesh(userSphereGeometry, userSphereMaterial);
        userSphere.position.set(0, 0, 0);
        cube.add(userSphere);

        // Create teal match spheres - positioned around the cube
        const numMatches = {len(matches)};
        const matchSpheres = [];
        const matchSphereGeometry = new THREE.SphereGeometry(0.12, 16, 16);
        const matchSphereMaterial = new THREE.MeshPhongMaterial({{ 
            color: 0x6b9b99,
            shininess: 30
        }});

        // Position match spheres in a distributed pattern within the cube
        const positions = [
            {{x: 0.4, y: 0.4, z: 0.4}},
            {{x: -0.4, y: 0.4, z: 0.4}},
            {{x: 0.4, y: -0.4, z: 0.4}},
            {{x: -0.4, y: -0.4, z: 0.4}},
            {{x: 0.4, y: 0.4, z: -0.4}},
            {{x: -0.4, y: 0.4, z: -0.4}},
            {{x: 0.4, y: -0.4, z: -0.4}},
            {{x: -0.4, y: -0.4, z: -0.4}},
            {{x: 0, y: 0.5, z: 0}},
            {{x: 0, y: -0.5, z: 0}},
            {{x: 0.5, y: 0, z: 0}},
            {{x: -0.5, y: 0, z: 0}},
            {{x: 0, y: 0, z: 0.5}},
            {{x: 0, y: 0, z: -0.5}},
            {{x: 0.3, y: 0.3, z: 0}},
            {{x: -0.3, y: -0.3, z: 0}},
        ];

        for (let i = 0; i < Math.min(numMatches, positions.length); i++) {{
            const matchSphere = new THREE.Mesh(matchSphereGeometry, matchSphereMaterial.clone());
            const pos = positions[i];
            matchSphere.position.set(pos.x, pos.y, pos.z);
            matchSphere.userData = {{ originalPosition: {{ ...pos }} }};
            matchSpheres.push(matchSphere);
            cube.add(matchSphere);
        }}

        scene.add(cube);

        // Lighting for the spheres
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        
        const pointLight = new THREE.PointLight(0xffffff, 0.8);
        pointLight.position.set(2, 2, 2);
        scene.add(pointLight);

        // Mouse interaction variables
        let isDragging = false;
        let previousMousePosition = {{ x: 0, y: 0 }};
        let isClicked = false;

        // Auto rotation and floating animation
        function autoRotate() {{
            if (!isDragging) {{
                cube.rotation.x += 0.003;
                cube.rotation.y += 0.005;
                
                // Gentle floating for spheres
                const time = Date.now() * 0.002;
                
                // User sphere gentle movement
                userSphere.position.y = Math.sin(time) * 0.05;
                
                // Match spheres subtle floating
                matchSpheres.forEach((sphere, index) => {{
                    const offset = index * 0.3;
                    const originalPos = sphere.userData.originalPosition;
                    sphere.position.x = originalPos.x + Math.sin(time + offset) * 0.03;
                    sphere.position.y = originalPos.y + Math.cos(time + offset * 1.2) * 0.03;
                    sphere.position.z = originalPos.z + Math.sin(time + offset * 0.8) * 0.03;
                }});
            }}
        }}

        // Mouse event handlers
        function onMouseDown(event) {{
            isDragging = true;
            canvas.style.cursor = 'grabbing';
            
            const rect = canvas.getBoundingClientRect();
            previousMousePosition = {{
                x: event.clientX - rect.left,
                y: event.clientY - rect.top
            }};
        }}

        function onMouseMove(event) {{
            if (!isDragging) return;

            const rect = canvas.getBoundingClientRect();
            const currentMousePosition = {{
                x: event.clientX - rect.left,
                y: event.clientY - rect.top
            }};

            const deltaMove = {{
                x: currentMousePosition.x - previousMousePosition.x,
                y: currentMousePosition.y - previousMousePosition.y
            }};

            const deltaRotationQuaternion = new THREE.Quaternion()
                .setFromEuler(new THREE.Euler(
                    toRadians(deltaMove.y * 0.5),
                    toRadians(deltaMove.x * 0.5),
                    0,
                    'XYZ'
                ));

            cube.quaternion.multiplyQuaternions(deltaRotationQuaternion, cube.quaternion);
            previousMousePosition = currentMousePosition;
        }}

        function onMouseUp() {{
            isDragging = false;
            canvas.style.cursor = 'grab';
        }}

        function onClick(event) {{
            if (!isClicked) {{
                isClicked = true;
                
                // Scale animation on click
                const originalScale = {{ x: 1, y: 1, z: 1 }};
                const targetScale = {{ x: 0.9, y: 0.9, z: 0.9 }};
                
                animateScale(cube.scale, targetScale, 100, () => {{
                    animateScale(cube.scale, {{ x: 1.05, y: 1.05, z: 1.05 }}, 100, () => {{
                        animateScale(cube.scale, originalScale, 100, () => {{
                            // Scroll to first match instead of redirecting
                            const firstMatch = document.querySelector('.match-card');
                            if (firstMatch) {{
                                firstMatch.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            }}
                            isClicked = false;
                        }});
                    }});
                }});
            }}
        }}

        // Simple scale animation function
        function animateScale(object, target, duration, callback) {{
            const start = {{ x: object.x, y: object.y, z: object.z }};
            const startTime = Date.now();
            
            function update() {{
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                object.x = start.x + (target.x - start.x) * progress;
                object.y = start.y + (target.y - start.y) * progress;
                object.z = start.z + (target.z - start.z) * progress;
                
                if (progress < 1) {{
                    requestAnimationFrame(update);
                }} else if (callback) {{
                    callback();
                }}
            }}
            
            update();
        }}

        function toRadians(angle) {{
            return angle * (Math.PI / 180);
        }}

        // Add event listeners
        canvas.addEventListener('mousedown', onMouseDown);
        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('mouseleave', onMouseUp);
        canvas.addEventListener('click', onClick);

        // Animation loop
        function animate() {{
            requestAnimationFrame(animate);
            autoRotate();
            renderer.render(scene, camera);
        }}

        animate();

        // Handle window resize
        window.addEventListener('resize', () => {{
            const containerSize = window.innerWidth < 768 ? 150 : 200;
            renderer.setSize(containerSize, containerSize);
            
            const container = document.querySelector('.canvas-container');
            container.style.width = containerSize + 'px';
            container.style.height = containerSize + 'px';
        }});
        </script>
        
    </div>
    '''

def enhance_matching_with_verification():
    """Add verification boost to existing matching system"""
    
    # Modify the existing MatchingSystem class to include verification bonus
    original_calculate_scores = MatchingSystem.calculate_compatibility_scores
    
    def calculate_compatibility_scores_with_verification(self, user1_profile: Dict, user2_profile: Dict) -> Dict[str, float]:
        """Enhanced scoring that includes verification bonus"""
        # Get base compatibility scores
        scores = original_calculate_scores(self, user1_profile, user2_profile)
        
        # Check verification status of both users
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get verification status (assuming we can get user_ids from profiles)
            user1_id = user1_profile.get('user_id')
            user2_id = user2_profile.get('user_id')
            
            verification_bonus = 0
            
            if user1_id and user2_id:
                cursor.execute('''
                    SELECT 
                        (SELECT is_verified FROM users WHERE id = %s) as user1_verified,
                        (SELECT is_verified FROM users WHERE id = %s) as user2_verified
                ''', (user1_id, user2_id))
                
                result = cursor.fetchone()
                if result:
                    user1_verified = result['user1_verified']
                    user2_verified = result['user2_verified']
                    
                    # Both verified: +10 point bonus to overall compatibility
                    if user1_verified and user2_verified:
                        verification_bonus = 10
                    # One verified: +5 point bonus
                    elif user1_verified or user2_verified:
                        verification_bonus = 5
            
            conn.close()
            
            # Apply verification bonus to all scores
            if verification_bonus > 0:
                for key in scores:
                    scores[key] = min(100, scores[key] + verification_bonus)
                    
                print(f"Applied +{verification_bonus} verification bonus to compatibility scores")
            
        except Exception as e:
            print(f"Error applying verification bonus: {e}")
        
        return scores
    
    # Replace the method
    MatchingSystem.calculate_compatibility_scores = calculate_compatibility_scores_with_verification

# ============================================================================
# NETWORK MANAGEMENT SYSTEM (V2)
# ============================================================================

class NetworkManager:
    """Manages V2 network functionality including LinkedIn integration"""

    def __init__(self, user_auth_system, encryption_system):
        self.user_auth = user_auth_system
        self.encryption = encryption_system

    def create_network(self, user_id: int, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new network for the user"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO networks (owner_id, name, description)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (user_id, name, description))

            network_id = cursor.fetchone()['id']
            conn.commit()
            conn.close()

            return {"success": True, "network_id": network_id}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_networks(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all networks owned by the user"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, description, created_at,
                       (SELECT COUNT(*) FROM network_people WHERE network_id = networks.id) as people_count
                FROM networks
                WHERE owner_id = %s AND is_active = TRUE
                ORDER BY created_at DESC
            ''', (user_id,))

            networks = cursor.fetchall()
            conn.close()

            return [dict(row) for row in networks]

        except Exception as e:
            print(f"Error fetching networks: {e}")
            return []

    def add_person_to_network(self, network_id: int, name: str, linkedin_url: str = "") -> Dict[str, Any]:
        """Add a person to a network"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Validate network ownership would be added here

            cursor.execute('''
                INSERT INTO network_people (network_id, name, linkedin_url)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (network_id, name, linkedin_url))

            person_id = cursor.fetchone()['id']
            conn.commit()
            conn.close()

            return {"success": True, "person_id": person_id}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_people_from_csv(self, network_id: int, csv_data: str) -> Dict[str, Any]:
        """Import people from CSV data"""
        try:
            import csv
            import io

            print(f"Starting CSV import for network {network_id}")
            print(f"CSV data length: {len(csv_data)}")
            print(f"CSV data preview: {csv_data[:200]}...")

            conn = get_db_connection()
            cursor = conn.cursor()

            # Parse CSV - handle both with and without headers
            csv_file = io.StringIO(csv_data)

            # First, check if the data has proper headers
            lines = csv_data.strip().split('\n')
            if len(lines) == 0:
                return {"success": False, "error": "Empty CSV data"}

            first_line = lines[0].lower()
            has_headers = 'name' in first_line and ('linkedin' in first_line or 'url' in first_line)

            print(f"First line: {lines[0]}")
            print(f"Has headers: {has_headers}")

            imported_count = 0
            errors = []

            if has_headers:
                # Use DictReader for CSV with headers
                csv_file = io.StringIO(csv_data)
                reader = csv.DictReader(csv_file)

                for row_num, row in enumerate(reader, 1):
                    try:
                        print(f"Processing row {row_num}: {row}")
                        name = row.get('name', '').strip()
                        linkedin_url = row.get('linkedin_url', '').strip()

                        if name:
                            cursor.execute('''
                                INSERT INTO network_people (network_id, name, linkedin_url)
                                VALUES (%s, %s, %s)
                            ''', (network_id, name, linkedin_url))
                            imported_count += 1
                            print(f"Imported: {name}")
                        else:
                            print(f"Skipping row {row_num}: no name provided")

                    except Exception as row_error:
                        error_msg = f"Row {row_num} error: {str(row_error)}"
                        print(error_msg)
                        errors.append(error_msg)
            else:
                # Handle CSV without headers - assume first column is name, second is linkedin_url
                csv_file = io.StringIO(csv_data)
                reader = csv.reader(csv_file)

                for row_num, row in enumerate(reader, 1):
                    try:
                        print(f"Processing row {row_num}: {row}")
                        if len(row) >= 1:
                            name = row[0].strip()
                            linkedin_url = row[1].strip() if len(row) >= 2 else ''

                            if name:
                                cursor.execute('''
                                    INSERT INTO network_people (network_id, name, linkedin_url)
                                    VALUES (%s, %s, %s)
                                ''', (network_id, name, linkedin_url))
                                imported_count += 1
                                print(f"Imported: {name}")
                            else:
                                print(f"Skipping row {row_num}: no name provided")
                        else:
                            print(f"Skipping row {row_num}: empty row")

                    except Exception as row_error:
                        error_msg = f"Row {row_num} error: {str(row_error)}"
                        print(error_msg)
                        errors.append(error_msg)

            conn.commit()
            conn.close()

            print(f"CSV import completed: {imported_count} imported, {len(errors)} errors")
            return {
                "success": True,
                "imported_count": imported_count,
                "errors": errors
            }

        except Exception as e:
            error_msg = f"CSV import failed: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return {"success": False, "error": error_msg}

    def get_network_people(self, network_id: int) -> List[Dict[str, Any]]:
        """Get all people in a network"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, linkedin_url, profile_summary, skills,
                       industry, location, created_at
                FROM network_people
                WHERE network_id = %s
                ORDER BY name
            ''', (network_id,))

            people = cursor.fetchall()
            conn.close()

            return [dict(row) for row in people]

        except Exception as e:
            print(f"Error fetching network people: {e}")
            return []

    def get_network_relationships(self, network_id: int) -> List[Dict[str, Any]]:
        """Get all relationships in a network"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT nr.*,
                       p1.name as person1_name,
                       p2.name as person2_name
                FROM network_relationships nr
                JOIN network_people p1 ON nr.person1_id = p1.id
                JOIN network_people p2 ON nr.person2_id = p2.id
                WHERE nr.network_id = %s
            ''', (network_id,))

            relationships = cursor.fetchall()
            conn.close()

            return [dict(row) for row in relationships]

        except Exception as e:
            print(f"Error fetching network relationships: {e}")
            return []

    def generate_network_compatibility(self, people: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate random compatibility scores and relationships for network visualization"""
        import random

        try:
            compatibility_matrix = {}
            relationships = []

            # Generate pairwise compatibility scores
            for i, person1 in enumerate(people):
                compatibility_matrix[person1['id']] = {}

                for j, person2 in enumerate(people):
                    if i != j:
                        # Generate random compatibility score (0.0 to 1.0)
                        # Bias towards moderate compatibility (0.3 to 0.8)
                        score = random.uniform(0.2, 0.9)
                        compatibility_matrix[person1['id']][person2['id']] = score

                        # If compatibility is above threshold (0.6), create a relationship
                        if score > 0.6:
                            relationships.append({
                                'person1_id': person1['id'],
                                'person2_id': person2['id'],
                                'person1_name': person1['name'],
                                'person2_name': person2['name'],
                                'compatibility_score': score
                            })

            # Calculate each person's total connections for clustering
            connection_counts = {}
            for person in people:
                person_id = person['id']
                connections = [r for r in relationships if r['person1_id'] == person_id or r['person2_id'] == person_id]
                connection_counts[person_id] = len(connections)

            return {
                'compatibility_matrix': compatibility_matrix,
                'relationships': relationships,
                'connection_counts': connection_counts,
                'people_count': len(people)
            }

        except Exception as e:
            print(f"Error generating network compatibility: {e}")
            return {
                'compatibility_matrix': {},
                'relationships': [],
                'connection_counts': {},
                'people_count': 0
            }

    def update_relationship_score(self, network_id: int, person1_id: int, person2_id: int,
                                 manual_score: float, note: str = "") -> Dict[str, Any]:
        """Update manual relationship score"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Ensure person1_id < person2_id for consistency
            if person1_id > person2_id:
                person1_id, person2_id = person2_id, person1_id

            cursor.execute('''
                INSERT INTO network_relationships
                    (network_id, person1_id, person2_id, manual_score, manual_note)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (person1_id, person2_id)
                DO UPDATE SET
                    manual_score = EXCLUDED.manual_score,
                    manual_note = EXCLUDED.manual_note,
                    updated_at = CURRENT_TIMESTAMP
            ''', (network_id, person1_id, person2_id, manual_score, note))

            conn.commit()
            conn.close()

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

# Initialize systems

from data_safety import DataEncryption, GDPRCompliance
from email_followup import EmailFollowupSystem
from onboarding import add_onboarding_routes

data_encryption = DataEncryption()
user_auth = UserAuthSystem()
# Initialize GDPR compliance
# After initializing data_encryption and user_auth
gdpr_compliance = GDPRCompliance(user_auth, data_encryption, get_db_connection)
#matching_system = MatchingSystem(API_KEY)
verification_system = IdentityVerificationSystem(user_auth)
subscription_manager = SubscriptionManager(user_auth, get_db_connection)
network_manager = NetworkManager(user_auth, data_encryption)
try:
    enhanced_matching_system, interaction_tracker = integrate_enhanced_matching(app, user_auth, API_KEY, db_connection_func=get_db_connection)
    enhanced_matching_system.processing_status = processing_status
    print("✓ Enhanced matching system initialized")
except Exception as e:
    from enhanced_matching_system import EnhancedMatchingSystem, InteractionTracker, MatchingSystem
    
    enhanced_matching_system = EnhancedMatchingSystem(API_KEY)
    enhanced_matching_system.set_user_auth(user_auth)
    enhanced_matching_system.set_db_connection(get_db_connection)
    interaction_tracker = InteractionTracker(enhanced_matching_system, get_db_connection)
    print("✓ Enhanced matching system created directly")
    
email_followup = EmailFollowupSystem(user_auth, get_db_connection)
enhance_matching_with_verification()

add_onboarding_routes(app, login_required, user_auth, render_template_with_header, get_db_connection, process_matching_background)
# ============================================================================
# ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/')
def home():
    """Landing page explaining dinner simulation concept"""
    if 'user_id' in session:
        return redirect('/dashboard')
    
    content = '''
    <style>
        .landing-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 3rem 2rem;
            min-height: 80vh;
        }

        .hero-section {
            text-align: center;
            margin-bottom: 4rem;
        }

        .hero-title {
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: clamp(2.5rem, 6vw, 3.5rem);
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--color-charcoal);
            letter-spacing: -0.02em;
            line-height: 1.1;
        }

        .hero-subtitle {
            font-size: clamp(1.125rem, 3vw, 1.25rem);
            line-height: 1.6;
            color: var(--color-gray-600);
            margin-bottom: 1rem;
            font-weight: 400;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
        }

        .use-cases-title {
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--color-charcoal);
            text-align: center;
            margin: 3rem 0 2rem;
        }

        .use-cases-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 2rem;
            margin-bottom: 3rem;
        }

        .use-case-card {
            background: var(--color-white);
            border-radius: 20px;
            padding: 2.5rem 2rem;
            box-shadow:
                0 1px 3px rgba(0,0,0,0.04),
                0 8px 24px rgba(0,0,0,0.08);
            border: 1px solid rgba(0, 0, 0, 0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
            text-decoration: none;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }

        .use-case-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--color-sage);
            transform: scaleX(0);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .use-case-card:hover {
            transform: translateY(-8px);
            box-shadow:
                0 4px 8px rgba(0,0,0,0.06),
                0 16px 48px rgba(0,0,0,0.12);
        }

        .use-case-card:hover::before {
            transform: scaleX(1);
        }

        .use-case-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            display: block;
        }

        .use-case-title {
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: 1.375rem;
            font-weight: 600;
            color: var(--color-charcoal);
            margin-bottom: 0.75rem;
        }

        .use-case-description {
            font-size: 0.9375rem;
            line-height: 1.6;
            color: var(--color-gray-600);
            margin-bottom: 1.5rem;
            flex-grow: 1;
        }

        .use-case-link {
            color: var(--color-emerald);
            font-weight: 600;
            font-size: 0.9375rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .use-case-link::after {
            content: '→';
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .use-case-card:hover .use-case-link::after {
            transform: translateX(4px);
        }

        .cta-section {
            text-align: center;
            margin-top: 4rem;
            padding: 3rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            border-radius: 24px;
            border: 1px solid rgba(0, 0, 0, 0.05);
        }

        .cta-title {
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            color: var(--color-charcoal);
            margin-bottom: 1rem;
        }

        .cta-subtitle {
            font-size: 1rem;
            color: var(--color-gray-600);
            margin-bottom: 2rem;
        }

        .cta-buttons {
            display: flex;
            gap: 1.5rem;
            justify-content: center;
            flex-wrap: wrap;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 1rem;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: none;
            cursor: pointer;
            font-family: 'Satoshi', sans-serif;
            white-space: nowrap;
            min-width: 180px;
            justify-content: center;
        }

        .btn-primary {
            background: black;
            color: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }

        .btn-primary:hover {
            background: #333;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}

        .btn-secondary {
            background: var(--color-white);
            color: var(--color-gray-600);
            border: 1px solid var(--color-gray-600);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }

        .btn-secondary:hover {
            background: var(--color-gray-50);
            border-color: var(--color-emerald);
            color: var(--color-emerald);
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        }

        /* Mobile Responsive */
        @media (max-width: 768px) {
            .landing-container {
                padding: 2rem 1rem;
            }

            .use-cases-grid {
                grid-template-columns: 1fr;
                gap: 1.5rem;
            }

            .cta-buttons {
                flex-direction: column;
                align-items: center;
            }

            .btn {
                width: 100%;
                max-width: 280px;
            }
        }

        /* Animations */
        .hero-section {
            animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .use-case-card {
            animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .use-case-card:nth-child(1) { animation-delay: 0.1s; }
        .use-case-card:nth-child(2) { animation-delay: 0.2s; }
        .use-case-card:nth-child(3) { animation-delay: 0.3s; }
        .use-case-card:nth-child(4) { animation-delay: 0.4s; }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>

    <div class="landing-container">
        <div class="hero-section">
            <h1 class="hero-title"> Predicting How People Will Work Together With Agent Based Modelling</h1>
            <p class="hero-subtitle">
                Stop guessing. Start knowing. Pont creates AI simulations of real people to predict compatibility,
                reactions, and team dynamics before they happen.
            </p>
        </div>

        <h2 class="use-cases-title">Choose Your Use Case</h2>

        <div class="use-cases-grid">
            <a href="/therapy" class="use-case-card">
                
                <h3 class="use-case-title">Run a Therapy Practice</h3>
                <p class="use-case-description">
                    Match patients with the right therapist instantly using our intelligent matching widget.
                    Improve patient satisfaction from the first session.
                </p>
                <span class="use-case-link">Learn More</span>
            </a>

            <a href="/teams" class="use-case-card">
                
                <h3 class="use-case-title">Lead a Team</h3>
                <p class="use-case-description">
                    Predict how your team will respond to changes before you announce them.
                    Test scenarios and walk into meetings prepared.
                </p>
                <span class="use-case-link">Learn More</span>
            </a>

            <a href="/recruiting" class="use-case-card">
                
                <h3 class="use-case-title">Hire Better</h3>
                <p class="use-case-description">
                    Assess culture fit before making offers. Let candidates see if they'd thrive
                    on your team before they apply.
                </p>
                <span class="use-case-link">Learn More</span>
            </a>

            <a href="/networking" class="use-case-card">
                
                <h3 class="use-case-title">Maximize Networking</h3>
                <p class="use-case-description">
                    Know exactly who to meet at your next event. We analyze attendees and
                    recommend the highest-value connections.
                </p>
                <span class="use-case-link">Learn More</span>
            </a>
        </div>

        <div class="cta-section">
            <h2 class="cta-title">Ready To Stop Guessing?</h2>
            <p class="cta-subtitle">Join teams using AI to make better people decisions.</p>
            <div class="cta-buttons">
                <a href="/register" class="btn btn-primary">Start Free Trial</a>
                <a href="/login" class="btn btn-secondary">Sign In</a>
            </div>
            <p style="margin-top: 1rem; color: var(--color-gray-600); font-size: 0.875rem;">
                20 free simulations. No credit card required.
            </p>
        </div>
    </div>
    '''
    
    return render_template_with_header("home", content)


@app.route('/therapy')
def therapy_landing():
    """Therapy practice landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')

    content = '''
    <style>
        .therapy-container { max-width: 900px; margin: 0 auto; padding: 3rem 2rem; }
        .hero { text-align: center; margin-bottom: 4rem; }
        .hero-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: clamp(2.5rem, 5vw, 3.5rem); font-weight: 600; margin-bottom: 1rem; color: var(--color-charcoal); line-height: 1.1; }
        .hero-subtitle { font-size: clamp(1.125rem, 2.5vw, 1.375rem); color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.5; }
        .hero-badges { display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem; font-size: 0.875rem; color: var(--color-emerald); }
        .section { margin: 4rem 0; }
        .section-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: 2rem; font-weight: 600; color: var(--color-charcoal); margin-bottom: 1.5rem; }
        .section-subtitle { font-size: 1.125rem; color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.6; }
        .btn { display: inline-flex; align-items: center; gap: 0.75rem; padding: 1rem 2rem; border-radius: 50px; font-weight: 600; font-size: 1rem; text-decoration: none; transition: all 0.3s; border: none; cursor: pointer; font-family: 'Satoshi', sans-serif; min-width: 180px; justify-content: center; }
        .btn-primary { background: black; color: white; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
        .btn-primary:hover { background: #333; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); }
        .btn-secondary { background: var(--color-white); color: var(--color-gray-600); border: 1px solid var(--color-gray-600); }
        .btn-secondary:hover { background: var(--color-gray-50); border-color: var(--color-emerald); color: var(--color-emerald); transform: translateY(-2px); }
        .cta-buttons { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
    </style>
    <div class="therapy-container">
        <div class="hero">
            <h1 class="hero-title">Match Patients With The Right Therapist—Instantly</h1>
            <p class="hero-subtitle">Embed our intelligent matching widget on your website. Patients complete a questionnaire and instantly see which therapists align with their needs.</p>
            <div class="hero-badges"><span>✓ HIPAA-compliant</span><span>✓ Setup in 10 minutes</span><span>✓ 20 free matches</span></div>
            <div class="cta-buttons"><a href="/register" class="btn btn-primary">Start Free Trial</a><a href="/" class="btn btn-secondary">Back to Home</a></div>
        </div>
        <div class="section">
            <h2 class="section-title">Simple, Transparent Pricing</h2>
            <p style="font-size: 3rem; font-weight: 600; color: var(--color-charcoal);">£10<span style="font-size: 1.5rem; font-weight: 400;">/month</span></p>
            <p class="section-subtitle">Unlimited patient matches • Unlimited therapist profiles • All features included</p>
            <a href="/register" class="btn btn-primary">Start Free Trial</a>
        </div>
    </div>
    '''
    return render_template_with_header("Therapy Practice Matching - Pont", content)


@app.route('/teams')
def teams_landing():
    """Team leaders landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')

    content = '''
    <style>
        .teams-container { max-width: 900px; margin: 0 auto; padding: 3rem 2rem; }
        .hero { text-align: center; margin-bottom: 4rem; }
        .hero-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: clamp(2.5rem, 5vw, 3.5rem); font-weight: 600; margin-bottom: 1rem; color: var(--color-charcoal); line-height: 1.1; }
        .hero-subtitle { font-size: clamp(1.125rem, 2.5vw, 1.375rem); color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.5; }
        .hero-badges { display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem; font-size: 0.875rem; color: var(--color-emerald); }
        .section { margin: 4rem 0; }
        .section-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: 2rem; font-weight: 600; color: var(--color-charcoal); margin-bottom: 1.5rem; }
        .section-subtitle { font-size: 1.125rem; color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.6; }
        .btn { display: inline-flex; align-items: center; gap: 0.75rem; padding: 1rem 2rem; border-radius: 50px; font-weight: 600; font-size: 1rem; text-decoration: none; transition: all 0.3s; border: none; cursor: pointer; font-family: 'Satoshi', sans-serif; min-width: 180px; justify-content: center; }
        .btn-primary { background: black; color: white; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
        .btn-primary:hover { background: #333; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); }
        .btn-secondary { background: var(--color-white); color: var(--color-gray-600); border: 1px solid var(--color-gray-600); }
        .btn-secondary:hover { background: var(--color-gray-50); border-color: var(--color-emerald); color: var(--color-emerald); transform: translateY(-2px); }
        .cta-buttons { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
    </style>
    <div class="teams-container">
        <div class="hero">
            <h1 class="hero-title">Know How Your Team Will Respond Before You Ask</h1>
            <p class="hero-subtitle">Test organizational changes, predict reactions to pivots, and understand team dynamics before making decisions. Walk into important conversations prepared.</p>
            <div class="hero-badges"><span>✓ 20 free simulations</span><span>✓ Results in minutes</span><span>✓ £10/month</span></div>
            <div class="cta-buttons"><a href="/register" class="btn btn-primary">Start Free Trial</a><a href="/" class="btn btn-secondary">Back to Home</a></div>
        </div>
        <div class="section">
            <h2 class="section-title">Simple Pricing</h2>
            <p style="font-size: 3rem; font-weight: 600; color: var(--color-charcoal);">£10<span style="font-size: 1.5rem; font-weight: 400;">/month</span></p>
            <p class="section-subtitle">20 free simulations • Unlimited after that • All three modes • Unlimited team members</p>
            <a href="/register" class="btn btn-primary">Start Free Trial</a>
        </div>
    </div>
    '''
    return render_template_with_header("Team Simulation - Pont", content)


@app.route('/recruiting')
def recruiting_landing():
    """Recruiting/hiring landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')

    content = '''
    <style>
        .recruiting-container { max-width: 900px; margin: 0 auto; padding: 3rem 2rem; }
        .hero { text-align: center; margin-bottom: 4rem; }
        .hero-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: clamp(2.5rem, 5vw, 3.5rem); font-weight: 600; margin-bottom: 1rem; color: var(--color-charcoal); line-height: 1.1; }
        .hero-subtitle { font-size: clamp(1.125rem, 2.5vw, 1.375rem); color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.5; }
        .hero-badges { display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem; font-size: 0.875rem; color: var(--color-emerald); }
        .section { margin: 4rem 0; }
        .section-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: 2rem; font-weight: 600; color: var(--color-charcoal); margin-bottom: 1.5rem; }
        .section-subtitle { font-size: 1.125rem; color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.6; }
        .btn { display: inline-flex; align-items: center; gap: 0.75rem; padding: 1rem 2rem; border-radius: 50px; font-weight: 600; font-size: 1rem; text-decoration: none; transition: all 0.3s; border: none; cursor: pointer; font-family: 'Satoshi', sans-serif; min-width: 180px; justify-content: center; }
        .btn-primary { background: black; color: white; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
        .btn-primary:hover { background: #333; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); }
        .btn-secondary { background: var(--color-white); color: var(--color-gray-600); border: 1px solid var(--color-gray-600); }
        .btn-secondary:hover { background: var(--color-gray-50); border-color: var(--color-emerald); color: var(--color-emerald); transform: translateY(-2px); }
        .cta-buttons { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
    </style>
    <div class="recruiting-container">
        <div class="hero">
            <h1 class="hero-title">Let Candidates Assess Their Own Culture Fit</h1>
            <p class="hero-subtitle">Embed our compatibility widget on your careers page. Candidates see how they'd fit with your team before applying. Attract people who will actually thrive in your culture.</p>
            <div class="hero-badges"><span>✓ 20 free uses</span><span>✓ Setup in 10 minutes</span><span>✓ £10/month</span></div>
            <div class="cta-buttons"><a href="/register" class="btn btn-primary">Start Free Trial</a><a href="/" class="btn btn-secondary">Back to Home</a></div>
        </div>
        <div class="section">
            <h2 class="section-title">Simple Pricing</h2>
            <p style="font-size: 3rem; font-weight: 600; color: var(--color-charcoal);">£10<span style="font-size: 1.5rem; font-weight: 400;">/month</span></p>
            <p class="section-subtitle">Unlimited candidate uses • Full team profiling • 20 free simulations for internal use</p>
            <a href="/register" class="btn btn-primary">Start Free Trial</a>
        </div>
    </div>
    '''
    return render_template_with_header("Recruiting & Culture Fit - Pont", content)


@app.route('/networking')
def networking_landing():
    """Networking events landing page"""
    if 'user_id' in session:
        return redirect('/dashboard')

    content = '''
    <style>
        .networking-container { max-width: 900px; margin: 0 auto; padding: 3rem 2rem; }
        .hero { text-align: center; margin-bottom: 4rem; }
        .hero-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: clamp(2.5rem, 5vw, 3.5rem); font-weight: 600; margin-bottom: 1rem; color: var(--color-charcoal); line-height: 1.1; }
        .hero-subtitle { font-size: clamp(1.125rem, 2.5vw, 1.375rem); color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.5; }
        .hero-badges { display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem; font-size: 0.875rem; color: var(--color-emerald); }
        .section { margin: 4rem 0; }
        .section-title { font-family: 'Sentient', 'Satoshi', sans-serif; font-size: 2rem; font-weight: 600; color: var(--color-charcoal); margin-bottom: 1.5rem; }
        .section-subtitle { font-size: 1.125rem; color: var(--color-gray-600); margin-bottom: 2rem; line-height: 1.6; }
        .btn { display: inline-flex; align-items: center; gap: 0.75rem; padding: 1rem 2rem; border-radius: 50px; font-weight: 600; font-size: 1rem; text-decoration: none; transition: all 0.3s; border: none; cursor: pointer; font-family: 'Satoshi', sans-serif; min-width: 180px; justify-content: center; }
        .btn-primary { background: black; color: white; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3); }
        .btn-primary:hover { background: #333; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); }
        .btn-secondary { background: var(--color-white); color: var(--color-gray-600); border: 1px solid var(--color-gray-600); }
        .btn-secondary:hover { background: var(--color-gray-50); border-color: var(--color-emerald); color: var(--color-emerald); transform: translateY(-2px); }
        .cta-buttons { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
    </style>
    <div class="networking-container">
        <div class="hero">
            <h1 class="hero-title">Know Exactly Who To Meet At Your Next Event</h1>
            <p class="hero-subtitle">Upload the attendee list. Tell us your goals. We'll analyze everyone and recommend who each person on your team should prioritize meeting. Make networking strategic, not random.</p>
            <div class="hero-badges"><span>✓ 20 free analyses</span><span>✓ Results in 5 minutes</span><span>✓ £10/month</span></div>
            <div class="cta-buttons"><a href="/register" class="btn btn-primary">Start Free Trial</a><a href="/" class="btn btn-secondary">Back to Home</a></div>
        </div>
        <div class="section">
            <h2 class="section-title">Simple Pricing</h2>
            <p style="font-size: 3rem; font-weight: 600; color: var(--color-charcoal);">£10<span style="font-size: 1.5rem; font-weight: 400;">/month</span></p>
            <p class="section-subtitle">20 free analyses • Unlimited after that • Analyze unlimited attendees per event</p>
            <a href="/register" class="btn btn-primary">Start Free Trial</a>
        </div>
    </div>
    '''
    return render_template_with_header("Networking Events - Pont", content)


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
        
        existing_user = user_auth.get_user_by_email(email)
        existing_phone_user = user_auth.get_user_by_phone(phone)
        if existing_phone_user:
            flash('Phone number already exists. Please sign in here.', 'error')
            return redirect('/login')
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
                flash('Account created successfully! Let\'s set up your profile.', 'success')
                return redirect('/onboarding/step/1')
            else:
                flash(result['error'], 'error')
    
    # Registration form HTML (same as before)
    flash_html = ""
    messages = get_flashed_messages(with_categories=True)
    if messages:
        flash_html = '<div class="flash-messages">'
        for category, message in messages:
            flash_html += f'<div class="flash-{category}">{message}</div>'
        flash_html += '</div>'
    
    content = f'''
    <style>
        body {{
            background-color: white;
            color: black;
            font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .aesthetic-container {{
            background-color: white;
            max-width: 500px;
            width: 100%;
            padding: 60px 40px;
            text-align: center;
        }}
        
        .aesthetic-title {{
            font-size: 32px;
            font-weight: 300;
            margin-bottom: 8px;
            color: black;
            letter-spacing: -0.5px;
        }}
        
        .aesthetic-subtitle {{
            font-size: 16px;
            color: black;
            margin-bottom: 48px;
            line-height: 1.5;
        }}
        
        .form-group {{
            margin-bottom: 24px;
            text-align: left;
        }}
        
        .form-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
        }}
        
        .form-row .form-group {{
            flex: 1;
            margin-bottom: 0;
        }}
        
        .form-label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            color: black;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .form-input {{
            width: 100%;
            padding: 16px 20px;
            background-color: white;
            border: 1px solid black;
            border-radius: 8px;
            color: black;
            font-size: 16px;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }}
        
        .form-input:focus {{
            outline: none;
            border-color: black;
            box-shadow: 0 0 0 1px black;
            background-color: white;
        }}
        
        .form-input::placeholder {{
            color: rgba(45, 45, 45, 0.5);
        }}
        
        .register-button {{
            width: 100%;
            padding: 16px;
            background-color: black;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 16px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .register-button:hover {{
            background-color: #333;
            transform: translateY(-1px);
        }}
        
        .register-button:active {{
            transform: translateY(0);
        }}
        
        .form-links {{
            margin-top: 32px;
            font-size: 14px;
        }}
        
        .form-links a {{
            color: black;
            text-decoration: none;
            transition: color 0.3s ease;
        }}
        
        .form-links a:hover {{
            color: #ff9500;
        }}
        
        .flash-messages {{
            margin-bottom: 24px;
        }}
        
        .flash-error {{
            background-color: rgba(255, 149, 0, 0.1);
            border: 1px solid rgba(255, 149, 0, 0.3);
            color: #ff9500;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
            text-align: left;
        }}
        
        .flash-success {{
            background-color: rgba(107, 155, 153, 0.1);
            border: 1px solid rgba(0, 0, 0, 0.3);
            color: black;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
            text-align: left;
        }}
    </style>
    
    <div class="aesthetic-container">
        <h1 class="aesthetic-title">Create your account</h1>
        <p class="aesthetic-subtitle">Join us and start your journey</p>
        
        {flash_html}
        
        <form method="POST">
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">First Name</label>
                    <input type="text" name="first_name" class="form-input" placeholder="John" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Last Name</label>
                    <input type="text" name="last_name" class="form-input" placeholder="Doe" required>
                </div>
            </div>
            
            <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" name="email" class="form-input" placeholder="john@example.com" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">Phone Number</label>
                <input type="tel" name="phone" class="form-input" placeholder="+44 7XXX XXXXXX" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">Password</label>
                <input type="password" name="password" class="form-input" placeholder="••••••••" required minlength="6">
            </div>
            
            <div class="form-group">
                <label class="form-label">Confirm Password</label>
                <input type="password" name="confirm_password" class="form-input" placeholder="••••••••" required>
            </div>
            
            <button type="submit" class="register-button">
                Create Account
            </button>
            <div class="form-links" style="margin-top: 12px; font-size: 12px; color: black;">
                By creating an account, you agree to our <a href="/terms-of-service">Terms of Service</a> and <a href="/privacy-policy">Privacy Policy</a>.
            </div>
        </form>
        
        <div class="form-links">
            Already have an account? <a href="/login">Sign in here</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("home", content)

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
    
    # Get flash messages and convert to HTML
    flash_html = ""
    messages = get_flashed_messages(with_categories=True)
    if messages:
        flash_html = '<div class="flash-messages">'
        for category, message in messages:
            flash_html += f'<div class="flash-{category}">{message}</div>'
        flash_html += '</div>'
    
    # Login form with aesthetic design
    content = f'''
    <style>
        body {{
            background-color: white;
            color: black;
            font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .aesthetic-container {{
            background-color: white;
            max-width: 400px;
            width: 100%;
            padding: 60px 40px;
            text-align: center;
        }}
        
        .aesthetic-title {{
            font-size: 32px;
            font-weight: 300;
            margin-bottom: 8px;
            color: black;
            letter-spacing: -0.5px;
        }}
        
        .aesthetic-subtitle {{
            font-size: 16px;
            color: black;
            margin-bottom: 48px;
            line-height: 1.5;
        }}
        
        .form-group {{
            margin-bottom: 24px;
            text-align: left;
        }}
        
        .form-label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            color: black;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .form-input {{
            width: 100%;
            padding: 16px 20px;
            background-color: rgba(255, 255, 255, 0.3);
            border: 1px solid rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            color: black;
            font-size: 16px;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }}
        
        .form-input:focus {{
            outline: none;
            border-color: black;
            box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.3);
            background-color: white;
        }}
        
        .form-input::placeholder {{
            color: rgba(45, 45, 45, 0.5);
        }}
        
        .login-button {{
            width: 100%;
            padding: 16px;
            background-color: black;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 16px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .login-button:hover {{
            background-color: #333;
            transform: translateY(-1px);
        }}
        
        .login-button:active {{
            transform: translateY(0);
        }}
        
        .form-links {{
            margin-top: 32px;
            font-size: 14px;
        }}
        
        .form-links a {{
            color: black;
            text-decoration: none;
            transition: color 0.3s ease;
        }}
        
        .form-links a:hover {{
            color: #ff9500;
        }}
        
        .divider {{
            margin: 24px 0;
            color: rgba(107, 155, 153, 0.5);
        }}
        
        /* Flash message styling */
        .flash-messages {{
            margin-bottom: 24px;
        }}
        
        .flash-error {{
            background-color: rgba(255, 149, 0, 0.1);
            border: 1px solid rgba(255, 149, 0, 0.3);
            color: #ff9500;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
        }}
        
        .flash-success {{
            background-color: rgba(107, 155, 153, 0.1);
            border: 1px solid rgba(0, 0, 0, 0.3);
            color: black;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
        }}
    </style>
    
    <div class="aesthetic-container">
        <h1 class="aesthetic-title">Welcome back</h1>
        <p class="aesthetic-subtitle">Enter your credentials to access your account</p>
        
        {flash_html}
        
        <form method="POST">
            <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" name="email" class="form-input" placeholder="your@email.com" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">Password</label>
                <input type="password" name="password" class="form-input" placeholder="••••••••" required>
            </div>
            
            <button type="submit" class="login-button">
                Sign In
            </button>
        </form>
        
        <div class="form-links">
            <a href="/forgot-password">Forgot your password?</a>
            <div class="divider">•</div>
            Don't have an account? <a href="/register">Create one here</a>
        </div>
    </div>
    '''
    
    return content

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
    
    # Get flash messages and convert to HTML
    flash_html = ""
    messages = get_flashed_messages(with_categories=True)
    if messages:
        flash_html = '<div class="flash-messages">'
        for category, message in messages:
            flash_html += f'<div class="flash-{category}">{message}</div>'
        flash_html += '</div>'
    
    # Forgot password form with aesthetic design
    content = f'''
    <style>
        body {{
            background-color: white;
            color: black;
            font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .aesthetic-container {{
            background-color: white;
            max-width: 400px;
            width: 100%;
            padding: 60px 40px;
            text-align: center;
        }}
        
        .aesthetic-title {{
            font-size: 32px;
            font-weight: 300;
            margin-bottom: 8px;
            color: black;
            letter-spacing: -0.5px;
        }}
        
        .aesthetic-subtitle {{
            font-size: 16px;
            color: black;
            margin-bottom: 32px;
            line-height: 1.5;
        }}
        
        .info-card {{
            background: rgba(107, 155, 153, 0.1);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 32px;
            text-align: left;
            border: 1px solid rgba(107, 155, 153, 0.2);
        }}
        
        .info-card-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
            font-weight: 600;
            color: black;
        }}
        
        .info-icon {{
            font-size: 20px;
        }}
        
        .info-text {{
            font-size: 14px;
            color: black;
            line-height: 1.5;
        }}
        
        .form-group {{
            margin-bottom: 24px;
            text-align: left;
        }}
        
        .form-label {{
            display: block;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
            color: black;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .form-input {{
            width: 100%;
            padding: 16px 20px;
            background-color: white;
            border: 1px solid white;
            border-radius: 8px;
            color: black;
            font-size: 16px;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }}
        
        .form-input:focus {{
            outline: none;
            border-color: black;
            box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.3);
            background-color: white;
        }}
        
        .form-input::placeholder {{
            color: rgba(45, 45, 45, 0.5);
        }}
        
        .reset-button {{
            width: 100%;
            padding: 16px;
            background-color: black;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 16px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .reset-button:hover {{
            background-color: #333;
            transform: translateY(-1px);
        }}
        
        .reset-button:active {{
            transform: translateY(0);
        }}
        
        .form-links {{
            margin-top: 32px;
            font-size: 14px;
        }}
        
        .form-links a {{
            color: black;
            text-decoration: none;
            transition: color 0.3s ease;
        }}
        
        .form-links a:hover {{
            color: #ff9500;
        }}
        
        /* Flash message styling */
        .flash-messages {{
            margin-bottom: 24px;
        }}
        
        .flash-error {{
            background-color: rgba(255, 149, 0, 0.1);
            border: 1px solid rgba(255, 149, 0, 0.3);
            color: #ff9500;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
            text-align: left;
        }}
        
        .flash-success {{
            background-color: rgba(107, 155, 153, 0.1);
            border: 1px solid rgba(0, 0, 0, 0.3);
            color: black;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 14px;
            text-align: left;
        }}
    </style>
    
    <div class="aesthetic-container">
        <h1 class="aesthetic-title">Reset your password</h1>
        <p class="aesthetic-subtitle">We'll send you a secure reset link</p>
        
        <div class="info-card">
            <div class="info-card-header">
                <span>Forgot your password?</span>
            </div>
            <div class="info-text">
                Enter your email address and we'll send you a link to reset your password.
            </div>
        </div>
        
        {flash_html}
        
        <form method="POST">
            <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" name="email" class="form-input" placeholder="your@email.com" required autofocus>
            </div>
            
            <button type="submit" class="reset-button">
                Send Reset Link
            </button>
        </form>
        
        <div class="form-links">
            <a href="/login">← Remember your password?</a>
        </div>
    </div>
    '''
    
    return content

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
                    <h1 style="color: black; font-size: 24px; margin-bottom: 16px;">Password Reset Successful!</h1>
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
            <a href="/login" style="color: black; text-decoration: none;">Back to Login</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Set New Password", content)

# ============================================================================
# DEPRECATED: Old verification routes removed
# ============================================================================

@app.route('/profile-settings')
@login_required
def profile_settings():
    """Profile settings page"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    subscription_status = subscription_manager.get_user_subscription_status(user_id)

    # Get flash messages and convert to HTML
    flash_html = ""
    messages = get_flashed_messages(with_categories=True)
    if messages:
        flash_html = '<div class="flash-messages">'
        for category, message in messages:
            flash_html += f'<div class="flash-{category}">{message}</div>'
        flash_html += '</div>'

    # Render subscription management section
    subscription_html = render_subscription_management_section(subscription_status, user_id)
    
    content = f'''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        body {{
            background-color: white;
            color: black;
            font-family: "Satoshi", 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
        }}
        
        .settings-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .settings-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        
        .settings-title {{
            font-family: "Sentient", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: black;
            letter-spacing: -0.02em;
        }}
        
        .settings-header p {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            line-height: 1.6;
            color: black;
            margin: 0;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .subscription-section {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            margin: 2rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            transition: all 0.3s ease;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        
        .subscription-section:hover {{
            transform: translateY(-4px);
            border-color: rgba(0, 0, 0, 0.3);
        }}
        
        .subscription-active {{
            border-left: 4px solid black;
            background: #f5f5f5;
        }}
        
        .subscription-free {{
            border-left: 4px solid black;
        }}
        
        .verification-section {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            margin: 2rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            transition: all 0.3s ease;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        
        .verification-section:hover {{
            transform: translateY(-4px);
            border-color: rgba(0, 0, 0, 0.3);
        }}
        
        .verification-section h3 {{
            font-family: "Sentient", sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            margin: 0 0 1.5rem 0;
            color: black;
        }}
        
        .subscription-section h3 {{
            font-family: "Sentient", sans-serif;
            font-size: 1.75rem;
            font-weight: 600;
            margin: 0 0 1.5rem 0;
            color: black;
        }}
        
        .plan-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: white;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 50px;
            font-family: "Satoshi", sans-serif;
            font-weight: 600;
            font-size: 0.875rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .plan-badge.free {{
            background: rgba(107, 155, 153, 0.6);
        }}
        
        .verified-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: white;
            color: black;
            padding: 0.75rem 1.5rem;
            border-radius: 50px;
            font-family: "Satoshi", sans-serif;
            font-weight: 600;
            font-size: 0.875rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .subscription-details {{
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 16px;
            margin: 1.5rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .verification-benefits {{
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 16px;
            margin: 1.5rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            font-family: "Satoshi", sans-serif;
            line-height: 1.6;
        }}
        
        .verification-pending {{
            background: rgba(255, 149, 0, 0.1);
            backdrop-filter: blur(10px);
            padding: 1.5rem;
            border-radius: 12px;
            margin: 1.5rem 0;
            border: 1px solid rgba(255, 149, 0, 0.3);
            font-family: "Satoshi", sans-serif;
        }}
        
        .status-pending {{
            color: #ff9500;
            font-weight: 600;
        }}
        
        .btn-manage {{
            font-family: "Sentient", sans-serif;
            background: white;
            color: black;
            border: 1px solid black;
            padding: 1rem 2rem;
            border: none;
            border-radius: 50px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.875rem;
            text-decoration: none;
            display: inline-block;
            margin: 0.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .btn-manage:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.4);
        }}
        
        .btn-upgrade {{
            background: black;
            color: white;
        }}
        
        .btn-cancel {{
            background: rgba(45, 45, 45, 0.6);
            color: white;
        }}
        
        .btn-verify {{
            font-family: "Sentient", sans-serif;
            background: black;
            color: white;
            padding: 1rem 2rem;
            border: none;
            border-radius: 50px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.875rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}
        
        .btn-verify:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.4);
        }}
        
        .usage-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1.5rem;
            margin: 1.5rem 0;
        }}
        
        .usage-stat {{
            text-align: center;
            padding: 1.5rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .stat-number {{
            font-family: 'Sentient', sans-serif;
            font-size: 2rem;
            font-weight: 700;
            color: black;
            margin-bottom: 0.5rem;
        }}
        
        .stat-label {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.75rem;
            color: rgba(45, 45, 45, 0.7);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-weight: 600;
        }}
        
        .back-link {{
            font-family: "Satoshi", sans-serif;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: black;
            text-decoration: none;
            font-weight: 500;
            margin: 1rem;
            padding: 0.75rem 1.5rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 50px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }}
        
        .back-link:hover {{
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.9);
            color: black;
        }}
        
        /* Flash message styling */
        .flash-messages {{
            margin-bottom: 2rem;
        }}
        
        .flash-error {{
            background: rgba(255, 149, 0, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 149, 0, 0.5);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
        }}
        
        .flash-success {{
            background: rgba(107, 155, 153, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(107, 155, 153, 0.5);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
        }}
        
        /* Responsive design */
        @media (max-width: 768px) {{
            .settings-container {{
                padding: 1rem;
            }}
            
            .settings-header {{
                padding: 1.5rem 1rem;
            }}
            
            .subscription-section,
            .verification-section {{
                padding: 1.5rem;
            }}
            
            .settings-title {{
                font-size: 2rem;
            }}
        }}
    </style>
    
    <div class="settings-container">
        {flash_html}
        
        <div class="settings-header">
            <h1 class="settings-title">Profile Settings</h1>
            <p>Manage your account, subscription, and privacy settings</p>
        </div>
        
        <!-- Profile Information Section -->
        <div class="subscription-section">
            <h2 style="font-family: 'Sentient', sans-serif; color: black; margin-bottom: 1.5rem; font-size: 1.5rem;">Basic Information</h2>
            <p style="color: black; margin-bottom: 2rem; line-height: 1.6;">Update your personal details, bio, location, and profile settings.</p>
            <div style="text-align: center;">
                <a href="/edit-profile" class="btn-manage btn-upgrade" style="font-size: 1rem; padding: 1.25rem 2rem;">
                    Click here to edit your basic information
                </a>
            </div>
        </div>

        {subscription_html}

        <div style="text-align: center; margin-top: 3rem;">
            <a href="/dashboard" class="back-link">Back to Dashboard</a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Profile Settings", content, user_info)

def render_verification_section(verification_status: Dict) -> str:
    """Render verification section based on user's current status"""
    
    if verification_status.get('is_verified'):
        # User is already verified
        verified_date = verification_status.get('verified_at', 'Recently')
        if verified_date != 'Recently':
            try:
                from datetime import datetime
                verified_date = datetime.fromisoformat(verified_date.replace('Z', '+00:00')).strftime('%B %d, %Y')
            except:
                verified_date = 'Recently'
        
        return f'''
        <div class="verification-section">
            <div class="verified-badge">
                Verified Account
            </div>
            <h3 style="color: var(--color-emerald); margin-bottom: 1rem;">Identity Verified</h3>
            <p>Your account has been verified on {verified_date}. Your profile displays a blue verified badge to other users, showing that you're a real person.</p>
            
            <div class="verification-benefits">
                <strong>Active Benefits:</strong><br>
                • Blue verified badge on your profile<br>
                • Higher match-to-meet conversion rates<br>
                • Increased trust from other users<br>
                • Priority in matching algorithms<br>
                • Enhanced platform safety
            </div>
        </div>
        '''
    
    elif verification_status.get('pending_request'):
        # User has a pending verification request
        pending = verification_status['pending_request']
        status = pending['status']
        
        if status == 'pending':
            if pending.get('photo_received'):
                status_text = '<span class="status-pending">Under Review</span> - Our team is reviewing your submission'
            else:
                status_text = '<span class="status-pending">Awaiting Photos</span> - Please send your verification photos'
            
            expires_date = pending.get('expires_at', '')
            try:
                from datetime import datetime
                expires_date = datetime.fromisoformat(expires_date.replace('Z', '+00:00')).strftime('%B %d, %Y')
            except:
                expires_date = 'Soon'
            
            return f'''
            <div class="verification-section">
                <h3 style="color: var(--color-emerald); margin-bottom: 1rem;">Verification In Progress</h3>
                
                <div class="verification-pending">
                    <strong>Status:</strong> {status_text}<br>
                    <strong>Expires:</strong> {expires_date}
                </div>
                
                <p>Your verification request is being processed. Check your email for detailed instructions on submitting your ID photos.</p>
                
                <div style="margin-top: 1.5rem;">
                    <strong>Next Steps:</strong><br>
                    1. Check your email for verification instructions<br>
                    2. Send clear photos of your ID and selfie to our verification email<br>
                    3. Include your verification code in the photo<br>
                    4. Wait 1-2 business days for review
                </div>
            </div>
            '''
        
        elif status == 'rejected':
            reason = pending.get('rejection_reason', 'Photos did not meet verification requirements')
            
            return f'''
            <div class="verification-section">
                <h3 style="color: #dc3545; margin-bottom: 1rem;">Verification Needs Attention</h3>
                
                <div style="background: #f8d7da; color: #721c24; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                    <strong>Reason:</strong> {reason}
                </div>
                
                <p>Your previous verification attempt couldn't be approved. You can submit a new verification request with updated photos.</p>
                
                <form method="POST" action="/request-verification" style="margin-top: 1.5rem;">
                    <button type="submit" class="btn-verify">Request New Verification</button>
                </form>
            </div>
            '''
    
    else:
        # User can request verification
        return '''
        <div class="verification-section">
            <h3 style="color: var(--color-emerald); margin-bottom: 1rem;">Get Verified</h3>
            <p>Verify your identity to get a blue verified badge and increase your match success rate.</p>
            
            <div class="verification-benefits">
                <strong>Benefits of Verification:</strong><br>
                • Blue verified badge on your profile<br>
                • 40% higher match-to-meet conversion rates<br>
                • Increased trust from other users<br>
                • Priority in matching algorithms<br>
                • Help make the platform safer for everyone
            </div>
            
            <div style="background: #fff3cd; color: #856404; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                <strong>How it works:</strong><br>
                1. Click "Start Verification" below<br>
                2. Receive instructions via email<br>
                3. Send photos of your ID + selfie<br>
                4. Get approved within 1-2 business days
            </div>
            
            <form method="POST" action="/request-verification" style="margin-top: 1.5rem;">
                <button type="submit" class="btn-verify">Start Verification Process</button>
            </form>
        </div>
        '''

def render_subscription_management_section(subscription_status: Dict, user_id: int = None) -> str:
    """Render subscription management section based on user's current status"""

    # Get simulation count if user_id provided
    sim_count = 0
    if user_id:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM simulations WHERE created_by = %s', (user_id,))
            result = cursor.fetchone()
            sim_count = result['count'] if result else 0
            conn.close()
        except:
            sim_count = 0

    if subscription_status['is_subscribed']:
        status = subscription_status.get('status')
        expires_at = subscription_status.get('expires_at', 'Unknown')
        
        # Format the date properly
        if expires_at and expires_at != 'Unknown' and str(expires_at).lower() != 'none':
            try:
                if isinstance(expires_at, str):
                    # If it's a string, try to parse it
                    from datetime import datetime
                    expires_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                else:
                    # If it's already a datetime object
                    expires_date = expires_at
                expires_at_formatted = expires_date.strftime('%B %d, %Y')
            except:
                expires_at_formatted = 'Date unavailable'
        else:
            expires_at_formatted = 'Date unavailable'
        
        if status == 'cancelled':
            # Subscription is cancelled but still active until expiry
            return f'''
            <div class="subscription-section subscription-active" style="border-left: 4px solid black;">
                <h3 style="color: black; margin-bottom: 1rem;">Subscription Management</h3>
                
                <div class="plan-badge" style="background: white; color: black;">
                    Premium Plan - Cancelled
                </div>
                
                <div class="subscription-details">
                    <div class="usage-stats">
                        <div class="usage-stat">
                            <div class="stat-number">∞</div>
                            <div class="stat-label">Simulations Available</div>
                        </div>
                        <div class="usage-stat">
                            <div class="stat-number">{sim_count}</div>
                            <div class="stat-label">Total Simulations Run</div>
                        </div>
                    </div>

                    <p><strong>Expires:</strong> {expires_at_formatted}</p>
                    <p><strong>Plan:</strong> Premium (£9.99/month)</p>
                    <p style="color: black; font-weight: 600;">Your subscription has been cancelled and will expire on {expires_at_formatted}. You'll continue to have premium access until then.</p>
                </div>

                <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                    <a href="/subscription/plans" class="btn-manage btn-upgrade">
                        Reactivate Subscription
                    </a>
                </div>

                <div style="margin-top: 1.5rem; font-size: 0.875rem; color: var(--color-gray-600);">
                    After expiry, you'll be limited to 20 free simulations total.
                </div>
            </div>
            '''
        else:
            # Active subscription
            return f'''
            <div class="subscription-section subscription-active">
                <h3 style="color: var(--color-emerald); margin-bottom: 1rem;">Subscription Management</h3>
                
                <div class="plan-badge">
                    Premium Plan Active
                </div>
                
                <div class="subscription-details">
                    <div class="usage-stats">
                        <div class="usage-stat">
                            <div class="stat-number">∞</div>
                            <div class="stat-label">Simulations Available</div>
                        </div>
                        <div class="usage-stat">
                            <div class="stat-number">{sim_count}</div>
                            <div class="stat-label">Total Simulations Run</div>
                        </div>
                    </div>

                    <p><strong>Next Billing:</strong> {expires_at_formatted}</p>
                    <p><strong>Plan:</strong> Premium (£9.99/month)</p>
                </div>

                <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                    <a href="/subscription/cancel" class="btn-manage btn-cancel">
                        Cancel Subscription
                    </a>
                </div>

                <div style="margin-top: 1.5rem; font-size: 0.875rem; color: var(--color-gray-600);">
                    Your subscription includes unlimited simulations and priority support.
                </div>
            </div>
            '''
    else:
        # Free plan
        remaining = max(0, 20 - sim_count)

        return f'''
        <div class="subscription-section subscription-free">
            <h3 style="color: var(--color-emerald); margin-bottom: 1rem;">Subscription Management</h3>

            <div class="plan-badge free">
                Free Plan
            </div>

            <div class="subscription-details">
                <div class="usage-stats">
                    <div class="usage-stat">
                        <div class="stat-number">{remaining}</div>
                        <div class="stat-label">Simulations Remaining</div>
                    </div>
                    <div class="usage-stat">
                        <div class="stat-number">{sim_count}</div>
                        <div class="stat-label">Simulations Used</div>
                    </div>
                    <div class="usage-stat">
                        <div class="stat-number">20</div>
                        <div class="stat-label">Free Total Limit</div>
                    </div>
                </div>

                <p>You're currently on the free plan with {remaining} simulation{"s" if remaining != 1 else ""} remaining.</p>
            </div>

            <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                <a href="/subscription/plans" class="btn-manage btn-upgrade">
                    Upgrade to Premium
                </a>
            </div>

            <div style="margin-top: 1.5rem; font-size: 0.875rem; color: var(--color-gray-600);">
                Upgrade to Premium for unlimited simulations and priority support.
            </div>
        </div>
        '''
    

# ============================================================================
# ROUTES - DASHBOARD & MATCHING
# ============================================================================

def render_organizations_dashboard(user_info: Dict, organizations: List[Dict]) -> str:
    """Render the organizations dashboard"""
    if organizations:
        org_cards = []
        for org in organizations:
            role_badge = '<span style="background: gold; color: black; padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">OWNER</span>' if org['is_owner'] else ''

            # Add action buttons (edit/delete for owner, leave for members)
            action_buttons = ''
            if org['is_owner']:
                action_buttons = f'''
                <div class="org-card-actions" style="display: flex; gap: 0.5rem; margin-top: 1rem;" onclick="event.stopPropagation();">
                    <button onclick="window.location.href='/organization/{org['id']}/edit'"
                            style="flex: 1; padding: 0.5rem; background: white; border: 1px solid #ddd; border-radius: 8px; cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: 'Satoshi', sans-serif;">
                        Edit
                    </button>
                    <button onclick="if(confirm('Delete this organization? This cannot be undone.')) window.location.href='/organization/{org['id']}/delete'"
                            style="flex: 1; padding: 0.5rem; background: white; border: 1px solid #dc3545; color: #dc3545; border-radius: 8px; cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: 'Satoshi', sans-serif;">
                        Delete
                    </button>
                </div>
                '''
            else:
                action_buttons = f'''
                <div class="org-card-actions" style="margin-top: 1rem;" onclick="event.stopPropagation();">
                    <button onclick="if(confirm('Leave this organization?')) window.location.href='/organization/{org['id']}/leave'"
                            style="width: 100%; padding: 0.5rem; background: white; border: 1px solid #dc3545; color: #dc3545; border-radius: 8px; cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: 'Satoshi', sans-serif;">
                        Leave Organization
                    </button>
                </div>
                '''

            org_card = f'''
            <div class="org-card" onclick="window.location.href='/organization/{org['id']}'" style="cursor: pointer;">
                <div class="org-card-header">
                    <h3 class="org-card-title">{org['name']}</h3>
                    {role_badge}
                </div>
                <p class="org-card-description">{org['description'] or 'No description'}</p>
                <div class="org-card-footer">
                    <span class="org-card-members">{org['member_count']} member{'s' if org['member_count'] != 1 else ''}</span>
                    <span class="org-card-arrow">→</span>
                </div>
                {action_buttons}
            </div>
            '''
            org_cards.append(org_card)

        orgs_html = '\n'.join(org_cards)
    else:
        orgs_html = '''
        <div class="empty-state">
            <p class="empty-state-message">No organizations yet. Create one or join one!</p>
            <a href="/create-organization" class="btn btn-primary">Create Organization</a>
        </div>
        '''

    content = f'''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        .dashboard-container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .dashboard-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .dashboard-title {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: black;
            letter-spacing: -0.02em;
        }}

        .dashboard-subtitle {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            color: black;
        }}

        .organizations-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .org-card {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }}

        .org-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border-color: rgba(0, 0, 0, 0.3);
        }}

        .org-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}

        .org-card-title {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
            color: black;
        }}

        .org-card-description {{
            font-family: "Satoshi", sans-serif;
            color: #666;
            margin-bottom: 1rem;
            line-height: 1.5;
        }}

        .org-card-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: "Satoshi", sans-serif;
            color: black;
            font-weight: 500;
        }}

        .org-card-arrow {{
            font-size: 1.5rem;
            transition: transform 0.3s ease;
        }}

        .org-card:hover .org-card-arrow {{
            transform: translateX(4px);
        }}

        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .empty-state-message {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            color: #666;
            margin-bottom: 2rem;
        }}

        .btn {{
            font-family: "Satoshi", sans-serif;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }}

        .btn-primary {{
            background: black;
            color: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }}

        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}

        .action-bar {{
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin-top: 2rem;
            flex-wrap: wrap;
        }}

        .btn-secondary {{
            background: white;
            color: black;
            border: 2px solid black;
        }}

        .btn-secondary:hover {{
            background: black;
            color: white;
        }}

        .join-org-form {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 2rem;
            margin-top: 2rem;
            border: 1px solid rgba(0, 0, 0, 0.1);
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }}

        .join-org-title {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: black;
        }}

        .form-input {{
            font-family: "Satoshi", sans-serif;
            width: 100%;
            padding: 1rem;
            border: 1px solid rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            font-size: 1rem;
            margin-bottom: 1rem;
            box-sizing: border-box;
        }}

        .form-input:focus {{
            outline: none;
            border-color: black;
        }}
    </style>

    <div class="dashboard-container">
        <div class="dashboard-header">
            <h1 class="dashboard-title">Your Organizations</h1>
            <p class="dashboard-subtitle">Select an organization to run simulations</p>
        </div>

        <div class="organizations-grid">
            {orgs_html}
        </div>

        <div class="action-bar">
            <a href="/create-organization" class="btn btn-primary">+ Create Organization</a>
            <button onclick="document.getElementById('joinOrgForm').style.display='block'; this.style.display='none';" class="btn btn-secondary">Join Organization</button>
        </div>

        <div id="joinOrgForm" class="join-org-form" style="display: none;">
            <h3 class="join-org-title">Join an Organization</h3>
            <p style="color: #666; margin-bottom: 1.5rem; font-family: 'Satoshi', sans-serif;">Enter the invite code or paste the invite link</p>
            <form method="POST" action="/join-organization-by-code">
                <input type="text" name="invite_code" class="form-input" placeholder="Invite code or full invite link" required>
                <div style="display: flex; gap: 0.5rem;">
                    <button type="submit" class="btn btn-primary" style="flex: 1;">Join</button>
                    <button type="button" onclick="this.closest('form').reset(); document.getElementById('joinOrgForm').style.display='none'; document.querySelector('.btn-secondary').style.display='inline-flex';" class="btn btn-secondary" style="flex: 1;">Cancel</button>
                </div>
            </form>
        </div>
    </div>
    '''

    return content


@app.route('/settings')
@login_required
def settings():
    """User settings - redirects to profile settings"""
    return redirect('/profile-settings')

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard - shows list of organizations"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    if not user_info:
        flash('Account information not found', 'error')
        return redirect('/login')

    # If profile not completed, redirect to onboarding
    if not user_info.get('profile_completed', False):
        return redirect('/onboarding/step/1')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all organizations the user is a member of
        cursor.execute('''
            SELECT o.id, o.name, o.description, o.created_at,
                   (SELECT COUNT(*) FROM organization_members om2
                    WHERE om2.organization_id = o.id AND om2.is_active = TRUE) as member_count,
                   (o.created_by = %s) as is_owner
            FROM organizations o
            INNER JOIN organization_members om ON o.id = om.organization_id
            WHERE om.user_id = %s AND o.is_active = TRUE
            GROUP BY o.id, o.name, o.description, o.created_at, o.created_by
            ORDER BY o.created_at DESC
        ''', (user_id, user_id))

        organizations = cursor.fetchall()
        conn.close()

        content = render_organizations_dashboard(user_info, organizations)
        return render_template_with_header("Dashboard", content, user_info)

    except Exception as e:
        print(f"Error loading dashboard: {e}")
        flash('Error loading dashboard', 'error')
        return redirect('/login')


def render_matches_dashboard_with_event(user_info: Dict, matches: List[Dict], event: Dict) -> str:
    """Render matches dashboard with event details displayed at the top"""
    user_id = session['user_id']

    # Format event date and time
    event_date = event['date_time'].strftime('%A, %B %d, %Y')
    event_time = event['date_time'].strftime('%I:%M %p')

    # Event header section
    event_header = f'''
    <div class="event-header" style="background: white; border: 2px solid black; border-radius: 15px; padding: 2rem; margin-bottom: 2rem; text-align: center;">
        <h2 style="font-family: 'Sentient', serif; font-size: 1.8rem; color: black; margin-bottom: 1rem; font-weight: 600;">Your Upcoming Event</h2>
        <h3 style="font-family: 'Satoshi', sans-serif; font-size: 1.4rem; color: black; margin-bottom: 1.5rem; font-weight: 700;">{event['title']}</h3>
        <div style="display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; font-family: 'Satoshi', sans-serif; color: black; margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Date:</strong> {event_date}
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Time:</strong> {event_time}
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Venue:</strong> {event['venue_name'] or 'TBA'}
            </div>
        </div>
        {f'<div style="margin-bottom: 1.5rem; color: black; font-family: Satoshi, sans-serif;"><strong>Address:</strong> {event["venue_address"]}</div>' if event.get('venue_address') else ''}
        <div style="margin-bottom: 1.5rem; padding: 1rem; background: black; color: white; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 500;">
            Below are your compatible matches who will also be attending this event
        </div>
        <div>
            <a href="/withdraw-from-event" onclick="return confirm('Are you sure you want to withdraw from this event? You will no longer be matched with other attendees.')"
               style="background: black; color: white; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 0.875rem; display: inline-block; transition: all 0.3s ease;">
                Withdraw from Event
            </a>
        </div>
    </div>
    '''

    # Get the existing matches dashboard content but modify the title
    matches_content = render_matches_dashboard(user_info, matches)

    # Insert event header at the beginning of matches content
    # Find the dashboard container and insert event header after it starts
    dashboard_start = matches_content.find('<div class="dashboard-container">') + len('<div class="dashboard-container">')

    if dashboard_start > len('<div class="dashboard-container">') - 1:
        modified_content = (
            matches_content[:dashboard_start] +
            event_header +
            matches_content[dashboard_start:]
        )
    else:
        # Fallback if structure is different
        modified_content = event_header + matches_content

    return modified_content

def render_no_matches_dashboard_with_event(event: Dict) -> str:
    """Render no matches dashboard with event details and small orange sphere in draggable teal cube"""
    # Format event date and time
    event_date = event['date_time'].strftime('%A, %B %d, %Y')
    event_time = event['date_time'].strftime('%I:%M %p')

    # Event header section
    event_header = f'''
    <div class="event-header" style="background: white; border: 2px solid black; border-radius: 15px; padding: 2rem; margin-bottom: 2rem; text-align: center;">
        <h2 style="font-family: 'Sentient', serif; font-size: 1.8rem; color: black; margin-bottom: 1rem; font-weight: 600;">Your Upcoming Event</h2>
        <h3 style="font-family: 'Satoshi', sans-serif; font-size: 1.4rem; color: black; margin-bottom: 1.5rem; font-weight: 700;">{event['title']}</h3>
        <div style="display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; font-family: 'Satoshi', sans-serif; color: black; margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Date:</strong> {event_date}
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Time:</strong> {event_time}
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <strong>Venue:</strong> {event['venue_name'] or 'TBA'}
            </div>
        </div>
        {f'<div style="margin-bottom: 1.5rem; color: black; font-family: Satoshi, sans-serif;"><strong>Address:</strong> {event["venue_address"]}</div>' if event.get('venue_address') else ''}
        <div style="margin-bottom: 1.5rem; padding: 1rem; background: black; color: white; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 500;">
            No compatible matches found yet for this event
        </div>
        <div>
            <a href="/withdraw-from-event" onclick="return confirm('Are you sure you want to withdraw from this event? You will no longer be matched with other attendees.')"
               style="background: black; color: white; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 0.875rem; display: inline-block; transition: all 0.3s ease;">
                Withdraw from Event
            </a>
        </div>
    </div>
    '''

    no_matches_content = '''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        .no-matches-container {
            position: relative;
            width: 100%;
            min-height: 100vh;
            padding: 2rem 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            text-align: center;
            overflow: visible;
        }
        
        .canvas-container {
            width: 200px;
            height: 200px;
            margin: 3rem auto 2rem auto;
            z-index: 2;
        }
        
        #cube-canvas {
            width: 100%;
            height: 100%;
            cursor: grab;
        }
        
        #cube-canvas:active {
            cursor: grabbing;
        }
        
        .content-overlay {
            position: relative;
            z-index: 1;
            max-width: 600px;
            padding: 2rem;
        }
        
        .no-matches-title {
            font-family: "Sentient", sans-serif;
            font-size: clamp(2rem, 6vw, 3rem);
            font-weight: 500;
            color: black;
            margin-bottom: 1rem;
            background: white;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .no-matches-subtitle {
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            color: black;
            margin-bottom: 2rem;
            line-height: 1.6;
        }
        
        .reasons-list {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            padding: 1.5rem;
            margin: 2rem auto;
            text-align: left;
            max-width: 400px;
        }
        
        .reason-item {
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            margin: 0.75rem 0;
            font-family: "Satoshi", sans-serif;
            font-size: 0.9rem;
            color: black;
        }
        
        .reason-bullet {
            width: 6px;
            height: 6px;
            background: white;
            border-radius: 50%;
            flex-shrink: 0;
            margin-top: 0.5rem;
        }
        
        .btn-update {
            font-family: "Satoshi", sans-serif;
            background: white;
            color: #ffffff;
            padding: 1rem 2rem;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.875rem;
            transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 2rem;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            display: inline-block;
        }
        
        .btn-update:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.4);
        }
        
        
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        
        /* Responsive design */
        @media (max-width: 768px) {
            .canvas-container {
                width: 150px;
                height: 150px;
            }
            
            .content-overlay {
                padding: 1rem;
            }
            
            .reasons-list {
                max-width: 100%;
                padding: 1.25rem;
            }
            
            
        }
    </style>
    
    <!-- Include required libraries -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    
    <div class="no-matches-container">
        <div class="canvas-container">
            <canvas id="cube-canvas"></canvas>
        </div>
        
        <div class="content-overlay">
            <h1 class="no-matches-title">No matches found yet</h1>
            <p class="no-matches-subtitle">Your agent didn't match with anyone just yet</p>
            
            <div class="reasons-list">
                <div class="reason-item">
                    <div class="reason-bullet"></div>
                    <span>Your preferences are very specific</span>
                </div>
                <div class="reason-item">
                    <div class="reason-bullet"></div>
                    <span>More users are joining daily</span>
                </div>
            </div>
            
            <p class="no-matches-subtitle">
                Try updating your profile by clicking the cube or check back later
            </p>
            
        </div>
        
    </div>
    
    <script>
        // Scene setup
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        camera.position.z = 3;

        const canvas = document.querySelector("#cube-canvas");
        const renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            alpha: true
        });
        renderer.setSize(200, 200);
        renderer.setPixelRatio(window.devicePixelRatio);

        // Create cube with teal wireframe
        const cubeGeometry = new THREE.BoxGeometry(1.5, 1.5, 1.5);
        const cubeMaterial = new THREE.MeshBasicMaterial({ 
            color: 0x000000, 
            transparent: true, 
            opacity: 0 
        });
        const cube = new THREE.Mesh(cubeGeometry, cubeMaterial);

        // Add wireframe edges
        const edges = new THREE.EdgesGeometry(cubeGeometry);
        const lineMaterial = new THREE.LineBasicMaterial({ 
            color: 0x6b9b99,
            linewidth: 2
        });
        const wireframe = new THREE.LineSegments(edges, lineMaterial);
        cube.add(wireframe);

        // Create orange sphere inside
        const sphereGeometry = new THREE.SphereGeometry(0.3, 16, 16);
        const sphereMaterial = new THREE.MeshPhongMaterial({ 
            color: 0xff9500,
            shininess: 30
        });
        const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
        cube.add(sphere);

        scene.add(cube);

        // Lighting for the sphere
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        
        const pointLight = new THREE.PointLight(0xffffff, 0.8);
        pointLight.position.set(2, 2, 2);
        scene.add(pointLight);

        // Mouse interaction variables
        let isDragging = false;
        let previousMousePosition = { x: 0, y: 0 };
        let isClicked = false;

        // Auto rotation
        function autoRotate() {
            if (!isDragging) {
                cube.rotation.x += 0.005;
                cube.rotation.y += 0.008;
                
                // Gentle floating for the inner sphere
                const time = Date.now() * 0.003;
                sphere.position.y = Math.sin(time) * 0.1;
            }
        }

        // Mouse event handlers
        function onMouseDown(event) {
            isDragging = true;
            canvas.style.cursor = 'grabbing';
            
            const rect = canvas.getBoundingClientRect();
            previousMousePosition = {
                x: event.clientX - rect.left,
                y: event.clientY - rect.top
            };
        }

        function onMouseMove(event) {
            if (!isDragging) return;

            const rect = canvas.getBoundingClientRect();
            const currentMousePosition = {
                x: event.clientX - rect.left,
                y: event.clientY - rect.top
            };

            const deltaMove = {
                x: currentMousePosition.x - previousMousePosition.x,
                y: currentMousePosition.y - previousMousePosition.y
            };

            const deltaRotationQuaternion = new THREE.Quaternion()
                .setFromEuler(new THREE.Euler(
                    toRadians(deltaMove.y * 0.5),
                    toRadians(deltaMove.x * 0.5),
                    0,
                    'XYZ'
                ));

            cube.quaternion.multiplyQuaternions(deltaRotationQuaternion, cube.quaternion);

            previousMousePosition = currentMousePosition;
        }

        function onMouseUp() {
            isDragging = false;
            canvas.style.cursor = 'grab';
        }

        function onClick(event) {
            if (!isClicked) {
                isClicked = true;
                
                // Scale animation on click
                const originalScale = { x: 1, y: 1, z: 1 };
                const targetScale = { x: 0.8, y: 0.8, z: 0.8 };
                
                animateScale(cube.scale, targetScale, 100, () => {
                    animateScale(cube.scale, { x: 1.1, y: 1.1, z: 1.1 }, 100, () => {
                        animateScale(cube.scale, originalScale, 100, () => {
                            window.location.href = '/choose-agent';
                        });
                    });
                });
            }
        }

        // Simple scale animation function
        function animateScale(object, target, duration, callback) {
            const start = { x: object.x, y: object.y, z: object.z };
            const startTime = Date.now();
            
            function update() {
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                object.x = start.x + (target.x - start.x) * progress;
                object.y = start.y + (target.y - start.y) * progress;
                object.z = start.z + (target.z - start.z) * progress;
                
                if (progress < 1) {
                    requestAnimationFrame(update);
                } else if (callback) {
                    callback();
                }
            }
            
            update();
        }

        function toRadians(angle) {
            return angle * (Math.PI / 180);
        }

        // Add event listeners
        canvas.addEventListener('mousedown', onMouseDown);
        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('mouseleave', onMouseUp);
        canvas.addEventListener('click', onClick);

        // Animation loop
        function animate() {
            requestAnimationFrame(animate);
            autoRotate();
            renderer.render(scene, camera);
        }

        animate();

        // Handle window resize
        window.addEventListener('resize', () => {
            const containerSize = window.innerWidth < 768 ? 150 : 200;
            renderer.setSize(containerSize, containerSize);
            
            const container = document.querySelector('.canvas-container');
            container.style.width = containerSize + 'px';
            container.style.height = containerSize + 'px';
        });
    </script>
    '''

    # Combine event header with no matches content
    # Insert event header at the beginning of no matches content after the opening div
    content_start = no_matches_content.find('<div class="no-matches-container">') + len('<div class="no-matches-container">')

    if content_start > len('<div class="no-matches-container">') - 1:
        final_content = (
            no_matches_content[:content_start] +
            event_header +
            no_matches_content[content_start:]
        )
    else:
        # Fallback if structure is different
        final_content = event_header + no_matches_content

    return final_content

def render_new_profile_dashboard() -> str:
    """Render dashboard for new users without profile"""
    return '''
    <div class="container">
        <div style="text-align: center; margin-bottom: 40px; padding: 30px; background: #f4f2eb; border-radius: 15px; border: 2px solid black;">
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
            <a href="/choose-agent" class="btn btn-primary" style="padding: 16px 32px; font-size: 16px;">
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
# ROUTES - ORGANIZATION & SIMULATION MANAGEMENT
# ============================================================================

@app.route('/create-organization', methods=['GET', 'POST'])
@login_required
def create_organization():
    """Create a new organization"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    if request.method == 'POST':
        org_name = request.form.get('org_name', '').strip()
        org_description = request.form.get('org_description', '').strip()

        if not org_name:
            flash('Organization name is required', 'error')
            return redirect('/create-organization')

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Generate unique invite token
            invite_token = secrets.token_urlsafe(16)

            # Create organization
            cursor.execute('''
                INSERT INTO organizations (name, description, created_by, invite_token)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (org_name, org_description, user_id, invite_token))

            org_id = cursor.fetchone()['id']

            # Add creator as first member with 'owner' role
            cursor.execute('''
                INSERT INTO organization_members (organization_id, user_id, role)
                VALUES (%s, %s, 'owner')
            ''', (org_id, user_id))

            conn.commit()
            conn.close()

            flash(f'Organization "{org_name}" created successfully!', 'success')
            return redirect(f'/organization/{org_id}')

        except Exception as e:
            print(f"Error creating organization: {e}")
            flash('Error creating organization. Please try again.', 'error')
            return redirect('/create-organization')

    # GET request - show form
    content = '''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        .create-org-container {
            max-width: 700px;
            margin: 0 auto;
            padding: 2rem;
            min-height: 80vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .org-header {
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .org-title {
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: black;
            letter-spacing: -0.02em;
        }

        .org-subtitle {
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            line-height: 1.6;
            color: black;
            margin: 0;
        }

        .form-section {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 2.5rem;
            margin: 2rem 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-label {
            font-family: "Satoshi", sans-serif;
            display: block;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            opacity: 0.8;
            font-weight: 600;
            color: #2d2d2d;
        }

        .form-input, .form-textarea {
            font-family: "Satoshi", sans-serif;
            width: 100%;
            padding: 1rem 1.25rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            color: #2d2d2d;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }

        .form-input:focus, .form-textarea:focus {
            outline: none;
            border-color: rgba(107, 155, 153, 0.3);
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
        }

        .form-textarea {
            resize: vertical;
            min-height: 100px;
        }

        .btn {
            font-family: "Satoshi", sans-serif;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.875rem;
            text-decoration: none;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
            backdrop-filter: blur(10px);
        }

        .btn-primary {
            background: black;
            color: white;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }

        .action-buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            margin-top: 2rem;
        }
    </style>

    <div class="create-org-container">
        <div class="org-header">
            <h1 class="org-title">Create Your Organization</h1>
            <p class="org-subtitle">Start by setting up your team or business organization</p>
        </div>

        <form method="POST" class="form-section">
            <div class="form-group">
                <label class="form-label">Organization Name</label>
                <input type="text" name="org_name" required
                       placeholder="e.g., Acme Corp, Marketing Team, Product Squad"
                       class="form-input">
            </div>

            <div class="form-group">
                <label class="form-label">Description (Optional)</label>
                <textarea name="org_description"
                          placeholder="Brief description of your organization or team..."
                          class="form-textarea"></textarea>
            </div>

            <div class="action-buttons">
                <button type="submit" class="btn btn-primary">
                    Create Organization
                </button>
            </div>
        </form>
    </div>
    '''

    return render_template_with_header("Create Organization", content, user_info)


@app.route('/join-organization-by-code', methods=['POST'])
@login_required
def join_organization_by_code():
    """Join organization by entering invite code/link"""
    user_id = session['user_id']
    invite_input = request.form.get('invite_code', '').strip()

    if not invite_input:
        flash('Please enter an invite code or link', 'error')
        return redirect('/dashboard')

    # Extract token from full URL or use as-is
    if '/' in invite_input:
        # It's a full URL, extract the token
        invite_token = invite_input.split('/')[-1]
    else:
        invite_token = invite_input

    # Redirect to the join-organization handler
    return redirect(f'/join-organization/{invite_token}')


@app.route('/join-organization/<invite_token>')
def join_organization(invite_token):
    """Join an organization via invite link"""
    # Check if user is logged in
    if 'user_id' not in session:
        # Store invite token in session and redirect to register/login
        session['pending_org_invite'] = invite_token
        flash('Please sign up or log in to join this organization', 'info')
        return redirect('/register')

    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    # Check if user has completed profile
    if not user_info.get('profile_completed', False):
        # Store invite token and redirect to onboarding
        session['pending_org_invite'] = invite_token
        flash('Please complete your profile first', 'info')
        return redirect('/onboarding/step/1')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Find organization by invite token
        cursor.execute('''
            SELECT id, name, description FROM organizations
            WHERE invite_token = %s AND is_active = TRUE
        ''', (invite_token,))

        org = cursor.fetchone()

        if not org:
            conn.close()
            flash('Invalid or expired invite link', 'error')
            return redirect('/dashboard')

        # Check if user is already a member
        cursor.execute('''
            SELECT id FROM organization_members
            WHERE organization_id = %s AND user_id = %s
        ''', (org['id'], user_id))

        if cursor.fetchone():
            conn.close()
            flash(f'You are already a member of {org["name"]}', 'info')
            return redirect(f'/organization/{org["id"]}')

        # Add user to organization
        cursor.execute('''
            INSERT INTO organization_members (organization_id, user_id, role)
            VALUES (%s, %s, 'member')
        ''', (org['id'], user_id))

        conn.commit()
        conn.close()

        # Clear pending invite from session
        session.pop('pending_org_invite', None)

        flash(f'Successfully joined {org["name"]}!', 'success')
        return redirect(f'/organization/{org["id"]}')

    except Exception as e:
        print(f"Error joining organization: {e}")
        flash('Error joining organization. Please try again.', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/leave')
@login_required
def leave_organization(org_id):
    """Leave an organization"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is a member
        cursor.execute('''
            SELECT o.created_by FROM organizations o
            INNER JOIN organization_members om ON o.id = om.organization_id
            WHERE o.id = %s AND om.user_id = %s
        ''', (org_id, user_id))

        result = cursor.fetchone()

        if not result:
            flash('You are not a member of this organization', 'error')
            conn.close()
            return redirect('/dashboard')

        # Don't allow owner to leave
        if result['created_by'] == user_id:
            flash('Owners cannot leave their organization. Delete it instead.', 'error')
            conn.close()
            return redirect('/dashboard')

        # Remove user from organization
        cursor.execute('''
            DELETE FROM organization_members
            WHERE organization_id = %s AND user_id = %s
        ''', (org_id, user_id))

        conn.commit()
        conn.close()

        flash('Successfully left the organization', 'success')
        return redirect('/dashboard')

    except Exception as e:
        print(f"Error leaving organization: {e}")
        flash('Error leaving organization', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_organization(org_id):
    """Edit organization (owner only)"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is the owner
        cursor.execute('''
            SELECT id, name, description, created_by
            FROM organizations
            WHERE id = %s AND created_by = %s AND is_active = TRUE
        ''', (org_id, user_id))

        org = cursor.fetchone()

        if not org:
            conn.close()
            flash('Organization not found or you do not have permission', 'error')
            return redirect('/dashboard')

        if request.method == 'POST':
            new_name = request.form.get('org_name', '').strip()
            new_description = request.form.get('org_description', '').strip()

            if not new_name:
                flash('Organization name is required', 'error')
            else:
                cursor.execute('''
                    UPDATE organizations
                    SET name = %s, description = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_name, new_description, org_id))

                conn.commit()
                conn.close()

                flash('Organization updated successfully', 'success')
                return redirect('/dashboard')

        conn.close()

        # Show edit form
        user_info = user_auth.get_user_info(user_id)
        content = f'''
        <style>
            @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");
            /* Reuse create-org styles */
        </style>
        <div class="create-org-container" style="max-width: 700px; margin: 2rem auto; padding: 2rem;">
            <div class="org-header" style="text-align: center; margin-bottom: 2rem; padding: 2rem; background: rgba(255,255,255,0.9); border-radius: 20px;">
                <h1 style="font-family: 'Sentient', sans-serif; font-size: 2rem; color: black;">Edit Organization</h1>
            </div>
            <form method="POST" style="background: rgba(255,255,255,0.9); padding: 2rem; border-radius: 20px;">
                <div style="margin-bottom: 1.5rem;">
                    <label style="display: block; font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.5rem;">Organization Name</label>
                    <input type="text" name="org_name" value="{org['name']}" required
                           style="width: 100%; padding: 1rem; border: 1px solid #ddd; border-radius: 12px; font-size: 1rem; font-family: 'Satoshi', sans-serif; box-sizing: border-box;">
                </div>
                <div style="margin-bottom: 1.5rem;">
                    <label style="display: block; font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.5rem;">Description</label>
                    <textarea name="org_description" rows="4"
                           style="width: 100%; padding: 1rem; border: 1px solid #ddd; border-radius: 12px; font-size: 1rem; font-family: 'Satoshi', sans-serif; box-sizing: border-box;">{org['description'] or ''}</textarea>
                </div>
                <div style="display: flex; gap: 1rem;">
                    <button type="submit" style="flex: 1; padding: 1rem; background: black; color: white; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; font-family: 'Satoshi', sans-serif;">
                        Save Changes
                    </button>
                    <a href="/dashboard" style="flex: 1; padding: 1rem; background: white; color: black; border: 2px solid black; border-radius: 12px; font-weight: 600; text-decoration: none; text-align: center; font-family: 'Satoshi', sans-serif; display: block;">
                        Cancel
                    </a>
                </div>
            </form>
        </div>
        '''

        return render_template_with_header("Edit Organization", content, user_info)

    except Exception as e:
        print(f"Error editing organization: {e}")
        flash('Error loading organization', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/delete')
@login_required
def delete_organization(org_id):
    """Delete organization (owner only)"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is the owner
        cursor.execute('''
            SELECT created_by FROM organizations
            WHERE id = %s AND created_by = %s AND is_active = TRUE
        ''', (org_id, user_id))

        if not cursor.fetchone():
            conn.close()
            flash('Organization not found or you do not have permission', 'error')
            return redirect('/dashboard')

        # Soft delete - set is_active to false
        cursor.execute('''
            UPDATE organizations
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (org_id,))

        conn.commit()
        conn.close()

        flash('Organization deleted successfully', 'success')
        return redirect('/dashboard')

    except Exception as e:
        print(f"Error deleting organization: {e}")
        flash('Error deleting organization', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/embed-settings', methods=['GET', 'POST'])
@login_required
def organization_embed_settings(org_id):
    """Configure embed widget for organization (owner only)"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is the owner
        cursor.execute('''
            SELECT o.id, o.name, o.created_by
            FROM organizations o
            WHERE o.id = %s AND o.is_active = TRUE
        ''', (org_id,))

        org = cursor.fetchone()

        if not org or org['created_by'] != user_id:
            conn.close()
            flash('Organization not found or you do not have permission', 'error')
            return redirect('/dashboard')

        if request.method == 'POST':
            mode = request.form.get('mode')
            person_specification = request.form.get('person_specification', '').strip()
            use_linkedin = request.form.get('use_linkedin') == 'on'

            if mode not in ['party', 'simulation']:
                flash('Invalid mode selected', 'error')
                return redirect(f'/organization/{org_id}/embed-settings')

            # Check if embed config already exists
            cursor.execute('''
                SELECT id, embed_token FROM embed_configurations
                WHERE organization_id = %s
            ''', (org_id,))

            existing_config = cursor.fetchone()

            if existing_config:
                # Update existing config
                cursor.execute('''
                    UPDATE embed_configurations
                    SET mode = %s, person_specification = %s, use_linkedin = %s, is_active = TRUE
                    WHERE id = %s
                ''', (mode, person_specification if mode == 'simulation' else None, use_linkedin, existing_config['id']))
                embed_token = existing_config['embed_token']
            else:
                # Create new config
                embed_token = secrets.token_urlsafe(32)
                cursor.execute('''
                    INSERT INTO embed_configurations
                    (organization_id, embed_token, mode, person_specification, use_linkedin, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (org_id, embed_token, mode, person_specification if mode == 'simulation' else None, use_linkedin, user_id))

            conn.commit()
            flash('Embed settings saved successfully', 'success')

        # Get current embed configuration
        cursor.execute('''
            SELECT * FROM embed_configurations
            WHERE organization_id = %s
        ''', (org_id,))

        embed_config = cursor.fetchone()
        conn.close()

        # Render settings page
        content = render_embed_settings_page(org, embed_config, user_info)
        return render_template_with_header(f"Embed Settings - {org['name']}", content, user_info)

    except Exception as e:
        print(f"Error in embed settings: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading embed settings', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/applicants')
@login_required
def organization_applicants(org_id):
    """View applicants for organization"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is a member of the organization
        cursor.execute('''
            SELECT o.id, o.name, om.role
            FROM organizations o
            INNER JOIN organization_members om ON o.id = om.organization_id
            WHERE o.id = %s AND om.user_id = %s AND o.is_active = TRUE AND om.is_active = TRUE
        ''', (org_id, user_id))

        org = cursor.fetchone()

        if not org:
            conn.close()
            flash('Organization not found or you do not have access', 'error')
            return redirect('/dashboard')

        # Get all applicants for this organization
        cursor.execute('''
            SELECT
                id, full_name, email, linkedin_url,
                compatibility_results, behavioral_fit_analysis,
                status, created_at, application_token
            FROM applicants
            WHERE organization_id = %s
            ORDER BY created_at DESC
        ''', (org_id,))

        applicants = cursor.fetchall()

        # Parse compatibility results for each applicant
        for applicant in applicants:
            if applicant['compatibility_results']:
                try:
                    applicant['compatibility_data'] = json.loads(applicant['compatibility_results'])
                    # Calculate average score
                    scores = [m.get('compatibility_score', 0) for m in applicant['compatibility_data'].get('members', [])]
                    applicant['avg_score'] = sum(scores) / len(scores) if scores else 0
                except:
                    applicant['compatibility_data'] = {}
                    applicant['avg_score'] = 0

        conn.close()

        # Render applicants dashboard
        content = render_applicants_dashboard(org, applicants, user_info)
        return render_template_with_header(f"Applicants - {org['name']}", content, user_info)

    except Exception as e:
        print(f"Error loading applicants: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading applicants', 'error')
        return redirect('/dashboard')


@app.route('/organization/<int:org_id>/applicant/<int:applicant_id>')
@login_required
def view_applicant(org_id, applicant_id):
    """View detailed applicant profile"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is a member of the organization
        cursor.execute('''
            SELECT o.id, o.name, om.role
            FROM organizations o
            INNER JOIN organization_members om ON o.id = om.organization_id
            WHERE o.id = %s AND om.user_id = %s AND o.is_active = TRUE AND om.is_active = TRUE
        ''', (org_id, user_id))

        org = cursor.fetchone()

        if not org:
            conn.close()
            flash('Organization not found or you do not have access', 'error')
            return redirect('/dashboard')

        # Get applicant details
        cursor.execute('''
            SELECT
                id, full_name, email, linkedin_url,
                onboarding_data, compatibility_results, behavioral_fit_analysis,
                status, notes, created_at
            FROM applicants
            WHERE id = %s AND organization_id = %s
        ''', (applicant_id, org_id))

        applicant = cursor.fetchone()

        if not applicant:
            conn.close()
            flash('Applicant not found', 'error')
            return redirect(f'/organization/{org_id}/applicants')

        # Parse JSON data
        if applicant['onboarding_data']:
            applicant['onboarding'] = json.loads(applicant['onboarding_data'])
        if applicant['compatibility_results']:
            applicant['compatibility_data'] = json.loads(applicant['compatibility_results'])

        conn.close()

        # Render detailed applicant view
        content = render_applicant_detail(org, applicant, user_info)
        return render_template_with_header(f"{applicant['full_name']} - {org['name']}", content, user_info)

    except Exception as e:
        print(f"Error loading applicant: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading applicant', 'error')
        return redirect(f'/organization/{org_id}/applicants')


@app.route('/organization/<int:org_id>/applicant/<int:applicant_id>/update-status', methods=['POST'])
@login_required
def update_applicant_status(org_id, applicant_id):
    """Update applicant status"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user has permission (owner or member)
        cursor.execute('''
            SELECT om.role
            FROM organization_members om
            WHERE om.organization_id = %s AND om.user_id = %s AND om.is_active = TRUE
        ''', (org_id, user_id))

        member = cursor.fetchone()

        if not member:
            conn.close()
            return jsonify({'success': False, 'error': 'No permission'}), 403

        status = request.json.get('status')
        notes = request.json.get('notes', '')

        if status not in ['pending', 'reviewing', 'shortlisted', 'rejected', 'hired']:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid status'}), 400

        cursor.execute('''
            UPDATE applicants
            SET status = %s, notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND organization_id = %s
        ''', (status, notes, applicant_id, org_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating applicant status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def render_embed_settings_page(org: Dict, embed_config: Optional[Dict], user_info: Dict) -> str:
    """Render the embed settings configuration page"""

    current_mode = embed_config['mode'] if embed_config else 'party'
    person_spec = embed_config['person_specification'] if embed_config else ''
    embed_token = embed_config['embed_token'] if embed_config else None

    # Generate embed code if config exists
    embed_code_section = ''
    if embed_token:
        # Use production URL if in production, otherwise use request host
        base_url = os.environ.get('BASE_URL', '').rstrip('/')
        if not base_url or 'localhost' in base_url:
            # Fallback: use pont.world if BASE_URL is not set or is localhost
            if os.environ.get('FLASK_ENV') == 'production':
                base_url = 'https://pont.world'
            else:
                base_url = request.host_url.rstrip('/')

        embed_url = f"{base_url}/embed/{embed_token}"
        iframe_code = f'<iframe src="{embed_url}" width="100%" height="800" frameborder="0"></iframe>'

        # Escape quotes for JavaScript
        iframe_code_escaped = iframe_code.replace("'", "\\'")

        embed_code_section = f'''
        <div style="margin-top: 2rem; padding: 2rem; background: #f8f9fa; border-radius: 12px;">
            <h3 style="font-family: 'Sentient', sans-serif; font-size: 1.5rem; margin-bottom: 1rem;">Embed Code</h3>

            <div style="margin-bottom: 2rem;">
                <h4 style="font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.75rem;">For Websites (HTML)</h4>
                <p style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem; margin-bottom: 0.75rem;">
                    Copy and paste this code into your website's HTML:
                </p>
                <div style="background: white; padding: 1rem; border-radius: 8px; border: 1px solid #ddd; font-family: monospace; font-size: 0.875rem; overflow-x: auto; margin-bottom: 0.75rem; position: relative;">
                    <code id="htmlCode">{iframe_code}</code>
                </div>
                <button onclick="copyToClipboard('htmlCode')" id="copyHtmlBtn"
                        style="padding: 0.75rem 1.5rem; background: black; color: white; border: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; cursor: pointer;">
                    Copy HTML Code
                </button>
            </div>

            <div style="margin-bottom: 2rem;">
                <h4 style="font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.75rem;">For Notion</h4>
                <p style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem; margin-bottom: 0.75rem;">
                    1. Copy the URL below<br>
                    2. In Notion, type <code>/embed</code> and press Enter<br>
                    3. Paste the URL and click "Embed link"
                </p>
                <div style="background: white; padding: 1rem; border-radius: 8px; border: 1px solid #ddd; font-family: monospace; font-size: 0.875rem; overflow-x: auto; margin-bottom: 0.75rem;">
                    <code id="notionUrl">{embed_url}</code>
                </div>
                <button onclick="copyToClipboard('notionUrl')" id="copyNotionBtn"
                        style="padding: 0.75rem 1.5rem; background: black; color: white; border: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; cursor: pointer;">
                    Copy URL for Notion
                </button>
            </div>

            <div>
                <h4 style="font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.75rem;">Direct Link</h4>
                <p style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem;">
                    <a href="{embed_url}" target="_blank" style="color: #0066cc; text-decoration: underline;">{embed_url}</a>
                </p>
            </div>
        </div>

        <script>
            function copyToClipboard(elementId) {{
                const element = document.getElementById(elementId);
                const text = element.textContent;
                const buttonId = elementId === 'htmlCode' ? 'copyHtmlBtn' : 'copyNotionBtn';
                const button = document.getElementById(buttonId);
                const originalText = button.textContent;

                // Try modern clipboard API first
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(text).then(() => {{
                        button.textContent = '✓ Copied!';
                        button.style.background = '#10b981';

                        setTimeout(() => {{
                            button.textContent = originalText;
                            button.style.background = 'black';
                        }}, 2000);
                    }}).catch(err => {{
                        console.error('Clipboard API failed:', err);
                        fallbackCopy(text, button, originalText);
                    }});
                }} else {{
                    // Fallback for browsers without clipboard API
                    fallbackCopy(text, button, originalText);
                }}
            }}

            function fallbackCopy(text, button, originalText) {{
                // Create temporary textarea
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);

                try {{
                    textarea.select();
                    textarea.setSelectionRange(0, 99999); // For mobile devices

                    const successful = document.execCommand('copy');
                    if (successful) {{
                        button.textContent = '✓ Copied!';
                        button.style.background = '#10b981';

                        setTimeout(() => {{
                            button.textContent = originalText;
                            button.style.background = 'black';
                        }}, 2000);
                    }} else {{
                        alert('Copy failed. Please select and copy the code manually.');
                    }}
                }} catch (err) {{
                    console.error('Fallback copy failed:', err);
                    alert('Copy not supported. Please select and copy the code manually.');
                }} finally {{
                    document.body.removeChild(textarea);
                }}
            }}
        </script>
        '''

    party_checked = 'checked' if current_mode == 'party' else ''
    simulation_checked = 'checked' if current_mode == 'simulation' else ''
    person_spec_display = 'block' if current_mode == 'simulation' else 'none'
    use_linkedin = embed_config.get('use_linkedin', False) if embed_config else False
    linkedin_checked = 'checked' if use_linkedin else ''

    content = f'''
    <div style="max-width: 800px; margin: 0 auto; padding: 2rem;">
        <div style="margin-bottom: 2rem;">
            <a href="/organization/{org['id']}" style="color: #666; text-decoration: none; font-family: 'Satoshi', sans-serif;">
                ← Back to Organization
            </a>
        </div>

        <h2 style="font-family: 'Sentient', sans-serif; font-size: 2rem; margin-bottom: 1rem;">Embeddable Widget Settings</h2>
        <p style="font-family: 'Satoshi', sans-serif; color: #666; margin-bottom: 2rem;">
            Configure how your team assessment widget appears on your website or Notion page.
        </p>

        <form method="POST" style="background: white; padding: 2rem; border-radius: 12px; border: 1px solid #ddd;">
            <div style="margin-bottom: 2rem;">
                <label style="display: block; font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 1rem;">Widget Mode</label>

                <div style="margin-bottom: 1rem; padding: 1.5rem; border: 2px solid {'black' if current_mode == 'party' else '#ddd'}; border-radius: 12px; cursor: pointer;"
                     onclick="document.getElementById('mode_party').checked = true; togglePersonSpec();">
                    <label style="display: flex; align-items: start; cursor: pointer;">
                        <input type="radio" name="mode" id="mode_party" value="party" {party_checked}
                               onchange="togglePersonSpec()"
                               style="margin-right: 1rem; margin-top: 0.25rem;">
                        <div>
                            <div style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.125rem; margin-bottom: 0.5rem;">
                                Party Mode (Compatibility)
                            </div>
                            <div style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem;">
                                Shows the user how compatible they are with each team member. Perfect for recruiting, team building, or finding cultural fit.
                            </div>
                        </div>
                    </label>
                </div>

                <div style="margin-bottom: 1rem; padding: 1.5rem; border: 2px solid {'black' if current_mode == 'simulation' else '#ddd'}; border-radius: 12px; cursor: pointer;"
                     onclick="document.getElementById('mode_simulation').checked = true; togglePersonSpec();">
                    <label style="display: flex; align-items: start; cursor: pointer;">
                        <input type="radio" name="mode" id="mode_simulation" value="simulation" {simulation_checked}
                               onchange="togglePersonSpec()"
                               style="margin-right: 1rem; margin-top: 0.25rem;">
                        <div>
                            <div style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.125rem; margin-bottom: 0.5rem;">
                                Simulation Mode (Team Assessment)
                            </div>
                            <div style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem;">
                                Shows how each team member would engage with a specific type of person. Perfect for clinical teams, customer service, or client-facing roles.
                            </div>
                        </div>
                    </label>
                </div>
            </div>

            <div id="person_spec_section" style="margin-bottom: 2rem; display: {person_spec_display};">
                <label style="display: block; font-family: 'Satoshi', sans-serif; font-weight: 600; margin-bottom: 0.5rem;">
                    Person Specification
                </label>
                <p style="font-family: 'Satoshi', sans-serif; color: #666; font-size: 0.875rem; margin-bottom: 0.75rem;">
                    Describe the type of person entering your clinic/team (e.g., "new patient seeking therapy", "client requesting legal advice", "customer with a complaint")
                </p>
                <input type="text" name="person_specification" value="{person_spec}"
                       placeholder="e.g., new patient seeking therapy"
                       style="width: 100%; padding: 1rem; border: 1px solid #ddd; border-radius: 12px; font-size: 1rem; font-family: 'Satoshi', sans-serif; box-sizing: border-box;">
            </div>

            <div style="display: flex; gap: 1rem;">
                <button type="submit" style="flex: 1; padding: 1rem; background: black; color: white; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; font-family: 'Satoshi', sans-serif;">
                    Save & Generate Embed Code
                </button>
                <a href="/organization/{org['id']}" style="flex: 1; padding: 1rem; background: white; color: black; border: 2px solid black; border-radius: 12px; font-weight: 600; text-decoration: none; text-align: center; font-family: 'Satoshi', sans-serif; display: block;">
                    Cancel
                </a>
            </div>
        </form>

        {embed_code_section}

        <script>
            function togglePersonSpec() {{
                const simulationMode = document.getElementById('mode_simulation').checked;
                const personSpecSection = document.getElementById('person_spec_section');
                personSpecSection.style.display = simulationMode ? 'block' : 'none';
            }}
        </script>
    </div>
    '''

    return content


@app.route('/embed/<embed_token>')
def embed_widget(embed_token):
    """Public embed widget - no authentication required"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get embed configuration
        cursor.execute('''
            SELECT ec.*, o.name as org_name
            FROM embed_configurations ec
            INNER JOIN organizations o ON ec.organization_id = o.id
            WHERE ec.embed_token = %s AND ec.is_active = TRUE
        ''', (embed_token,))

        config = cursor.fetchone()
        conn.close()

        if not config:
            return "Invalid or inactive embed widget", 404

        # Render minimal onboarding questionnaire
        content = render_embed_onboarding(config)
        return content

    except Exception as e:
        print(f"Error loading embed widget: {e}")
        import traceback
        traceback.print_exc()
        return "Error loading widget", 500


@app.route('/embed/<embed_token>/process', methods=['POST'])
def embed_process(embed_token):
    """Process embed widget submission and return results"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get embed configuration
        cursor.execute('''
            SELECT ec.*, o.id as org_id, o.name as org_name
            FROM embed_configurations ec
            INNER JOIN organizations o ON ec.organization_id = o.id
            WHERE ec.embed_token = %s AND ec.is_active = TRUE
        ''', (embed_token,))

        config = cursor.fetchone()

        if not config:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid widget'}), 404

        # Get organization members and their profiles
        cursor.execute('''
            SELECT
                u.id, u.first_name, u.last_name,
                up.profile_data
            FROM organization_members om
            INNER JOIN users u ON om.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE om.organization_id = %s AND om.is_active = TRUE
        ''', (config['org_id'],))

        members = cursor.fetchall()

        # Collect onboarding data from form
        onboarding_data = {
            'full_name': request.form.get('full_name', ''),
            'email': request.form.get('email', ''),
            'linkedin_url': request.form.get('linkedin_url', ''),
            'age': request.form.get('age', ''),
            'location': request.form.get('location', ''),
            'defining_moment': request.form.get('defining_moment', ''),
            'resource_allocation': request.form.get('resource_allocation', ''),
            'conflict_response': request.form.get('conflict_response', ''),
            'trade_off': request.form.get('trade_off', ''),
            'social_identity': request.form.get('social_identity', ''),
            'moral_dilemma': request.form.get('moral_dilemma', ''),
            'system_trust': request.form.get('system_trust', ''),
            'stress_response': request.form.get('stress_response', ''),
            'future_values': request.form.get('future_values', '')
        }

        # Create session token
        session_token = secrets.token_urlsafe(32)

        # Save session data
        cursor.execute('''
            INSERT INTO embed_sessions (embed_config_id, session_token, onboarding_data)
            VALUES (%s, %s, %s)
            RETURNING id
        ''', (config['id'], session_token, json.dumps(onboarding_data)))

        session_id = cursor.fetchone()['id']
        conn.commit()

        # Run simulation based on mode
        if config['mode'] == 'party':
            # Party mode: compatibility between user and each team member
            results = run_embed_party_mode(onboarding_data, members, config)
        else:
            # Simulation mode: how team engages with this person specification
            results = run_embed_simulation_mode(onboarding_data, members, config)

        # Update session with results
        cursor.execute('''
            UPDATE embed_sessions
            SET results_data = %s
            WHERE id = %s
        ''', (json.dumps(results), session_id))

        # If in party mode (applicant assessment), also create an applicant record
        applicant_id = None
        if config['mode'] == 'party' and onboarding_data.get('full_name') and onboarding_data.get('email'):
            # Generate behavioral fit analysis
            behavioral_fit = generate_behavioral_fit_analysis(onboarding_data, results, members)

            # Create applicant record
            application_token = secrets.token_urlsafe(32)
            cursor.execute('''
                INSERT INTO applicants (
                    organization_id, embed_session_id, full_name, email, linkedin_url,
                    application_token, onboarding_data, compatibility_results, behavioral_fit_analysis
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                config['org_id'], session_id, onboarding_data['full_name'],
                onboarding_data['email'], onboarding_data.get('linkedin_url', ''),
                application_token, json.dumps(onboarding_data), json.dumps(results),
                behavioral_fit
            ))
            applicant_id = cursor.fetchone()['id']

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'session_token': session_token,
            'applicant_id': applicant_id,
            'results': results
        })

    except Exception as e:
        print(f"Error processing embed widget: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def generate_behavioral_fit_analysis(user_data: Dict, compatibility_results: Dict, members: List[Dict]) -> str:
    """Generate comprehensive behavioral fit analysis for applicant"""
    client = OpenAI(api_key=API_KEY)

    # Extract key patterns from compatibility results
    all_scores = []
    strengths_list = []
    challenges_list = []

    for member_result in compatibility_results.get('members', []):
        if 'compatibility_score' in member_result:
            all_scores.append(member_result['compatibility_score'])
        if 'strengths' in member_result:
            strengths_list.extend(member_result['strengths'])
        if 'challenges' in member_result:
            challenges_list.extend(member_result['challenges'])

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

    prompt = f"""You are an expert organizational psychologist analyzing a candidate's behavioral fit with a team.

Candidate Profile:
- Defining Moment: {user_data.get('defining_moment', 'N/A')}
- Resource Allocation: {user_data.get('resource_allocation', 'N/A')}
- Conflict Response: {user_data.get('conflict_response', 'N/A')}
- Trade-off Decisions: {user_data.get('trade_off', 'N/A')}
- Social Identity: {user_data.get('social_identity', 'N/A')}
- Moral Compass: {user_data.get('moral_dilemma', 'N/A')}
- System Trust: {user_data.get('system_trust', 'N/A')}
- Stress Response: {user_data.get('stress_response', 'N/A')}
- Future Values: {user_data.get('future_values', 'N/A')}

Team Compatibility Analysis:
- Average compatibility score: {avg_score:.1f}/100
- Number of team members analyzed: {len(members)}
- Common strengths identified: {', '.join(set(strengths_list[:5]))}
- Common challenges identified: {', '.join(set(challenges_list[:5]))}

Provide a comprehensive behavioral fit analysis covering:
1. **Core Behavioral Traits**: What are the candidate's primary behavioral patterns based on their responses?
2. **Team Dynamics Fit**: How would this person mesh with the team's existing dynamics?
3. **Communication Style**: How does the candidate communicate and process information?
4. **Collaboration Potential**: Strengths and challenges in working with this team
5. **Cultural Add**: What unique perspective or value would this person bring?
6. **Risk Factors**: Any potential areas of concern or friction
7. **Recommendations**: How to best onboard and integrate this person

Write a detailed analysis (300-500 words) that helps the team understand if this is a good behavioral fit."""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating behavioral fit analysis: {e}")
        return f"Behavioral fit analysis unavailable. Average compatibility score: {avg_score:.1f}/100"


def run_embed_party_mode(user_data: Dict, members: List[Dict], config: Dict) -> Dict:
    """Run party mode for embed widget - analyze compatibility between user and team"""
    client = OpenAI(api_key=API_KEY)

    # Create user profile summary from onboarding
    user_summary = f"""
User Profile Summary:
Name: {user_data.get('full_name', 'N/A')}
Age: {user_data.get('age', 'N/A')}
Location: {user_data.get('location', 'N/A')}
LinkedIn: {user_data.get('linkedin_url', 'N/A')}

- Defining Moment: {user_data.get('defining_moment', 'N/A')}
- Resource Allocation: {user_data.get('resource_allocation', 'N/A')}
- Conflict Response: {user_data.get('conflict_response', 'N/A')}
- Trade-off: {user_data.get('trade_off', 'N/A')}
- Social Identity: {user_data.get('social_identity', 'N/A')}
- Moral Dilemma: {user_data.get('moral_dilemma', 'N/A')}
- System Trust: {user_data.get('system_trust', 'N/A')}
- Stress Response: {user_data.get('stress_response', 'N/A')}
- Future Values: {user_data.get('future_values', 'N/A')}
"""

    results = {'members': []}

    for member in members:
        member_name = f"{member['first_name']} {member['last_name']}"
        member_profile = {}

        if member.get('profile_data'):
            try:
                member_profile = json.loads(member['profile_data'])
            except:
                pass

        # Create member profile summary
        member_summary = f"""
Team Member: {member_name}
{member_profile.get('agent_onboarding_script', 'Profile not available')}
"""

        prompt = f"""You are analyzing compatibility between a potential new person and an existing team member.

{user_summary}

{member_summary}

Analyze the compatibility between this person and {member_name}. Focus on:
1. Communication style compatibility
2. Value alignment
3. Work style compatibility
4. Potential synergies
5. Potential friction points

Return your analysis as JSON with this structure:
{{
    "compatibility_score": <0-100>,
    "summary": "<brief 2-3 sentence overview>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "challenges": ["<challenge 1>", "<challenge 2>"],
    "recommendation": "<overall recommendation>"
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            analysis = json.loads(response.choices[0].message.content)
            results['members'].append({
                'name': member_name,
                'analysis': analysis
            })

        except Exception as e:
            print(f"Error analyzing compatibility for {member_name}: {e}")
            results['members'].append({
                'name': member_name,
                'analysis': {
                    'compatibility_score': 50,
                    'summary': 'Analysis unavailable',
                    'strengths': [],
                    'challenges': [],
                    'recommendation': 'Unable to complete analysis'
                }
            })

    return results


def run_embed_simulation_mode(user_data: Dict, members: List[Dict], config: Dict) -> Dict:
    """Run simulation mode for embed widget - analyze how team would engage with this person"""
    client = OpenAI(api_key=API_KEY)

    person_spec = config.get('person_specification', 'new person')

    # Create person profile from onboarding
    person_profile = f"""
A {person_spec} with the following characteristics:
Name: {user_data.get('full_name', 'N/A')}
Age: {user_data.get('age', 'N/A')}
Location: {user_data.get('location', 'N/A')}
LinkedIn: {user_data.get('linkedin_url', 'N/A')}

- Defining Moment: {user_data.get('defining_moment', 'N/A')}
- Resource Allocation: {user_data.get('resource_allocation', 'N/A')}
- Conflict Response: {user_data.get('conflict_response', 'N/A')}
- Trade-off: {user_data.get('trade_off', 'N/A')}
- Social Identity: {user_data.get('social_identity', 'N/A')}
- Moral Dilemma: {user_data.get('moral_dilemma', 'N/A')}
- System Trust: {user_data.get('system_trust', 'N/A')}
- Stress Response: {user_data.get('stress_response', 'N/A')}
- Future Values: {user_data.get('future_values', 'N/A')}
"""

    results = {'members': []}

    for member in members:
        member_name = f"{member['first_name']} {member['last_name']}"
        member_profile = {}

        if member.get('profile_data'):
            try:
                member_profile = json.loads(member['profile_data'])
            except:
                pass

        # Create member profile summary
        member_summary = f"""
Team Member: {member_name}
{member_profile.get('agent_onboarding_script', 'Profile not available')}
"""

        prompt = f"""You are analyzing how a team member would engage with a specific type of person.

{person_profile}

{member_summary}

Analyze how {member_name} would engage with this {person_spec}. Consider:
1. Their natural approach and interaction style
2. Strengths they would bring to this engagement
3. Potential challenges or blind spots
4. Quality of the therapeutic/professional relationship
5. Overall effectiveness

Return your analysis as JSON with this structure:
{{
    "engagement_style": "<description of how they would approach>",
    "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
    "challenges": ["<challenge 1>", "<challenge 2>"],
    "relationship_quality": "<assessment of relationship dynamics>",
    "effectiveness_score": <0-100>,
    "recommendation": "<overall assessment>"
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            analysis = json.loads(response.choices[0].message.content)
            results['members'].append({
                'name': member_name,
                'analysis': analysis
            })

        except Exception as e:
            print(f"Error analyzing engagement for {member_name}: {e}")
            results['members'].append({
                'name': member_name,
                'analysis': {
                    'engagement_style': 'Analysis unavailable',
                    'strengths': [],
                    'challenges': [],
                    'relationship_quality': 'Unable to assess',
                    'effectiveness_score': 50,
                    'recommendation': 'Unable to complete analysis'
                }
            })

    return results


def render_applicants_dashboard(org: Dict, applicants: List[Dict], user_info: Dict) -> str:
    """Render the applicants dashboard for an organization"""

    applicants_html = ''
    if applicants:
        for applicant in applicants:
            avg_score = applicant.get('avg_score', 0)
            status_color = {
                'pending': '#fbbf24',
                'reviewing': '#3b82f6',
                'shortlisted': '#10b981',
                'rejected': '#ef4444',
                'hired': '#8b5cf6'
            }.get(applicant['status'], '#6b7280')

            applicants_html += f'''
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
                    <div style="flex-grow: 1;">
                        <h3 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.25rem; margin-bottom: 0.5rem;">
                            <a href="/organization/{org['id']}/applicant/{applicant['id']}" style="color: black; text-decoration: none;">
                                {applicant['full_name']}
                            </a>
                        </h3>
                        <p style="font-family: 'Satoshi', sans-serif; color: #6b7280; font-size: 0.875rem;">
                            {applicant['email']}
                            {f" • <a href='{applicant['linkedin_url']}' target='_blank' style='color: #0066cc;'>LinkedIn</a>" if applicant.get('linkedin_url') else ''}
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <div style="display: inline-block; padding: 0.5rem 1rem; background: {status_color}; color: white; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 0.875rem; margin-bottom: 0.5rem;">
                            {applicant['status'].capitalize()}
                        </div>
                        <div style="font-family: 'Satoshi', sans-serif; font-size: 0.875rem; color: #6b7280;">
                            Applied {applicant['created_at'].strftime('%b %d, %Y') if hasattr(applicant['created_at'], 'strftime') else applicant['created_at']}
                        </div>
                    </div>
                </div>

                <div style="display: flex; gap: 1rem; align-items: center;">
                    <div style="flex-grow: 1; background: #f3f4f6; border-radius: 8px; height: 8px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #ef4444, #fbbf24, #10b981); width: {avg_score}%; height: 100%;"></div>
                    </div>
                    <div style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.125rem; min-width: 60px; text-align: right;">
                        {avg_score:.0f}/100
                    </div>
                </div>

                <div style="margin-top: 1rem;">
                    <a href="/organization/{org['id']}/applicant/{applicant['id']}"
                       style="display: inline-block; padding: 0.75rem 1.5rem; background: black; color: white; text-decoration: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 0.875rem;">
                        View Full Analysis →
                    </a>
                </div>
            </div>
            '''
    else:
        applicants_html = f'''
        <div style="text-align: center; padding: 4rem 2rem; background: #f9fafb; border-radius: 12px; border: 2px dashed #d1d5db;">
            <p style="font-family: 'Satoshi', sans-serif; font-size: 1.125rem; color: #6b7280; margin-bottom: 1rem;">
                No applicants yet
            </p>
            <p style="font-family: 'Satoshi', sans-serif; color: #9ca3af; font-size: 0.875rem;">
                Share your widget to start receiving applications
            </p>
            <a href="/organization/{org['id']}/embed-settings"
               style="display: inline-block; margin-top: 1.5rem; padding: 0.75rem 1.5rem; background: black; color: white; text-decoration: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600;">
                Configure Widget
            </a>
        </div>
        '''

    content = f'''
    <div style="max-width: 1200px; margin: 0 auto; padding: 2rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
            <div>
                <a href="/organization/{org['id']}" style="color: #6b7280; text-decoration: none; font-family: 'Satoshi', sans-serif; display: block; margin-bottom: 0.5rem;">
                    ← Back to {org['name']}
                </a>
                <h2 style="font-family: 'Sentient', sans-serif; font-size: 2rem; margin: 0;">
                    Applicants
                </h2>
            </div>
            <div>
                <a href="/organization/{org['id']}/embed-settings"
                   style="display: inline-block; padding: 0.75rem 1.5rem; background: white; border: 2px solid black; color: black; text-decoration: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; margin-right: 1rem;">
                    Widget Settings
                </a>
            </div>
        </div>

        {applicants_html}
    </div>
    '''

    return content


def render_applicant_detail(org: Dict, applicant: Dict, user_info: Dict) -> str:
    """Render detailed applicant profile view"""

    # Extract compatibility data
    compatibility_html = ''
    if applicant.get('compatibility_data'):
        for member in applicant['compatibility_data'].get('members', []):
            score = member.get('compatibility_score', 0)
            score_color = '#10b981' if score >= 75 else '#fbbf24' if score >= 50 else '#ef4444'

            strengths_html = ''.join([f"<li>{s}</li>" for s in member.get('strengths', [])])
            challenges_html = ''.join([f"<li>{c}</li>" for c in member.get('challenges', [])])

            compatibility_html += f'''
            <div style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h4 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.125rem; margin: 0;">
                        {member.get('member_name', 'Team Member')}
                    </h4>
                    <div style="font-family: 'Satoshi', sans-serif; font-weight: 700; font-size: 1.5rem; color: {score_color};">
                        {score}/100
                    </div>
                </div>

                <div style="margin-bottom: 1rem;">
                    <div style="background: #f3f4f6; border-radius: 8px; height: 8px; overflow: hidden;">
                        <div style="background: {score_color}; width: {score}%; height: 100%;"></div>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem;">
                    <div>
                        <h5 style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #10b981; margin-bottom: 0.5rem;">Strengths</h5>
                        <ul style="font-family: 'Satoshi', sans-serif; font-size: 0.875rem; color: #4b5563; margin: 0; padding-left: 1.25rem;">
                            {strengths_html}
                        </ul>
                    </div>
                    <div>
                        <h5 style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #f59e0b; margin-bottom: 0.5rem;">Challenges</h5>
                        <ul style="font-family: 'Satoshi', sans-serif; font-size: 0.875rem; color: #4b5563; margin: 0; padding-left: 1.25rem;">
                            {challenges_html}
                        </ul>
                    </div>
                </div>
            </div>
            '''

    # Extract onboarding responses
    onboarding = applicant.get('onboarding', {})
    responses_html = f'''
    <div style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.25rem; margin-bottom: 1rem;">Profile Responses</h3>
        <div style="display: grid; gap: 1rem;">
            <div>
                <p style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #6b7280; font-size: 0.875rem; margin-bottom: 0.25rem;">Defining Moment</p>
                <p style="font-family: 'Satoshi', sans-serif; color: #1f2937; margin: 0;">{onboarding.get('defining_moment', 'N/A')}</p>
            </div>
            <div>
                <p style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #6b7280; font-size: 0.875rem; margin-bottom: 0.25rem;">Conflict Response</p>
                <p style="font-family: 'Satoshi', sans-serif; color: #1f2937; margin: 0;">{onboarding.get('conflict_response', 'N/A')}</p>
            </div>
            <div>
                <p style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #6b7280; font-size: 0.875rem; margin-bottom: 0.25rem;">Stress Response</p>
                <p style="font-family: 'Satoshi', sans-serif; color: #1f2937; margin: 0;">{onboarding.get('stress_response', 'N/A')}</p>
            </div>
            <div>
                <p style="font-family: 'Satoshi', sans-serif; font-weight: 600; color: #6b7280; font-size: 0.875rem; margin-bottom: 0.25rem;">Future Values</p>
                <p style="font-family: 'Satoshi', sans-serif; color: #1f2937; margin: 0;">{onboarding.get('future_values', 'N/A')}</p>
            </div>
        </div>
    </div>
    '''

    # Status update section
    status_options = ['pending', 'reviewing', 'shortlisted', 'rejected', 'hired']
    status_select = ''.join([
        f"<option value='{s}' {'selected' if s == applicant['status'] else ''}>{s.capitalize()}</option>"
        for s in status_options
    ])

    content = f'''
    <div style="max-width: 1200px; margin: 0 auto; padding: 2rem;">
        <div style="margin-bottom: 2rem;">
            <a href="/organization/{org['id']}/applicants" style="color: #6b7280; text-decoration: none; font-family: 'Satoshi', sans-serif;">
                ← Back to Applicants
            </a>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 2rem;">
            <div>
                <h2 style="font-family: 'Sentient', sans-serif; font-size: 2rem; margin-bottom: 0.5rem;">
                    {applicant['full_name']}
                </h2>
                <p style="font-family: 'Satoshi', sans-serif; color: #6b7280; margin: 0;">
                    {applicant['email']}
                    {f" • <a href='{applicant['linkedin_url']}' target='_blank' style='color: #0066cc;'>LinkedIn Profile</a>" if applicant.get('linkedin_url') else ''}
                </p>
            </div>
            <div style="min-width: 200px;">
                <label style="display: block; font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 0.875rem; margin-bottom: 0.5rem;">Status</label>
                <select id="statusSelect" onchange="updateStatus()"
                        style="width: 100%; padding: 0.75rem; border: 1px solid #d1d5db; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                    {status_select}
                </select>
            </div>
        </div>

        <div style="background: #f0f9ff; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem;">
            <h3 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.125rem; margin-bottom: 1rem;">Behavioral Fit Analysis</h3>
            <div style="font-family: 'Satoshi', sans-serif; color: #1f2937; line-height: 1.6; white-space: pre-wrap;">
                {applicant.get('behavioral_fit_analysis', 'Analysis not available')}
            </div>
        </div>

        <h3 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.5rem; margin-bottom: 1rem;">Team Compatibility Breakdown</h3>
        {compatibility_html}

        {responses_html}

        <div style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem;">
            <h3 style="font-family: 'Satoshi', sans-serif; font-weight: 600; font-size: 1.25rem; margin-bottom: 1rem;">Notes</h3>
            <textarea id="notesTextarea"
                      style="width: 100%; min-height: 120px; padding: 1rem; border: 1px solid #d1d5db; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-size: 1rem; resize: vertical;"
                      placeholder="Add notes about this applicant...">{applicant.get('notes', '')}</textarea>
            <button onclick="saveNotes()"
                    style="margin-top: 1rem; padding: 0.75rem 1.5rem; background: black; color: white; border: none; border-radius: 8px; font-family: 'Satoshi', sans-serif; font-weight: 600; cursor: pointer;">
                Save Notes
            </button>
        </div>
    </div>

    <script>
        function updateStatus() {{
            const status = document.getElementById('statusSelect').value;
            const notes = document.getElementById('notesTextarea').value;

            fetch('/organization/{org['id']}/applicant/{applicant['id']}/update-status', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ status: status, notes: notes }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Status updated successfully');
                }} else {{
                    alert('Error updating status: ' + data.error);
                }}
            }});
        }}

        function saveNotes() {{
            const status = document.getElementById('statusSelect').value;
            const notes = document.getElementById('notesTextarea').value;

            fetch('/organization/{org['id']}/applicant/{applicant['id']}/update-status', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ status: status, notes: notes }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Notes saved successfully');
                }} else {{
                    alert('Error saving notes: ' + data.error);
                }}
            }});
        }}
    </script>
    '''

    return content


def render_embed_onboarding(config: Dict) -> str:
    """Render minimal onboarding questionnaire for embed widget"""

    mode_description = ""
    if config['mode'] == 'party':
        mode_description = "Answer these questions to see how compatible you are with our team members."
    else:
        person_spec = config.get('person_specification', 'a person')
        mode_description = f"Answer these questions as if you are {person_spec} to see how our team would engage with you."

    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{config['org_name']} - Team Assessment</title>
    <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: "Satoshi", sans-serif;
            background: white;
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 700px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 3rem;
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }}

        h1 {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 2.5rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
            color: black;
            letter-spacing: -0.02em;
        }}

        .subtitle {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            line-height: 1.6;
            color: black;
            opacity: 0.8;
            margin-bottom: 2rem;
        }}

        .question {{
            margin-bottom: 2rem;
        }}

        .question-label {{
            font-family: "Satoshi", sans-serif;
            display: block;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.75rem;
            opacity: 0.8;
            font-weight: 600;
            color: #2d2d2d;
        }}

        .question-description {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
            color: #666;
            margin-bottom: 0.75rem;
            line-height: 1.5;
        }}

        input, textarea {{
            font-family: "Satoshi", sans-serif;
            width: 100%;
            padding: 1rem 1.25rem;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 16px;
            color: #2d2d2d;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }}

        textarea {{
            resize: vertical;
            min-height: 120px;
        }}

        input:focus, textarea:focus {{
            outline: none;
            border-color: rgba(107, 155, 153, 0.3);
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(107, 155, 153, 0.15);
        }}

        .submit-btn {{
            width: 100%;
            padding: 1.25rem;
            background: black;
            color: white;
            border: none;
            border-radius: 16px;
            font-family: "Satoshi", sans-serif;
            font-weight: 600;
            font-size: 1.125rem;
            cursor: pointer;
            transition: all 0.3s ease;
        }}

        .submit-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        }}

        .submit-btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        .results {{
            display: none;
        }}

        .results.show {{
            display: block;
        }}

        .member-result {{
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
        }}

        .member-result:hover {{
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
        }}

        .member-name {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.5rem;
            font-weight: 500;
            margin-bottom: 0.75rem;
            color: black;
            letter-spacing: -0.02em;
        }}

        .score {{
            display: inline-block;
            background: black;
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 12px;
            font-weight: 600;
            margin-bottom: 1rem;
            font-size: 0.875rem;
        }}

        .analysis-section {{
            margin-top: 1.25rem;
        }}

        .analysis-title {{
            font-family: "Satoshi", sans-serif;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: #2d2d2d;
            opacity: 0.8;
        }}

        .analysis-text {{
            font-family: "Satoshi", sans-serif;
            color: #2d2d2d;
            line-height: 1.6;
            font-size: 0.9375rem;
        }}

        .analysis-text ul {{
            margin-top: 0.5rem;
            padding-left: 1.5rem;
        }}

        .analysis-text li {{
            margin-bottom: 0.5rem;
        }}

        .loading {{
            text-align: center;
            padding: 3rem;
            display: none;
        }}

        .loading.show {{
            display: block;
        }}

        .loading p {{
            font-family: "Satoshi", sans-serif;
            font-size: 1.125rem;
            color: #2d2d2d;
            opacity: 0.8;
        }}

        .spinner {{
            border: 4px solid rgba(0, 0, 0, 0.1);
            border-top: 4px solid black;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }}

        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div id="questionnaire">
            <h1>{config['org_name']}</h1>
            <p class="subtitle">{mode_description}</p>

            <form id="onboardingForm">
                <div class="question">
                    <label class="question-label">Full Name (Optional)</label>
                    <input type="text" name="full_name" style="width: 100%; padding: 1rem; border: 2px solid #ddd; border-radius: 12px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                </div>

                <div class="question">
                    <label class="question-label">Email (Optional)</label>
                    <input type="email" name="email" style="width: 100%; padding: 1rem; border: 2px solid #ddd; border-radius: 12px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                </div>

                <div class="question">
                    <label class="question-label">LinkedIn URL (Optional)</label>
                    <p class="question-description">Your LinkedIn profile helps us understand your professional background.</p>
                    <input type="url" name="linkedin_url" placeholder="https://linkedin.com/in/yourname" style="width: 100%; padding: 1rem; border: 2px solid #ddd; border-radius: 12px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                </div>

                <div class="question">
                    <label class="question-label">Age</label>
                    <input type="number" name="age" min="18" max="100" style="width: 100%; padding: 1rem; border: 2px solid #ddd; border-radius: 12px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                </div>

                <div class="question">
                    <label class="question-label">Location (City, Country)</label>
                    <input type="text" name="location" placeholder="e.g., London, UK" style="width: 100%; padding: 1rem; border: 2px solid #ddd; border-radius: 12px; font-family: 'Satoshi', sans-serif; font-size: 1rem;">
                </div>

                <div class="question">
                    <label class="question-label">Defining Moment</label>
                    <p class="question-description">Describe a life-changing decision that shaped who you are today.</p>
                    <textarea name="defining_moment" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Resource Allocation</label>
                    <p class="question-description">If you received an unexpected $10,000 windfall, how would you allocate it?</p>
                    <textarea name="resource_allocation" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Conflict Response</label>
                    <p class="question-description">Describe a time when you had a significant disagreement with someone. How did you navigate it?</p>
                    <textarea name="conflict_response" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Trade-off Scenario</label>
                    <p class="question-description">Would you prefer a high-paying job you find meaningless, or meaningful work with lower pay? Why?</p>
                    <textarea name="trade_off" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Social Identity</label>
                    <p class="question-description">What communities or groups are most important to your identity?</p>
                    <textarea name="social_identity" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Moral Dilemma</label>
                    <p class="question-description">A close friend does something unethical at work. Do you report it or stay loyal? Why?</p>
                    <textarea name="moral_dilemma" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">System Trust</label>
                    <p class="question-description">How much do you trust institutions (government, corporations, media)? Why?</p>
                    <textarea name="system_trust" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Stress Response</label>
                    <p class="question-description">Describe a highly stressful situation and how you coped with it.</p>
                    <textarea name="stress_response" required></textarea>
                </div>

                <div class="question">
                    <label class="question-label">Future & Values</label>
                    <p class="question-description">What are your most important goals for the next 5 years?</p>
                    <textarea name="future_values" required></textarea>
                </div>

                <button type="submit" class="submit-btn" id="submitBtn">View Results</button>
            </form>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Analyzing responses...</p>
        </div>

        <div class="results" id="results">
            <h1>Results</h1>
            <p class="subtitle" id="resultsSubtitle"></p>
            <div id="resultsContent"></div>
        </div>
    </div>

    <script>
        document.getElementById('onboardingForm').addEventListener('submit', async (e) => {{
            e.preventDefault();

            const formData = new FormData(e.target);
            const submitBtn = document.getElementById('submitBtn');
            const questionnaire = document.getElementById('questionnaire');
            const loading = document.getElementById('loading');
            const results = document.getElementById('results');

            // Show loading
            questionnaire.style.display = 'none';
            loading.classList.add('show');
            submitBtn.disabled = true;

            try {{
                const response = await fetch('/embed/{config['embed_token']}/process', {{
                    method: 'POST',
                    body: formData
                }});

                const data = await response.json();

                if (data.success) {{
                    displayResults(data.results, '{config['mode']}');
                    loading.classList.remove('show');
                    results.classList.add('show');
                }} else {{
                    alert('Error: ' + (data.error || 'Unknown error'));
                    loading.classList.remove('show');
                    questionnaire.style.display = 'block';
                    submitBtn.disabled = false;
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('An error occurred. Please try again.');
                loading.classList.remove('show');
                questionnaire.style.display = 'block';
                submitBtn.disabled = false;
            }}
        }});

        function displayResults(results, mode) {{
            const resultsContent = document.getElementById('resultsContent');
            const resultsSubtitle = document.getElementById('resultsSubtitle');

            if (mode === 'party') {{
                resultsSubtitle.textContent = 'Your compatibility with each team member:';

                resultsContent.innerHTML = results.members.map(member => {{
                    const analysis = member.analysis;
                    return `
                        <div class="member-result">
                            <div class="member-name">${{member.name}}</div>
                            <div class="score">Compatibility: ${{analysis.compatibility_score}}%</div>
                            <div class="analysis-section">
                                <p class="analysis-text">${{analysis.summary}}</p>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Strengths</div>
                                <ul class="analysis-text">
                                    ${{analysis.strengths.map(s => `<li>${{s}}</li>`).join('')}}
                                </ul>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Potential Challenges</div>
                                <ul class="analysis-text">
                                    ${{analysis.challenges.map(c => `<li>${{c}}</li>`).join('')}}
                                </ul>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Recommendation</div>
                                <p class="analysis-text">${{analysis.recommendation}}</p>
                            </div>
                        </div>
                    `;
                }}).join('');
            }} else {{
                resultsSubtitle.textContent = 'How each team member would engage with you:';

                resultsContent.innerHTML = results.members.map(member => {{
                    const analysis = member.analysis;
                    return `
                        <div class="member-result">
                            <div class="member-name">${{member.name}}</div>
                            <div class="score">Effectiveness: ${{analysis.effectiveness_score}}%</div>
                            <div class="analysis-section">
                                <div class="analysis-title">Engagement Style</div>
                                <p class="analysis-text">${{analysis.engagement_style}}</p>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Strengths</div>
                                <ul class="analysis-text">
                                    ${{analysis.strengths.map(s => `<li>${{s}}</li>`).join('')}}
                                </ul>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Challenges</div>
                                <ul class="analysis-text">
                                    ${{analysis.challenges.map(c => `<li>${{c}}</li>`).join('')}}
                                </ul>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Relationship Quality</div>
                                <p class="analysis-text">${{analysis.relationship_quality}}</p>
                            </div>
                            <div class="analysis-section">
                                <div class="analysis-title">Overall Assessment</div>
                                <p class="analysis-text">${{analysis.recommendation}}</p>
                            </div>
                        </div>
                    `;
                }}).join('');
            }}
        }}
    </script>
</body>
</html>
    '''


@app.route('/organization/<int:org_id>')
@login_required
def organization_view(org_id):
    """View organization with Three.js visualization and simulation interface"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user is a member of this organization
        cursor.execute('''
            SELECT om.role, o.id, o.name, o.description, o.invite_token, o.created_by
            FROM organization_members om
            INNER JOIN organizations o ON om.organization_id = o.id
            WHERE om.organization_id = %s AND om.user_id = %s AND o.is_active = TRUE
        ''', (org_id, user_id))

        membership = cursor.fetchone()

        if not membership:
            conn.close()
            flash('You do not have access to this organization', 'error')
            return redirect('/dashboard')

        org_info = {
            'id': membership['id'],
            'name': membership['name'],
            'description': membership['description'],
            'invite_token': membership['invite_token'],
            'is_owner': membership['created_by'] == user_id,
            'role': membership['role']
        }

        # Get all members of the organization
        cursor.execute('''
            SELECT u.id, u.first_name, u.last_name,
                   u.first_name_encrypted, u.last_name_encrypted,
                   om.role, om.joined_at
            FROM organization_members om
            INNER JOIN users u ON om.user_id = u.id
            WHERE om.organization_id = %s AND om.is_active = TRUE
            ORDER BY om.joined_at ASC
        ''', (org_id,))

        members_raw = cursor.fetchall()

        # Decrypt member names with fallback to plain text
        members = []
        for member in members_raw:
            first_name = user_auth.encryption.decrypt_sensitive_data(member['first_name_encrypted']) if member['first_name_encrypted'] else member.get('first_name') or ''
            last_name = user_auth.encryption.decrypt_sensitive_data(member['last_name_encrypted']) if member['last_name_encrypted'] else member.get('last_name') or ''

            members.append({
                'id': member['id'],
                'first_name': first_name,
                'last_name': last_name,
                'role': member['role'],
                'joined_at': member['joined_at']
            })

        # Get recent simulations for this organization
        cursor.execute('''
            SELECT s.id, s.scenario_text, s.created_at, s.status,
                   u.first_name, u.first_name_encrypted
            FROM simulations s
            INNER JOIN users u ON s.created_by = u.id
            WHERE s.organization_id = %s
            ORDER BY s.created_at DESC
            LIMIT 10
        ''', (org_id,))

        simulations_raw = cursor.fetchall()

        # Decrypt simulation creator names with fallback
        recent_simulations = []
        for sim in simulations_raw:
            created_by_name = user_auth.encryption.decrypt_sensitive_data(sim['first_name_encrypted']) if sim['first_name_encrypted'] else sim.get('first_name') or 'Unknown'
            recent_simulations.append({
                'id': sim['id'],
                'scenario_text': sim['scenario_text'],
                'created_at': sim['created_at'],
                'status': sim['status'],
                'created_by_name': created_by_name
            })

        conn.close()

        content = render_organization_view(org_info, members, recent_simulations, user_info)
        return render_template_with_header(f"{org_info['name']}", content, user_info)

    except Exception as e:
        print(f"Error loading organization: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading organization', 'error')
        return redirect('/dashboard')


def render_organization_view(org_info: Dict, members: List[Dict], simulations: List[Dict], user_info: Dict) -> str:
    """Render the organization view with Three.js visualization"""

    # Prepare members data for Three.js
    members_json = []
    for idx, member in enumerate(members):
        members_json.append({
            'id': member['id'],
            'name': f"{member['first_name']} {member['last_name']}",
            'role': member['role'],
            'position': {
                'x': 0,  # Will be positioned by Three.js
                'y': 0,
                'z': 0
            }
        })

    members_json_str = json.dumps(members_json)

    # Prepare simulations for sidebar
    simulations_html = ''
    if simulations:
        for sim in simulations:
            sim_preview = sim['scenario_text'][:50] + '...' if len(sim['scenario_text']) > 50 else sim['scenario_text']
            sim_date = sim['created_at'].strftime('%b %d, %Y')
            simulations_html += f'''
            <div class="simulation-item" onclick="loadSimulation({sim['id']})">
                <button class="delete-sim-btn" onclick="event.stopPropagation(); deleteSimulation({sim['id']})" title="Delete simulation">×</button>
                <div class="simulation-title">{sim_preview}</div>
                <div class="simulation-meta">{sim_date} • by {sim['created_by_name']}</div>
            </div>
            '''
    else:
        simulations_html = '<div class="no-simulations">No simulations yet</div>'

    # Generate invite link
    invite_url = f"{request.host_url}join-organization/{org_info['invite_token']}"

    content = f'''
    <style>
        @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        .org-view-container {{
            display: flex;
            height: calc(100vh - 80px);
            width: 100%;
            gap: 0;
            font-family: "Satoshi", sans-serif;
        }}

        /* Left Sidebar - Saved Simulations */
        .left-sidebar {{
            width: 280px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-right: 1px solid rgba(0, 0, 0, 0.1);
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            transition: transform 0.3s ease;
        }}

        .left-sidebar.collapsed {{
            transform: translateX(-280px);
        }}

        .sidebar-header {{
            padding: 1rem 1.5rem;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .sidebar-title {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            color: black;
        }}

        .new-simulation-btn {{
            background: black;
            color: white;
            border: none;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }}

        .new-simulation-btn:hover {{
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}

        .simulations-list {{
            padding: 1rem;
            flex: 1;
            overflow-y: auto;
        }}

        .simulation-item {{
            padding: 1rem;
            background: white;
            border-radius: 12px;
            margin-bottom: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid rgba(0, 0, 0, 0.05);
            position: relative;
        }}

        .simulation-item:hover {{
            transform: translateX(4px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            border-color: rgba(0, 0, 0, 0.2);
        }}

        .simulation-item:hover .delete-sim-btn {{
            opacity: 1;
        }}

        .simulation-title {{
            font-weight: 600;
            font-size: 0.875rem;
            color: black;
            margin-bottom: 0.5rem;
            padding-right: 24px;
        }}

        .simulation-meta {{
            font-size: 0.75rem;
            color: #666;
        }}

        .delete-sim-btn {{
            position: absolute;
            top: 0.75rem;
            right: 0.75rem;
            background: #ef4444;
            color: white;
            border: none;
            width: 20px;
            height: 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.2s ease;
        }}

        .delete-sim-btn:hover {{
            background: #dc2626;
        }}

        .no-simulations {{
            text-align: center;
            padding: 2rem 1rem;
            color: #666;
            font-size: 0.875rem;
        }}

        /* Center - Three.js Canvas */
        .center-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
            position: relative;
        }}

        .org-header-bar {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .org-name {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: black;
        }}

        .invite-section {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .invite-link-input {{
            font-family: "Satoshi", sans-serif;
            padding: 0.5rem 1rem;
            background: white;
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            font-size: 0.875rem;
            width: 300px;
        }}

        .copy-btn {{
            background: black;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 600;
            transition: all 0.2s ease;
        }}

        .copy-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }}

        .canvas-container {{
            flex: 1;
            position: relative;
            overflow: hidden;
        }}

        #three-canvas {{
            width: 100%;
            height: 100%;
            display: block;
        }}

        .simulation-form {{
            position: absolute;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%);
            width: 90%;
            max-width: 600px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .mode-toggle {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            background: rgba(0, 0, 0, 0.05);
            border-radius: 8px;
            padding: 0.25rem;
        }}

        .mode-btn {{
            flex: 1;
            padding: 0.5rem 1rem;
            border: none;
            background: transparent;
            border-radius: 6px;
            cursor: pointer;
            font-family: "Satoshi", sans-serif;
            font-size: 0.875rem;
            font-weight: 600;
            color: #666;
            transition: all 0.2s ease;
        }}

        .mode-btn.active {{
            background: black;
            color: white;
        }}

        .mode-btn:hover:not(.active) {{
            background: rgba(0, 0, 0, 0.1);
        }}

        .scenario-input {{
            font-family: "Satoshi", sans-serif;
            width: 100%;
            padding: 1rem;
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 12px;
            font-size: 1rem;
            resize: vertical;
            min-height: 80px;
            margin-bottom: 1rem;
        }}

        .scenario-input:focus {{
            outline: none;
            border-color: rgba(0, 0, 0, 0.3);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}

        .simulate-btn {{
            background: black;
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: all 0.2s ease;
            font-family: "Satoshi", sans-serif;
        }}

        .simulate-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }}

        .simulate-btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }}

        /* Right Sidebar - Results */
        .right-sidebar {{
            width: 350px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-left: 1px solid rgba(0, 0, 0, 0.1);
            overflow-y: auto;
            transition: transform 0.3s ease;
            transform: translateX(350px);
        }}

        .right-sidebar.visible {{
            transform: translateX(0);
        }}

        .response-container {{
            padding: 1.5rem;
        }}

        .response-header {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.25rem;
            font-weight: 600;
            color: black;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
        }}

        .response-content {{
            font-size: 0.875rem;
            line-height: 1.6;
            color: #333;
        }}

        .response-json {{
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 8px;
            font-family: monospace;
            font-size: 0.8rem;
            overflow-x: auto;
            margin-top: 1rem;
        }}

        .member-count {{
            font-size: 0.875rem;
            color: #666;
            margin-left: 1rem;
        }}

        /* Subscription Modal */
        .subscription-modal {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .subscription-modal-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(8px);
        }}

        .subscription-modal-content {{
            position: relative;
            background: white;
            border-radius: 20px;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            animation: modalSlideIn 0.3s ease-out;
            overflow: hidden;
        }}

        @keyframes modalSlideIn {{
            from {{
                opacity: 0;
                transform: translateY(-30px) scale(0.95);
            }}
            to {{
                opacity: 1;
                transform: translateY(0) scale(1);
            }}
        }}

        .subscription-modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 2rem 2rem 1rem 2rem;
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
        }}

        .subscription-modal-header h2 {{
            font-family: "Sentient", "Satoshi", sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
            color: black;
        }}

        .modal-close-btn {{
            background: none;
            border: none;
            font-size: 2rem;
            color: #999;
            cursor: pointer;
            padding: 0;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: all 0.2s ease;
        }}

        .modal-close-btn:hover {{
            background: rgba(0, 0, 0, 0.05);
            color: black;
        }}

        .subscription-modal-body {{
            padding: 2rem;
            text-align: center;
        }}

        .subscription-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
        }}

        .subscription-message {{
            font-size: 1.1rem;
            line-height: 1.6;
            color: #333;
            margin-bottom: 1.5rem;
        }}

        .subscription-features {{
            background: rgba(0, 0, 0, 0.02);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 1.5rem;
        }}

        .feature-item {{
            font-size: 1rem;
            color: #333;
            padding: 0.5rem 0;
            text-align: left;
            font-weight: 500;
        }}

        .subscription-modal-footer {{
            padding: 1.5rem 2rem 2rem 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}

        .btn-subscribe-now {{
            background: black;
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 12px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            font-family: "Satoshi", sans-serif;
            transition: all 0.2s ease;
        }}

        .btn-subscribe-now:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }}

        .btn-cancel {{
            background: transparent;
            color: #666;
            border: none;
            padding: 0.75rem;
            font-size: 0.95rem;
            cursor: pointer;
            font-family: "Satoshi", sans-serif;
            transition: color 0.2s ease;
        }}

        .btn-cancel:hover {{
            color: black;
        }}

    </style>

    <div class="org-view-container">
        <!-- Left Sidebar: Saved Simulations -->
        <div class="left-sidebar" id="leftSidebar">
            <div class="sidebar-header">
                <div class="sidebar-title">Chats</div>
                <button class="new-simulation-btn" onclick="clearSimulation()" title="New Simulation">+</button>
            </div>
            <div class="simulations-list">
                {simulations_html}
            </div>
        </div>

        <!-- Center: Three.js Visualization -->
        <div class="center-content">
            <div class="org-header-bar">
                <div>
                    <span class="org-name">{org_info['name']}</span>
                    <span class="member-count">{len(members)} member{'s' if len(members) != 1 else ''}</span>
                </div>
                <div class="invite-section">
                    <input type="text" class="invite-link-input" id="inviteLink" value="{invite_url}" readonly>
                    <button class="copy-btn" onclick="copyInviteLink()">Copy Link</button>
                    <a href="/organization/{org_info['id']}/applicants" class="copy-btn" style="margin-left: 0.5rem; text-decoration: none;">View Applicants</a>
                    {f'<a href="/organization/{org_info["id"]}/embed-settings" class="copy-btn" style="margin-left: 0.5rem; text-decoration: none;">Widget Settings</a>' if org_info['is_owner'] else ''}
                </div>
            </div>

            <div class="canvas-container">
                <canvas id="three-canvas"></canvas>

                <div class="simulation-form">
                    <div class="mode-toggle">
                        <button class="mode-btn active" id="simulationModeBtn" onclick="switchMode('simulation')">
                            Simulation Mode
                        </button>
                        <button class="mode-btn" id="partyModeBtn" onclick="switchMode('party')">
                            Party Mode
                        </button>
                        <button class="mode-btn" id="networkingModeBtn" onclick="switchMode('networking')">
                            Networking Mode
                        </button>
                    </div>
                    <textarea
                        class="scenario-input"
                        id="scenarioInput"
                        placeholder="Enter a scenario to simulate... (e.g., 'A major deadline is moved up by two weeks')"
                    ></textarea>
                    <textarea
                        class="scenario-input"
                        id="attendeeInput"
                        placeholder="Paste attendee list (one per line, format: Name, LinkedIn URL)"
                        style="display: none; margin-top: 1rem;"
                    ></textarea>
                    <button class="simulate-btn" id="simulateBtn" onclick="runSimulation()">
                        Simulate Responses
                    </button>
                </div>
            </div>
        </div>

        <!-- Right Sidebar: Response Details -->
        <div class="right-sidebar" id="rightSidebar">
            <div class="response-container" id="responseContainer">
                <div class="response-header">Select a team member</div>
                <div class="response-content">
                    Click on a team member's sphere to see their predicted response to the scenario.
                </div>
            </div>
        </div>
    </div>

    <!-- Subscription Required Modal -->
    <div id="subscriptionModal" class="subscription-modal" style="display: none;">
        <div class="subscription-modal-overlay" onclick="closeSubscriptionModal()"></div>
        <div class="subscription-modal-content">
            <div class="subscription-modal-header">
                <h2>Subscription Required</h2>
                <button class="modal-close-btn" onclick="closeSubscriptionModal()">&times;</button>
            </div>
            <div class="subscription-modal-body">
                <div class="subscription-icon">🔒</div>
                <p class="subscription-message" id="subscriptionMessage">
                    You've used all 20 free simulations. Subscribe now to continue running simulations and unlock unlimited access to all features.
                </p>
                <div class="subscription-features">
                    <div class="feature-item">✓ Unlimited simulations</div>
                    <div class="feature-item">✓ Unlimited organizations</div>
                    <div class="feature-item">✓ Advanced embeddings & analytics</div>
                    <div class="feature-item">✓ Priority support</div>
                </div>
            </div>
            <div class="subscription-modal-footer">
                <button class="btn-subscribe-now" onclick="window.location.href='/subscription/plans'">
                    Subscribe Now
                </button>
                <button class="btn-cancel" onclick="closeSubscriptionModal()">
                    Maybe Later
                </button>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
        const orgId = {org_info['id']};
        const members = {members_json_str};
        let currentSimulationId = null;
        let simulationResults = {{}};
        let currentMode = 'simulation'; // 'simulation', 'party', or 'networking'
        let partyResults = null;
        let networkingResults = null;
        let compatibilityLines = [];
        let externalAttendees = [];

        // Three.js Setup
        const canvas = document.getElementById('three-canvas');
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf8f9fa);

        // Camera setup
        const camera = new THREE.PerspectiveCamera(
            50,
            canvas.clientWidth / canvas.clientHeight,
            0.1,
            1000
        );
        camera.position.set(0, 5, 15);
        camera.lookAt(0, 0, 0);

        // Renderer
        const renderer = new THREE.WebGLRenderer({{
            canvas: canvas,
            antialias: true
        }});
        renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);

        const mainLight = new THREE.DirectionalLight(0xffffff, 0.8);
        mainLight.position.set(10, 10, 10);
        scene.add(mainLight);

        const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
        fillLight.position.set(-5, 5, -5);
        scene.add(fillLight);

        // Create cleaner spheres for members
        const spheres = [];
        const labels = [];
        const memberCount = members.length;
        const radius = Math.max(4, memberCount * 0.5);

        console.log('Creating', memberCount, 'spheres with radius', radius);

        members.forEach((member, index) => {{
            const angle = (index / memberCount) * Math.PI * 2;
            const x = Math.cos(angle) * radius;
            const z = Math.sin(angle) * radius;
            const y = 0;

            // Create sphere
            const geometry = new THREE.SphereGeometry(0.6, 32, 32);
            const material = new THREE.MeshStandardMaterial({{
                color: 0x2d3748,
                metalness: 0.3,
                roughness: 0.4,
                emissive: 0x000000
            }});

            const sphere = new THREE.Mesh(geometry, material);
            sphere.position.set(x, y, z);
            sphere.userData = {{
                memberId: member.id,
                memberName: member.name,
                originalY: y,
                hoverOffset: 0,
                targetScale: 1.0
            }};
            scene.add(sphere);
            spheres.push(sphere);

            console.log('Created sphere for', member.name, 'at', x, y, z);

            // Create label using sprite
            const canvas2d = document.createElement('canvas');
            const context = canvas2d.getContext('2d');
            canvas2d.width = 256;
            canvas2d.height = 64;

            context.fillStyle = 'rgba(0, 0, 0, 0)';
            context.fillRect(0, 0, canvas2d.width, canvas2d.height);

            context.font = 'Bold 24px Satoshi, Arial, sans-serif';
            context.fillStyle = '#2d3748';
            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.fillText(member.name, 128, 32);

            const texture = new THREE.CanvasTexture(canvas2d);
            const spriteMaterial = new THREE.SpriteMaterial({{
                map: texture,
                transparent: true
            }});
            const sprite = new THREE.Sprite(spriteMaterial);
            sprite.position.set(x, y + 1.2, z);
            sprite.scale.set(3, 0.75, 1);
            scene.add(sprite);
            labels.push(sprite);
        }});

        console.log('Total spheres created:', spheres.length);

        // Mouse interaction
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        let INTERSECTED = null;

        canvas.addEventListener('mousemove', (event) => {{
            const rect = canvas.getBoundingClientRect();
            mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(spheres);

            if (intersects.length > 0) {{
                if (INTERSECTED !== intersects[0].object) {{
                    if (INTERSECTED) {{
                        INTERSECTED.userData.hoverOffset = 0;
                        INTERSECTED.userData.targetScale = 1.0;
                    }}
                    INTERSECTED = intersects[0].object;
                    INTERSECTED.userData.hoverOffset = 0.3;
                    INTERSECTED.userData.targetScale = 1.1;
                    canvas.style.cursor = 'pointer';
                }}
            }} else {{
                if (INTERSECTED) {{
                    INTERSECTED.userData.hoverOffset = 0;
                    INTERSECTED.userData.targetScale = 1.0;
                }}
                INTERSECTED = null;
                canvas.style.cursor = 'default';
            }}
        }});

        canvas.addEventListener('click', () => {{
            if (INTERSECTED) {{
                const memberId = INTERSECTED.userData.memberId;
                const memberName = INTERSECTED.userData.memberName;

                if (currentMode === 'party' && partyResults) {{
                    showCompatibilityMatches(memberId, memberName);
                }} else if (currentMode === 'networking' && networkingResults) {{
                    showNetworkingRecommendations(memberId, memberName);
                }} else if (currentSimulationId) {{
                    showMemberResponse(memberId, memberName);
                }}
            }}
        }});

        // Animation loop
        const clock = new THREE.Clock();

        function animate() {{
            requestAnimationFrame(animate);
            const elapsed = clock.getElapsedTime();

            // Animate spheres
            spheres.forEach((sphere, index) => {{
                // Gentle floating
                const bob = Math.sin(elapsed * 0.6 + index * 0.5) * 0.15;
                const targetY = sphere.userData.originalY + bob + sphere.userData.hoverOffset;
                sphere.position.y += (targetY - sphere.position.y) * 0.08;

                // Gentle rotation
                sphere.rotation.y += 0.003;

                // Update label
                if (labels[index]) {{
                    labels[index].position.y = sphere.position.y + 1.2;
                }}

                // Smooth scale
                const targetScale = sphere.userData.targetScale;
                sphere.scale.x += (targetScale - sphere.scale.x) * 0.1;
                sphere.scale.y += (targetScale - sphere.scale.y) * 0.1;
                sphere.scale.z += (targetScale - sphere.scale.z) * 0.1;
            }});

            renderer.render(scene, camera);
        }}

        console.log('Starting animation loop');
        animate();

        // Handle window resize
        window.addEventListener('resize', () => {{
            camera.aspect = canvas.clientWidth / canvas.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(canvas.clientWidth, canvas.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        }});

        // Mode switching
        function switchMode(mode) {{
            currentMode = mode;

            // Update button states
            document.getElementById('simulationModeBtn').classList.toggle('active', mode === 'simulation');
            document.getElementById('partyModeBtn').classList.toggle('active', mode === 'party');
            document.getElementById('networkingModeBtn').classList.toggle('active', mode === 'networking');

            // Update placeholder and button text
            const scenarioInput = document.getElementById('scenarioInput');
            const attendeeInput = document.getElementById('attendeeInput');
            const btn = document.getElementById('simulateBtn');

            if (mode === 'party') {{
                scenarioInput.placeholder = 'Party Mode analyzes how compatible each team member is with each other in social settings. Enter a scenario to see compatibility insights...';
                attendeeInput.style.display = 'none';
                btn.textContent = 'Analyze Compatibility';
            }} else if (mode === 'networking') {{
                scenarioInput.placeholder = 'Enter your networking goal... (e.g., "Find potential investors for my startup")';
                attendeeInput.style.display = 'block';
                btn.textContent = 'Analyze Networking Matches';
            }} else {{
                scenarioInput.placeholder = 'Enter a scenario to simulate... (e.g., "A major deadline is moved up by two weeks")';
                attendeeInput.style.display = 'none';
                btn.textContent = 'Simulate Responses';
            }}

            // Clear results and reset view
            clearSimulation();
        }}

        // Simulation functions
        async function runSimulation() {{
            const scenario = document.getElementById('scenarioInput').value.trim();
            if (!scenario) {{
                alert('Please enter a scenario');
                return;
            }}

            if (currentMode === 'party') {{
                return runPartyMode(scenario);
            }} else if (currentMode === 'networking') {{
                return runNetworkingMode(scenario);
            }}

            const btn = document.getElementById('simulateBtn');

            btn.disabled = true;
            btn.textContent = 'Simulating...';

            try {{
                const response = await fetch('/api/run-simulation', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        org_id: orgId,
                        scenario: scenario
                    }})
                }});

                const data = await response.json();

                if (data.success) {{
                    currentSimulationId = data.simulation_id;
                    simulationResults = data.responses;

                    // Animate spheres with results - smooth color transition
                    spheres.forEach((sphere, index) => {{
                        if (simulationResults[sphere.userData.memberId]) {{
                            // Stagger the animation
                            setTimeout(() => {{
                                const targetColor = new THREE.Color(0x6b9b99); // Teal accent
                                animateColorTransition(sphere.material, targetColor, 1000);
                            }}, index * 100);
                        }}
                    }});

                    // Show right sidebar with instruction message
                    setTimeout(() => {{
                        const sidebar = document.getElementById('rightSidebar');
                        const container = document.getElementById('responseContainer');

                        container.innerHTML = `
                            <div class="response-header">Simulation Complete!</div>
                            <div class="response-content">
                                Click on a sphere to see their reaction to the scenario.
                            </div>
                        `;

                        sidebar.classList.add('visible');
                    }}, spheres.length * 100);
                }} else {{
                    // Check if subscription is required
                    if (data.requires_subscription) {{
                        showSubscriptionModal(data.message, data.simulations_used);
                    }} else {{
                        alert('Error: ' + data.error);
                    }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Failed to run simulation');
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Simulate Responses';
            }}
        }}

        // Party Mode
        async function runPartyMode(scenario) {{
            const btn = document.getElementById('simulateBtn');
            btn.disabled = true;
            btn.textContent = 'Analyzing...';

            // Clear existing lines
            clearCompatibilityLines();

            try {{
                const response = await fetch('/api/run-party-mode', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        org_id: orgId,
                        scenario: scenario
                    }})
                }});

                const data = await response.json();

                if (data.success) {{
                    partyResults = data.compatibility;

                    // Draw compatibility lines
                    drawCompatibilityLines(data.compatibility);

                    // Show success message in sidebar
                    setTimeout(() => {{
                        const sidebar = document.getElementById('rightSidebar');
                        const container = document.getElementById('responseContainer');

                        container.innerHTML = `
                            <div class="response-header">Compatibility Analysis Complete!</div>
                            <div class="response-content">
                                Click on any sphere to see who they're most compatible with in this scenario.
                            </div>
                        `;

                        sidebar.classList.add('visible');
                    }}, 500);
                }} else {{
                    // Check if subscription is required
                    if (data.requires_subscription) {{
                        showSubscriptionModal(data.message, data.simulations_used);
                    }} else {{
                        alert('Error: ' + data.error);
                    }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Failed to run party mode analysis');
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Analyze Compatibility';
            }}
        }}

        function clearCompatibilityLines() {{
            compatibilityLines.forEach(line => {{
                scene.remove(line);
                line.geometry.dispose();
                line.material.dispose();
            }});
            compatibilityLines = [];
        }}

        function drawCompatibilityLines(compatibility) {{
            clearCompatibilityLines();

            // Create a map to track bidirectional matches
            const bidirectional = new Map();

            // First pass: identify bidirectional matches
            Object.entries(compatibility).forEach(([userId1, data]) => {{
                const user1Id = parseInt(userId1);
                data.top_matches.forEach(match => {{
                    const user2Id = match.user_id;
                    const key = [Math.min(user1Id, user2Id), Math.max(user1Id, user2Id)].join('-');

                    if (bidirectional.has(key)) {{
                        bidirectional.get(key).bidirectional = true;
                    }} else {{
                        bidirectional.set(key, {{ userId1: user1Id, userId2: user2Id, bidirectional: false }});
                    }}
                }});
            }});

            // Second pass: draw lines
            Object.entries(compatibility).forEach(([userId, data]) => {{
                const user1Id = parseInt(userId);
                const sphere1 = spheres.find(s => s.userData.memberId === user1Id);

                if (!sphere1) return;

                data.top_matches.forEach((match, index) => {{
                    const sphere2 = spheres.find(s => s.userData.memberId === match.user_id);
                    if (!sphere2) return;

                    const key = [Math.min(user1Id, match.user_id), Math.max(user1Id, match.user_id)].join('-');
                    const isBidirectional = bidirectional.get(key)?.bidirectional;

                    // Only draw line if user1Id < user2Id to avoid duplicates
                    if (user1Id < match.user_id) {{
                        const lineColor = isBidirectional ? 0x4ade80 : 0x9ca3af;
                        const lineWidth = isBidirectional ? 3 : 1.5;

                        const points = [];
                        points.push(sphere1.position.clone());
                        points.push(sphere2.position.clone());

                        const geometry = new THREE.BufferGeometry().setFromPoints(points);
                        const material = new THREE.LineBasicMaterial({{
                            color: lineColor,
                            linewidth: lineWidth,
                            opacity: 0.6,
                            transparent: true
                        }});

                        const line = new THREE.Line(geometry, material);
                        scene.add(line);
                        compatibilityLines.push(line);
                    }}
                }});
            }});
        }}

        function showCompatibilityMatches(memberId, memberName) {{
            const compatibility = partyResults[memberId];
            if (!compatibility) {{
                alert('No compatibility data for this member');
                return;
            }}

            const sidebar = document.getElementById('rightSidebar');
            const container = document.getElementById('responseContainer');

            let matchesHtml = '';
            compatibility.top_matches.forEach((match, index) => {{
                matchesHtml += `
                    <div style="margin-bottom: 1rem; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                        <div style="font-weight: 600; margin-bottom: 0.5rem;">${{index + 1}}. ${{match.name}}</div>
                        <div style="font-size: 0.875rem; color: #666; margin-bottom: 0.5rem;">
                            Compatibility: ${{(match.score * 100).toFixed(0)}}%
                        </div>
                        <div style="font-size: 0.875rem; line-height: 1.5;">
                            ${{match.analysis}}
                        </div>
                    </div>
                `;
            }});

            container.innerHTML = `
                <div class="response-header">${{memberName}}'s Best Matches</div>
                <div class="response-content">
                    ${{matchesHtml}}
                </div>
            `;

            sidebar.classList.add('visible');
        }}

        // Networking Mode
        async function runNetworkingMode(goal) {{
            const attendeeList = document.getElementById('attendeeInput').value.trim();
            if (!attendeeList) {{
                alert('Please paste the attendee list');
                return;
            }}

            const btn = document.getElementById('simulateBtn');
            btn.disabled = true;
            btn.textContent = 'Analyzing...';

            clearCompatibilityLines();

            try {{
                const response = await fetch('/api/run-networking-mode', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        org_id: orgId,
                        goal: goal,
                        attendee_list: attendeeList
                    }})
                }});

                const data = await response.json();

                if (data.success) {{
                    networkingResults = data.recommendations;

                    // Show success message in sidebar
                    setTimeout(() => {{
                        const sidebar = document.getElementById('rightSidebar');
                        const container = document.getElementById('responseContainer');

                        container.innerHTML = `
                            <div class="response-header">Networking Analysis Complete!</div>
                            <div class="response-content">
                                Click on any team member's sphere to see who they should connect with at this event.
                            </div>
                        `;

                        sidebar.classList.add('visible');
                    }}, 500);
                }} else {{
                    // Check if subscription is required
                    if (data.requires_subscription) {{
                        showSubscriptionModal(data.message, data.simulations_used);
                    }} else {{
                        alert('Error: ' + data.error);
                    }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Failed to run networking analysis');
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Analyze Networking Matches';
            }}
        }}

        function showNetworkingRecommendations(memberId, memberName) {{
            const recommendations = networkingResults[memberId];
            if (!recommendations) {{
                alert('No networking recommendations for this member');
                return;
            }}

            const sidebar = document.getElementById('rightSidebar');
            const container = document.getElementById('responseContainer');

            let recsHtml = '';
            recommendations.top_matches.forEach((match, index) => {{
                recsHtml += `
                    <div style="margin-bottom: 1rem; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                        <div style="font-weight: 600; margin-bottom: 0.5rem;">${{index + 1}}. ${{match.name}}</div>
                        <div style="font-size: 0.875rem; color: #666; margin-bottom: 0.25rem;">
                            ${{match.title || 'Attendee'}}
                        </div>
                        <div style="font-size: 0.875rem; color: #666; margin-bottom: 0.5rem;">
                            Relevance: ${{(match.score * 100).toFixed(0)}}%
                        </div>
                        <div style="font-size: 0.875rem; line-height: 1.5;">
                            ${{match.reason}}
                        </div>
                    </div>
                `;
            }});

            container.innerHTML = `
                <div class="response-header">${{memberName}}'s Networking Targets</div>
                <div class="response-content">
                    ${{recsHtml}}
                </div>
            `;

            sidebar.classList.add('visible');
        }}

        function showMemberResponse(memberId, memberName) {{
            const response = simulationResults[memberId];
            if (!response) {{
                alert('No response available for this member');
                return;
            }}

            const sidebar = document.getElementById('rightSidebar');
            const container = document.getElementById('responseContainer');

            // Format response nicely
            let formattedResponse = '';

            if (response.error) {{
                formattedResponse = `
                    <div style="padding: 1rem; background: #fee; border-radius: 8px; color: #c33;">
                        <strong>Error:</strong> ${{response.error}}
                    </div>
                `;
            }} else {{
                formattedResponse = `
                    <div class="response-section">
                        <h4 style="font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 0.5rem; font-weight: 600;">Immediate Reaction</h4>
                        <p style="color: #333; line-height: 1.6; margin-bottom: 1.5rem;">${{response.immediate_reaction || 'N/A'}}</p>
                    </div>

                    <div class="response-section">
                        <h4 style="font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 0.5rem; font-weight: 600;">Likely Action</h4>
                        <p style="color: #333; line-height: 1.6; margin-bottom: 1.5rem;">${{response.likely_action || 'N/A'}}</p>
                    </div>

                    <div class="response-section">
                        <h4 style="font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 0.5rem; font-weight: 600;">Reasoning</h4>
                        <p style="color: #333; line-height: 1.6; margin-bottom: 1.5rem;">${{response.reasoning || 'N/A'}}</p>
                    </div>

                    <div class="response-section">
                        <h4 style="font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 0.5rem; font-weight: 600;">Stress Level</h4>
                        <div style="margin-bottom: 1.5rem;">
                            <span style="display: inline-block; padding: 0.5rem 1rem; background: ${{
                                response.stress_level === 'low' ? '#d4edda' :
                                response.stress_level === 'high' ? '#f8d7da' : '#fff3cd'
                            }}; color: ${{
                                response.stress_level === 'low' ? '#155724' :
                                response.stress_level === 'high' ? '#721c24' : '#856404'
                            }}; border-radius: 8px; font-weight: 600; text-transform: uppercase; font-size: 0.75rem;">
                                ${{response.stress_level || 'N/A'}}
                            </span>
                        </div>
                    </div>

                    <div class="response-section">
                        <h4 style="font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 0.5rem; font-weight: 600;">Suggested Approach</h4>
                        <p style="color: #333; line-height: 1.6; padding: 1rem; background: #f8f9fa; border-radius: 8px; border-left: 3px solid #6b9b99;">${{response.suggested_approach || 'N/A'}}</p>
                    </div>
                `;
            }}

            container.innerHTML = `
                <div class="response-header">${{memberName}}</div>
                <div class="response-content">
                    ${{formattedResponse}}
                </div>
            `;

            sidebar.classList.add('visible');
        }}

        // Smooth color transition helper
        function animateColorTransition(material, targetColor, duration) {{
            const startColor = material.color.clone();
            const startTime = Date.now();

            function updateColor() {{
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);

                // Ease out cubic
                const eased = 1 - Math.pow(1 - progress, 3);

                material.color.lerpColors(startColor, targetColor, eased);

                if (progress < 1) {{
                    requestAnimationFrame(updateColor);
                }}
            }}

            updateColor();
        }}

        function clearSimulation() {{
            document.getElementById('scenarioInput').value = '';
            document.getElementById('attendeeInput').value = '';
            currentSimulationId = null;
            simulationResults = {{}};
            partyResults = null;
            networkingResults = null;

            // Clear compatibility lines
            clearCompatibilityLines();

            // Reset sphere colors with animation
            const originalColor = new THREE.Color(0x2d3748);
            spheres.forEach((sphere, index) => {{
                setTimeout(() => {{
                    animateColorTransition(sphere.material, originalColor, 800);
                }}, index * 50);
            }});

            document.getElementById('rightSidebar').classList.remove('visible');
        }}

        function copyInviteLink() {{
            const input = document.getElementById('inviteLink');
            input.select();
            document.execCommand('copy');

            const btn = event.target;
            const originalText = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => {{
                btn.textContent = originalText;
            }}, 2000);
        }}

        function showSubscriptionModal(message, simulationsUsed) {{
            const modal = document.getElementById('subscriptionModal');
            const messageEl = document.getElementById('subscriptionMessage');

            if (message) {{
                messageEl.textContent = message;
            }}

            modal.style.display = 'flex';
            // Prevent body scroll when modal is open
            document.body.style.overflow = 'hidden';
        }}

        function closeSubscriptionModal() {{
            const modal = document.getElementById('subscriptionModal');
            modal.style.display = 'none';
            // Restore body scroll
            document.body.style.overflow = 'auto';
        }}

        // Close modal on ESC key
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'Escape') {{
                closeSubscriptionModal();
            }}
        }});

        async function loadSimulation(simId) {{
            console.log('Loading simulation:', simId);

            try {{
                const response = await fetch(`/api/load-simulation/${{simId}}`);
                const data = await response.json();

                if (data.success) {{
                    // Load the scenario into the input
                    document.getElementById('scenarioInput').value = data.scenario;

                    // Set current simulation
                    currentSimulationId = data.simulation_id;
                    simulationResults = data.responses;

                    // Update sphere colors with animation
                    const targetColor = new THREE.Color(0x6b9b99);
                    spheres.forEach((sphere, index) => {{
                        if (simulationResults[sphere.userData.memberId]) {{
                            setTimeout(() => {{
                                animateColorTransition(sphere.material, targetColor, 800);
                            }}, index * 80);
                        }}
                    }});

                    // Show right sidebar with instruction message
                    setTimeout(() => {{
                        const sidebar = document.getElementById('rightSidebar');
                        const container = document.getElementById('responseContainer');

                        container.innerHTML = `
                            <div class="response-header">Simulation Loaded</div>
                            <div class="response-content">
                                Click on a sphere to see their reaction to the scenario.
                            </div>
                        `;

                        sidebar.classList.add('visible');
                    }}, spheres.length * 80);

                    console.log('Loaded simulation with', Object.keys(simulationResults).length, 'responses');
                }} else {{
                    alert('Error loading simulation: ' + data.error);
                }}
            }} catch (error) {{
                console.error('Error loading simulation:', error);
                alert('Failed to load simulation');
            }}
        }}

        async function deleteSimulation(simId) {{
            if (!confirm('Are you sure you want to delete this simulation?')) {{
                return;
            }}

            try {{
                const response = await fetch(`/api/delete-simulation/${{simId}}`, {{
                    method: 'DELETE'
                }});

                const data = await response.json();

                if (data.success) {{
                    // Reload the page to refresh the simulation list
                    window.location.reload();
                }} else {{
                    alert('Error deleting simulation: ' + data.error);
                }}
            }} catch (error) {{
                console.error('Error deleting simulation:', error);
                alert('Failed to delete simulation');
            }}
        }}
    </script>
    '''

    return content


@app.route('/api/run-simulation', methods=['POST'])
@login_required
def run_simulation():
    """Run a simulation for all members of an organization"""
    user_id = session['user_id']

    try:
        data = request.get_json()
        org_id = data.get('org_id')
        scenario = data.get('scenario', '').strip()

        if not org_id or not scenario:
            return jsonify({'success': False, 'error': 'Missing org_id or scenario'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify user is a member of this organization
        cursor.execute('''
            SELECT 1 FROM organization_members
            WHERE organization_id = %s AND user_id = %s AND is_active = TRUE
        ''', (org_id, user_id))

        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Not authorized'}), 403

        # Check subscription status and simulation count
        subscription_status = subscription_manager.get_user_subscription_status(user_id)

        # Count user's simulations
        cursor.execute('''
            SELECT COUNT(*) as sim_count FROM simulations
            WHERE created_by = %s
        ''', (user_id,))

        sim_count = cursor.fetchone()['sim_count']

        # Check if user needs subscription (20 free simulations)
        if not subscription_status['is_subscribed'] and sim_count >= 20:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Simulation limit reached',
                'message': f'You have used all 20 free simulations. Please subscribe to continue.',
                'simulations_used': sim_count,
                'requires_subscription': True
            }), 402  # Payment Required status code

        # Create simulation record
        cursor.execute('''
            INSERT INTO simulations (organization_id, scenario_text, created_by, status)
            VALUES (%s, %s, %s, 'processing')
            RETURNING id
        ''', (org_id, scenario, user_id))

        simulation_id = cursor.fetchone()['id']
        conn.commit()

        # Get all members of the organization with their profiles
        cursor.execute('''
            SELECT u.id, u.first_name, u.last_name, up.profile_data
            FROM organization_members om
            INNER JOIN users u ON om.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE om.organization_id = %s AND om.is_active = TRUE
        ''', (org_id,))

        members = cursor.fetchall()

        # Initialize OpenAI client
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY)

        responses = {}

        # Generate responses for each member
        for member in members:
            member_id = member['id']
            member_name = f"{member['first_name']} {member['last_name']}"

            # Get profile data
            profile_data = {}
            if member['profile_data']:
                try:
                    profile_data = json.loads(member['profile_data'])
                except:
                    profile_data = {}

            # Build prompt from profile data
            profile_summary = build_profile_summary(profile_data, member_name)

            # Call OpenAI to generate response
            prompt = f"""You are simulating how {member_name} would respond to a workplace scenario.

Based on their personality profile:
{profile_summary}

Scenario: {scenario}

Predict how {member_name} would respond to this scenario. Provide your response in the following JSON format:
{{
    "immediate_reaction": "Their first emotional/mental response",
    "likely_action": "What they would actually do or say",
    "reasoning": "Why they would respond this way based on their personality",
    "stress_level": "low/medium/high",
    "suggested_approach": "How to best work with them in this situation"
}}

Return ONLY the JSON, no other text."""

            try:
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a workplace psychology expert who predicts how people will respond to scenarios based on their personality profiles."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )

                response_text = completion.choices[0].message.content.strip()

                # Try to parse JSON response
                try:
                    # Remove markdown code blocks if present
                    if response_text.startswith('```'):
                        response_text = response_text.split('```')[1]
                        if response_text.startswith('json'):
                            response_text = response_text[4:]
                        response_text = response_text.strip()

                    response_json = json.loads(response_text)
                except json.JSONDecodeError:
                    # Fallback if JSON parsing fails
                    response_json = {
                        "immediate_reaction": response_text[:200],
                        "likely_action": "Unable to parse structured response",
                        "reasoning": response_text,
                        "stress_level": "medium",
                        "suggested_approach": "Review response manually"
                    }

                responses[member_id] = response_json

                # Save response to database
                cursor.execute('''
                    INSERT INTO simulation_responses (simulation_id, user_id, response_json)
                    VALUES (%s, %s, %s)
                ''', (simulation_id, member_id, json.dumps(response_json)))

            except Exception as e:
                print(f"Error generating response for member {member_id}: {e}")
                responses[member_id] = {
                    "error": "Failed to generate response",
                    "details": str(e)
                }

        # Mark simulation as completed
        cursor.execute('''
            UPDATE simulations
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (simulation_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'simulation_id': simulation_id,
            'responses': responses
        })

    except Exception as e:
        print(f"Error running simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/run-party-mode', methods=['POST'])
@login_required
def run_party_mode():
    """Run party mode compatibility analysis for all organization members"""
    user_id = session['user_id']

    try:
        data = request.get_json()
        org_id = data.get('org_id')
        scenario = data.get('scenario', '').strip()

        if not org_id or not scenario:
            return jsonify({'success': False, 'error': 'Missing org_id or scenario'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check subscription status and simulation count
        subscription_status = subscription_manager.get_user_subscription_status(user_id)

        # Count user's simulations
        cursor.execute('''
            SELECT COUNT(*) as sim_count FROM simulations
            WHERE created_by = %s
        ''', (user_id,))

        sim_count = cursor.fetchone()['sim_count']

        # Check if user needs subscription (20 free simulations)
        if not subscription_status['is_subscribed'] and sim_count >= 20:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Simulation limit reached',
                'message': f'You have used all 20 free simulations. Please subscribe to continue.',
                'simulations_used': sim_count,
                'requires_subscription': True
            }), 402  # Payment Required status code

        # Verify user is member of organization
        cursor.execute('''
            SELECT id FROM organization_members
            WHERE organization_id = %s AND user_id = %s AND is_active = TRUE
        ''', (org_id, user_id))

        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Not a member of this organization'}), 403

        # Get all active members with their profiles
        cursor.execute('''
            SELECT
                u.id, u.first_name, u.last_name,
                up.profile_data
            FROM organization_members om
            INNER JOIN users u ON om.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE om.organization_id = %s AND om.is_active = TRUE
        ''', (org_id,))

        members = cursor.fetchall()
        conn.close()

        # Parse profile data JSON
        parsed_members = []
        for member in members:
            member_dict = dict(member)
            if member_dict.get('profile_data'):
                try:
                    member_dict['profile'] = json.loads(member_dict['profile_data'])
                except:
                    member_dict['profile'] = {}
            else:
                member_dict['profile'] = {}
            parsed_members.append(member_dict)

        members = parsed_members

        if len(members) < 2:
            return jsonify({'success': False, 'error': 'Need at least 2 members for compatibility analysis'}), 400

        # Initialize OpenAI client
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY)

        # Analyze compatibility for each member
        compatibility_results = {}

        for member in members:
            member_id = member['id']
            member_name = f"{member['first_name']} {member['last_name']}"

            # Analyze compatibility with all other members
            matches = []

            for other_member in members:
                if other_member['id'] == member_id:
                    continue

                other_name = f"{other_member['first_name']} {other_member['last_name']}"

                # Build compatibility analysis prompt
                member_profile = build_profile_summary(member.get('profile', {}), member_name)
                other_profile = build_profile_summary(other_member.get('profile', {}), other_name)

                prompt = f"""You are analyzing compatibility between two people for a social scenario.

Scenario: {scenario}

Person 1: {member_profile}

Person 2: {other_profile}

Analyze how compatible these two people would be in this scenario. Consider:
1. Personality compatibility
2. Communication styles
3. Shared interests/values
4. How they might interact in this specific scenario

Provide your analysis as JSON:
{{
    "score": 0.0-1.0,
    "analysis": "2-3 sentence explanation of why they would or wouldn't work well together in this scenario"
}}"""

                try:
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are an expert in social dynamics and personality compatibility."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=200
                    )

                    response_text = completion.choices[0].message.content.strip()

                    # Parse JSON
                    if response_text.startswith('```'):
                        response_text = response_text.split('```')[1]
                        if response_text.startswith('json'):
                            response_text = response_text[4:]
                        response_text = response_text.strip()

                    result = json.loads(response_text)

                    matches.append({
                        'user_id': other_member['id'],
                        'name': other_name,
                        'score': result.get('score', 0.5),
                        'analysis': result.get('analysis', 'Analysis unavailable')
                    })

                except Exception as e:
                    print(f"Error analyzing compatibility: {e}")
                    matches.append({
                        'user_id': other_member['id'],
                        'name': other_name,
                        'score': 0.5,
                        'analysis': 'Unable to analyze compatibility'
                    })

            # Sort by score and keep top 3
            matches.sort(key=lambda x: x['score'], reverse=True)
            top_matches = matches[:min(3, len(matches))]

            compatibility_results[member_id] = {
                'top_matches': top_matches
            }

        return jsonify({
            'success': True,
            'compatibility': compatibility_results
        })

    except Exception as e:
        print(f"Error running party mode: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def scrape_linkedin_profile(linkedin_url: str) -> dict:
    """Scrape LinkedIn profile using Fresh LinkedIn Profile Data API"""
    if not FRESH_API_KEY:
        print("Warning: FRESH_API_KEY not set, skipping LinkedIn scraping")
        return None

    try:
        url = "https://fresh-linkedin-profile-data.p.rapidapi.com/get-linkedin-profile"
        querystring = {"linkedin_url": linkedin_url, "include_skills": "true"}

        headers = {
            "x-rapidapi-key": FRESH_API_KEY,
            "x-rapidapi-host": "fresh-linkedin-profile-data.p.rapidapi.com"
        }

        response = requests.get(url, headers=headers, params=querystring, timeout=15)

        if response.status_code == 200:
            data = response.json()

            # Extract current position from experiences
            current_company = None
            current_title = None
            if data.get('experiences') and len(data['experiences']) > 0:
                current_exp = data['experiences'][0]
                current_title = current_exp.get('title')
                current_company = current_exp.get('company')

            # Extract skills
            skills = []
            if data.get('skills'):
                skills = [skill if isinstance(skill, str) else skill.get('name') for skill in data['skills'][:10]]
                skills = [s for s in skills if s]  # Filter out None values

            return {
                'name': data.get('full_name') or data.get('name'),
                'headline': data.get('headline'),
                'summary': data.get('summary') or data.get('about'),
                'current_company': current_company,
                'current_title': current_title,
                'location': data.get('location') or data.get('city'),
                'skills': skills,
                'industry': data.get('industry')
            }
        else:
            print(f"Fresh API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"Error scraping LinkedIn profile {linkedin_url}: {e}")
        return None


@app.route('/api/run-networking-mode', methods=['POST'])
@login_required
def run_networking_mode():
    """Run networking mode to match org members with external attendees"""
    user_id = session['user_id']

    try:
        data = request.get_json()
        org_id = data.get('org_id')
        goal = data.get('goal', '').strip()
        attendee_list = data.get('attendee_list', '').strip()

        if not org_id or not goal or not attendee_list:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check subscription status and simulation count
        subscription_status = subscription_manager.get_user_subscription_status(user_id)

        # Count user's simulations
        cursor.execute('''
            SELECT COUNT(*) as sim_count FROM simulations
            WHERE created_by = %s
        ''', (user_id,))

        sim_count = cursor.fetchone()['sim_count']

        # Check if user needs subscription (20 free simulations)
        if not subscription_status['is_subscribed'] and sim_count >= 20:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Simulation limit reached',
                'message': f'You have used all 20 free simulations. Please subscribe to continue.',
                'simulations_used': sim_count,
                'requires_subscription': True
            }), 402  # Payment Required status code

        # Verify user is member of organization
        cursor.execute('''
            SELECT id FROM organization_members
            WHERE organization_id = %s AND user_id = %s AND is_active = TRUE
        ''', (org_id, user_id))

        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Not a member of this organization'}), 403

        # Get all active org members with profiles
        cursor.execute('''
            SELECT
                u.id, u.first_name, u.last_name,
                up.profile_data
            FROM organization_members om
            INNER JOIN users u ON om.user_id = u.id
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE om.organization_id = %s AND om.is_active = TRUE
        ''', (org_id,))

        members = cursor.fetchall()
        conn.close()

        # Parse profile data
        parsed_members = []
        for member in members:
            member_dict = dict(member)
            if member_dict.get('profile_data'):
                try:
                    member_dict['profile'] = json.loads(member_dict['profile_data'])
                except:
                    member_dict['profile'] = {}
            else:
                member_dict['profile'] = {}
            parsed_members.append(member_dict)

        members = parsed_members

        # Parse attendee list (format: "Name, LinkedIn URL" per line)
        attendees = []
        for line in attendee_list.split('\n'):
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                name = parts[0]
                linkedin = parts[1]
                # Scrape LinkedIn profile if URL provided
                linkedin_data = scrape_linkedin_profile(linkedin) if linkedin else None
                attendees.append({
                    'name': linkedin_data.get('name') if linkedin_data else name,
                    'linkedin': linkedin,
                    'linkedin_data': linkedin_data
                })
            elif len(parts) == 1:
                attendees.append({
                    'name': parts[0],
                    'linkedin': None,
                    'linkedin_data': None
                })

        if not attendees:
            return jsonify({'success': False, 'error': 'No valid attendees found in list'}), 400

        # Initialize OpenAI client
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY)

        # Analyze matches for each org member
        recommendations = {}

        for member in members:
            member_id = member['id']
            member_name = f"{member['first_name']} {member['last_name']}"
            member_profile = build_profile_summary(member.get('profile', {}), member_name)

            matches = []

            for attendee in attendees:
                # Build attendee profile from LinkedIn data
                attendee_info = f"External Attendee: {attendee['name']}"

                if attendee.get('linkedin_data'):
                    ld = attendee['linkedin_data']
                    attendee_info += f"\n- Current Role: {ld.get('current_title', 'Unknown')} at {ld.get('current_company', 'Unknown')}"
                    if ld.get('headline'):
                        attendee_info += f"\n- Headline: {ld['headline']}"
                    if ld.get('location'):
                        attendee_info += f"\n- Location: {ld['location']}"
                    if ld.get('industry'):
                        attendee_info += f"\n- Industry: {ld['industry']}"
                    if ld.get('skills'):
                        attendee_info += f"\n- Key Skills: {', '.join(ld['skills'][:5])}"
                    if ld.get('summary'):
                        summary_preview = ld['summary'][:200] + "..." if len(ld['summary']) > 200 else ld['summary']
                        attendee_info += f"\n- Summary: {summary_preview}"
                elif attendee.get('linkedin'):
                    attendee_info += f"\nLinkedIn: {attendee['linkedin']}"

                # Build networking analysis prompt
                prompt = f"""You are analyzing networking opportunities for a professional.

Goal: {goal}

Team Member: {member_profile}

{attendee_info}

Analyze whether this team member should connect with this attendee based on the networking goal.
Consider their backgrounds, skills, industries, and how they could mutually benefit each other.

Provide your analysis as JSON:
{{
    "score": 0.0-1.0,
    "reason": "2-3 sentences explaining why this connection would be valuable for achieving the goal"
}}"""

                try:
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are an expert networking strategist."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=150
                    )

                    response_text = completion.choices[0].message.content.strip()

                    # Parse JSON
                    if response_text.startswith('```'):
                        response_text = response_text.split('```')[1]
                        if response_text.startswith('json'):
                            response_text = response_text[4:]
                        response_text = response_text.strip()

                    result = json.loads(response_text)

                    # Get title from LinkedIn data if available
                    title = None
                    if attendee.get('linkedin_data'):
                        title = attendee['linkedin_data'].get('current_title')

                    matches.append({
                        'name': attendee['name'],
                        'title': title,
                        'linkedin': attendee.get('linkedin'),
                        'score': result.get('score', 0.5),
                        'reason': result.get('reason', 'Connection recommended')
                    })

                except Exception as e:
                    print(f"Error analyzing networking match: {e}")
                    # Get title from LinkedIn data if available
                    title = None
                    if attendee.get('linkedin_data'):
                        title = attendee['linkedin_data'].get('current_title')

                    matches.append({
                        'name': attendee['name'],
                        'title': title,
                        'linkedin': attendee.get('linkedin'),
                        'score': 0.5,
                        'reason': 'Unable to analyze connection'
                    })

            # Sort by score and keep top 5
            matches.sort(key=lambda x: x['score'], reverse=True)
            top_matches = matches[:min(5, len(matches))]

            recommendations[member_id] = {
                'top_matches': top_matches
            }

        return jsonify({
            'success': True,
            'recommendations': recommendations
        })

    except Exception as e:
        print(f"Error running networking mode: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def build_profile_summary(profile_data: dict, member_name: str) -> str:
    """Build a readable summary of a user's profile for the AI prompt"""
    if not profile_data:
        return f"{member_name} has not completed their personality profile yet."

    summary_parts = [f"Profile for {member_name}:"]

    # Add key personality dimensions
    personality_fields = {
        'decision_making': ('Decision Making', 'Logic-driven', 'Emotion-driven'),
        'social_energy': ('Social Energy', 'Intimate connections', 'Wide social circles'),
        'communication_depth': ('Communication', 'Surface-level', 'Deep conversations'),
        'conflict_approach': ('Conflict Style', 'Direct confrontation', 'Gentle discussion'),
        'life_pace': ('Life Pace', 'Structured routine', 'Spontaneous flow')
    }

    for field, (label, low_label, high_label) in personality_fields.items():
        if field in profile_data:
            value = profile_data[field]
            if isinstance(value, (int, float)):
                if value <= 3:
                    desc = f"Tends toward {low_label.lower()}"
                elif value >= 7:
                    desc = f"Tends toward {high_label.lower()}"
                else:
                    desc = f"Balanced between {low_label.lower()} and {high_label.lower()}"
                summary_parts.append(f"- {label}: {desc}")

    # Add categorical responses
    categorical_fields = {
        'friendship_superpower': 'Friendship Strength',
        'friend_support_style': 'Support Style',
        'stress_preference': 'Under Stress Prefers',
        'processing_style': 'Emotional Processing',
        'friend_motivation': 'Motivation for Connection'
    }

    for field, label in categorical_fields.items():
        if field in profile_data:
            value = profile_data[field]
            if value:
                readable_value = value.replace('_', ' ').title()
                summary_parts.append(f"- {label}: {readable_value}")

    # Add text responses
    text_fields = {
        'ideal_friendship_description': 'Ideal Relationship',
        'unique_interest': 'Unique Interest',
        'life_experience_impact': 'Formative Experience'
    }

    for field, label in text_fields.items():
        if field in profile_data:
            value = profile_data[field]
            if value and len(str(value).strip()) > 0:
                summary_parts.append(f"- {label}: {value}")

    return '\n'.join(summary_parts)


@app.route('/api/load-simulation/<int:simulation_id>', methods=['GET'])
@login_required
def load_simulation(simulation_id):
    """Load a historical simulation with all responses"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get simulation details
        cursor.execute('''
            SELECT s.id, s.organization_id, s.scenario_text, s.created_at, s.status
            FROM simulations s
            INNER JOIN organization_members om ON s.organization_id = om.organization_id
            WHERE s.id = %s AND om.user_id = %s AND om.is_active = TRUE
        ''', (simulation_id, user_id))

        simulation = cursor.fetchone()

        if not simulation:
            conn.close()
            return jsonify({'success': False, 'error': 'Simulation not found'}), 404

        # Get all responses for this simulation
        cursor.execute('''
            SELECT sr.user_id, sr.response_json
            FROM simulation_responses sr
            WHERE sr.simulation_id = %s
        ''', (simulation_id,))

        response_rows = cursor.fetchall()
        conn.close()

        # Parse responses
        responses = {}
        for row in response_rows:
            try:
                responses[row['user_id']] = json.loads(row['response_json'])
            except:
                responses[row['user_id']] = {'error': 'Failed to parse response'}

        return jsonify({
            'success': True,
            'simulation_id': simulation['id'],
            'scenario': simulation['scenario_text'],
            'responses': responses,
            'created_at': simulation['created_at'].isoformat() if simulation['created_at'] else None
        })

    except Exception as e:
        print(f"Error loading simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-simulation/<int:simulation_id>', methods=['DELETE'])
@login_required
def delete_simulation(simulation_id):
    """Delete a simulation and all its responses"""
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify user has permission to delete this simulation
        # User must be a member of the organization that owns the simulation
        cursor.execute('''
            SELECT s.id, s.organization_id, s.created_by
            FROM simulations s
            INNER JOIN organization_members om ON s.organization_id = om.organization_id
            WHERE s.id = %s AND om.user_id = %s AND om.is_active = TRUE
        ''', (simulation_id, user_id))

        simulation = cursor.fetchone()

        if not simulation:
            conn.close()
            return jsonify({'success': False, 'error': 'Simulation not found or access denied'}), 404

        # Delete simulation responses first (foreign key constraint)
        cursor.execute('DELETE FROM simulation_responses WHERE simulation_id = %s', (simulation_id,))

        # Delete the simulation
        cursor.execute('DELETE FROM simulations WHERE id = %s', (simulation_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Simulation deleted successfully'
        })

    except Exception as e:
        print(f"Error deleting simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ROUTES - V2 NETWORK MANAGEMENT
# ============================================================================

def render_networks_list(networks):
    """Helper function to render networks list"""
    if networks:
        network_items = []
        for network in networks:
            network_item = f'''
            <div class="network-item">
                <div class="network-info">
                    <h4>{network['name']}</h4>
                    <p>{network.get('description', '')} - {network['people_count']} people</p>
                </div>
                <div class="network-actions">
                    <a href="/network/{network['id']}" class="btn">View</a>
                </div>
            </div>
            '''
            network_items.append(network_item)

        networks_html = f'''
        <div class="networks-list">
            <h3>Your Networks ({len(networks)})</h3>
            {chr(10).join(network_items)}
        </div>
        '''
    else:
        networks_html = '<div class="networks-list"><p style="text-align: center; color: black;">No networks created yet</p></div>'

    return networks_html

@app.route('/network-mode')
@login_required
def network_mode():
    """V2 Network mode selection page"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    if not user_info:
        flash('Account information not found', 'error')
        return redirect('/login')

    # Check if user has completed profile
    if not user_info.get('profile_completed', False):
        flash('Please complete your profile first', 'warning')
        return redirect('/onboarding')

    # Get user's networks
    networks = network_manager.get_user_networks(user_id)

    content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Network Mode </title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url("https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=sentient@400,500,600,700&display=swap");

            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
                background: white;
                min-height: 100vh;
                padding: 2rem;
            }}

            .container {{
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 3rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}

            h1 {{
                font-family: "Sentient", sans-serif;
                color: black;
                font-size: 2.5rem;
                font-weight: 600;
                margin-bottom: 1rem;
                text-align: center;
            }}

            .subtitle {{
                text-align: center;
                color: black;
                font-size: 1.1rem;
                margin-bottom: 3rem;
            }}

            .action-cards {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 2rem;
                margin-bottom: 3rem;
            }}

            .action-card {{
                background: #f5f5f5;
                border: 2px solid #e2e8f0;
                border-radius: 16px;
                padding: 2rem;
                text-align: center;
                transition: all 0.3s ease;
                cursor: pointer;
            }}

            .action-card:hover {{
                border-color: black;
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.15);
            }}

            .action-card h3 {{
                color: black;
                font-size: 1.5rem;
                margin-bottom: 1rem;
                font-weight: 600;
            }}

            .action-card p {{
                color: black;
                margin-bottom: 1.5rem;
                line-height: 1.6;
            }}

            .btn {{
                background: black;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                transition: background 0.3s ease;
            }}

            .btn:hover {{
                background: #333;
                text-decoration: none;
                color: white;
            }}

            .btn-secondary {{
                background: white;
                color: black;
                border: 1px solid black;
            }}

            .btn-secondary:hover {{
                background: black;
                color: white;
            }}

            .networks-list {{
                margin-top: 2rem;
            }}

            .network-item {{
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 1.5rem;
                margin-bottom: 1rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            .network-info h4 {{
                color: black;
                margin-bottom: 0.5rem;
            }}

            .network-info p {{
                color: black;
                font-size: 0.9rem;
            }}

            .network-actions {{
                display: flex;
                gap: 1rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Network Mode</h1>
            <p class="subtitle">Analyze and visualize connections within your network</p>

            <div class="action-cards">
                <div class="action-card" onclick="location.href='/create-network'">
                    <h3> Create New Network</h3>
                    <p>Import a list of people and their LinkedIn profiles to see predicted compatibility</p>
                    <a href="/create-network" class="btn">Get Started</a>
                </div>

                <div class="action-card" onclick="location.href='/settings'">
                    <h3> Switch to Individual Mode</h3>
                    <p>Go back to the traditional one-on-one matching experience</p>
                    <a href="/settings" class="btn btn-secondary">Switch Mode</a>
                </div>
            </div>

            {render_networks_list(networks)}
        </div>
    </body>
    </html>
    '''

    return content

@app.route('/create-network', methods=['GET', 'POST'])
@login_required
def create_network():
    """Create a new network"""
    user_id = session['user_id']

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Network name is required', 'error')
            return redirect('/create-network')

        result = network_manager.create_network(user_id, name, description)

        if result['success']:
            flash('Network created successfully!', 'success')
            return redirect(f'/network/{result["network_id"]}/setup')
        else:
            flash(f'Error creating network: {result["error"]}', 'error')

    content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Create Network </title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Clash+Display:wght@200..700&display=swap");
            @import url("https://fonts.googleapis.com/css2?family=Satoshi:wght@300..900&display=swap");

            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
                background: white;
                min-height: 100vh;
                padding: 2rem;
            }

            .container {
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 3rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }

            h1 {
                font-family: "Sentient", sans-serif;
                color: black;
                font-size: 2.5rem;
                font-weight: 600;
                margin-bottom: 1rem;
                text-align: center;
            }

            .form-group {
                margin-bottom: 1.5rem;
            }

            label {
                display: block;
                color: black;
                font-weight: 600;
                margin-bottom: 0.5rem;
            }

            input, textarea {
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
                transition: border-color 0.3s ease;
            }

            input:focus, textarea:focus {
                outline: none;
                border-color: black;
            }

            textarea {
                height: 100px;
                resize: vertical;
            }

            .btn {
                background: white;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                width: 100%;
                text-align: center;
                font-size: 16px;
                transition: background 0.3s ease;
                cursor: pointer;
            }

            .btn:hover {
                background: #5a67d8;
            }

            .back-link {
                display: block;
                text-align: center;
                margin-top: 1rem;
                color: black;
                text-decoration: none;
            }

            .back-link:hover {
                color: black;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1> Create Network</h1>

            <form method="POST">
                <div class="form-group">
                    <label for="name">Network Name *</label>
                    <input type="text" id="name" name="name" required
                           placeholder="e.g., Tech Meetup Group, College Friends">
                </div>

                <div class="form-group">
                    <label for="description">Description</label>
                    <textarea id="description" name="description"
                              placeholder="Brief description of this network (optional)"></textarea>
                </div>

                <button type="submit" class="btn">Create Network</button>
            </form>

            <a href="/network-mode" class="back-link">← Back to Network Mode</a>
        </div>
    </body>
    </html>
    '''

    return content

def render_people_list(people):
    """Helper function to render people list"""
    if people:
        people_items = []
        for person in people:
            person_item = f'''
            <div class="person-item">
                <div class="person-info">
                    <h4>{person['name']}</h4>
                    <p>{person['linkedin_url'] if person['linkedin_url'] else 'No LinkedIn URL'}</p>
                </div>
            </div>
            '''
            people_items.append(person_item)

        return chr(10).join(people_items)
    else:
        return '<p style="text-align: center; color: black; padding: 2rem;">No people added yet</p>'

def render_proceed_section(network_id, people_count):
    """Helper function to render proceed section"""
    if people_count >= 2:
        return f'''
        <div class="proceed-section">
            <a href="/network/{network_id}" class="btn btn-success">
                🚀 Generate Network Visualization ({people_count} people)
            </a>
        </div>
        '''
    else:
        return '''
        <div class="proceed-section">
            <p style="color: black;">Add at least 2 people to generate network visualization</p>
        </div>
        '''

def render_network_visualization(network_id: int, people: List[Dict[str, Any]], compatibility_data: Dict[str, Any]) -> str:
    """Render interactive network visualization similar to V1 matching"""

    # Prepare data for JavaScript
    people_json = [
        {
            'id': person['id'],
            'name': person['name'],
            'linkedin_url': person.get('linkedin_url', ''),
            'x': 0,  # Will be calculated by JavaScript
            'y': 0   # Will be calculated by JavaScript
        }
        for person in people
    ]

    relationships = compatibility_data['relationships']
    connection_counts = compatibility_data['connection_counts']
    show_names = len(people) <= 10

    import json

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Network Visualization</title>
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Clash+Display:wght@200..700&display=swap");
            @import url("https://fonts.googleapis.com/css2?family=Satoshi:wght@300..900&display=swap");

            body {{
                font-family: 'Satoshi', 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
                margin: 0;
                padding: 20px;
                background: white;
                min-height: 100vh;
                color: white;
            }}

            .visualization-container {{
                max-width: 1200px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 30px;
                color: black;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            }}

            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}

            .header h1 {{
                font-family: 'Sentient', sans-serif;
                font-size: 2.5rem;
                font-weight: 600;
                margin: 0;
                background: white;
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}

            .controls {{
                text-align: center;
                margin-bottom: 20px;
            }}

            .btn {{
                background: white;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 25px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 5px;
                font-weight: 600;
                transition: all 0.3s ease;
            }}

            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
            }}

            .network-canvas {{
                width: 100%;
                height: 600px;
                border: 2px solid #e2e8f0;
                border-radius: 12px;
                background: #f7fafc;
                display: block;
                margin: 0 auto;
                cursor: move;
            }}

            .stats {{
                display: flex;
                justify-content: space-around;
                margin-top: 20px;
                padding: 20px;
                background: rgba(102, 126, 234, 0.1);
                border-radius: 12px;
            }}

            .stat {{
                text-align: center;
            }}

            .stat-value {{
                font-size: 2rem;
                font-weight: bold;
                color: black;
            }}

            .stat-label {{
                font-size: 0.9rem;
                color: black;
                margin-top: 5px;
            }}

            .legend {{
                margin-top: 20px;
                padding: 15px;
                background: rgba(255, 255, 255, 0.7);
                border-radius: 8px;
                font-size: 0.9rem;
            }}
        </style>
    </head>
    <body>
        <div class="visualization-container">
            <div class="header">
                <h1>Network Visualization</h1>
                <p>{len(people)} people • {len(relationships)} connections</p>
            </div>

            <div class="controls">
                <a href="/network/{network_id}/setup" class="btn">← Back to Setup</a>
                <button onclick="resetView()" class="btn">Reset View</button>
                <button onclick="toggleAnimation()" class="btn" id="animBtn">Pause Animation</button>
            </div>

            <canvas id="networkCanvas" class="network-canvas"></canvas>

            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{len(people)}</div>
                    <div class="stat-label">People</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len(relationships)}</div>
                    <div class="stat-label">Connections</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{max(connection_counts.values()) if connection_counts else 0}</div>
                    <div class="stat-label">Max Connections</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len([p for p in people if connection_counts.get(p['id'], 0) == 0])}</div>
                    <div class="stat-label">Isolated</div>
                </div>
            </div>

            <div class="legend">
                <strong>Interaction:</strong> Click on a person to highlight their connections •
                {"Names are always visible" if show_names else "Hover over dots to see names"} •
                Connected people cluster together • Drag to pan the view
            </div>
        </div>

        <script>
            const canvas = document.getElementById('networkCanvas');
            const ctx = canvas.getContext('2d');

            // Set canvas size
            canvas.width = canvas.offsetWidth;
            canvas.height = canvas.offsetHeight;

            // Data
            const people = {json.dumps(people_json)};
            const relationships = {json.dumps(relationships)};
            const showNames = {json.dumps(show_names)};
            const connectionCounts = {json.dumps(connection_counts)};

            // State
            let selectedPerson = null;
            let hoveredPerson = null;
            let animationRunning = true;
            let panOffset = {{x: 0, y: 0}};
            let isDragging = false;
            let dragStart = {{x: 0, y: 0}};

            // Initialize positions using clustering algorithm
            initializePositions();

            function initializePositions() {{
                const centerX = canvas.width / 2;
                const centerY = canvas.height / 2;
                const radius = Math.min(canvas.width, canvas.height) * 0.3;

                people.forEach((person, index) => {{
                    const connections = connectionCounts[person.id] || 0;

                    // Cluster highly connected people towards center
                    const clusterRadius = radius * (1 - connections * 0.1);
                    const angle = (index / people.length) * 2 * Math.PI;

                    person.x = centerX + Math.cos(angle) * clusterRadius;
                    person.y = centerY + Math.sin(angle) * clusterRadius;

                    // Add some randomness
                    person.x += (Math.random() - 0.5) * 100;
                    person.y += (Math.random() - 0.5) * 100;

                    // Keep within bounds
                    person.x = Math.max(50, Math.min(canvas.width - 50, person.x));
                    person.y = Math.max(50, Math.min(canvas.height - 50, person.y));

                    // Initialize velocity for animation
                    person.vx = (Math.random() - 0.5) * 2;
                    person.vy = (Math.random() - 0.5) * 2;
                }});
            }}

            function animate() {{
                if (!animationRunning) return;

                // Apply forces for clustering and separation
                people.forEach(person => {{
                    let fx = 0, fy = 0;

                    people.forEach(other => {{
                        if (person.id === other.id) return;

                        const dx = other.x - person.x;
                        const dy = other.y - person.y;
                        const distance = Math.sqrt(dx*dx + dy*dy);

                        if (distance < 1) return;

                        // Check if connected
                        const connected = relationships.some(r =>
                            (r.person1_id === person.id && r.person2_id === other.id) ||
                            (r.person2_id === person.id && r.person1_id === other.id)
                        );

                        if (connected) {{
                            // Attract connected people
                            const force = 0.001;
                            fx += dx * force;
                            fy += dy * force;
                        }} else {{
                            // Repel unconnected people
                            const force = 500 / (distance * distance);
                            fx -= (dx / distance) * force;
                            fy -= (dy / distance) * force;
                        }}
                    }});

                    // Apply forces with damping
                    person.vx = (person.vx + fx) * 0.9;
                    person.vy = (person.vy + fy) * 0.9;

                    // Update position
                    person.x += person.vx;
                    person.y += person.vy;

                    // Keep within bounds
                    person.x = Math.max(30, Math.min(canvas.width - 30, person.x));
                    person.y = Math.max(30, Math.min(canvas.height - 30, person.y));
                }});

                requestAnimationFrame(animate);
            }}

            function draw() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // Draw relationships first (behind dots)
                relationships.forEach(rel => {{
                    const person1 = people.find(p => p.id === rel.person1_id);
                    const person2 = people.find(p => p.id === rel.person2_id);

                    if (!person1 || !person2) return;

                    const isSelected = selectedPerson &&
                        (selectedPerson.id === person1.id || selectedPerson.id === person2.id);

                    ctx.strokeStyle = isSelected ? 'black' :
                        selectedPerson ? '#cbd5e0' : '#a0aec0';
                    ctx.lineWidth = isSelected ? 3 : 1;
                    ctx.globalAlpha = isSelected ? 1 : selectedPerson ? 0.3 : 0.6;

                    ctx.beginPath();
                    ctx.moveTo(person1.x + panOffset.x, person1.y + panOffset.y);
                    ctx.lineTo(person2.x + panOffset.x, person2.y + panOffset.y);
                    ctx.stroke();
                }});

                ctx.globalAlpha = 1;

                // Draw people as dots
                people.forEach(person => {{
                    const connections = connectionCounts[person.id] || 0;
                    const isSelected = selectedPerson && selectedPerson.id === person.id;
                    const isConnected = selectedPerson && relationships.some(r =>
                        (r.person1_id === selectedPerson.id && r.person2_id === person.id) ||
                        (r.person2_id === selectedPerson.id && r.person1_id === person.id)
                    );

                    // Determine color and size
                    let color = '#4a5568';  // Default gray
                    let size = 8 + connections * 2;  // Size based on connections

                    if (isSelected) {{
                        color = '#38a169';  // Green for selected (like V1)
                        size += 4;
                    }} else if (selectedPerson && isConnected) {{
                        color = 'black';  // Blue for connected
                    }} else if (selectedPerson) {{
                        color = '#a0aec0';  // Light gray for others when something is selected
                    }}

                    // Draw dot
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.arc(person.x + panOffset.x, person.y + panOffset.y, size, 0, 2 * Math.PI);
                    ctx.fill();

                    // Draw border
                    ctx.strokeStyle = '#ffffff';
                    ctx.lineWidth = 2;
                    ctx.stroke();

                    // Draw name if applicable
                    const showName = showNames || hoveredPerson === person;
                    if (showName) {{
                        ctx.fillStyle = 'black';
                        ctx.font = '12px Satoshi, sans-serif';
                        ctx.textAlign = 'center';
                        ctx.fillText(person.name, person.x + panOffset.x, person.y + panOffset.y - size - 8);
                    }}
                }});

                requestAnimationFrame(draw);
            }}

            // Event handlers
            canvas.addEventListener('click', (e) => {{
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left - panOffset.x;
                const y = e.clientY - rect.top - panOffset.y;

                let clickedPerson = null;
                people.forEach(person => {{
                    const distance = Math.sqrt((x - person.x)**2 + (y - person.y)**2);
                    if (distance <= 15) {{
                        clickedPerson = person;
                    }}
                }});

                selectedPerson = selectedPerson === clickedPerson ? null : clickedPerson;
            }});

            canvas.addEventListener('mousemove', (e) => {{
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left - panOffset.x;
                const y = e.clientY - rect.top - panOffset.y;

                if (isDragging) {{
                    panOffset.x = e.clientX - dragStart.x;
                    panOffset.y = e.clientY - dragStart.y;
                    return;
                }}

                hoveredPerson = null;
                people.forEach(person => {{
                    const distance = Math.sqrt((x - person.x)**2 + (y - person.y)**2);
                    if (distance <= 15) {{
                        hoveredPerson = person;
                    }}
                }});

                canvas.style.cursor = hoveredPerson ? 'pointer' : 'move';
            }});

            canvas.addEventListener('mousedown', (e) => {{
                isDragging = true;
                dragStart.x = e.clientX - panOffset.x;
                dragStart.y = e.clientY - panOffset.y;
                canvas.style.cursor = 'grabbing';
            }});

            canvas.addEventListener('mouseup', () => {{
                isDragging = false;
                canvas.style.cursor = 'move';
            }});

            canvas.addEventListener('mouseleave', () => {{
                hoveredPerson = null;
                isDragging = false;
                canvas.style.cursor = 'move';
            }});

            // Control functions
            function resetView() {{
                selectedPerson = null;
                panOffset = {{x: 0, y: 0}};
                initializePositions();
            }}

            function toggleAnimation() {{
                animationRunning = !animationRunning;
                document.getElementById('animBtn').textContent =
                    animationRunning ? 'Pause Animation' : 'Resume Animation';
                if (animationRunning) animate();
            }}

            // Start animation and rendering
            animate();
            draw();
        </script>
    </body>
    </html>
    '''

@app.route('/network/<int:network_id>/setup', methods=['GET', 'POST'])
@login_required
def network_setup(network_id):
    """Setup network by adding people"""
    user_id = session['user_id']

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_person':
            name = request.form.get('name', '').strip()
            linkedin_url = request.form.get('linkedin_url', '').strip()

            if name:
                result = network_manager.add_person_to_network(network_id, name, linkedin_url)
                if result['success']:
                    flash('Person added successfully!', 'success')
                else:
                    flash(f'Error adding person: {result["error"]}', 'error')

        elif action == 'import_csv':
            csv_data = request.form.get('csv_data', '').strip()
            print(f"CSV import action triggered. Data length: {len(csv_data)}")
            print(f"Form data keys: {list(request.form.keys())}")
            print(f"CSV data preview: {csv_data[:100]}...")

            if csv_data:
                result = network_manager.import_people_from_csv(network_id, csv_data)
                print(f"Import result: {result}")

                if result['success']:
                    flash(f'Imported {result["imported_count"]} people successfully!', 'success')
                    if result['errors']:
                        flash(f'Some errors occurred: {"; ".join(result["errors"])}', 'warning')
                else:
                    flash(f'Error importing CSV: {result["error"]}', 'error')
            else:
                print("No CSV data received")
                flash('No CSV data provided', 'error')

        return redirect(f'/network/{network_id}/setup')

    # Get current people in network
    people = network_manager.get_network_people(network_id)

    content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Setup Network </title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Clash+Display:wght@200..700&display=swap");
            @import url("https://fonts.googleapis.com/css2?family=Satoshi:wght@300..900&display=swap");

            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: 'Sentient', -apple-system, BlinkMacSystemFont, sans-serif;
                background: white;
                min-height: 100vh;
                padding: 2rem;
            }}

            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 3rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}

            h1 {{
                font-family: "Sentient", sans-serif;
                color: black;
                font-size: 2.5rem;
                font-weight: 600;
                margin-bottom: 1rem;
                text-align: center;
            }}

            .tabs {{
                display: flex;
                margin-bottom: 2rem;
                border-bottom: 2px solid #e2e8f0;
            }}

            .tab {{
                padding: 1rem 2rem;
                background: none;
                border: none;
                color: black;
                font-weight: 600;
                cursor: pointer;
                border-bottom: 2px solid transparent;
                transition: all 0.3s ease;
            }}

            .tab.active {{
                color: black;
                border-bottom-color: black;
            }}

            .tab-content {{
                display: none;
            }}

            .tab-content.active {{
                display: block;
            }}

            .form-group {{
                margin-bottom: 1.5rem;
            }}

            label {{
                display: block;
                color: black;
                font-weight: 600;
                margin-bottom: 0.5rem;
            }}

            input, textarea {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
                transition: border-color 0.3s ease;
            }}

            input:focus, textarea:focus {{
                outline: none;
                border-color: black;
            }}

            textarea {{
                height: 200px;
                resize: vertical;
                font-family: monospace;
            }}

            .btn {{
                background: white;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                text-decoration: none;
                display: inline-block;
                transition: background 0.3s ease;
                cursor: pointer;
            }}

            .btn:hover {{
                background: #5a67d8;
            }}

            .btn-success {{
                background: #48bb78;
            }}

            .btn-success:hover {{
                background: #38a169;
            }}

            .people-list {{
                margin-top: 2rem;
                padding-top: 2rem;
                border-top: 2px solid #e2e8f0;
            }}

            .person-item {{
                background: #f5f5f5;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 1rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            .person-info h4 {{
                color: black;
                margin-bottom: 0.25rem;
            }}

            .person-info p {{
                color: black;
                font-size: 0.9rem;
            }}

            .csv-example {{
                background: #f5f5f5;
                padding: 1rem;
                border-radius: 8px;
                margin-bottom: 1rem;
                font-family: monospace;
                font-size: 0.9rem;
                border: 1px solid #e2e8f0;
            }}

            .proceed-section {{
                text-align: center;
                margin-top: 2rem;
                padding-top: 2rem;
                border-top: 2px solid #e2e8f0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>👥 Setup Your Network</h1>

            <div class="tabs">
                <button class="tab active" onclick="showTab('manual')">Add Manually</button>
                <button class="tab" onclick="showTab('csv')">Import CSV</button>
            </div>

            <!-- Manual Entry Tab -->
            <div id="manual" class="tab-content active">
                <form method="POST">
                    <input type="hidden" name="action" value="add_person">
                    <div class="form-group">
                        <label for="name">Person's Name *</label>
                        <input type="text" id="name" name="name" required
                               placeholder="e.g., John Smith">
                    </div>

                    <div class="form-group">
                        <label for="linkedin_url">LinkedIn URL (optional)</label>
                        <input type="url" id="linkedin_url" name="linkedin_url"
                               placeholder="https://linkedin.com/in/johnsmith">
                    </div>

                    <button type="submit" class="btn">Add Person</button>
                </form>
            </div>

            <!-- CSV Import Tab -->
            <div id="csv" class="tab-content">
                <div class="csv-example">
                    <strong>CSV Format Example:</strong><br>
                    name,linkedin_url<br>
                    John Smith,https://linkedin.com/in/johnsmith<br>
                    Jane Doe,https://linkedin.com/in/janedoe<br>
                    Bob Johnson,
                </div>

                <form method="POST">
                    <input type="hidden" name="action" value="import_csv">
                    <div class="form-group">
                        <label for="csv_data">Paste CSV Data</label>
                        <textarea id="csv_data" name="csv_data" required
                                  placeholder="name,linkedin_url&#10;John Smith,https://linkedin.com/in/johnsmith&#10;Jane Doe,https://linkedin.com/in/janedoe"></textarea>
                    </div>

                    <button type="submit" class="btn">Import People</button>
                </form>
            </div>

            <!-- Current People List -->
            <div class="people-list">
                <h3>People in Network ({len(people)})</h3>
                {render_people_list(people)}
            </div>

            {render_proceed_section(network_id, len(people))}
        </div>

        <script>
            function showTab(tabName) {{
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => {{
                    tab.classList.remove('active');
                }});
                document.querySelectorAll('.tab').forEach(tab => {{
                    tab.classList.remove('active');
                }});

                // Show selected tab
                document.getElementById(tabName).classList.add('active');
                event.target.classList.add('active');
            }}
        </script>
    </body>
    </html>
    '''

    return content

@app.route('/network/<int:network_id>')
@login_required
def network_visualization(network_id):
    """Network visualization dashboard"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)

    # Get network people
    people = network_manager.get_network_people(network_id)

    if not people:
        flash('No people found in network', 'error')
        return redirect(f'/network/{network_id}/setup')

    # Generate compatibility matrix
    compatibility_data = network_manager.generate_network_compatibility(people)

    content = render_network_visualization(network_id, people, compatibility_data)
    return render_template_with_header(f"Network Visualization", content, user_info)

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
        
        # Handle matching mode update
        matching_mode = request.form.get('matching_mode', 'individual')
        if matching_mode in ['individual', 'network']:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET matching_mode = %s WHERE id = %s', (matching_mode, user_id))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error updating matching mode: {e}")

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
        
        flash('Profile updated successfully!', 'success')

        # Redirect based on matching mode
        if matching_mode == 'network':
            return redirect('/network-mode')
        else:
            flash('Finding new matches...', 'info')
            return redirect('/processing')
    
    # GET request - show the update form
    existing_profile = user_auth.get_user_profile(user_id)
    existing_blocked = user_auth.get_blocked_users(user_id)
    
    # Get current matching mode
    current_mode = user_info.get('matching_mode', 'individual')

    # Render update form with matching mode toggle
    content = f'''
    <div class="container">
        <h1 style="font-family: 'Sentient', 'Satoshi', sans-serif; font-size: 28px; text-align: center; margin-bottom: 32px; color: black;">Update Your Profile</h1>

        <form method="POST">

            <!-- Matching Mode Toggle -->
            <div style="background: #f8f9fa; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 2px solid #e9ecef;">
                <h3 style="font-family: 'Sentient', 'Satoshi', sans-serif; color: black; margin-bottom: 15px; font-size: 18px;">Matching Mode</h3>
                <p style="font-family: 'Satoshi', sans-serif; color: black; margin-bottom: 15px; font-size: 14px;">Choose how you want to use Connect:</p>

                <div style="display: grid; gap: 10px;">
                    <label style="display: flex; align-items: center; padding: 12px; background: {'#f0f0f0' if current_mode == 'individual' else 'white'}; border: 2px solid {'black' if current_mode == 'individual' else '#dee2e6'}; border-radius: 8px; cursor: pointer;">
                        <input type="radio" name="matching_mode" value="individual" {'checked' if current_mode == 'individual' else ''} style="margin-right: 10px;">
                        <div>
                            <strong style="font-family: 'Sentient', 'Satoshi', sans-serif; color: black;">Individual Mode</strong>
                            <div style="font-family: 'Satoshi', sans-serif; font-size: 12px; color: black;">Traditional one-on-one matching</div>
                        </div>
                    </label>

                    <label style="display: flex; align-items: center; padding: 12px; background: {'#f0f0f0' if current_mode == 'network' else 'white'}; border: 2px solid {'black' if current_mode == 'network' else '#dee2e6'}; border-radius: 8px; cursor: pointer;">
                        <input type="radio" name="matching_mode" value="network" {'checked' if current_mode == 'network' else ''} style="margin-right: 10px;">
                        <div>
                            <strong style="font-family: 'Sentient', 'Satoshi', sans-serif; color: black;">Network Mode</strong>
                            <div style="font-family: 'Satoshi', sans-serif; font-size: 12px; color: black;">Import and analyze connections within your network</div>
                        </div>
                    </label>
                </div>
            </div>

            <!-- Update Button -->
            <div style="text-align: center; margin-top: 30px;">
                <button type="submit" class="btn" style="font-family: 'Sentient', 'Satoshi', sans-serif; background: black; color: white; padding: 16px 32px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer;">
                    Update Settings & Profile
                </button>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header("Update Profile", content, user_info)



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
        conn = get_db_connection()
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

@app.route('/privacy-policy')
def privacy_policy():
    """Privacy policy page"""
    content = '''
    <div class="container">
        <h1>Privacy Policy</h1>
        <p><em>Last updated: September 16, 2025</em></p>

        <p>Since our platform is all about building trust and meaningful human connections, 
        we want to be clear about how we handle your data. This page explains what data we collect, 
        how we use it, and how we protect it every step of the way.</p>

        <h2>1. Who We Are</h2>
        <p>Pont Diagnostics Ltd (“Pont”, “we”, “us”, “our”) is committed to protecting your privacy. 
        We operate a human-to-human matchmaking and therapist-matching platform.</p>
        <ul>
            <li><strong>Company name:</strong> Pont Diagnostics Ltd</li>
            <li><strong>Company number:</strong> 16012024</li>
            <li><strong>Registered office:</strong> 124 City Road, London, EC1V 2NX, United Kingdom</li>
            <li><strong>Email:</strong> alessa@pont-diagnostics.com</li>
            <li><strong>Data Protection Lead:</strong> Alessa Weiler</li>
        </ul>

        <h2>2. Where This Privacy Policy Applies</h2>
        <p>This policy applies to all our services, including our app, website, and events. 
        If a specific service has its own privacy policy, that one will apply instead.</p>

        <h2>3. Data We Collect</h2>
        <h3>Data you give us</h3>
        <ul>
            <li><strong>Account Data:</strong> email, phone number, date of birth, and password (encrypted)</li>
            <li><strong>Profile Data:</strong> your responses, preferences, interests, and optional sensitive data (e.g. health, orientation)</li>
            <li><strong>Content:</strong> photos, audio, text, or other content you share (including chats)</li>
            <li><strong>Purchase Data:</strong> subscription or feature purchases (via secure third-party providers)</li>
        </ul>

        <h3>Data we collect automatically</h3>
        <ul>
            <li><strong>Usage Data:</strong> login times, features used, and interactions</li>
            <li><strong>Technical Data:</strong> device ID, IP address, app settings, crash reports, cookies</li>
            <li><strong>Geolocation Data:</strong> approximate location (if permission is granted)</li>
        </ul>

        <h3>Data from third parties</h3>
        <ul>
            <li>Basic info if you sign up via Apple/Google or link a social account</li>
            <li>Information about you if reported by another member or through support requests</li>
        </ul>

        <h2>4. How We Use Data</h2>
        <ul>
            <li>Provide our service: set up accounts, recommend matches, personalize experiences</li>
            <li>Improve Pont: test new features, analyze usage, make the platform safer</li>
            <li>Process payments: subscriptions, purchases, billing</li>
            <li>Keep the community safe: detect fraud, enforce terms, verify accounts</li>
            <li>Comply with legal obligations</li>
        </ul>
        <p><strong>We never sell your personal data to third parties.</strong></p>

        <h2>5. How We Protect and Share Data</h2>
        <ul>
            <li>All sensitive data is encrypted (AES-256)</li>
            <li>Profile and diagnostic data anonymized for matching or research</li>
            <li>Shared only as needed:
                <ul>
                    <li>With members: only what you choose to display</li>
                    <li>With service providers: hosting, analytics, payments</li>
                    <li>With therapists: only if you opt in</li>
                    <li>With authorities: only if legally required</li>
                </ul>
            </li>
        </ul>

        <h2>6. Your Rights</h2>
        <ul>
            <li><a href="/privacy/export-data">Export your data</a></li>
            <li><a href="/privacy/delete-account">Delete your account</a></li>
            <li>Update your profile anytime in settings</li>
            <li>Withdraw consent (e.g. location, health data) via device settings or by emailing admin@pont.world</li>
        </ul>

        <h2>7. Data Retention</h2>
        <ul>
            <li>Profiles deleted immediately on account closure</li>
            <li>Data retained for safety/legal reasons:
                <ul>
                    <li>3 months after account closure (safety window)</li>
                    <li>Up to 10 years for financial transactions</li>
                    <li>As long as necessary to prevent banned users rejoining</li>
                </ul>
            </li>
            <li>Aggregated, anonymized data may be kept for research and product improvement</li>
        </ul>

        <h2>8. Children’s Privacy</h2>
        <p>Pont is for adults 18+ only. We do not allow minors to use our service.</p>

        <h2>9. Changes to this Policy</h2>
        <p>We may update this policy as we grow and add features. 
        If significant changes are made, we’ll notify you in advance.</p>

        <h2>10. Contact Us</h2>
        <p>If you have questions or concerns, contact us:</p>
        <ul>
            <li><strong>Email:</strong> alessa@pont-diagnostics.com</li>
            <li><strong>Post:</strong> Pont Diagnostics Ltd, 124 City Road, London, EC1V 2NX, UK</li>
        </ul>
    </div>
    '''
    return render_template_with_header("Privacy Policy", content)

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page with UK legal framework"""
    
    from datetime import date
    current_date = date.today().strftime("%B %d, %Y")
    
    content = f'''
    <style>
        .terms-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: var(--color-charcoal);
        }}
        
        .terms-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2rem;
            background: var(--color-white);
            border-radius: 16px;
            border-left: 4px solid var(--color-emerald);
        }}
        
        .terms-title {{
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: 2.5rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: var(--color-charcoal);
        }}
        
        .last-updated {{
            font-style: italic;
            color: var(--color-gray-600);
            margin-bottom: 2rem;
        }}
        
        .terms-content {{
            background: var(--color-white);
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        
        .section-title {{
            font-family: 'Sentient', 'Satoshi', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            margin: 2rem 0 1rem 0;
            color: var(--color-emerald);
            border-bottom: 2px solid var(--color-sage);
            padding-bottom: 0.5rem;
        }}
        
        .subsection-title {{
            font-weight: 600;
            margin: 1.5rem 0 0.75rem 0;
            color: var(--color-charcoal);
            font-size: 1.125rem;
        }}
        
        .terms-content p {{
            margin-bottom: 1rem;
        }}
        
        .terms-content ul, .terms-content ol {{
            margin: 1rem 0 1rem 2rem;
        }}
        
        .terms-content li {{
            margin-bottom: 0.5rem;
        }}
        
        .important-notice {{
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            margin: 2rem 0;
            border-left: 4px solid var(--color-emerald);
        }}
        
        .contact-section {{
            background: var(--color-gray-50);
            padding: 2rem;
            border-radius: 12px;
            margin-top: 3rem;
            text-align: center;
        }}
        
        .back-link {{
            display: inline-block;
            background: white;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            margin-top: 2rem;
            transition: all 0.3s ease;
        }}
        
        .back-link:hover {{
            background: white;
            transform: translateY(-1px);
        }}
        
        strong {{
            color: var(--color-emerald);
        }}
        
        em {{
            color: var(--color-gray-600);
        }}
    </style>
    
    <div class="terms-container">
        <div class="terms-header">
            <h1 class="terms-title">Terms of Service</h1>
            <p class="last-updated">Last updated: {current_date}</p>
        </div>
        
        <div class="terms-content">
            <div class="important-notice">
                <strong>Important:</strong> By using Connect, you agree to these Terms of Service and our Privacy Policy. 
                Please read them carefully before creating an account.
            </div>
            
            <h2 class="section-title">1. About These Terms</h2>
            <p>
                These terms of service ("Terms") govern your use of the Connect friendship matching platform ("Service") 
                operated by [Your Company Name] ("we", "us", or "our"), a company registered in England and Wales.
            </p>
            <p>
                By accessing or using Connect, you agree to be bound by these Terms. If you disagree with any part of 
                these terms, you may not access the Service.
            </p>
            
            <h2 class="section-title">2. Description of Service</h2>
            <p>
                Connect is a friendship matching platform that uses artificial intelligence and personality analysis to help users 
                find compatible friendships. Our Service includes:
            </p>
            <ul>
                <li>Personality and compatibility assessment tools</li>
                <li>Research-backed matching algorithms based on compatibility factors</li>
                <li>Secure contact exchange between matched users</li>
                <li>Profile management and comprehensive privacy controls</li>
            </ul>
            
            <h2 class="section-title">3. User Accounts and Eligibility</h2>
            
            <div class="subsection-title">3.1 Age Requirements</div>
            <p>
                You must be at least 18 years old to use Connect. By creating an account, you represent and warrant 
                that you are at least 18 years of age and have the legal capacity to enter into these Terms.
            </p>
            
            <div class="subsection-title">3.2 Account Information</div>
            <p>When creating an account, you agree to:</p>
            <ul>
                <li>Provide accurate, current, and complete information during registration</li>
                <li>Maintain and promptly update your information to keep it accurate and complete</li>
                <li>Maintain the security and confidentiality of your password and account credentials</li>
                <li>Accept responsibility for all activities that occur under your account</li>
                <li>Notify us immediately of any unauthorised use of your account</li>
            </ul>
            
            <div class="subsection-title">3.3 Account Limitations</div>
            <p>
                You may only maintain one active account on Connect. Creating multiple accounts is prohibited and 
                may result in suspension of all associated accounts.
            </p>
            
            <h2 class="section-title">4. User Conduct and Acceptable Use</h2>
            
            <div class="subsection-title">4.1 Prohibited Activities</div>
            <p>You agree not to use Connect to:</p>
            <ul>
                <li>Engage in any unlawful activities or violate applicable laws and regulations</li>
                <li>Harass, abuse, threaten, or intimidate other users</li>
                <li>Impersonate any person or entity, or falsely represent your affiliation with any person or entity</li>
                <li>Provide false, misleading, or deceptive information in your profile or communications</li>
                <li>Send spam, unsolicited advertisements, or commercial communications</li>
                <li>Attempt to gain unauthorised access to other user accounts, our systems, or networks</li>
                <li>Use automated software, bots, or scripts to access or interact with the Service</li>
                <li>Collect or harvest personal information about other users without consent</li>
                <li>Engage in any form of discrimination based on protected characteristics</li>
            </ul>
            
            <div class="subsection-title">4.2 Profile Content Standards</div>
            <p>All profile content must comply with UK law and must not contain:</p>
            <ul>
                <li>Hate speech, discriminatory language, or content that promotes prejudice</li>
                <li>Defamatory, libellous, or false statements about individuals or organisations</li>
                <li>Personal information of third parties without their explicit consent</li>
                <li>Content that infringes intellectual property rights</li>
                <li>Promotional material, advertisements, or links to external commercial websites</li>
                <li>Content that violates any person's privacy or data protection rights</li>
            </ul>
            
            <h2 class="section-title">5. Data Protection and Privacy</h2>
            
            <div class="subsection-title">5.1 GDPR Compliance</div>
            <p>
                We process your personal data in accordance with the General Data Protection Regulation (GDPR) 
                and the Data Protection Act 2018. Our data practices are detailed in our Privacy Policy.
            </p>
            
            <div class="subsection-title">5.2 Data Security Measures</div>
            <p>
                We implement appropriate technical and organisational measures to protect your personal data, 
                including encryption, anonymisation, and secure storage. However, no method of data transmission 
                or storage is completely secure, and we cannot guarantee absolute security.
            </p>
            
            <div class="subsection-title">5.3 Your Data Rights</div>
            <p>Under UK data protection law, you have the right to:</p>
            <ul>
                <li>Access your personal data and obtain copies</li>
                <li>Rectify inaccurate or incomplete data</li>
                <li>Erase your personal data in certain circumstances</li>
                <li>Restrict processing of your data</li>
                <li>Data portability where technically feasible</li>
                <li>Object to processing based on legitimate interests</li>
            </ul>
            
            <h2 class="section-title">6. Matching Algorithm and Service Limitations</h2>
            
            <div class="subsection-title">6.1 Algorithm Functionality</div>
            <p>
                Our AI matching system analyses personality traits, values, and preferences to suggest compatible connections. 
                The system is designed to improve over time but has inherent limitations.
            </p>
            
            <div class="subsection-title">6.2 No Guarantees</div>
            <p>We expressly disclaim any warranties or guarantees regarding:</p>
            <ul>
                <li>The accuracy or reliability of matching predictions</li>
                <li>The success or longevity of friendships formed through the platform</li>
                <li>The behaviour or character of other users</li>
                <li>The outcome of meetings between matched users</li>
            </ul>
            
            <h2 class="section-title">7. Safety and Meeting Guidelines</h2>
            
            <div class="subsection-title">7.1 Personal Safety</div>
            <p>We strongly recommend that when meeting matches in person, you:</p>
            <ul>
                <li>Meet initially in public, well-lit locations with good mobile reception</li>
                <li>Inform a trusted friend or family member of your plans and expected return</li>
                <li>Trust your instincts and leave immediately if you feel uncomfortable</li>
                <li>Avoid sharing personal details like your home address or workplace initially</li>
                <li>Consider arranging your own transportation to and from meetings</li>
            </ul>
            
            <div class="subsection-title">7.2 Reporting and Safety Features</div>
            <p>
                If you experience harassment, inappropriate behaviour, or safety concerns, report the incident 
                immediately using our reporting tools or by contacting us directly. We investigate all reports 
                and may suspend or terminate accounts that violate our community standards.
            </p>
            
            <h2 class="section-title">8. Intellectual Property Rights</h2>
            <p>
                The Service, including its software, algorithms, design, content, and functionality, is owned by us 
                and is protected by copyright, trademark, and other intellectual property laws of England and Wales 
                and international treaties. You may not reproduce, distribute, modify, or create derivative works 
                without our express written consent.
            </p>
            
            <h2 class="section-title">9. Service Availability and Modifications</h2>
            
            <div class="subsection-title">9.1 Service Availability</div>
            <p>
                We aim to provide reliable service but cannot guarantee uninterrupted availability. We may 
                temporarily suspend the Service for maintenance, updates, or technical issues. We are not liable 
                for any inconvenience or losses resulting from service interruptions.
            </p>
            
            <div class="subsection-title">9.2 Changes to Terms</div>
            <p>
                We reserve the right to modify these Terms at any time. We will provide reasonable notice of 
                material changes via email or prominent platform notification. Your continued use of the Service 
                after such notice constitutes acceptance of the modified Terms.
            </p>
            
            <h2 class="section-title">10. Account Suspension and Termination</h2>
            
            <div class="subsection-title">10.1 Termination by You</div>
            <p>
                You may terminate your account at any time using the account deletion feature in your settings. 
                Upon termination, your personal data will be deleted in accordance with our Privacy Policy.
            </p>
            
            <div class="subsection-title">10.2 Termination by Us</div>
            <p>We may suspend or terminate your account immediately if you:</p>
            <ul>
                <li>Materially breach these Terms of Service</li>
                <li>Engage in conduct that harms other users or damages our reputation</li>
                <li>Provide false information during registration or use of the Service</li>
                <li>Attempt to circumvent our security measures or access controls</li>
                <li>Violate applicable laws while using our Service</li>
            </ul>
            
            <h2 class="section-title">11. Limitation of Liability and Disclaimers</h2>
            
            <div class="subsection-title">11.1 Service Provided "As Is"</div>
            <p>
                Connect is provided on an "as is" and "as available" basis. To the fullest extent permitted by 
                English law, we disclaim all warranties, whether express or implied, including warranties of 
                merchantability, fitness for a particular purpose, and non-infringement.
            </p>
            
            <div class="subsection-title">11.2 Exclusion of Liability</div>
            <p>
                Subject to applicable consumer protection laws, we exclude liability for any indirect, 
                incidental, special, consequential, or punitive damages, including but not limited to:
            </p>
            <ul>
                <li>Loss of profits, revenue, data, or business opportunities</li>
                <li>Emotional distress or reputational damage</li>
                <li>Damages resulting from interactions with other users</li>
                <li>Technical failures or data breaches beyond our reasonable control</li>
            </ul>
            
            <div class="subsection-title">11.3 Consumer Rights</div>
            <p>
                Nothing in these Terms excludes or limits our liability for death or personal injury caused by 
                our negligence, fraud, fraudulent misrepresentation, or any other liability that cannot be 
                excluded under English law. Your statutory consumer rights remain unaffected.
            </p>
            
            <h2 class="section-title">12. Indemnification</h2>
            <p>
                You agree to indemnify and hold harmless Connect, its officers, directors, employees, and agents 
                from any claims, damages, losses, liabilities, costs, or expenses (including reasonable legal fees) 
                arising from your use of the Service, violation of these Terms, or infringement of any rights of 
                another person or entity.
            </p>
            
            <h2 class="section-title">13. Governing Law and Dispute Resolution</h2>
            
            <div class="subsection-title">13.1 Governing Law</div>
            <p>
                These Terms are governed by and construed in accordance with the laws of England and Wales, 
                without regard to conflict of law principles.
            </p>
            
            <div class="subsection-title">13.2 Jurisdiction</div>
            <p>
                Any disputes arising from these Terms or your use of the Service shall be subject to the 
                exclusive jurisdiction of the courts of England and Wales. You agree to submit to the 
                personal jurisdiction of such courts.
            </p>
            
            <div class="subsection-title">13.3 Alternative Dispute Resolution</div>
            <p>
                Before pursuing formal legal proceedings, we encourage users to contact us directly to resolve 
                disputes amicably. We are committed to addressing legitimate concerns promptly and fairly.
            </p>
            
            <h2 class="section-title">14. Severability and Entire Agreement</h2>
            <p>
                If any provision of these Terms is deemed invalid or unenforceable by a court of competent 
                jurisdiction, the remaining provisions shall remain in full force and effect. These Terms, 
                together with our Privacy Policy, constitute the entire agreement between you and Connect 
                regarding the use of our Service.
            </p>
            
            <h2 class="section-title">15. Contact Information</h2>
            <p>
                For questions about these Terms of Service, please contact us:
            </p>
            <ul>
                <li><strong>Email:</strong> admin@pont.world</li>
                <li><strong>Post:</strong> [Your Company Name], [Your Business Address], England</li>
                <li><strong>Company Registration:</strong> [Companies House Number]</li>
            </ul>
            
            <p>
                For data protection enquiries, you may also contact the Information Commissioner's Office (ICO) 
                at ico.org.uk if you have concerns about how we handle your personal data.
            </p>
            
            <div class="contact-section">
                <p><strong>Questions about these terms?</strong></p>
                <p>Our team is available to clarify any provisions or address your concerns.</p>
                <a href="/dashboard" class="back-link">Back to Dashboard</a>
            </div>
        </div>
    </div>
    '''
    
    return render_template_with_header("Terms of Service", content)

# ============================================================================
# SUBSCRIPTION MANAGEMENT
# ============================================================================

@app.route('/admin/cleanup-customers')
def cleanup_invalid_customers():
    """Clean up invalid Stripe customer IDs - REMOVE AFTER USE"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clear invalid customer IDs
        cursor.execute('''
            UPDATE user_subscriptions 
            SET stripe_customer_id = NULL, stripe_subscription_id = NULL, status = 'inactive'
            WHERE stripe_customer_id IS NOT NULL
        ''')
        
        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        return f"Cleaned up {rows_updated} invalid customer records"
        
    except Exception as e:
        return f"Error: {e}"


@app.route('/admin/webhook-test')
def webhook_test_page():
    """Admin page to test webhook configuration"""
    admin_password = request.args.get('password')
    if admin_password != os.environ.get('ADMIN_PASSWORD', 'admin123'):
        return '''
        <form method="GET">
            <h2>Admin Access Required</h2>
            <input type="password" name="password" placeholder="Admin Password" required>
            <button type="submit">Access Admin Panel</button>
        </form>
        '''
    
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Webhook Configuration Test</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .status {{ padding: 10px; margin: 10px 0; border-radius: 4px; }}
            .success {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }}
            .error {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }}
            .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }}
        </style>
    </head>
    <body>
        <h1>Webhook Configuration Test</h1>
        
        <h2>Environment Check</h2>
        <div class="status {'success' if webhook_secret else 'error'}">
            <strong>STRIPE_WEBHOOK_SECRET:</strong> {'✓ Configured' if webhook_secret else '✗ Missing'}
        </div>
        
        <div class="status {'success' if webhook_secret and webhook_secret.startswith('whsec_') else 'warning'}">
            <strong>Webhook Secret Format:</strong> 
            {'✓ Valid format' if webhook_secret and webhook_secret.startswith('whsec_') else '⚠ Should start with whsec_'}
        </div>
        
        <h2>Test Instructions</h2>
        <ol>
            <li>In Stripe Dashboard, go to Developers → Webhooks</li>
            <li>Create endpoint: <code>https://yourdomain.com/webhook/stripe</code></li>
            <li>Select events: 
                <ul>
                    <li>checkout.session.completed</li>
                    <li>customer.subscription.created</li>
                    <li>customer.subscription.updated</li>
                    <li>customer.subscription.deleted</li>
                    <li>invoice.payment_failed</li>
                    <li>invoice.payment_succeeded</li>
                </ul>
            </li>
            <li>Copy the signing secret and set STRIPE_WEBHOOK_SECRET environment variable</li>
            <li>Use "Send test webhook" in Stripe Dashboard to test</li>
        </ol>
        
        <h2>Recent Webhook Events</h2>
        <a href="/admin/webhook-logs?password={admin_password}">View Webhook Logs</a>
        
        <h2>Quick Test</h2>
        <form action="/admin/test-webhook-endpoint" method="POST">
            <input type="hidden" name="password" value="{admin_password}">
            <button type="submit">Test Webhook Endpoint Availability</button>
        </form>
    </body>
    </html>
    '''


@app.route('/admin/test-webhook-endpoint', methods=['POST'])
def test_webhook_endpoint():
    """Test that the webhook endpoint is accessible"""
    admin_password = request.form.get('password')
    if admin_password != os.environ.get('ADMIN_PASSWORD', 'admin123'):
        return "Unauthorized", 401
    
    # This would normally be called by Stripe with proper headers
    # We're just testing that the endpoint responds correctly to invalid requests
    
    try:
        # Test with missing signature (should fail gracefully)
        response = app.test_client().post('/webhook/stripe', 
                                        data='{"test": "data"}',
                                        headers={'Content-Type': 'application/json'})
        
        if response.status_code == 400:
            return '''
            <h2>✓ Webhook Endpoint Test Passed</h2>
            <p>Endpoint correctly rejected request without valid signature.</p>
            <p><a href="/admin/webhook-test">Back to Webhook Test</a></p>
            '''
        else:
            return f'''
            <h2>⚠ Unexpected Response</h2>
            <p>Expected 400, got {response.status_code}</p>
            <p>Response: {response.get_data(as_text=True)}</p>
            '''
            
    except Exception as e:
        return f'''
        <h2>✗ Test Failed</h2>
        <p>Error: {e}</p>
        <p><a href="/admin/webhook-test">Back to Webhook Test</a></p>
        '''


@app.route('/admin/webhook-logs')
def webhook_logs():
    """Show recent webhook processing logs"""
    admin_password = request.args.get('password')
    if admin_password != os.environ.get('ADMIN_PASSWORD', 'admin123'):
        return "Unauthorized", 401
    
    try:
        # Get recent subscription changes
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, status, stripe_customer_id, stripe_subscription_id, 
                   updated_at, created_at
            FROM user_subscriptions 
            ORDER BY updated_at DESC 
            LIMIT 20
        ''')
        
        subscriptions = cursor.fetchall()
        conn.close()
        
        logs_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Webhook Logs</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
                .status-active { color: green; font-weight: bold; }
                .status-cancelled { color: red; }
                .status-past_due { color: orange; }
            </style>
        </head>
        <body>
            <h1>Recent Subscription Changes</h1>
            <table>
                <tr>
                    <th>User ID</th>
                    <th>Status</th>
                    <th>Customer ID</th>
                    <th>Subscription ID</th>
                    <th>Updated</th>
                    <th>Created</th>
                </tr>
        '''
        
        for sub in subscriptions:
            status_class = f"status-{sub['status']}"
            logs_html += f'''
            <tr>
                <td>{sub['user_id']}</td>
                <td class="{status_class}">{sub['status']}</td>
                <td>{sub['stripe_customer_id'] or 'N/A'}</td>
                <td>{sub['stripe_subscription_id'] or 'N/A'}</td>
                <td>{sub['updated_at']}</td>
                <td>{sub['created_at']}</td>
            </tr>
            '''
        
        logs_html += '''
            </table>
            <p><a href="/admin/webhook-test">Back to Webhook Test</a></p>
        </body>
        </html>
        '''
        
        return logs_html
        
    except Exception as e:
        return f"Error retrieving logs: {e}"

# ============================================================================
# ADMIN USER MANAGEMENT ROUTES
# ============================================================================

@app.route('/admin/users')
def admin_users():
    """Admin interface for managing users"""
    admin_password = request.args.get('password')
    if admin_password != os.environ.get('ADMIN_PASSWORD', 'admin123'):
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Access Required</title>
            <style>
                body { font-family: 'Sentient', sans-serif; padding: 40px; background: white; color: black; }
                .form-container { max-width: 400px; margin: 0 auto; padding: 30px; border: 1px solid #ddd; border-radius: 8px; }
                input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
                button { background: white; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
                button:hover { background: #333; }
            </style>
        </head>
        <body>
            <div class="form-container">
                <h2>Admin Access Required</h2>
                <form method="GET">
                    <input type="password" name="password" placeholder="Admin Password" required>
                    <button type="submit">Access User Management</button>
                </form>
            </div>
        </body>
        </html>
        '''

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all users with their basic info and subscription status
        cursor.execute('''
            SELECT
                u.id, u.email, u.first_name, u.last_name, u.created_at, u.last_login,
                u.profile_completed, u.is_active, u.email_encrypted, u.first_name_encrypted, u.last_name_encrypted,
                us.status as subscription_status
            FROM users u
            LEFT JOIN user_subscriptions us ON u.id = us.user_id
            ORDER BY u.created_at DESC
        ''')

        users = cursor.fetchall()
        conn.close()

        # Build the HTML response
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Management</title>
            <style>
                body { font-family: 'Sentient', sans-serif; padding: 20px; background: white; color: black; }
                .header { margin-bottom: 30px; }
                table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background: #f5f5f5; font-weight: bold; }
                tr:nth-child(even) { background: #f9f9f9; }
                .delete-btn { background: #dc3545; color: white; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
                .delete-btn:hover { background: #c82333; }
                .verified { color: black; font-weight: bold; }
                .unverified { color: #dc3545; }
                .actions { text-align: center; }
                .stats { display: flex; gap: 20px; margin-bottom: 20px; }
                .stat-box { background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }
            </style>
            <script>
                function deleteUser(userId, email) {
                    if (confirm('Are you sure you want to delete user: ' + email + '?\\n\\nThis will permanently delete all their data including:\\n- Profile information\\n- Messages\\n- Matches\\n- Subscription data\\n\\nThis action cannot be undone!')) {
                        fetch('/admin/delete-user', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                user_id: userId,
                                password: '$(admin_password)'
                            })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('User deleted successfully');
                                location.reload();
                            } else {
                                alert('Error: ' + data.message);
                            }
                        })
                        .catch(error => {
                            alert('Error deleting user: ' + error);
                        });
                    }
                }
            </script>
        </head>
        <body>
            <div class="header">
                <h1>User Management</h1>
                <div class="stats">
                    <div class="stat-box">
                        <h3>''' + str(len(users)) + '''</h3>
                        <p>Total Users</p>
                    </div>
                    <div class="stat-box">
                        <h3>''' + str(len([u for u in users if u.get('is_verified')])) + '''</h3>
                        <p>Verified Users</p>
                    </div>
                    <div class="stat-box">
                        <h3>''' + str(len([u for u in users if u.get('subscription_status') == 'active'])) + '''</h3>
                        <p>Active Subscribers</p>
                    </div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Age</th>
                        <th>Created</th>
                        <th>Last Login</th>
                        <th>Verified</th>
                        <th>Subscription</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''

        for user in users:
            # Try to decrypt encrypted data, fallback to plain text
            try:
                email = user.get('email') or (data_encryption.decrypt_sensitive_data(user['email_encrypted']) if user.get('email_encrypted') else 'N/A')
                first_name = user.get('first_name') or (data_encryption.decrypt_sensitive_data(user['first_name_encrypted']) if user.get('first_name_encrypted') else '')
                last_name = user.get('last_name') or (data_encryption.decrypt_sensitive_data(user['last_name_encrypted']) if user.get('last_name_encrypted') else '')
            except Exception:
                # If decryption fails, use plain text or N/A
                email = user.get('email') or 'N/A'
                first_name = user.get('first_name') or ''
                last_name = user.get('last_name') or ''

            name = f"{first_name} {last_name}".strip() or 'N/A'
            verified_status = '<span class="verified">Verified</span>' if user.get('is_verified') else '<span class="unverified">Unverified</span>'
            subscription = user.get('subscription_status') or 'None'

            html += f'''
                    <tr>
                        <td>{user['id']}</td>
                        <td>{email}</td>
                        <td>{name}</td>
                        <td>{user.get('age') or 'N/A'}</td>
                        <td>{user['created_at']}</td>
                        <td>{user.get('last_login') or 'Never'}</td>
                        <td>{verified_status}</td>
                        <td>{subscription}</td>
                        <td class="actions">
                            <button class="delete-btn" onclick="deleteUser({user['id']}, '{email}')">Delete</button>
                        </td>
                    </tr>
            '''

        html += '''
                </tbody>
            </table>

            <div style="margin-top: 30px;">
                <a href="/admin/verification-queue?password=''' + admin_password + '''">Verification Queue</a> |
                <a href="/admin/webhook-logs?password=''' + admin_password + '''">Webhook Logs</a>
            </div>
        </body>
        </html>
        '''

        return html.replace('$(admin_password)', admin_password)

    except Exception as e:
        return f"Error retrieving users: {e}"

@app.route('/admin/delete-user', methods=['POST'])
def admin_delete_user():
    """Admin endpoint to delete a user and all their data"""
    try:
        data = request.get_json()
        admin_password = data.get('password')
        user_id = data.get('user_id')

        # Verify admin password
        if admin_password != os.environ.get('ADMIN_PASSWORD', 'admin123'):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401

        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Get user email for logging
            cursor.execute('SELECT email FROM users WHERE id = %s', (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404

            user_email = user['email']

            # Delete user data in proper order (foreign key dependencies)

            # 1. Delete dependent network data first (to resolve foreign key constraint)
            cursor.execute('DELETE FROM network_viz_settings WHERE network_id IN (SELECT id FROM networks WHERE owner_id = %s)', (user_id,))
            cursor.execute('DELETE FROM network_relationships WHERE network_id IN (SELECT id FROM networks WHERE owner_id = %s)', (user_id,))
            cursor.execute('DELETE FROM network_people WHERE network_id IN (SELECT id FROM networks WHERE owner_id = %s)', (user_id,))
            cursor.execute('DELETE FROM networks WHERE owner_id = %s', (user_id,))

            # 2. Delete user matches
            cursor.execute('DELETE FROM user_matches WHERE user_id = %s OR matched_user_id = %s', (user_id, user_id))

            # 3. Delete contact requests
            cursor.execute('DELETE FROM contact_requests WHERE requester_id = %s OR requested_id = %s', (user_id, user_id))

            # 3. Delete blocked users
            cursor.execute('DELETE FROM blocked_users WHERE user_id = %s', (user_id,))

            # 4. Delete authentication data
            cursor.execute('DELETE FROM password_reset_tokens WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM identity_verification_requests WHERE user_id = %s', (user_id,))

            # 5. Delete subscription data
            cursor.execute('DELETE FROM user_subscriptions WHERE user_id = %s', (user_id,))

            # 6. Delete event data
            cursor.execute('DELETE FROM event_registrations WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM event_feedback WHERE user_id = %s', (user_id,))

            # 7. Delete other user data
            cursor.execute('DELETE FROM user_interactions WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM followup_tracking WHERE user1_id = %s OR user2_id = %s', (user_id, user_id))
            cursor.execute('DELETE FROM matching_usage WHERE user_id = %s', (user_id,))

            # 8. Delete user profile
            cursor.execute('DELETE FROM user_profiles WHERE user_id = %s', (user_id,))

            # 9. Finally delete the user
            cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))

            conn.commit()

            print(f"Admin deleted user: {user_email} (ID: {user_id})")

            return jsonify({'success': True, 'message': f'User {user_email} deleted successfully'})

        except Exception as e:
            conn.rollback()
            print(f"Error deleting user {user_id}: {e}")
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'})

        finally:
            conn.close()

    except Exception as e:
        print(f"Error in delete_user endpoint: {e}")
        return jsonify({'success': False, 'message': 'Server error'})


# Add webhook event logging for production monitoring
def log_webhook_event(event_type, event_id, user_id=None, status="success", error=None):
    """Log webhook events for monitoring and debugging"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create webhook_logs table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_id TEXT NOT NULL,
                user_id INTEGER,
                status TEXT NOT NULL,
                error_message TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert log entry
        cursor.execute('''
            INSERT INTO webhook_logs (event_type, event_id, user_id, status, error_message)
            VALUES (%s, %s, %s, %s, %s)
        ''', (event_type, event_id, user_id, status, error))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        # Don't let logging errors break webhook processing
        logger.error(f"Failed to log webhook event: {e}")


@app.route('/subscription/check')
@login_required
def check_subscription():
    """Check if user can run matching"""
    user_id = session['user_id']
    status = subscription_manager.get_user_subscription_status(user_id)
    return jsonify(status)

@app.route('/subscription/subscribe')
@login_required
def subscribe():
    """Create Stripe checkout session"""
    user_id = session['user_id']
    
    # Check if user already has active subscription
    status = subscription_manager.get_user_subscription_status(user_id)
    if status['is_subscribed']:
        flash('You already have an active subscription!', 'success')
        return redirect('/profile-settings')
    
    result = subscription_manager.create_checkout_session(user_id, request.url_root)
    
    if result['success']:
        return redirect(result['checkout_url'])
    else:
        flash(f"Error creating checkout: {result['error']}", 'error')
        return redirect('/subscription/plans')

@app.route('/subscription/plans')
@login_required
def subscription_plans():
    """Show subscription plans page"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    status = subscription_manager.get_user_subscription_status(user_id)
    
    content = f'''
    <style>
        .subscription-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            font-family: 'Satoshi', sans-serif;
        }}
        
        .subscription-header {{
            text-align: center;
            margin-bottom: 3rem;
            padding: 2.5rem 2rem;
            background: var(--color-white);
            border-radius: 20px;
            border-left: 4px solid var(--color-emerald);
        }}
        
        .plan-card {{
            background: var(--color-white);
            border-radius: 20px;
            padding: 2.5rem;
            margin: 2rem 0;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            border-left: 4px solid var(--color-sage);
            position: relative;
        }}
        
        .plan-popular {{
            border-left-color: var(--color-emerald);
            transform: scale(1.02);
        }}
        
        .plan-popular::before {{
            content: "Most Popular";
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        
        .plan-price {{
            font-family: 'Sentient', sans-serif;
            font-size: 2.5rem;
            font-weight: 600;
            color: var(--color-emerald);
            margin-bottom: 0.5rem;
        }}
        
        .plan-features {{
            list-style: none;
            padding: 0;
            margin: 1.5rem 0;
        }}
        
        .plan-features li {{
            padding: 0.5rem 0;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        
        .plan-features li::before {{
            content: "✓";
            color: var(--color-emerald);
            font-weight: bold;
            font-size: 1.1rem;
        }}
        
        .btn-subscribe {{
            background: white;
            color: white;
            padding: 1rem 2rem;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 600;
            font-size: 1rem;
            display: inline-block;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
            width: 100%;
            text-align: center;
        }}
        
        .btn-subscribe:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(22, 122, 96, 0.3);
        }}
        
        .btn-current {{
            background: var(--color-gray-600);
            cursor: not-allowed;
        }}
        
        .status-banner {{
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            text-align: center;
            font-weight: 500;
        }}
        
        .status-free {{
            background: white;
            color: var(--color-charcoal);
        }}
        
        .status-subscribed {{
            background: white;
            color: white;
        }}
    </style>
    
    <div class="subscription-container">
        <div class="subscription-header">
            <h1 style="font-family: 'Sentient', sans-serif; font-size: 2.5rem; margin-bottom: 1rem;">
                Upgrade Your Matching
            </h1>
            <p style="font-size: 1.125rem; color: var(--color-gray-600);">
                Get unlimited matches and find your perfect connections
            </p>
        </div>
        
        {render_subscription_status_banner(status)}
        
        <div class="plan-card">
            <h3 style="font-family: 'Sentient', sans-serif; font-size: 1.5rem; margin-bottom: 1rem;">
                Free Plan
            </h3>
            <div class="plan-price">£0<span style="font-size: 1rem; color: var(--color-gray-600);">/month</span></div>
            
            <ul class="plan-features">
                <li>1 free match run per month</li>
                <li>Basic compatibility analysis</li>
                <li>Contact request system</li>
                <li>Profile creation</li>
            </ul>
            
            <div style="text-align: center; margin-top: 2rem;">
                {f'<div class="btn-subscribe btn-current">Current Plan</div>' if not status['is_subscribed'] else '<div class="btn-subscribe" style="opacity: 0.6;">Free Tier</div>'}
            </div>
            
            <div style="text-align: center; margin-top: 1rem; font-size: 0.875rem; color: var(--color-gray-600);">
                Free matches remaining: {status['free_matches_remaining']}
            </div>
        </div>
        
        <div class="plan-card plan-popular">
            <h3 style="font-family: 'Sentient', sans-serif; font-size: 1.5rem; margin-bottom: 1rem;">
                Premium Matching
            </h3>
            <div class="plan-price">£9.99<span style="font-size: 1rem; color: var(--color-gray-600);">/month</span></div>
            
            <ul class="plan-features">
                <li>Unlimited match runs</li>
                <li>Enhanced AI analysis</li>
                <li>Priority matching algorithm</li>
                <li>Advanced compatibility insights</li>
                <li>Exclusive match filters</li>
                <li>24/7 support</li>
            </ul>
            
            <div style="text-align: center; margin-top: 2rem;">
                {render_subscription_button(status)}
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 3rem;">
            <a href="/dashboard" style="color: var(--color-emerald); text-decoration: none; font-weight: 500;">
                ← Back to Dashboard
            </a>
        </div>
    </div>
    '''
    
    return render_template_with_header("Subscription Plans", content, user_info)

def render_subscription_status_banner(status: Dict) -> str:
    """Render status banner based on subscription"""
    if status['is_subscribed']:
        expires = status.get('expires_at', 'Unknown')
        return f'''
        <div class="status-banner status-subscribed">
            ✓ Premium subscriber - Unlimited matching until {expires}
        </div>
        '''
    else:
        remaining = status['free_matches_remaining']
        return f'''
        <div class="status-banner status-free">
            Free Plan - {remaining} free match{"" if remaining == 1 else "es"} remaining this month
        </div>
        '''

def render_subscription_button(status: Dict) -> str:
    """Render appropriate subscription button"""
    if status['is_subscribed']:
        return '<div class="btn-subscribe btn-current">Current Plan</div>'
    else:
        return '<a href="/subscription/subscribe" class="btn-subscribe">Upgrade to Premium</a>'

@app.route('/subscription/success')
@login_required
def subscription_success():
    """Handle successful subscription"""
    session_id = request.args.get('session_id')
    
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == 'paid':
                flash('Welcome to Premium! You now have unlimited matching.', 'success')
            else:
                flash('Payment is being processed. You will receive confirmation shortly.', 'success')
        except Exception as e:
            flash('Subscription activated successfully!', 'success')
    
    return redirect('/dashboard')

@app.route('/subscription/manage')
@login_required
def manage_subscription():
    """Redirect to Stripe customer portal for subscription management"""
    user_id = session['user_id']
    
    try:
        # Get the customer's Stripe customer ID
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result['stripe_customer_id']:
            flash('No active subscription found', 'error')
            return redirect('/profile-settings')
        
        # Create Stripe customer portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=result['stripe_customer_id'],
            return_url=request.url_root + 'profile-settings'
        )
        
        return redirect(portal_session.url)
        
    except Exception as e:
        print(f"Error creating portal session: {e}")
        flash('Unable to access subscription management. Please try again.', 'error')
        return redirect('/profile-settings')

@app.route('/subscription/cancel', methods=['GET', 'POST'])
@login_required
def cancel_subscription():
    """Cancel subscription confirmation page"""
    user_id = session['user_id']
    user_info = user_auth.get_user_info(user_id)
    
    if request.method == 'POST':
        confirm = request.form.get('confirm_cancel')
        if confirm == 'yes':
            try:
                result = subscription_manager.cancel_subscription(user_id)
                if result['success']:
                    flash('Subscription cancelled successfully. You can continue using Premium features until your current billing period ends.', 'success')
                else:
                    flash(f'Error cancelling subscription: {result["error"]}', 'error')
            except Exception as e:
                flash('Unable to cancel subscription. Please contact support.', 'error')
        
        return redirect('/profile-settings')
    
    # Show cancellation confirmation page
    content = '''
    <div class="container" style="max-width: 600px;">
        <h1 style="color: #dc3545; text-align: center; margin-bottom: 2rem;">Cancel Subscription</h1>
        
        <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
            <h3 style="color: #856404; margin-bottom: 1rem;">Before you cancel:</h3>
            <ul style="color: #856404;">
                <li>You'll lose access to unlimited matching</li>
                <li>You'll return to 1 free match per month</li>
                <li>Algorithm boost will no longer be available</li>
                <li>You can resubscribe anytime</li>
            </ul>
        </div>
        
        <form method="POST">
            <div style="text-align: center;">
                <p style="margin-bottom: 2rem;">Are you sure you want to cancel your Premium subscription?</p>
                
                <div style="display: flex; gap: 1rem; justify-content: center;">
                    <a href="/profile-settings" class="btn btn-secondary">Keep Subscription</a>
                    <button type="submit" name="confirm_cancel" value="yes" 
                            class="btn" style="background: white; color: white;">
                        Yes, Cancel Subscription
                    </button>
                </div>
            </div>
        </form>
    </div>
    '''
    
    return render_template_with_header("Cancel Subscription", content, user_info)

@app.route('/subscription/cancelled')
@login_required
def subscription_cancelled():
    """Handle cancelled subscription"""
    flash('Subscription cancelled. You can upgrade anytime from your dashboard.', 'error')
    return redirect('/subscription/plans')



def handle_checkout_completion_secure(session):
        """Handle successful checkout with proper error handling"""
        try:
            user_id = session['metadata'].get('user_id')
            if not user_id:
                logger.error(f"Missing user_id in session metadata: {session['id']}")
                return
            
            user_id = int(user_id)
            customer_id = session['customer']
            subscription_id = session['subscription']
            
            logger.info(f"Processing checkout completion for user {user_id}, session {session['id']}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Use INSERT ... ON CONFLICT for atomic upsert
                cursor.execute('''
                    INSERT INTO user_subscriptions 
                    (user_id, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at)
                    VALUES (%s, %s, %s, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        stripe_customer_id = EXCLUDED.stripe_customer_id,
                        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                ''', (user_id, customer_id, subscription_id))
                
                conn.commit()
                logger.info(f"Successfully activated subscription for user {user_id}")
                
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error for user {user_id}: {db_error}")
                raise
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error handling checkout completion: {e}")
            raise


def handle_subscription_created_secure(subscription):
        """Handle subscription creation with validation"""
        try:
            customer_id = subscription['customer']
            subscription_id = subscription['id']
            status = subscription['status']
            
            # Get subscription details from Stripe
            current_period_end = subscription.get('current_period_end')
            cancel_at_period_end = subscription.get('cancel_at_period_end', False)
            
            logger.info(f"Processing subscription creation: {subscription_id}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Find user by customer ID and update subscription details
                cursor.execute('''
                    UPDATE user_subscriptions 
                    SET stripe_subscription_id = %s, 
                        status = %s,
                        current_period_end = to_timestamp(%s),
                        cancel_at_period_end = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE stripe_customer_id = %s
                ''', (subscription_id, status, current_period_end, cancel_at_period_end, customer_id))
                
                if cursor.rowcount == 0:
                    logger.warning(f"No user found for customer {customer_id}")
                else:
                    logger.info(f"Updated subscription {subscription_id} for customer {customer_id}")
                
                conn.commit()
                
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error for subscription {subscription_id}: {db_error}")
                raise
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error handling subscription creation: {e}")
            raise


def handle_subscription_updated_secure(subscription):
        """Handle subscription updates with comprehensive field updates"""
        try:
            subscription_id = subscription['id']
            status = subscription['status']
            current_period_end = subscription.get('current_period_end')
            cancel_at_period_end = subscription.get('cancel_at_period_end', False)
            
            logger.info(f"Processing subscription update: {subscription_id} -> {status}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    UPDATE user_subscriptions 
                    SET status = %s, 
                        current_period_end = to_timestamp(%s), 
                        cancel_at_period_end = %s, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE stripe_subscription_id = %s
                ''', (status, current_period_end, cancel_at_period_end, subscription_id))
                
                if cursor.rowcount == 0:
                    logger.warning(f"No subscription found with ID {subscription_id}")
                else:
                    logger.info(f"Updated subscription {subscription_id} to status: {status}")
                
                conn.commit()
                
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error updating subscription {subscription_id}: {db_error}")
                raise
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error handling subscription update: {e}")
            raise


def handle_subscription_deleted_secure(subscription):
        """Handle subscription cancellation"""
        try:
            subscription_id = subscription['id']
            
            logger.info(f"Processing subscription deletion: {subscription_id}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    UPDATE user_subscriptions 
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE stripe_subscription_id = %s
                ''', (subscription_id,))
                
                if cursor.rowcount == 0:
                    logger.warning(f"No subscription found with ID {subscription_id}")
                else:
                    logger.info(f"Cancelled subscription {subscription_id}")
                
                conn.commit()
                
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error cancelling subscription {subscription_id}: {db_error}")
                raise
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error handling subscription deletion: {e}")
            raise


def handle_payment_failed_secure(invoice):
        """Handle failed payment attempts"""
        try:
            subscription_id = invoice.get('subscription')
            customer_id = invoice['customer']
            attempt_count = invoice.get('attempt_count', 0)
            
            logger.warning(f"Payment failed for customer {customer_id}, attempt {attempt_count}")
            
            # You might want to:
            # 1. Send notification email to user
            # 2. Update subscription status if final attempt
            # 3. Log for analytics
            
            if attempt_count >= 3:  # Stripe's default final attempt
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    cursor.execute('''
                        UPDATE user_subscriptions 
                        SET status = 'past_due', updated_at = CURRENT_TIMESTAMP
                        WHERE stripe_customer_id = %s
                    ''', (customer_id,))
                    
                    conn.commit()
                    logger.info(f"Marked subscription as past_due for customer {customer_id}")
                    
                except Exception as db_error:
                    conn.rollback()
                    logger.error(f"Database error marking past_due for customer {customer_id}: {db_error}")
                    raise
                    
                finally:
                    conn.close()
            
        except Exception as e:
            logger.error(f"Error handling payment failure: {e}")
            raise


def handle_payment_succeeded_secure(invoice):
        """Handle successful payment"""
        try:
            subscription_id = invoice.get('subscription')
            customer_id = invoice['customer']
            
            logger.info(f"Payment succeeded for customer {customer_id}")
            
            # Ensure subscription is marked as active
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    UPDATE user_subscriptions 
                    SET status = 'active', updated_at = CURRENT_TIMESTAMP
                    WHERE stripe_customer_id = %s AND status IN ('past_due', 'unpaid')
                ''', (customer_id,))
                
                if cursor.rowcount > 0:
                    logger.info(f"Reactivated subscription for customer {customer_id}")
                
                conn.commit()
                
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error reactivating subscription for customer {customer_id}: {db_error}")
                raise
                
            finally:
                conn.close()
            
        except Exception as e:
            logger.error(f"Error handling payment success: {e}")
            raise


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/webhook/stripe', methods=['POST'])
def secure_stripe_webhook():
    """
    Secure Stripe webhook handler with proper signature verification
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    if not endpoint_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return jsonify({'error': 'Webhook secret not configured'}), 500
    
    if not sig_header:
        logger.error("Missing Stripe signature header")
        return jsonify({'error': 'Missing signature'}), 400
    
    try:
        # Verify the webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
        logger.info(f"Verified webhook event: {event['type']} - {event['id']}")
        
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid payload: {e}")
        return jsonify({'error': 'Invalid payload'}), 400
        
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid signature: {e}")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle the verified event
    try:
        event_type = event['type']
        
        if event_type == 'checkout.session.completed':
            handle_checkout_completion_secure(event['data']['object'])
            
        elif event_type == 'customer.subscription.created':
            handle_subscription_created_secure(event['data']['object'])
            
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated_secure(event['data']['object'])
            
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted_secure(event['data']['object'])
            
        elif event_type == 'invoice.payment_failed':
            handle_payment_failed_secure(event['data']['object'])
            
        elif event_type == 'invoice.payment_succeeded':
            handle_payment_succeeded_secure(event['data']['object'])
            
        else:
            logger.info(f"Unhandled event type: {event_type}")
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook event {event['id']}: {e}")
        return jsonify({'error': 'Processing failed'}), 500


def handle_checkout_completion(session):
    """Handle successful checkout"""
    try:
        user_id = int(session['metadata']['user_id'])
        customer_id = session['customer']
        subscription_id = session['subscription']
        
        print(f"Processing checkout completion for user {user_id}")
        
        # Update or create subscription record
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if subscription record exists
        cursor.execute('SELECT id FROM user_subscriptions WHERE user_id = %s', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            cursor.execute('''
                UPDATE user_subscriptions 
                SET stripe_customer_id = %s, stripe_subscription_id = %s, 
                    status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (customer_id, subscription_id, user_id))
        else:
            # Create new record
            cursor.execute('''
                INSERT INTO user_subscriptions 
                (user_id, stripe_customer_id, stripe_subscription_id, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (user_id, customer_id, subscription_id))
        
        conn.commit()
        conn.close()
        
        print(f"✓ Subscription activated for user {user_id}")
        
    except Exception as e:
        print(f"Error handling checkout completion: {e}")

def handle_subscription_created(subscription):
    """Handle subscription creation"""
    try:
        customer_id = subscription['customer']
        subscription_id = subscription['id']
        status = subscription['status']
        
        # Find user by customer ID
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM user_subscriptions WHERE stripe_customer_id = %s', (customer_id,))
        result = cursor.fetchone()
        
        if result:
            user_id = result['user_id']
            cursor.execute('''
                UPDATE user_subscriptions 
                SET stripe_subscription_id = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (subscription_id, status, user_id))
            conn.commit()
            print(f"✓ Subscription created for user {user_id}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error handling subscription creation: {e}")

def handle_subscription_updated(subscription):
    """Handle subscription updates"""
    try:
        subscription_id = subscription['id']
        status = subscription['status']
        current_period_end = subscription['current_period_end']
        cancel_at_period_end = subscription['cancel_at_period_end']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE user_subscriptions 
            SET status = %s, current_period_end = to_timestamp(%s), 
                cancel_at_period_end = %s, updated_at = CURRENT_TIMESTAMP
            WHERE stripe_subscription_id = %s
        ''', (status, current_period_end, cancel_at_period_end, subscription_id))
        
        conn.commit()
        conn.close()
        
        print(f"✓ Subscription {subscription_id} updated to status: {status}")
        
    except Exception as e:
        print(f"Error handling subscription update: {e}")

def handle_subscription_deleted(subscription):
    """Handle subscription cancellation"""
    try:
        subscription_id = subscription['id']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE user_subscriptions 
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE stripe_subscription_id = %s
        ''', (subscription_id,))
        
        conn.commit()
        conn.close()
        
        print(f"✓ Subscription {subscription_id} cancelled")
        
    except Exception as e:
        print(f"Error handling subscription deletion: {e}")

# ============================================================================
# MAIN APPLICATION RUNNER
# ============================================================================

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Create necessary directories
    os.makedirs('data', exist_ok=True)
    
    print("\n" + "="*60)
    print("💜 USER MATCHING PLATFORM")
    print("="*60)
    print("🌐 URL: http://localhost:8080")
    print("📝 Features: User profiles + AI matching + Block lists")
    print("🔒 Security: Full authentication + privacy controls")
    print("📊 Database: users.db")
    print("🎯 Matching: User-to-user compatibility")
    print("="*60 + "\n")
    
    # Run the app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)