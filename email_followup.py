import psycopg2
import threading
import secrets
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_FROM = os.environ.get('EMAIL_FROM', EMAIL_USER)

class EmailFollowupSystem:
    """Handles automated follow-up emails after successful connections and contact request notifications"""

    def __init__(self, user_auth_system, db_connection_func=None):
        self.user_auth = user_auth_system
        self.get_db_connection = db_connection_func  # Function to get DB connection
        self.init_followup_database()
    
    def init_followup_database(self):
        """Initialize follow-up tracking tables"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
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

        # Update the user_matches table to include follow-up data (PostgreSQL safe way)
        try:
            cursor.execute('ALTER TABLE user_matches ADD COLUMN IF NOT EXISTS user_would_meet_again BOOLEAN')
            cursor.execute('ALTER TABLE user_matches ADD COLUMN IF NOT EXISTS match_would_meet_again BOOLEAN')
            print("✓ Added follow-up columns to user_matches table")
        except psycopg2.Error as e:
            print(f"Follow-up columns already exist: {e}")
        
        conn.commit()
        conn.close()
        print("✓ Email follow-up database initialized")

    def schedule_followup_email(self, contact_request_id, user1_id, user2_id):
        """Schedule a follow-up email to be sent in 5 days"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get user information
            cursor.execute('SELECT first_name, last_name, email FROM users WHERE id = %s', (user1_id,))
            user1_info = cursor.fetchone()
            
            cursor.execute('SELECT first_name, last_name, email FROM users WHERE id = %s', (user2_id,))
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user1_id, user2_id, user1_name, user2_name, user1_email, user2_email, 
                       user1_token, user2_token
                FROM followup_tracking WHERE id = %s
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
                UPDATE followup_tracking SET email_sent_at = CURRENT_TIMESTAMP WHERE id = %s
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
                
            print(f"✓ Follow-up email sent to {to_email}")
            
        except Exception as e:
            print(f"Error sending follow-up email to {to_email}: {e}")
    
    def record_followup_response(self, token, response):
        """Record user's follow-up response"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Find the follow-up record and determine which user responded
            cursor.execute('''
                SELECT id, user1_id, user2_id, user1_token, user2_token 
                FROM followup_tracking 
                WHERE user1_token = %s OR user2_token = %s
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
                    SET user1_response = %s, user1_responded_at = CURRENT_TIMESTAMP 
                    WHERE id = %s
                ''', (response == 'yes', followup_id))
                responding_user_id = user1_id
                other_user_id = user2_id
            else:
                cursor.execute('''
                    UPDATE followup_tracking 
                    SET user2_response = %s, user2_responded_at = CURRENT_TIMESTAMP 
                    WHERE id = %s
                ''', (response == 'yes', followup_id))
                responding_user_id = user2_id
                other_user_id = user1_id
            
            # Update the user_matches table with the response
            cursor.execute('''
                UPDATE user_matches 
                SET user_would_meet_again = %s
                WHERE user_id = %s AND matched_user_id = %s
            ''', (response == 'yes', responding_user_id, other_user_id))
            
            # Also update the reverse match
            cursor.execute('''
                UPDATE user_matches 
                SET match_would_meet_again = %s 
                WHERE user_id = %s AND matched_user_id = %s
            ''', (response == 'yes', other_user_id, responding_user_id))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': 'Response recorded successfully'}
            
        except Exception as e:
            print(f"Error recording follow-up response: {e}")
            return {'success': False, 'error': 'Failed to record response'}

    def send_contact_request_notification(self, contact_request_id, requester_id, requested_id, message=''):
        """Send email notification when someone sends a contact request"""
        try:
            # Use the user auth system to get user information (handles encryption)
            requester_info = self.user_auth.get_user_info(requester_id)
            requested_info = self.user_auth.get_user_info(requested_id)

            if not requester_info or not requested_info:
                print(f"Error: Could not find user info for contact request notification")
                return False

            requester_name = f"{requester_info['first_name']} {requester_info['last_name']}"
            requested_name = f"{requested_info['first_name']} {requested_info['last_name']}"
            requested_email = requested_info['email']

            # Send notification email to the requested user
            self.send_contact_request_email(
                to_email=requested_email,
                requested_user_name=requested_name,
                requester_name=requester_name,
                message=message,
                contact_request_id=contact_request_id
            )

            print(f"✓ Contact request notification sent to {requested_email}")
            return True

        except Exception as e:
            print(f"Error sending contact request notification: {e}")
            return False

    def send_contact_request_email(self, to_email, requested_user_name, requester_name, message, contact_request_id):
        """Send contact request notification email"""
        try:
            subject = f"New Contact Request from {requester_name}"

            # Get the base URL for your app
            base_url = os.environ.get('BASE_URL', 'http://localhost:8080')
            login_url = f"{base_url}/login"
            contact_requests_url = f"{base_url}/contact-requests"

            # Prepare message display
            message_section = ""
            if message.strip():
                message_section = f"""
                <div style="background: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0;">
                    <h4 style="color: #167a60; margin-top: 0;">Message from {requester_name}:</h4>
                    <p style="font-style: italic; margin: 0;">{message}</p>
                </div>
                """

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
                    .highlight {{ background: #e8f5e8; padding: 15px; border-radius: 6px; border-left: 4px solid #167a60; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 24px;">🤝 New Contact Request</h1>
                        <p style="margin: 10px 0 0 0; opacity: 0.9;">Someone wants to connect with you!</p>
                    </div>

                    <div class="content">
                        <h2>Hi {requested_user_name}!</h2>

                        <div class="highlight">
                            <p style="margin: 0; font-size: 18px;"><strong>{requester_name}</strong> has sent you a contact request through our platform!</p>
                        </div>

                        {message_section}

                        <p>To view and respond to this contact request:</p>

                        <div style="text-align: center; margin: 25px 0;">
                            <a href="{login_url}" class="button">🔗 Log In to Respond</a>
                        </div>

                        <p>Once logged in, you can view all your contact requests and choose to accept or decline them. If you accept, you'll be able to share contact information and connect directly!</p>

                        <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin: 20px 0;">
                            <p style="margin: 0; font-size: 14px;"><strong>💡 Quick tip:</strong> After logging in, go to your <a href="{contact_requests_url}" style="color: #167a60;">Contact Requests</a> page to manage all pending requests.</p>
                        </div>

                        <p>Thank you for being part of our community!</p>

                        <p>Best regards,<br>The Connect Team</p>
                    </div>

                    <div class="footer">
                        <p>This email was sent because someone requested to connect with you through our platform.</p>
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

            print(f"✓ Contact request notification sent to {to_email}")

        except Exception as e:
            print(f"Error sending contact request notification to {to_email}: {e}")
