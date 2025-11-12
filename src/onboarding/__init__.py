"""
Onboarding Submodule

This module handles user onboarding functionality including:
- Multi-step onboarding process (onboarding)
- AI-powered profile analysis (onboarding_agent)
- Psychological profiling
- LinkedIn integration (removed)
"""

from .onboarding import add_onboarding_routes
from .onboarding_agent import OnboardingAgent

__all__ = [
    'add_onboarding_routes',
    'OnboardingAgent',
]
