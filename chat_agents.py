"""
Multi-Agent Chat System for Knowledge Platform
Phase 7: Intelligent query processing with specialized agents
"""

import os
import json
from typing import Dict, List, Optional, Any
from openai import OpenAI
from embedding_service import EmbeddingService
from vector_store import VectorStore
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get PostgreSQL database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


class DataQueryAgent:
    """
    Agent responsible for searching internal data sources
    - Document semantic search
    - Employee profile search
    - Hybrid search (vector + keyword)
    """

    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    def search_documents(
        self,
        org_id: int,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search documents using semantic search

        Args:
            org_id: Organization ID
            query: Search query
            top_k: Number of results to return
            filters: Optional metadata filters (doc_type, team, project, etc.)

        Returns:
            List of matching document chunks with metadata
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_single_embedding(query, org_id)

            # Search Pinecone
            results = self.vector_store.search(
                org_id=org_id,
                query_embedding=query_embedding,
                top_k=top_k,
                filters=filters
            )

            # Format results
            formatted_results = []
            for match in results.get('matches', []):
                formatted_results.append({
                    'doc_id': match['metadata'].get('doc_id'),
                    'chunk_text': match['metadata'].get('text', ''),
                    'filename': match['metadata'].get('filename', ''),
                    'doc_type': match['metadata'].get('doc_type', ''),
                    'score': match.get('score', 0),
                    'page': match['metadata'].get('page'),
                    'chunk_index': match['metadata'].get('chunk_index')
                })

            return formatted_results

        except Exception as e:
            print(f"Error searching documents: {e}")
            return []

    def search_employees(
        self,
        org_id: int,
        query: str,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search employee profiles using semantic search

        Args:
            org_id: Organization ID
            query: Search query (e.g., "who knows Python?")
            top_k: Number of results to return

        Returns:
            List of matching employees with metadata
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_single_embedding(query, org_id)

            # Search employee embeddings
            results = self.vector_store.search_employees(
                org_id=org_id,
                query_embedding=query_embedding,
                top_k=top_k
            )

            # Format results
            formatted_results = []
            for match in results.get('matches', []):
                formatted_results.append({
                    'user_id': match['metadata'].get('user_id'),
                    'name': match['metadata'].get('name', ''),
                    'title': match['metadata'].get('title', ''),
                    'email': match['metadata'].get('email', ''),
                    'specialties': match['metadata'].get('specialties', ''),
                    'relevance': match.get('score', 0)
                })

            return formatted_results

        except Exception as e:
            print(f"Error searching employees: {e}")
            return []

    def hybrid_search(
        self,
        org_id: int,
        query: str,
        top_k: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Perform combined search across documents and employees

        Args:
            org_id: Organization ID
            query: Search query
            top_k: Number of results per category

        Returns:
            Dictionary with 'documents' and 'employees' keys
        """
        return {
            'documents': self.search_documents(org_id, query, top_k),
            'employees': self.search_employees(org_id, query, min(top_k, 5))
        }


class ResearchAgent:
    """
    Agent responsible for external research using Perplexity API
    Searches the web for information not available in internal documents
    """

    def __init__(self):
        self.perplexity_api_key = os.environ.get('PERPLEXITY_API_KEY')
        self.enabled = bool(self.perplexity_api_key)

        if not self.enabled:
            print("Warning: PERPLEXITY_API_KEY not set. External research disabled.")

    def query_external(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Query external sources using Perplexity API

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of external sources with URLs, titles, and snippets
        """
        if not self.enabled:
            return []

        try:
            import requests

            response = requests.post(
                'https://api.perplexity.ai/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.perplexity_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'llama-3.1-sonar-small-128k-online',
                    'messages': [
                        {
                            'role': 'user',
                            'content': query
                        }
                    ],
                    'return_citations': True,
                    'return_related_questions': False
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                citations = data.get('citations', [])

                results = []
                for idx, url in enumerate(citations[:max_results]):
                    results.append({
                        'url': url,
                        'title': f"Source {idx + 1}",
                        'snippet': content[:200] + '...' if len(content) > 200 else content,
                        'relevance': 1.0 - (idx * 0.1)  # Simple relevance scoring
                    })

                return results
            else:
                print(f"Perplexity API error: {response.status_code}")
                return []

        except Exception as e:
            print(f"Error querying external sources: {e}")
            return []


class SynthesisAgent:
    """
    Agent responsible for synthesizing information from multiple sources
    Generates coherent answers with proper attribution
    """

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.api_key = os.environ.get('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=self.api_key)

    def synthesize(
        self,
        query: str,
        doc_results: List[Dict],
        employee_results: List[Dict],
        external_results: Optional[List[Dict]] = None,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Synthesize answer from multiple sources

        Args:
            query: User's query
            doc_results: Document search results
            employee_results: Employee search results
            external_results: External research results (optional)
            context: Additional context (conversation history, user preferences, etc.)

        Returns:
            Dictionary with:
            - answer: Generated answer text
            - confidence: Confidence score (0-1)
            - sources_used: List of sources cited
            - reasoning: Explanation of how answer was derived
        """
        external_results = external_results or []
        context = context or {}

        # Build synthesis prompt
        prompt = self._build_synthesis_prompt(
            query=query,
            doc_results=doc_results,
            employee_results=employee_results,
            external_results=external_results,
            context=context
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': '''You are a helpful AI assistant that synthesizes information from multiple sources.

Your job is to:
1. Answer the user's question accurately based on the provided sources
2. Cite sources explicitly (e.g., "According to [document.pdf]...")
3. Acknowledge when information is incomplete or uncertain
4. Distinguish between internal company knowledge and external sources
5. Provide a structured, clear answer

If multiple sources conflict, acknowledge the conflict and provide both perspectives.
If no relevant information is found, say so honestly.'''
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1500
            )

            answer = response.choices[0].message.content

            # Extract which sources were actually used
            sources_used = self._extract_sources_used(
                answer=answer,
                doc_results=doc_results,
                employee_results=employee_results,
                external_results=external_results
            )

            # Calculate confidence based on source quality and quantity
            confidence = self._calculate_confidence(doc_results, employee_results, external_results)

            return {
                'answer': answer,
                'confidence': confidence,
                'sources_used': sources_used,
                'reasoning': f"Synthesized from {len(sources_used)} sources"
            }

        except Exception as e:
            print(f"Error synthesizing answer: {e}")
            return {
                'answer': "I encountered an error while processing your question. Please try again.",
                'confidence': 0.0,
                'sources_used': [],
                'reasoning': f"Error: {str(e)}"
            }

    def _build_synthesis_prompt(
        self,
        query: str,
        doc_results: List[Dict],
        employee_results: List[Dict],
        external_results: List[Dict],
        context: Dict
    ) -> str:
        """Build prompt for synthesis"""
        prompt_parts = [f"User Question: {query}\n"]

        # Add document sources
        if doc_results:
            prompt_parts.append("\n=== INTERNAL DOCUMENTS ===")
            for idx, doc in enumerate(doc_results[:5]):  # Top 5 docs
                prompt_parts.append(
                    f"\n[{doc['filename']}] (relevance: {doc['score']:.2f})"
                    f"\n{doc['chunk_text']}\n"
                )

        # Add employee sources
        if employee_results:
            prompt_parts.append("\n=== TEAM MEMBERS ===")
            for emp in employee_results[:3]:  # Top 3 employees
                prompt_parts.append(
                    f"\n{emp['name']} - {emp['title']}"
                    f"\nSkills/Specialties: {emp['specialties']}\n"
                )

        # Add external sources
        if external_results:
            prompt_parts.append("\n=== EXTERNAL SOURCES ===")
            for ext in external_results[:3]:  # Top 3 external
                prompt_parts.append(
                    f"\n[{ext['title']}] {ext['url']}"
                    f"\n{ext['snippet']}\n"
                )

        # Add context if available
        if context.get('conversation_history'):
            prompt_parts.append("\n=== CONVERSATION CONTEXT ===")
            prompt_parts.append(context['conversation_history'])

        prompt_parts.append("\nPlease provide a comprehensive answer based on the sources above.")

        return "\n".join(prompt_parts)

    def _extract_sources_used(
        self,
        answer: str,
        doc_results: List[Dict],
        employee_results: List[Dict],
        external_results: List[Dict]
    ) -> List[Dict]:
        """Extract which sources were actually cited in the answer"""
        sources = []

        # Check document citations
        for doc in doc_results:
            if doc['filename'] in answer:
                sources.append({
                    'type': 'document',
                    'filename': doc['filename'],
                    'doc_id': doc['doc_id']
                })

        # Check employee mentions
        for emp in employee_results:
            if emp['name'] in answer:
                sources.append({
                    'type': 'employee',
                    'name': emp['name'],
                    'user_id': emp['user_id']
                })

        # Check external citations
        for ext in external_results:
            if ext['url'] in answer or ext['title'] in answer:
                sources.append({
                    'type': 'external',
                    'url': ext['url'],
                    'title': ext['title']
                })

        return sources

    def _calculate_confidence(
        self,
        doc_results: List[Dict],
        employee_results: List[Dict],
        external_results: List[Dict]
    ) -> float:
        """Calculate confidence score based on source quality"""
        confidence = 0.0

        # Base confidence on number and quality of sources
        if doc_results:
            avg_doc_score = sum(d['score'] for d in doc_results[:3]) / min(len(doc_results), 3)
            confidence += avg_doc_score * 0.5

        if employee_results:
            confidence += 0.3

        if external_results:
            confidence += 0.2

        return min(confidence, 1.0)


class MasterOrchestrator:
    """
    Master agent that orchestrates the entire query processing pipeline
    - Analyzes user query
    - Determines which agents to use
    - Coordinates agent execution
    - Combines results into final answer
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

        # Initialize sub-agents
        self.data_agent = DataQueryAgent(vector_store, embedding_service)
        self.research_agent = ResearchAgent()
        self.synthesis_agent = SynthesisAgent()

        self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

    def process_query(
        self,
        conversation_id: int,
        org_id: int,
        user_id: int,
        query: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process user query through multi-agent pipeline

        Args:
            conversation_id: Conversation ID
            org_id: Organization ID
            user_id: User ID
            query: User's query
            context: Optional conversation context

        Returns:
            Dictionary with:
            - answer: Final answer text
            - reasoning_steps: List of reasoning steps taken
            - sources: Document, employee, and external sources used
            - confidence: Confidence score
        """
        context = context or {}
        reasoning_steps = []

        try:
            # Step 1: Analyze query to determine intent
            reasoning_steps.append("Analyzing query to determine information needs")
            query_analysis = self._analyze_query(query)

            # Step 2: Search internal documents
            reasoning_steps.append(f"Searching internal documents for: {query}")
            doc_results = self.data_agent.search_documents(
                org_id=org_id,
                query=query,
                top_k=10
            )
            reasoning_steps.append(f"Found {len(doc_results)} relevant document chunks")

            # Step 3: Search employees if query is about people/skills
            employee_results = []
            if query_analysis.get('needs_employee_search', False):
                reasoning_steps.append("Searching team member profiles")
                employee_results = self.data_agent.search_employees(
                    org_id=org_id,
                    query=query,
                    top_k=5
                )
                reasoning_steps.append(f"Found {len(employee_results)} relevant team members")

            # Step 4: Search external sources if needed
            external_results = []
            if query_analysis.get('needs_external_search', False):
                reasoning_steps.append("Searching external sources")
                external_results = self.research_agent.query_external(query)
                reasoning_steps.append(f"Found {len(external_results)} external sources")

            # Step 5: Synthesize final answer
            reasoning_steps.append("Synthesizing answer from all sources")
            synthesis_result = self.synthesis_agent.synthesize(
                query=query,
                doc_results=doc_results,
                employee_results=employee_results,
                external_results=external_results,
                context=context
            )

            # Store conversation in database
            self._store_conversation_message(
                conversation_id=conversation_id,
                role='user',
                content=query
            )

            self._store_conversation_message(
                conversation_id=conversation_id,
                role='assistant',
                content=synthesis_result['answer'],
                reasoning_json=json.dumps({
                    'steps': reasoning_steps,
                    'query_analysis': query_analysis,
                    'agents_used': ['data_query', 'synthesis'] +
                                   (['research'] if external_results else [])
                }),
                source_documents_json=json.dumps(doc_results[:5]),
                source_employees_json=json.dumps(employee_results),
                source_external_json=json.dumps(external_results)
            )

            return {
                'answer': synthesis_result['answer'],
                'reasoning_steps': reasoning_steps,
                'sources': {
                    'documents': doc_results[:5],
                    'employees': employee_results,
                    'external': external_results
                },
                'confidence': synthesis_result['confidence'],
                'query_analysis': query_analysis
            }

        except Exception as e:
            print(f"Error processing query: {e}")
            return {
                'answer': f"I encountered an error processing your question: {str(e)}",
                'reasoning_steps': reasoning_steps + [f"Error: {str(e)}"],
                'sources': {'documents': [], 'employees': [], 'external': []},
                'confidence': 0.0,
                'query_analysis': {}
            }

    def _analyze_query(self, query: str) -> Dict:
        """
        Analyze query to determine what kind of information is needed

        Returns:
            Dictionary with:
            - needs_employee_search: bool
            - needs_external_search: bool
            - query_type: str (factual, analytical, person-related, etc.)
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        'role': 'system',
                        'content': '''Analyze the user's query and determine:
1. Does it ask about people, team members, or who has certain skills? (needs_employee_search)
2. Does it require external/current information not likely in company docs? (needs_external_search)
3. What type of query is it? (factual, analytical, person-related, procedural)

Respond in JSON format:
{
  "needs_employee_search": true/false,
  "needs_external_search": true/false,
  "query_type": "factual|analytical|person-related|procedural|general"
}'''
                    },
                    {
                        'role': 'user',
                        'content': query
                    }
                ],
                temperature=0.2,
                max_tokens=100
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            print(f"Error analyzing query: {e}")
            return {
                'needs_employee_search': 'who' in query.lower() or 'team' in query.lower(),
                'needs_external_search': False,
                'query_type': 'general'
            }

    def _store_conversation_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        reasoning_json: Optional[str] = None,
        source_documents_json: Optional[str] = None,
        source_employees_json: Optional[str] = None,
        source_external_json: Optional[str] = None
    ):
        """Store message in chat_messages table"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO chat_messages (
                    conversation_id, role, content, reasoning_json,
                    source_documents_json, source_employees_json, source_external_json,
                    timestamp
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ''', (
                conversation_id, role, content, reasoning_json,
                source_documents_json, source_employees_json, source_external_json
            ))

            # Update conversation last_message_at
            cursor.execute('''
                UPDATE chat_conversations
                SET last_message_at = NOW()
                WHERE id = %s
            ''', (conversation_id,))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"Error storing conversation message: {e}")
