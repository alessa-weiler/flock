# Compressed Protocol Onboarding - Setup Guide

## Quick Setup

### 1. Environment Variables

Your `.env` file already has the required keys! Just verify they're set:

```bash
# Already configured in your .env:
OPENAI_API_KEY=sk-proj-qKbwYeWzQWO3Hy...  ✓
FRESH_API_KEY=417aeebc49msh96387040dcf2b18p1a1e38jsn0d50fde29925  ✓
```

### 2. Install Dependencies

```bash
pip install openai requests
```

(You probably already have these installed!)

### 3. That's It!

The system is ready to use. When users complete onboarding:

1. They answer 10 compressed protocol questions (~15 min)
2. System scrapes their LinkedIn using Fresh API
3. OpenAI GPT-4o analyzes responses and extrapolates psychological insights
4. Combined personality profile saved to user profile

## How the APIs Work

### OpenAI API (GPT-4o)
- **Purpose**: AI analysis of onboarding responses
- **Model**: `gpt-4o`
- **Usage**: Called once per onboarding completion
- **Cost**: ~$0.10-0.20 per analysis
- **Key in .env**: `OPENAI_API_KEY`

### Fresh API (via RapidAPI)
- **Purpose**: LinkedIn profile scraping
- **Service**: Fresh LinkedIn Profile Data API on RapidAPI
- **Usage**: Called once per onboarding if LinkedIn URL provided
- **Cost**: Depends on RapidAPI plan (typically $0.01-0.05 per profile)
- **Key in .env**: `FRESH_API_KEY`

## Testing the System

### Test LinkedIn Scraping

```python
from linkedin_scraper import LinkedInScraper
import os

scraper = LinkedInScraper(fresh_api_key=os.environ.get('FRESH_API_KEY'))
data = scraper.scrape_profile("https://www.linkedin.com/in/example")
print(data)
```

### Test AI Analysis

```python
from onboarding_agent import OnboardingAgent
import os

agent = OnboardingAgent(api_key=os.environ.get('OPENAI_API_KEY'))

test_profile = {
    "age": 28,
    "defining_moment": "I left my corporate job to start a social enterprise...",
    "resource_allocation": "I would invest £5k in the business, save £3k, donate £2k...",
    # ... other responses
}

enriched = agent.process_onboarding(test_profile)
print(enriched['psychological_insights'])
```

## File Overview

### Core Files
- **`onboarding.py`** - 10-step onboarding form with compressed protocol questions
- **`onboarding_agent.py`** - OpenAI-powered psychological analysis agent
- **`linkedin_scraper.py`** - Fresh API LinkedIn profile scraper

### What Happens After Onboarding

1. User submits `/onboarding/complete`
2. Background task `process_onboarding_with_ai()` runs:
   ```python
   # Scrape LinkedIn
   linkedin_data = scraper.scrape_profile(linkedin_url)

   # Analyze with OpenAI
   enriched_profile = agent.process_onboarding(profile_data, linkedin_data)

   # Generate personality script
   onboarding_script = agent.create_agent_onboarding_script(enriched_profile)

   # Save to profile
   profile_data['agent_onboarding_script'] = onboarding_script
   user_auth.save_user_profile(user_id, profile_data)
   ```

3. User profile now contains:
   ```python
   {
       # Raw responses
       "defining_moment": "...",
       "resource_allocation": "...",
       # ...

       # Enriched data
       "ai_enriched": True,
       "linkedin_scraped_data": {...},
       "psychological_insights": {...},
       "agent_onboarding_script": "# AI Agent Personality Profile\n\n..."
   }
   ```

## Using the Personality Profile

The `agent_onboarding_script` is a comprehensive markdown document that can be used as context for AI agents:

```python
# Get user's personality profile
profile = user_auth.get_user_profile(user_id)
personality_script = profile.get('agent_onboarding_script')

# Use with OpenAI
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
            "role": "system",
            "content": f"You are an AI assistant personalized for this user.\n\n{personality_script}\n\nUse this profile to communicate in a way that resonates with their values, decision-making style, and personality."
        },
        {
            "role": "user",
            "content": "Help me decide if I should take this new job offer..."
        }
    ]
)

# The AI now knows the user's:
# - Core values
# - Decision-making patterns
# - Risk tolerance
# - Conflict style
# - Moral framework
# - etc.
```

## The 10 Compressed Protocol Questions

| Step | Question | Time | What It Reveals |
|------|----------|------|----------------|
| 1 | Basic Info (Age, LinkedIn, Gender, Location) | 1 min | Demographics |
| 2 | Defining Moment | 2 min | Values, risk tolerance, locus of control |
| 3 | Resource Allocation (£10k windfall) | 1 min | Financial priorities, altruism |
| 4 | Conflict Response | 2 min | Conflict style, emotional regulation |
| 5 | Trade-off (Job: Money vs Meaning) | 1 min | Work values, materialism |
| 6 | Social Identity | 2 min | Identity dimensions, in-group dynamics |
| 7 | Moral Dilemma (Lie for friend?) | 2 min | Moral framework, boundaries |
| 8 | System Trust | 1 min | Institutional trust, perceived agency |
| 9 | Stress Response | 2 min | Coping mechanisms, resilience |
| 10 | Future + Rapid Values | 2 min | Goals, optimism, value hierarchy |

**Total: ~15 minutes** vs 30+ with old system

## AI Analysis Output

The OpenAI agent produces structured psychological insights:

```json
{
    "core_values": {
        "primary_values": ["autonomy", "social impact", "growth"],
        "evidence": "chose entrepreneurship over consulting"
    },
    "decision_making_patterns": {
        "style": "balanced",
        "risk_tolerance": "high",
        "locus_of_control": "internal"
    },
    "personality_traits": {
        "openness": "High - values innovation",
        "conscientiousness": "High - structured goals",
        "extraversion": "Moderate",
        "agreeableness": "High - collaborative",
        "emotional_stability": "High - problem-focused coping"
    },
    "behavioral_predictions": {
        "likely_friend_compatibility": ["other entrepreneurs", "mission-driven individuals"],
        "potential_conflict_areas": ["rigid thinkers", "risk-averse people"],
        "ideal_social_contexts": ["collaborative projects", "intellectual discussions"]
    }
    // ... 10+ more categories
}
```

## Troubleshooting

### LinkedIn scraping fails
- Check Fresh API quota on RapidAPI dashboard
- Verify FRESH_API_KEY is correct in .env
- Test the API directly: https://rapidapi.com/freshdata/api/fresh-linkedin-profile-data

### AI analysis fails
- Verify OPENAI_API_KEY is correct
- Check OpenAI account has credits
- Review error logs for specific issues

### Processing takes too long
- Normal processing: 30-60 seconds
- LinkedIn scraping: 2-5 seconds
- AI analysis: 10-20 seconds
- If longer, check API rate limits

### Missing personality profile
- Ensure all 10 onboarding steps completed
- Check `profile_data['ai_enriched']` is True
- Review logs for background processing errors
- Verify `agent_onboarding_script` exists in profile

## Cost Estimates

Per user onboarding:
- **LinkedIn scraping**: $0.01-0.05 (Fresh API)
- **AI analysis**: $0.10-0.20 (OpenAI GPT-4o)
- **Total**: ~$0.15-0.25 per user

Very reasonable for the rich personality data you get!

## Next Steps

1. ✅ Environment variables already configured
2. ✅ Code already updated for OpenAI and Fresh API
3. 📝 Test onboarding flow: `/onboarding/step/1`
4. 📝 Complete all 10 steps
5. 📝 Check profile for `agent_onboarding_script`
6. 🚀 Use personality profile with AI agents!

Everything is ready to go! 🎉
