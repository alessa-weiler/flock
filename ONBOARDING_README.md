# Compressed Protocol Onboarding System

This onboarding system uses the **Compressed Protocol** methodology to efficiently gather high-variance diagnostic information about users in ~15 minutes, then uses AI to extrapolate rich psychological insights.

## Overview

The system consists of three main components:

1. **10-Step Onboarding Questions** (`onboarding.py`) - Compressed protocol questions
2. **LinkedIn Profile Scraper** (`linkedin_scraper.py`) - Enriches profiles with professional data
3. **AI Analysis Agent** (`onboarding_agent.py`) - Extrapolates psychological insights from responses

## The Compressed Protocol Questions

### Step 1: Basic Information
- Age, LinkedIn URL, Gender, Location, Postcode

### Step 2: Defining Moment (2 min)
**Question:** "Tell me about a decision you made that significantly changed the direction of your life. What did you choose and why?"

**Reveals:**
- Core values and priorities
- Risk tolerance
- Locus of control
- Self-narrative style

### Step 3: Resource Allocation (1 min)
**Question:** "Imagine you unexpectedly received £10,000. How would you use it?"

**Reveals:**
- Financial priorities
- Risk/security orientation
- Altruism vs. self-interest
- Time preference (immediate vs. delayed gratification)

### Step 4: Conflict Response (2 min)
**Question:** "Describe a time when you strongly disagreed with someone important to you. How did you handle it?"

**Reveals:**
- Conflict style (avoidant, aggressive, collaborative)
- Relationship priorities
- Emotional regulation
- Communication patterns

### Step 5: Trade-off Scenario (1 min)
**Question:** "If you had to choose between a job that pays well but bores you, versus one that excites you but pays barely enough to live on, which would you choose and why?"

**Reveals:**
- Materialism vs. meaning-seeking
- Risk tolerance
- Economic security needs
- Work values

### Step 6: Social Identity (2 min)
**Questions:**
1. "What groups or communities do you feel you belong to?"
2. "Which of these is most important to your sense of who you are?"

**Reveals:**
- Social identity dimensions (political, cultural, professional)
- In-group/out-group dynamics
- Identity centrality
- Value systems

### Step 7: Moral Dilemma (2 min)
**Question:** "A close friend asks you to lie to protect them from serious consequences they deserve. What do you do?"

**Reveals:**
- Moral framework (consequentialist vs. deontological)
- Loyalty vs. honesty
- Comfort with moral ambiguity
- Relationship boundaries

### Step 8: System Trust (1 min)
**Question:** "When you think about institutions like government, healthcare, or the economy, do you generally feel they work for people like you, against you, or neither? Why?"

**Reveals:**
- Trust in institutions
- Perceived agency
- Political orientation
- Systemic optimism/pessimism

### Step 9: Stress Response (2 min)
**Question:** "Tell me about the last time you felt really overwhelmed or stressed. What caused it and how did you cope?"

**Reveals:**
- Stress triggers
- Coping mechanisms (problem-focused vs. emotion-focused)
- Support network
- Resilience patterns

### Step 10: Future Orientation & Rapid-Fire Values (2 min)
**Question 1:** "In 5 years, what do you hope will be different about your life?"

**Rapid-Fire Questions:**
- Stability or excitement?
- Being liked or being respected?
- Tradition or innovation?
- Community or independence?
- Fairness or loyalty?

**Reveals:**
- Goal orientation
- Optimism/pessimism
- Life domain priorities
- Quick value hierarchy
- Schwartz values dimensions
- Moral foundations

## LinkedIn Enrichment

The system scrapes the user's LinkedIn profile to enrich the data with:

- Educational background (university, degree, field of study)
- Work experience and current position
- Professional skills
- Recent posts and activity themes
- Professional network insights

### Setup for LinkedIn Scraping

**Recommended: Use Proxycurl API**

LinkedIn actively blocks direct scraping. For production use, we recommend [Proxycurl](https://nubela.co/proxycurl/), a paid API service:

1. Sign up at https://nubela.co/proxycurl/
2. Get your API key
3. Set environment variable:
   ```bash
   export PROXYCURL_API_KEY="your_api_key_here"
   ```

**Fallback: Basic Scraping**

If no Proxycurl key is provided, the system will attempt basic scraping (limited data, unreliable).

## AI Agent Processing

After onboarding completion, the AI agent:

1. **Scrapes LinkedIn profile** (if URL provided)
2. **Analyzes responses** using Claude Sonnet 4 to extrapolate insights
3. **Generates structured psychological profile** including:
   - Core values and priorities
   - Decision-making patterns
   - Personality traits (Big Five assessment)
   - Social orientation and conflict style
   - Moral framework
   - Stress coping and resilience
   - Future orientation and goals
   - Work and achievement drivers
   - Trust and agency patterns
   - Behavioral predictions

4. **Creates final onboarding script** - A comprehensive personality profile that combines:
   - Raw user responses
   - LinkedIn professional data
   - AI-extrapolated psychological insights

This script is stored in the user's profile as `agent_onboarding_script` and serves as the foundation for their AI agent's personality.

## Setup Instructions

### 1. Environment Variables

```bash
# Required for AI analysis
export ANTHROPIC_API_KEY="your_anthropic_api_key"

# Optional but recommended for LinkedIn scraping
export PROXYCURL_API_KEY="your_proxycurl_api_key"
```

### 2. Dependencies

Install required packages:

```bash
pip install anthropic requests beautifulsoup4
```

### 3. Usage

The onboarding system is integrated into the Flask app. Users go through:

1. `/onboarding/step/1` through `/onboarding/step/10` - Answer questions
2. `/onboarding/complete` - Review and submit
3. Background processing kicks off:
   - LinkedIn scraping
   - AI analysis
   - Profile enrichment

The enriched profile is saved to the user's profile data with these new fields:

```python
{
    "ai_enriched": True,
    "linkedin_scraped_data": {...},  # Raw LinkedIn data
    "psychological_insights": {...},  # AI extrapolations
    "agent_onboarding_script": "...",  # Final personality profile text
    "processed_at": "2025-01-15T..."
}
```

## Accessing the Onboarding Script

To get a user's AI agent personality profile:

```python
profile = user_auth.get_user_profile(user_id)
onboarding_script = profile.get('agent_onboarding_script')

# This script can now be used as context for the user's AI agent
# e.g., prepended to prompts to give the agent the user's personality
```

## Design Principles

### Extrapolation Guidelines

The AI agent is instructed to:

- ✅ Base all extrapolations on direct evidence from responses
- ✅ Use hedge words (likely, suggests, indicates) when making inferences
- ✅ Acknowledge uncertainty where appropriate
- ✅ Distinguish between observed behaviors and interpretations
- ❌ Avoid stereotyping or unfounded assumptions
- ❌ Not infer protected characteristics
- ❌ Not make medical/clinical diagnoses

### Data Privacy

- LinkedIn scraping uses publicly available data only
- AI processing happens server-side
- Enriched profiles stored securely in user profile data
- Users can view/edit their onboarding responses

## Example Output

The final `agent_onboarding_script` is a comprehensive markdown document like:

```markdown
# AI Agent Personality Profile

## User Identity
- Age: 28
- Location: London, SW3 4HN
- Gender: Woman

## Professional Background (LinkedIn)
- Education: University of Oxford, BA Philosophy
- Current Role: Founder & CEO at Social Impact Startup
- Career Path: Previously McKinsey Consultant, Goldman Sachs Analyst

---

## Core Identity & Values

### Primary Values
- Social impact and community benefit
- Intellectual growth and learning
- Autonomy and independence
- Fairness and justice
- Innovation and disruption

**Evidence:** User chose to leave high-paying consulting job to start social enterprise (defining moment), would invest windfall in business and donate portion (resource allocation), prioritizes meaning over money (trade-off question).

### Defining Life Moment
> "Deciding to leave a stable consulting job at McKinsey to start my own social enterprise focused on educational inequality. I chose this because I realized I was optimizing for the wrong metrics - salary and prestige instead of impact and meaning..."

---

## Decision-Making & Cognitive Style

**Style:** Balanced (considers both logic and values)
**Risk Tolerance:** High
**Locus of Control:** Internal

**Supporting Evidence:**
User demonstrates high internal locus of control through entrepreneurial choice despite uncertainty. Risk tolerance evident in career change. Balances analytical thinking (consulting background) with value-driven decisions.

[... continues with 20+ more sections ...]
```

## Future Enhancements

Potential improvements:

1. **Real-time LinkedIn updates** - Periodic re-scraping to keep data fresh
2. **User review interface** - Allow users to review and correct AI insights
3. **Comparative analysis** - Show how user compares to population norms
4. **Personality matching** - Use profiles for compatibility scoring
5. **Dynamic questioning** - Adapt questions based on previous answers
6. **Multi-language support** - Translate questions and analyze responses in multiple languages

## Troubleshooting

### LinkedIn scraping fails
- Check if Proxycurl API key is set correctly
- Verify the LinkedIn URL format is correct
- Check Proxycurl API quota/limits

### AI analysis fails
- Verify Anthropic API key is set
- Check API quota limits
- Review error logs for specific issues

### Missing data in profile
- Ensure onboarding completed fully (all 10 steps)
- Check background processing completed (may take 30-60 seconds)
- Verify user_auth.save_user_profile() is working correctly

## Support

For issues or questions:
- Check application logs for error messages
- Review profile data structure in database
- Test individual components (scraper, agent) separately
- Contact admin@pont.world for platform-specific help
