import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import secrets
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any  # Add this line

# ============================================================================
# DATA ANONYMIZATION
# ============================================================================
class DataEncryption:
    """Handles all encryption and anonymization for user data"""
    
    def __init__(self):
        self.master_key = self._get_or_create_master_key()
        self.fernet = Fernet(self.master_key)
    
    def _get_or_create_master_key(self):
        """Get master encryption key from environment or create new one"""
        key_env = os.environ.get('ENCRYPTION_MASTER_KEY')
        if key_env:
            return key_env.encode()
        
        # Generate new key if none exists
        password = os.environ.get('ENCRYPTION_PASSWORD', 'default-change-in-production')
        salt = os.environ.get('ENCRYPTION_SALT', 'default-salt-change-in-production').encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data like email, phone, personal info"""
        if not data:
            return data
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        if not encrypted_data:
            return encrypted_data
        return self.fernet.decrypt(encrypted_data.encode()).decode()
    
    def hash_for_matching(self, data: str) -> str:
        """Create one-way hash for matching purposes (cannot be reversed)"""
        if not data:
            return data
        return hashlib.sha256(f"{data}_{os.environ.get('HASH_SALT', 'default-salt')}".encode()).hexdigest()
    
    def generate_anonymous_id(self) -> str:
        """Generate anonymous ID for user"""
        return secrets.token_urlsafe(16)
class GDPRCompliance:
    """Handle GDPR compliance features"""
    
    def __init__(self, user_auth_system, data_encryption, get_db_connection):
        self.user_auth = user_auth_system
        self.encryption = data_encryption
        self.get_db_connection = get_db_connection
    
    def export_user_data(self, user_id: int) -> Dict[str, Any]:
        """Export all user data in readable format (GDPR Article 15)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get user data
            cursor.execute('''
                SELECT anonymous_id, email_encrypted, first_name_encrypted, 
                       last_name_encrypted, phone_encrypted, created_at, data_consent_date
                FROM users WHERE id = %s
            ''', (user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return {'error': 'User not found'}
            
            anonymous_id = user_data[0]
            
            # Decrypt personal data
            decrypted_data = {
                'email': self.encryption.decrypt_sensitive_data(user_data[1]) if user_data[1] else None,
                'first_name': self.encryption.decrypt_sensitive_data(user_data[2]) if user_data[2] else None,
                'last_name': self.encryption.decrypt_sensitive_data(user_data[3]) if user_data[3] else None,
                'phone': self.encryption.decrypt_sensitive_data(user_data[4]) if user_data[4] else None,
                'created_at': user_data[5],
                'data_consent_date': user_data[6]
            }
            
            # Get profile data
            cursor.execute('SELECT profile_data_encrypted FROM anonymous_profiles WHERE anonymous_id = %s', 
                          (anonymous_id,))
            profile_result = cursor.fetchone()
            if profile_result:
                encrypted_profile = profile_result[0]
                profile_json = self.encryption.decrypt_sensitive_data(encrypted_profile)
                decrypted_data['profile'] = json.loads(profile_json)
            
            # Get processing log
            cursor.execute('''
                SELECT action, purpose, timestamp 
                FROM data_processing_log 
                WHERE anonymous_id = %s
                ORDER BY timestamp DESC
            ''', (anonymous_id,))
            processing_log = cursor.fetchall()
            decrypted_data['processing_history'] = [
                {'action': row[0], 'purpose': row[1], 'timestamp': row[2]}
                for row in processing_log
            ]
            
            conn.close()
            return decrypted_data
            
        except Exception as e:
            return {'error': f'Data export failed: {str(e)}'}
    
    def delete_user_data(self, user_id: int) -> Dict[str, Any]:
        """Permanently delete all user data (GDPR Article 17)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get anonymous ID
            cursor.execute('SELECT anonymous_id FROM users WHERE id = %s', (user_id,))
            result = cursor.fetchone()
            if not result:
                return {'success': False, 'error': 'User not found'}
            
            anonymous_id = result[0]
            
            # Delete all related data
            cursor.execute('DELETE FROM anonymous_profiles WHERE anonymous_id = %s', (anonymous_id,))
            cursor.execute('DELETE FROM data_processing_log WHERE anonymous_id = %s', (anonymous_id,))
            cursor.execute('DELETE FROM user_matches WHERE user_id = %s OR matched_user_id = %s', 
                          (user_id, user_id))
            cursor.execute('DELETE FROM contact_requests WHERE requester_id = %s OR requested_id = %s', 
                          (user_id, user_id))
            cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
            
            # Log deletion
            cursor.execute('''
                INSERT INTO data_processing_log (anonymous_id, action, purpose)
                VALUES (%s, 'data_deletion', 'user_request')
            ''', (anonymous_id,))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': 'All user data permanently deleted'}
            
        except Exception as e:
            return {'success': False, 'error': f'Deletion failed: {str(e)}'}
