"""
Onboarding AI Agent - Processes and extrapolates information from user responses
Follows the Compressed Protocol to create rich personality and behavioral insights
"""

from typing import Dict, Any, List
from openai import OpenAI
import os
import json


class OnboardingAgent:
    """AI agent that processes onboarding responses and extrapolates psychological insights"""

    def __init__(self, api_key: str = None):
        """Initialize the agent with OpenAI API"""
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY")
        )
        self.model = "gpt-4o"

    def process_onboarding(self, profile_data: Dict[str, Any], linkedin_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process onboarding responses and extrapolate insights

        Args:
            profile_data: User's onboarding responses
            linkedin_data: Scraped LinkedIn profile data (optional)

        Returns:
            Dict containing extrapolated insights and enriched profile
        """

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(profile_data, linkedin_data)

        # Call OpenAI to analyze
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            temperature=0.3,  # Lower temperature for more consistent analysis
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Parse the response
        analysis = response.choices[0].message.content

        # Structure the extrapolations
        extrapolations = self._parse_analysis(analysis)

        # Combine original responses with extrapolations
        enriched_profile = {
            "raw_responses": profile_data,
            "linkedin_data": linkedin_data,
            "psychological_insights": extrapolations,
            "agent_metadata": {
                "model": self.model,
                "analysis_version": "1.0",
                "processed_at": self._get_timestamp()
            }
        }

        return enriched_profile

    def _build_analysis_prompt(self, profile_data: Dict[str, Any], linkedin_data: Dict[str, Any] = None) -> str:
        """Build the prompt for Claude to analyze the onboarding responses"""

        prompt = """You are a psychological profiling expert analyzing onboarding responses using the Compressed Protocol methodology. Your task is to extrapolate logical insights from user responses WITHOUT drawing unreasonable conclusions.

**Guidelines:**
- Base all extrapolations on direct evidence from responses
- Avoid stereotyping or making unfounded assumptions
- Focus on behavioral patterns, values, and decision-making styles
- Acknowledge uncertainty where appropriate
- Do not infer demographics, protected characteristics, or make medical/clinical diagnoses

**User Responses:**

"""

        # Add each onboarding response
        response_fields = {
            "defining_moment": "1. Defining Moment (reveals values, risk tolerance, locus of control)",
            "resource_allocation": "2. Resource Allocation (reveals financial priorities, risk/security orientation, altruism)",
            "conflict_response": "3. Conflict Response (reveals conflict style, emotional regulation, communication patterns)",
            "trade_off_scenario": "4. Trade-off Scenario (reveals materialism vs. meaning-seeking, work values)",
            "social_identity_groups": "5a. Social Identity - Groups",
            "social_identity_central": "5b. Social Identity - Most Central",
            "moral_dilemma": "6. Moral Dilemma (reveals moral framework, loyalty vs. honesty)",
            "system_trust": "7. System Trust (reveals trust in institutions, perceived agency)",
            "stress_response": "8. Stress Response (reveals stress triggers, coping mechanisms)",
            "future_orientation": "9. Future Orientation (reveals goal orientation, optimism)",
            "value_stability_excitement": "10a. Values: Stability vs. Excitement",
            "value_liked_respected": "10b. Values: Being Liked vs. Being Respected",
            "value_tradition_innovation": "10c. Values: Tradition vs. Innovation",
            "value_community_independence": "10d. Values: Community vs. Independence",
            "value_fairness_loyalty": "10e. Values: Fairness vs. Loyalty"
        }

        for field, label in response_fields.items():
            value = profile_data.get(field, "Not provided")
            prompt += f"\n**{label}:**\n{value}\n"

        # Add LinkedIn data if available
        if linkedin_data:
            prompt += f"\n\n**LinkedIn Profile Data:**\n"
            prompt += f"- University: {linkedin_data.get('university', 'Not available')}\n"
            prompt += f"- Current Position: {linkedin_data.get('current_position', 'Not available')}\n"
            prompt += f"- Work History: {linkedin_data.get('work_history', 'Not available')}\n"
            prompt += f"- Skills: {linkedin_data.get('skills', 'Not available')}\n"
            prompt += f"- Recent Posts/Activity: {linkedin_data.get('recent_activity', 'Not available')}\n"

        prompt += """

**Analysis Task:**

Provide a structured analysis in JSON format with the following categories. Be specific and evidence-based.

```json
{
    "core_values": {
        "primary_values": ["list 3-5 core values evident from responses"],
        "value_conflicts": "any internal value tensions observed",
        "evidence": "key quotes/behaviors supporting this"
    },
    "decision_making_patterns": {
        "style": "logic-driven | emotion-driven | balanced",
        "risk_tolerance": "low | moderate | high",
        "locus_of_control": "internal | external | mixed",
        "evidence": "supporting observations"
    },
    "personality_traits": {
        "openness": "assessment with evidence",
        "conscientiousness": "assessment with evidence",
        "extraversion": "assessment with evidence",
        "agreeableness": "assessment with evidence",
        "emotional_stability": "assessment with evidence"
    },
    "social_orientation": {
        "conflict_style": "avoidant | aggressive | collaborative | accommodating",
        "communication_preference": "direct | indirect | context-dependent",
        "relationship_priorities": "what they value in relationships",
        "social_identity_salience": "which identities are most important"
    },
    "moral_framework": {
        "ethical_approach": "consequentialist | deontological | virtue-based | mixed",
        "loyalty_vs_honesty_balance": "analysis",
        "boundary_setting": "assessment of personal boundaries"
    },
    "stress_and_resilience": {
        "primary_stressors": ["identified stress triggers"],
        "coping_mechanisms": ["observed coping strategies"],
        "support_seeking": "pattern of seeking/accepting help",
        "resilience_indicators": "signs of resilience or vulnerability"
    },
    "future_orientation": {
        "time_horizon": "short-term | medium-term | long-term focused",
        "goal_clarity": "assessment of goal specificity",
        "optimism_level": "pessimistic | realistic | optimistic",
        "growth_areas": ["identified areas for development"]
    },
    "work_and_achievement": {
        "motivation_drivers": ["intrinsic | extrinsic | mixed"],
        "work_life_balance": "assessment",
        "achievement_orientation": "low | moderate | high",
        "professional_identity": "how work relates to self-concept"
    },
    "trust_and_agency": {
        "institutional_trust": "low | moderate | high",
        "perceived_agency": "internal | external",
        "political_orientation_indicators": "observable patterns (not assumptions)",
        "systemic_view": "optimistic | pessimistic | pragmatic"
    },
    "behavioral_predictions": {
        "likely_friend_compatibility": ["personality types/characteristics"],
        "potential_conflict_areas": ["areas of potential friction"],
        "ideal_social_contexts": ["settings where they thrive"],
        "communication_recommendations": ["how to communicate effectively with this person"]
    },
    "red_flags_and_strengths": {
        "strengths": ["notable positive qualities"],
        "potential_challenges": ["areas that might cause issues"],
        "growth_opportunities": ["development areas"]
    },
    "linkedin_insights": {
        "professional_trajectory": "analysis of career path",
        "educational_background_signals": "what education reveals",
        "network_and_influence": "professional positioning",
        "content_themes": "themes from posts/activity"
    }
}
```

Remember:
- Every claim must be supported by specific evidence from the responses
- Use hedge words (likely, suggests, indicates) when making inferences
- Distinguish between observed behaviors and interpretations
- Acknowledge gaps or contradictions in the data
"""

        return prompt

    def _parse_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse the Claude response into structured data"""
        try:
            # Extract JSON from the response
            start = analysis.find('{')
            end = analysis.rfind('}') + 1

            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")

            json_str = analysis[start:end]
            extrapolations = json.loads(json_str)

            return extrapolations

        except Exception as e:
            print(f"Error parsing analysis: {e}")
            # Return a basic structure if parsing fails
            return {
                "error": "Failed to parse analysis",
                "raw_analysis": analysis
            }

    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def create_agent_onboarding_script(self, enriched_profile: Dict[str, Any]) -> str:
        """
        Create a comprehensive onboarding script combining user responses and AI extrapolations
        This is the final personality profile used for the user's AI agent

        Args:
            enriched_profile: The complete profile with raw responses and extrapolations

        Returns:
            A formatted script for the AI agent
        """

        raw_responses = enriched_profile.get("raw_responses", {})
        insights = enriched_profile.get("psychological_insights", {})
        linkedin = enriched_profile.get("linkedin_data", {})

        script = f"""# AI Agent Personality Profile

## User Identity
- Age: {raw_responses.get('age', 'Unknown')}
- Location: {raw_responses.get('location', 'Unknown')}, {raw_responses.get('postcode', '')}
- Gender: {raw_responses.get('gender', 'Unknown')}

## Professional Background (LinkedIn)
- Education: {linkedin.get('university', 'Not available')}
- Current Role: {linkedin.get('current_position', 'Not available')}
- Career Path: {linkedin.get('work_history', 'Not available')}

---

## Core Identity & Values

### Primary Values
{self._format_list(insights.get('core_values', {}).get('primary_values', []))}

**Evidence:** {insights.get('core_values', {}).get('evidence', 'Not provided')}

**Value Conflicts:** {insights.get('core_values', {}).get('value_conflicts', 'None identified')}

### Defining Life Moment
> "{raw_responses.get('defining_moment', 'Not provided')}"

---

## Decision-Making & Cognitive Style

**Style:** {insights.get('decision_making_patterns', {}).get('style', 'Unknown')}
**Risk Tolerance:** {insights.get('decision_making_patterns', {}).get('risk_tolerance', 'Unknown')}
**Locus of Control:** {insights.get('decision_making_patterns', {}).get('locus_of_control', 'Unknown')}

**Supporting Evidence:**
{insights.get('decision_making_patterns', {}).get('evidence', 'Not provided')}

### Resource Allocation Preference
> "{raw_responses.get('resource_allocation', 'Not provided')}"

### Career vs. Passion Trade-off
> "{raw_responses.get('trade_off_scenario', 'Not provided')}"

---

## Personality Traits (Big Five Assessment)

**Openness:** {insights.get('personality_traits', {}).get('openness', 'Unknown')}
**Conscientiousness:** {insights.get('personality_traits', {}).get('conscientiousness', 'Unknown')}
**Extraversion:** {insights.get('personality_traits', {}).get('extraversion', 'Unknown')}
**Agreeableness:** {insights.get('personality_traits', {}).get('agreeableness', 'Unknown')}
**Emotional Stability:** {insights.get('personality_traits', {}).get('emotional_stability', 'Unknown')}

---

## Social & Interpersonal Style

**Conflict Style:** {insights.get('social_orientation', {}).get('conflict_style', 'Unknown')}
**Communication Preference:** {insights.get('social_orientation', {}).get('communication_preference', 'Unknown')}
**Relationship Priorities:** {insights.get('social_orientation', {}).get('relationship_priorities', 'Unknown')}

### Conflict Response Example
> "{raw_responses.get('conflict_response', 'Not provided')}"

### Social Identity
**Communities:** {raw_responses.get('social_identity_groups', 'Not provided')}
**Most Central:** {raw_responses.get('social_identity_central', 'Not provided')}

**Identity Salience:** {insights.get('social_orientation', {}).get('social_identity_salience', 'Unknown')}

---

## Moral & Ethical Framework

**Ethical Approach:** {insights.get('moral_framework', {}).get('ethical_approach', 'Unknown')}
**Loyalty vs. Honesty Balance:** {insights.get('moral_framework', {}).get('loyalty_vs_honesty_balance', 'Unknown')}
**Boundary Setting:** {insights.get('moral_framework', {}).get('boundary_setting', 'Unknown')}

### Moral Dilemma Response
> "{raw_responses.get('moral_dilemma', 'Not provided')}"

---

## Stress, Coping & Resilience

**Primary Stressors:**
{self._format_list(insights.get('stress_and_resilience', {}).get('primary_stressors', []))}

**Coping Mechanisms:**
{self._format_list(insights.get('stress_and_resilience', {}).get('coping_mechanisms', []))}

**Support Seeking Pattern:** {insights.get('stress_and_resilience', {}).get('support_seeking', 'Unknown')}
**Resilience Indicators:** {insights.get('stress_and_resilience', {}).get('resilience_indicators', 'Unknown')}

### Recent Stress Experience
> "{raw_responses.get('stress_response', 'Not provided')}"

---

## Future Orientation & Goals

**Time Horizon:** {insights.get('future_orientation', {}).get('time_horizon', 'Unknown')}
**Goal Clarity:** {insights.get('future_orientation', {}).get('goal_clarity', 'Unknown')}
**Optimism Level:** {insights.get('future_orientation', {}).get('optimism_level', 'Unknown')}

### 5-Year Vision
> "{raw_responses.get('future_orientation', 'Not provided')}"

**Growth Areas:**
{self._format_list(insights.get('future_orientation', {}).get('growth_areas', []))}

---

## Work & Achievement

**Motivation Drivers:**
{self._format_list(insights.get('work_and_achievement', {}).get('motivation_drivers', []))}

**Work-Life Balance:** {insights.get('work_and_achievement', {}).get('work_life_balance', 'Unknown')}
**Achievement Orientation:** {insights.get('work_and_achievement', {}).get('achievement_orientation', 'Unknown')}
**Professional Identity:** {insights.get('work_and_achievement', {}).get('professional_identity', 'Unknown')}

---

## Trust, Agency & Worldview

**Institutional Trust:** {insights.get('trust_and_agency', {}).get('institutional_trust', 'Unknown')}
**Perceived Agency:** {insights.get('trust_and_agency', {}).get('perceived_agency', 'Unknown')}
**Systemic View:** {insights.get('trust_and_agency', {}).get('systemic_view', 'Unknown')}

### System Trust Perspective
> "{raw_responses.get('system_trust', 'Not provided')}"

**Observable Patterns:** {insights.get('trust_and_agency', {}).get('political_orientation_indicators', 'Unknown')}

---

## Rapid-Fire Values Results

- **Stability vs. Excitement:** {raw_responses.get('value_stability_excitement', 'Not answered')}
- **Being Liked vs. Respected:** {raw_responses.get('value_liked_respected', 'Not answered')}
- **Tradition vs. Innovation:** {raw_responses.get('value_tradition_innovation', 'Not answered')}
- **Community vs. Independence:** {raw_responses.get('value_community_independence', 'Not answered')}
- **Fairness vs. Loyalty:** {raw_responses.get('value_fairness_loyalty', 'Not answered')}

---

## Behavioral Predictions & Compatibility

### Likely Friend Compatibility
{self._format_list(insights.get('behavioral_predictions', {}).get('likely_friend_compatibility', []))}

### Potential Conflict Areas
{self._format_list(insights.get('behavioral_predictions', {}).get('potential_conflict_areas', []))}

### Ideal Social Contexts
{self._format_list(insights.get('behavioral_predictions', {}).get('ideal_social_contexts', []))}

### Communication Recommendations
{self._format_list(insights.get('behavioral_predictions', {}).get('communication_recommendations', []))}

---

## Strengths & Growth Opportunities

### Strengths
{self._format_list(insights.get('red_flags_and_strengths', {}).get('strengths', []))}

### Potential Challenges
{self._format_list(insights.get('red_flags_and_strengths', {}).get('potential_challenges', []))}

### Growth Opportunities
{self._format_list(insights.get('red_flags_and_strengths', {}).get('growth_opportunities', []))}

---

## LinkedIn Professional Insights

**Professional Trajectory:** {insights.get('linkedin_insights', {}).get('professional_trajectory', 'Not available')}
**Educational Signals:** {insights.get('linkedin_insights', {}).get('educational_background_signals', 'Not available')}
**Network Position:** {insights.get('linkedin_insights', {}).get('network_and_influence', 'Not available')}
**Content Themes:** {insights.get('linkedin_insights', {}).get('content_themes', 'Not available')}

---

*Profile generated: {enriched_profile.get('agent_metadata', {}).get('processed_at', 'Unknown')}*
*Analysis model: {enriched_profile.get('agent_metadata', {}).get('model', 'Unknown')}*
"""

        return script

    def _format_list(self, items: List[str]) -> str:
        """Format a list of items as bullet points"""
        if not items:
            return "- None identified"
        return "\n".join([f"- {item}" for item in items])


# Example usage
if __name__ == "__main__":
    # Example profile data
    example_profile = {
        "age": 28,
        "location": "London",
        "gender": "woman",
        "defining_moment": "Deciding to leave a stable consulting job to start my own social enterprise...",
        "resource_allocation": "I'd invest £5000 in my business, put £3000 in savings, and donate £2000...",
        # ... other responses
    }

    example_linkedin = {
        "university": "University of Oxford",
        "current_position": "Founder & CEO at Social Impact Startup",
        "work_history": "Previously: Management Consultant at McKinsey, Analyst at Goldman Sachs",
        # ... other LinkedIn data
    }

    agent = OnboardingAgent()
    enriched = agent.process_onboarding(example_profile, example_linkedin)
    script = agent.create_agent_onboarding_script(enriched)

    print(script)
