"""
RAG (Retrieval-Augmented Generation) Pipeline
Phase 7: Streamlined retrieve-augment-generate workflow
"""

import os
from typing import Dict, List, Optional, Any
from openai import OpenAI
from embedding_service import EmbeddingService
from vector_store import VectorStore


class RAGPipeline:
    """
    Simplified RAG pipeline for document-based question answering

    Pipeline stages:
    1. Retrieve: Find relevant document chunks via semantic search
    2. Augment: Build context-enriched prompt with retrieved chunks
    3. Generate: Generate answer using GPT-4 with citations
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        model: str = "gpt-4o"
    ):
        """
        Initialize RAG pipeline

        Args:
            vector_store: Vector store for document retrieval
            embedding_service: Service for generating embeddings
            model: OpenAI model to use for generation
        """
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.model = model

        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key)

    def retrieve(
        self,
        org_id: int,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        min_score: float = 0.7
    ) -> List[Dict]:
        """
        Retrieve relevant document chunks

        Args:
            org_id: Organization ID
            query: User query
            top_k: Number of chunks to retrieve
            filters: Optional metadata filters
            min_score: Minimum relevance score threshold

        Returns:
            List of relevant document chunks with metadata
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_single_embedding(query, org_id)

            # Search vector store
            results = self.vector_store.search(
                org_id=org_id,
                query_embedding=query_embedding,
                top_k=top_k,
                filters=filters
            )

            # Filter by minimum score and format results
            retrieved_chunks = []
            for match in results.get('matches', []):
                score = match.get('score', 0)
                if score >= min_score:
                    retrieved_chunks.append({
                        'text': match['metadata'].get('text', ''),
                        'filename': match['metadata'].get('filename', ''),
                        'doc_id': match['metadata'].get('doc_id'),
                        'doc_type': match['metadata'].get('doc_type', ''),
                        'score': score,
                        'page': match['metadata'].get('page'),
                        'chunk_index': match['metadata'].get('chunk_index')
                    })

            # Re-rank by score (already sorted by Pinecone, but ensure it)
            retrieved_chunks.sort(key=lambda x: x['score'], reverse=True)

            return retrieved_chunks

        except Exception as e:
            print(f"Error retrieving chunks: {e}")
            return []

    def augment(
        self,
        query: str,
        retrieved_chunks: List[Dict],
        context: Optional[Dict] = None,
        system_instructions: Optional[str] = None
    ) -> str:
        """
        Build augmented prompt with retrieved context

        Args:
            query: User query
            retrieved_chunks: Retrieved document chunks
            context: Additional context (conversation history, user preferences, etc.)
            system_instructions: Custom system instructions

        Returns:
            Augmented prompt string
        """
        context = context or {}

        # Start with context section
        prompt_parts = []

        # Add conversation history if available
        if context.get('conversation_history'):
            prompt_parts.append("=== CONVERSATION HISTORY ===")
            prompt_parts.append(context['conversation_history'])
            prompt_parts.append("")

        # Add retrieved documents
        if retrieved_chunks:
            prompt_parts.append("=== RELEVANT DOCUMENTS ===")
            for idx, chunk in enumerate(retrieved_chunks[:5]):  # Top 5 chunks
                source_info = f"[{chunk['filename']}"
                if chunk.get('page'):
                    source_info += f", page {chunk['page']}"
                source_info += f"] (relevance: {chunk['score']:.2f})"

                prompt_parts.append(f"\nSource {idx + 1}: {source_info}")
                prompt_parts.append(chunk['text'])
                prompt_parts.append("")

        # Add user query
        prompt_parts.append("=== USER QUESTION ===")
        prompt_parts.append(query)
        prompt_parts.append("")

        # Add instructions
        default_instructions = """Please answer the question based on the documents provided above.
- Cite sources explicitly (e.g., "According to [filename]...")
- If the answer isn't in the documents, say so
- Provide specific quotes when relevant
- Be concise but comprehensive"""

        prompt_parts.append("=== INSTRUCTIONS ===")
        prompt_parts.append(system_instructions or default_instructions)

        return "\n".join(prompt_parts)

    def generate(
        self,
        augmented_prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500
    ) -> Dict[str, Any]:
        """
        Generate answer using GPT-4

        Args:
            augmented_prompt: Augmented prompt with context
            system_message: Optional custom system message
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with:
            - answer: Generated answer text
            - usage: Token usage stats
            - model: Model used
        """
        default_system = """You are a helpful AI assistant for an organization's knowledge platform.
Your role is to answer questions based on internal company documents.

Guidelines:
- Always cite your sources explicitly
- Distinguish between facts from documents and your own reasoning
- If information is uncertain or missing, acknowledge it
- Be professional, clear, and concise
- Maintain confidentiality - only use provided internal documents"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': system_message or default_system
                    },
                    {
                        'role': 'user',
                        'content': augmented_prompt
                    }
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

            answer = response.choices[0].message.content
            usage = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }

            return {
                'answer': answer,
                'usage': usage,
                'model': self.model
            }

        except Exception as e:
            print(f"Error generating answer: {e}")
            return {
                'answer': f"I encountered an error generating the answer: {str(e)}",
                'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                'model': self.model
            }

    def query(
        self,
        org_id: int,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        context: Optional[Dict] = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        End-to-end RAG query: retrieve → augment → generate

        Args:
            org_id: Organization ID
            query: User query
            top_k: Number of chunks to retrieve
            filters: Optional metadata filters
            context: Additional context
            temperature: Generation temperature

        Returns:
            Dictionary with:
            - answer: Generated answer
            - sources: Retrieved document chunks used
            - usage: Token usage stats
        """
        # Step 1: Retrieve
        retrieved_chunks = self.retrieve(
            org_id=org_id,
            query=query,
            top_k=top_k,
            filters=filters
        )

        if not retrieved_chunks:
            return {
                'answer': "I couldn't find any relevant documents to answer your question. "
                         "Please try rephrasing or check if documents have been uploaded.",
                'sources': [],
                'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
            }

        # Step 2: Augment
        augmented_prompt = self.augment(
            query=query,
            retrieved_chunks=retrieved_chunks,
            context=context
        )

        # Step 3: Generate
        generation_result = self.generate(
            augmented_prompt=augmented_prompt,
            temperature=temperature
        )

        return {
            'answer': generation_result['answer'],
            'sources': retrieved_chunks[:5],  # Return top 5 sources
            'usage': generation_result['usage'],
            'model': generation_result['model']
        }

    def stream_query(
        self,
        org_id: int,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        context: Optional[Dict] = None,
        temperature: float = 0.3
    ):
        """
        Stream RAG query response token by token

        Args:
            Same as query()

        Yields:
            Tuples of (chunk_type, data):
            - ('sources', List[Dict]): Retrieved sources
            - ('token', str): Generated tokens
            - ('usage', Dict): Final usage stats
        """
        # Step 1: Retrieve
        retrieved_chunks = self.retrieve(
            org_id=org_id,
            query=query,
            top_k=top_k,
            filters=filters
        )

        # Yield sources first
        yield ('sources', retrieved_chunks[:5])

        if not retrieved_chunks:
            yield ('token', "I couldn't find any relevant documents to answer your question.")
            yield ('usage', {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
            return

        # Step 2: Augment
        augmented_prompt = self.augment(
            query=query,
            retrieved_chunks=retrieved_chunks,
            context=context
        )

        # Step 3: Generate with streaming
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': """You are a helpful AI assistant for an organization's knowledge platform.
Answer questions based on internal company documents. Always cite sources."""
                    },
                    {
                        'role': 'user',
                        'content': augmented_prompt
                    }
                ],
                temperature=temperature,
                max_tokens=1500,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield ('token', chunk.choices[0].delta.content)

            # Note: Usage stats not available in streaming mode
            yield ('usage', {'note': 'Usage stats not available in streaming mode'})

        except Exception as e:
            print(f"Error streaming answer: {e}")
            yield ('token', f"\n\nError: {str(e)}")
            yield ('usage', {'error': str(e)})
