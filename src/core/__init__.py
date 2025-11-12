"""
Core Submodule

This module contains core functionality used across the application:
- Data encryption and GDPR compliance (data_safety)
- Payment processing with Stripe (payment)
- Email notification system (email_followup)
- Centralized logging configuration (logging_config)
"""

from .data_safety import DataEncryption, GDPRCompliance
from .email_followup import EmailFollowupSystem
from .logging_config import get_logger, setup_logging
from .payment import SubscriptionManager

__all__ = [
    'DataEncryption',
    'GDPRCompliance',
    'EmailFollowupSystem',
    'get_logger',
    'setup_logging',
    'SubscriptionManager',
]
