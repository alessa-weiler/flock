"""
Document Classifier using GPT-4 for intelligent auto-classification
Classifies documents by team, project, type, time period, confidentiality, and more
"""

import os
import json
from typing import Dict, List, Optional
from openai import OpenAI
import time


class DocumentClassifier:
    """
    Intelligent document classifier using GPT-4

    Features:
    - Multi-dimensional classification (team, project, type, date, confidentiality)
    - Entity extraction (mentioned people, organizations)
    - Tag generation
    - Confidence scoring
    - Organization context awareness
    """

    # Document types
    DOCUMENT_TYPES = [
        "contract", "policy", "report", "presentation", "meeting_notes",
        "invoice", "receipt", "proposal", "memo", "email", "spreadsheet",
        "handbook", "guide", "manual", "whitepaper", "case_study",
        "specification", "design_doc", "research", "analysis", "other"
    ]

    # Confidentiality levels
    CONFIDENTIALITY_LEVELS = ["public", "internal", "confidential", "restricted"]

    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Initialize classifier

        Args:
            model: OpenAI model to use (default: gpt-4o-mini)
        """
        self.model = model
        self.api_key = os.environ.get('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=self.api_key)

    def classify(
        self,
        document_text: str,
        filename: str,
        org_context: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Dict:
        """
        Classify a document using GPT-4

        Args:
            document_text: Full text of the document
            filename: Original filename
            org_context: Organization context (existing teams, projects, etc.)
            max_retries: Maximum retry attempts

        Returns:
            Dictionary with classification results:
            {
                'team': str,
                'project': str,
                'doc_type': str,
                'time_period': str,
                'confidentiality': str,
                'mentioned_people': List[str],
                'tags': List[str],
                'confidence_scores': {
                    'team': float,
                    'project': float,
                    'doc_type': float,
                    'time_period': float,
                    'confidentiality': float
                },
                'summary': str
            }
        """
        org_context = org_context or {}

        # Build classification prompt
        prompt = self._build_classification_prompt(
            document_text=document_text,
            filename=filename,
            org_context=org_context
        )

        # Call GPT-4 with retry logic
        for attempt in range(max_retries):
            try:
                print(f"Classifying document '{filename}' (attempt {attempt + 1}/{max_retries})")

                start_time = time.time()

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert document classifier. Analyze documents and provide structured classification information in JSON format."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,  # Lower temperature for more consistent results
                    response_format={"type": "json_object"}
                )

                end_time = time.time()

                # Parse response
                result_text = response.choices[0].message.content
                classification = json.loads(result_text)

                # Validate and normalize classification
                classification = self._validate_classification(classification)

                print(f"✓ Classification completed in {end_time - start_time:.2f}s")
                print(f"  Team: {classification.get('team', 'unknown')}")
                print(f"  Type: {classification.get('doc_type', 'unknown')}")
                print(f"  Project: {classification.get('project', 'none')}")

                return classification

            except json.JSONDecodeError as e:
                print(f"Error parsing classification JSON (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    # Return fallback classification
                    return self._get_fallback_classification(filename)

            except Exception as e:
                print(f"Error during classification (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return self._get_fallback_classification(filename)

        # Should not reach here, but just in case
        return self._get_fallback_classification(filename)

    def _build_classification_prompt(
        self,
        document_text: str,
        filename: str,
        org_context: Dict
    ) -> str:
        """
        Build the classification prompt for GPT-4

        Args:
            document_text: Document text (truncated if needed)
            filename: Original filename
            org_context: Organization context

        Returns:
            Formatted prompt string
        """
        # Truncate document text to avoid token limits (keep first 6000 chars)
        text_sample = document_text[:6000]
        if len(document_text) > 6000:
            text_sample += "\n\n[... document continues ...]"

        # Get org context
        known_teams = org_context.get('teams', [])
        known_projects = org_context.get('projects', [])

        prompt = f"""Analyze this document and provide a comprehensive classification.

**Document Filename:** {filename}

**Document Content:**
{text_sample}

**Organization Context:**
- Known Teams: {', '.join(known_teams) if known_teams else 'None specified'}
- Known Projects: {', '.join(known_projects) if known_projects else 'None specified'}

**Instructions:**
Provide a JSON response with the following structure:

{{
  "team": "The team this document belongs to (e.g., Engineering, Marketing, Sales, HR, Finance, Operations, Legal, Executive). Use known teams if applicable, or infer from content.",
  "project": "The project this document relates to (e.g., Q1 Launch, Product Redesign, Budget 2024). Use known projects if applicable, or 'none' if not project-specific.",
  "doc_type": "Document type. Choose from: {', '.join(self.DOCUMENT_TYPES)}",
  "time_period": "Time period referenced in the document (e.g., 2024-Q1, Jan-2024, FY2024, 2024, Q3-2023). Format as 'YYYY', 'YYYY-QN', 'MMM-YYYY', or 'FYYYYY'. Use 'ongoing' if no specific period.",
  "confidentiality": "Confidentiality level. Choose from: {', '.join(self.CONFIDENTIALITY_LEVELS)}. Use context clues like 'confidential', 'internal only', 'public', etc.",
  "mentioned_people": ["List of full names mentioned in the document. Include only actual people, not roles or positions. Limit to 10 most relevant."],
  "tags": ["3-5 relevant keywords/tags that describe the document content"],
  "summary": "Brief 1-2 sentence summary of the document",
  "confidence_scores": {{
    "team": 0.95,
    "project": 0.80,
    "doc_type": 0.98,
    "time_period": 0.90,
    "confidentiality": 0.85
  }}
}}

**Guidelines:**
1. If you cannot determine a field with confidence, use appropriate defaults:
   - team: "General"
   - project: "none"
   - doc_type: "other"
   - time_period: "ongoing"
   - confidentiality: "internal"

2. Confidence scores should be between 0.0 and 1.0:
   - 0.9-1.0: Very confident
   - 0.7-0.9: Confident
   - 0.5-0.7: Somewhat confident
   - 0.0-0.5: Low confidence

3. Extract only real person names from the content, not email signatures or headers.

4. Tags should be specific and relevant (e.g., "product-launch", "hiring", "Q1-metrics").

Respond ONLY with valid JSON, no additional text."""

        return prompt

    def _validate_classification(self, classification: Dict) -> Dict:
        """
        Validate and normalize classification results

        Args:
            classification: Raw classification from GPT-4

        Returns:
            Validated and normalized classification
        """
        validated = {
            'team': classification.get('team', 'General'),
            'project': classification.get('project', 'none'),
            'doc_type': classification.get('doc_type', 'other'),
            'time_period': classification.get('time_period', 'ongoing'),
            'confidentiality': classification.get('confidentiality', 'internal'),
            'mentioned_people': classification.get('mentioned_people', []),
            'tags': classification.get('tags', []),
            'summary': classification.get('summary', ''),
            'confidence_scores': classification.get('confidence_scores', {
                'team': 0.5,
                'project': 0.5,
                'doc_type': 0.5,
                'time_period': 0.5,
                'confidentiality': 0.5
            })
        }

        # Normalize doc_type
        if validated['doc_type'] not in self.DOCUMENT_TYPES:
            validated['doc_type'] = 'other'

        # Normalize confidentiality
        if validated['confidentiality'] not in self.CONFIDENTIALITY_LEVELS:
            validated['confidentiality'] = 'internal'

        # Ensure mentioned_people is a list
        if not isinstance(validated['mentioned_people'], list):
            validated['mentioned_people'] = []

        # Ensure tags is a list and limit to 5
        if not isinstance(validated['tags'], list):
            validated['tags'] = []
        validated['tags'] = validated['tags'][:5]

        # Validate confidence scores
        for key in ['team', 'project', 'doc_type', 'time_period', 'confidentiality']:
            score = validated['confidence_scores'].get(key, 0.5)
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                validated['confidence_scores'][key] = 0.5

        return validated

    def _get_fallback_classification(self, filename: str) -> Dict:
        """
        Get a basic fallback classification when GPT-4 fails

        Args:
            filename: Document filename

        Returns:
            Minimal classification
        """
        # Try to infer doc_type from filename extension
        doc_type = 'other'
        if filename.endswith('.pdf'):
            if 'report' in filename.lower():
                doc_type = 'report'
            elif 'contract' in filename.lower():
                doc_type = 'contract'
            elif 'invoice' in filename.lower():
                doc_type = 'invoice'
        elif filename.endswith(('.ppt', '.pptx')):
            doc_type = 'presentation'
        elif filename.endswith(('.xls', '.xlsx', '.csv')):
            doc_type = 'spreadsheet'

        return {
            'team': 'General',
            'project': 'none',
            'doc_type': doc_type,
            'time_period': 'ongoing',
            'confidentiality': 'internal',
            'mentioned_people': [],
            'tags': ['unclassified'],
            'summary': 'Document could not be automatically classified',
            'confidence_scores': {
                'team': 0.1,
                'project': 0.1,
                'doc_type': 0.3,
                'time_period': 0.1,
                'confidentiality': 0.3
            }
        }

    def get_org_context(self, org_id: int) -> Dict:
        """
        Get organization context for better classification

        This queries the database for known teams and projects in the organization.

        Args:
            org_id: Organization ID

        Returns:
            Dictionary with teams and projects
        """
        import psycopg2
        from psycopg2.extras import RealDictCursor

        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            return {'teams': [], 'projects': []}

        try:
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            cursor = conn.cursor()

            # Get unique teams from existing classifications
            cursor.execute('''
                SELECT DISTINCT team
                FROM document_classifications dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.organization_id = %s
                AND team IS NOT NULL
                AND team != 'General'
                ORDER BY team
            ''', (org_id,))

            teams = [row['team'] for row in cursor.fetchall()]

            # Get unique projects from existing classifications
            cursor.execute('''
                SELECT DISTINCT project
                FROM document_classifications dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.organization_id = %s
                AND project IS NOT NULL
                AND project != 'none'
                ORDER BY project
            ''', (org_id,))

            projects = [row['project'] for row in cursor.fetchall()]

            conn.close()

            return {
                'teams': teams,
                'projects': projects
            }

        except Exception as e:
            print(f"Error getting org context: {e}")
            return {'teams': [], 'projects': []}


def get_classifier(model: str = "gpt-4o-mini") -> DocumentClassifier:
    """
    Factory function to get classifier instance

    Args:
        model: OpenAI model to use

    Returns:
        Configured DocumentClassifier instance
    """
    return DocumentClassifier(model=model)
