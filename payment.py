import os
import stripe
from datetime import datetime, timedelta
from typing import Dict, Any, Callable
import logging

class SubscriptionManager:
    """Handles Stripe subscriptions and payment processing"""
    
    def __init__(self, user_auth_system, get_db_connection_func: Callable):
        self.user_auth = user_auth_system
        self.get_db_connection = get_db_connection_func
        stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
        self.price_id = os.environ.get('STRIPE_PRICE_ID')
    
    def get_user_subscription_status(self, user_id: int) -> Dict[str, Any]:
        """Get current subscription status for user"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT status, current_period_end, cancel_at_period_end, stripe_customer_id
                FROM user_subscriptions 
                WHERE user_id = %s
            ''', (user_id,))
            
            result = cursor.fetchone()
            
            # Check free matches used
            cursor.execute('''
                SELECT free_matches_used, last_free_match_date 
                FROM users 
                WHERE id = %s
            ''', (user_id,))
            
            user_data = cursor.fetchone()
            conn.close()
            
            free_matches_used = user_data['free_matches_used'] if user_data else 0
            last_free_match = user_data['last_free_match_date'] if user_data else None
            
            # Reset free matches monthly
            if last_free_match and last_free_match < datetime.now() - timedelta(days=30):
                self.reset_free_matches(user_id)
                free_matches_used = 0
            
            if result and result['status'] == 'active':
                # Check if subscription is cancelled but still active (running until period end)
                if result['cancel_at_period_end']:
                    return {
                        'is_subscribed': True,
                        'status': 'cancelled',  # Changed from 'active' to 'cancelled'
                        'expires_at': result['current_period_end'],
                        'cancel_at_period_end': True,
                        'can_run_matching': True,
                        'free_matches_remaining': 0,
                        'subscription_required': False
                    }
                else:
                    return {
                        'is_subscribed': True,
                        'status': result['status'],
                        'expires_at': result['current_period_end'],
                        'cancel_at_period_end': False,
                        'can_run_matching': True,
                        'free_matches_remaining': 0,
                        'subscription_required': False
                    }
            else:
                free_matches_remaining = max(0, 1 - free_matches_used)
                return {
                    'is_subscribed': False,
                    'status': 'inactive',
                    'can_run_matching': free_matches_remaining > 0,
                    'free_matches_remaining': free_matches_remaining,
                    'subscription_required': free_matches_remaining == 0
                }
                
        except Exception as e:
            print(f"Error getting subscription status: {e}")
            return {
                'is_subscribed': False,
                'status': 'error',
                'can_run_matching': False,
                'free_matches_remaining': 0,
                'subscription_required': True
            }

    def reset_free_matches(self, user_id: int):
        """Reset free matches counter monthly"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET free_matches_used = 0, last_free_match_date = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error resetting free matches: {e}")
    
    def create_checkout_session(self, user_id: int, request_url_root: str) -> Dict[str, Any]:
        """Create Stripe checkout session"""
        try:
            user_info = self.user_auth.get_user_info(user_id)
            if not user_info:
                return {'success': False, 'error': 'User not found'}
            
            # Get or create Stripe customer
            customer_id = self.get_or_create_customer(user_id, user_info['email'])
            
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': self.price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f"{request_url_root}subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{request_url_root}subscription/cancelled",
                metadata={
                    'user_id': str(user_id)
                }
            )
            
            return {
                'success': True,
                'checkout_url': session.url,
                'session_id': session.id
            }
            
        except Exception as e:
            print(f"Error creating checkout session: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_or_create_customer(self, user_id: int, email: str) -> str:
        """Get existing Stripe customer or create new one"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT stripe_customer_id FROM user_subscriptions WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            
            if result and result['stripe_customer_id']:
                conn.close()
                return result['stripe_customer_id']
            
            # Create new customer
            customer = stripe.Customer.create(
                email=email,
                metadata={'user_id': str(user_id)}
            )
            
            # Store customer ID
            cursor.execute('''
                INSERT INTO user_subscriptions (user_id, stripe_customer_id, status)
                VALUES (%s, %s, 'inactive')
                ON CONFLICT (user_id) 
                DO UPDATE SET stripe_customer_id = EXCLUDED.stripe_customer_id
            ''', (user_id, customer.id))
            
            conn.commit()
            conn.close()
            
            return customer.id
            
        except Exception as e:
            print(f"Error creating customer: {e}")
            raise
    
    def handle_subscription_event(self, event_data: Dict) -> bool:
        """Handle Stripe webhook events"""
        try:
            event_type = event_data['type']
            subscription = event_data['data']['object']
            
            if event_type in ['customer.subscription.created', 'customer.subscription.updated']:
                self.update_subscription(subscription)
            elif event_type == 'customer.subscription.deleted':
                self.handle_subscription_deleted(subscription)  # Updated method name
            elif event_type == 'invoice.payment_succeeded':
                self.handle_successful_payment(subscription)
            elif event_type == 'invoice.payment_failed':
                self.handle_failed_payment(subscription)
            
            return True
            
        except Exception as e:
            print(f"Error handling webhook: {e}")
            return False

    def handle_subscription_deleted(self, subscription: Dict):
        """Handle when subscription is actually deleted/expired"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE user_subscriptions 
                SET status = 'inactive',
                    updated_at = CURRENT_TIMESTAMP
                WHERE stripe_customer_id = %s
            ''', (subscription['customer'],))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error handling subscription deletion: {e}")

    def update_subscription(self, subscription: Dict):
        """Update subscription in database"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE user_subscriptions 
                SET stripe_subscription_id = %s,
                    status = %s,
                    current_period_start = %s,
                    current_period_end = %s,
                    cancel_at_period_end = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE stripe_customer_id = %s
            ''', (
                subscription['id'],
                subscription['status'],
                datetime.fromtimestamp(subscription['current_period_start']),
                datetime.fromtimestamp(subscription['current_period_end']),
                subscription['cancel_at_period_end'],
                subscription['customer']
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error updating subscription: {e}")
    
    def cancel_subscription(self, user_id: int) -> Dict[str, Any]:
        """Cancel user's subscription"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get subscription info
            cursor.execute('''
                SELECT stripe_subscription_id, stripe_customer_id 
                FROM user_subscriptions 
                WHERE user_id = %s AND status = 'active'
            ''', (user_id,))
            
            result = cursor.fetchone()
            if not result:
                return {'success': False, 'error': 'No active subscription found'}
            
            # Cancel the subscription in Stripe (at period end)
            updated_subscription = stripe.Subscription.modify(
                result['stripe_subscription_id'],
                cancel_at_period_end=True
            )
            
            # Update local database to reflect the cancellation
            cursor.execute('''
                UPDATE user_subscriptions 
                SET cancel_at_period_end = TRUE, 
                    current_period_end = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (datetime.fromtimestamp(updated_subscription['current_period_end']), user_id))
            
            conn.commit()
            conn.close()
            
            return {'success': True}
            
        except Exception as e:
            print(f"Error cancelling subscription: {e}")
            return {'success': False, 'error': str(e)}

    def record_matching_usage(self, user_id: int, is_free: bool = False):
        """Record when user runs matching"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Record usage
            subscription_status = self.get_user_subscription_status(user_id)
            cursor.execute('''
                INSERT INTO matching_usage (user_id, is_free_run, subscription_active)
                VALUES (%s, %s, %s)
            ''', (user_id, is_free, subscription_status['is_subscribed']))
            
            # Update free matches counter if needed
            if is_free:
                cursor.execute('''
                    UPDATE users 
                    SET free_matches_used = free_matches_used + 1,
                        last_free_match_date = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (user_id,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error recording matching usage: {e}")

    def handle_successful_payment(self, invoice):
        """Handle successful payment"""
        pass
    
    def handle_failed_payment(self, invoice):
        """Handle failed payment"""
        pass