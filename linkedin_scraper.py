"""
LinkedIn Profile Scraper using Fresh API
Scrapes public LinkedIn profile data to enrich user onboarding
"""

import requests
from typing import Dict, Any, List
import os


class LinkedInScraper:
    """Scraper for public LinkedIn profile data using Fresh API"""

    def __init__(self, fresh_api_key: str = None):
        """
        Initialize the LinkedIn scraper

        Args:
            fresh_api_key: API key for Fresh API (RapidAPI)
        """
        self.fresh_api_key = fresh_api_key or os.environ.get('FRESH_API_KEY')

        # Fresh API is accessed through RapidAPI
        self.base_url = "https://fresh-linkedin-profile-data.p.rapidapi.com"
        self.headers = {
            "x-rapidapi-key": self.fresh_api_key,
            "x-rapidapi-host": "fresh-linkedin-profile-data.p.rapidapi.com"
        }

    def scrape_profile(self, linkedin_url: str) -> Dict[str, Any]:
        """
        Scrape a LinkedIn profile using Fresh API

        Args:
            linkedin_url: The LinkedIn profile URL

        Returns:
            Dictionary containing scraped profile data
        """

        # Validate URL and extract username
        username = self._extract_username(linkedin_url)
        if not username:
            return {"error": "Invalid LinkedIn URL - could not extract username"}

        if not self.fresh_api_key:
            return {
                "error": "Fresh API key not configured",
                "note": "Set FRESH_API_KEY environment variable"
            }

        try:
            # Call Fresh API to get profile data
            response = requests.get(
                f"{self.base_url}/get-linkedin-profile",
                headers=self.headers,
                params={
                    "linkedin_url": linkedin_url,
                    "include_skills": "true"
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_fresh_api_response(data)
            else:
                return {
                    "error": f"Fresh API error: {response.status_code}",
                    "message": response.text
                }

        except Exception as e:
            return {"error": f"Failed to scrape LinkedIn profile: {str(e)}"}

    def _extract_username(self, linkedin_url: str) -> str:
        """Extract username from LinkedIn URL"""
        try:
            # LinkedIn URLs are typically: https://www.linkedin.com/in/username/
            if '/in/' in linkedin_url:
                parts = linkedin_url.split('/in/')
                if len(parts) > 1:
                    username = parts[1].rstrip('/')
                    # Remove any query parameters
                    if '?' in username:
                        username = username.split('?')[0]
                    return username
            return None
        except:
            return None

    def _parse_fresh_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Fresh API response into our format"""

        # Fresh API returns data in a specific structure
        # Adapt to the actual API response format

        profile_data = data.get('data', {}) if 'data' in data else data

        # Extract education
        education = []
        edu_list = profile_data.get('education', [])
        if isinstance(edu_list, list):
            for edu in edu_list:
                education.append({
                    'school': edu.get('school', {}).get('name') if isinstance(edu.get('school'), dict) else edu.get('school'),
                    'degree': edu.get('degree'),
                    'field': edu.get('field_of_study'),
                    'start': edu.get('start_date'),
                    'end': edu.get('end_date')
                })

        # Extract work experience
        work_history = []
        exp_list = profile_data.get('experiences', []) or profile_data.get('experience', [])
        if isinstance(exp_list, list):
            for exp in exp_list:
                work_history.append({
                    'company': exp.get('company', {}).get('name') if isinstance(exp.get('company'), dict) else exp.get('company'),
                    'title': exp.get('title'),
                    'description': exp.get('description'),
                    'start': exp.get('start_date'),
                    'end': exp.get('end_date'),
                    'location': exp.get('location')
                })

        # Get current position (first in list without end date)
        current_position = "Not specified"
        for exp in work_history:
            if not exp.get('end'):
                current_position = f"{exp.get('title', 'Position')} at {exp.get('company', 'Company')}"
                break

        # Get university (first education entry)
        university = "Not specified"
        if education and len(education) > 0:
            university = education[0].get('school', 'Not specified')

        # Extract skills
        skills = []
        skills_data = profile_data.get('skills', [])
        if isinstance(skills_data, list):
            for skill in skills_data:
                if isinstance(skill, dict):
                    skills.append(skill.get('name', ''))
                else:
                    skills.append(str(skill))

        # Extract location
        location = profile_data.get('location', 'Not specified')
        if isinstance(location, dict):
            location = location.get('name', 'Not specified')

        return {
            "full_name": profile_data.get('full_name') or profile_data.get('name'),
            "headline": profile_data.get('headline') or profile_data.get('tagline'),
            "summary": profile_data.get('summary') or profile_data.get('about'),
            "location": location,
            "university": university,
            "education": education,
            "current_position": current_position,
            "work_history": work_history,
            "skills": [s for s in skills if s],  # Filter empty strings
            "languages": profile_data.get('languages', []),
            "certifications": profile_data.get('certifications', []),
            "volunteer_work": profile_data.get('volunteer', []),
            "connections": profile_data.get('connections'),
            "follower_count": profile_data.get('follower_count'),
            "profile_url": profile_data.get('public_identifier') or profile_data.get('linkedin_url')
        }

    def enrich_profile_data(self, scraped_data: Dict[str, Any]) -> str:
        """
        Convert scraped LinkedIn data into a formatted string for AI processing

        Args:
            scraped_data: Dictionary of scraped profile data

        Returns:
            Formatted string summarizing the profile
        """

        if scraped_data.get('error'):
            return f"LinkedIn data unavailable: {scraped_data.get('error')}"

        summary = f"""LinkedIn Profile Summary:

**Name:** {scraped_data.get('full_name', 'Not available')}
**Headline:** {scraped_data.get('headline', 'Not available')}
**Location:** {scraped_data.get('location', 'Not available')}

**Education:**
"""

        # Add education details
        education = scraped_data.get('education', [])
        if education:
            for edu in education:
                school = edu.get('school', 'School')
                degree = edu.get('degree', '')
                field = edu.get('field', '')
                if degree or field:
                    summary += f"- {degree} in {field} from {school}\n" if field else f"- {degree} from {school}\n"
                else:
                    summary += f"- {school}\n"
        else:
            summary += "- Not available\n"

        summary += "\n**Work Experience:**\n"

        # Add work history
        work_history = scraped_data.get('work_history', [])
        if work_history:
            for exp in work_history[:5]:  # Top 5 positions
                title = exp.get('title', 'Position')
                company = exp.get('company', 'Company')
                summary += f"- {title} at {company}\n"
        else:
            summary += "- Not available\n"

        summary += f"\n**Current Position:** {scraped_data.get('current_position', 'Not available')}\n"

        # Add skills
        skills = scraped_data.get('skills', [])
        if skills:
            summary += f"\n**Skills:** {', '.join(skills[:15])}\n"  # Top 15 skills

        # Add summary/about section
        about = scraped_data.get('summary', '')
        if about:
            summary += f"\n**About:**\n{about[:500]}{'...' if len(about) > 500 else ''}\n"

        return summary


# Example usage
if __name__ == "__main__":
    # Example with Fresh API
    scraper = LinkedInScraper(
        fresh_api_key=os.environ.get("FRESH_API_KEY")
    )

    profile_data = scraper.scrape_profile("https://www.linkedin.com/in/example-profile")

    if profile_data.get('error'):
        print(f"Error: {profile_data.get('error')}")
    else:
        enriched_text = scraper.enrich_profile_data(profile_data)
        print(enriched_text)
