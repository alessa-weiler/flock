"""
Vector Store for Pinecone integration
Handles vector storage, search, and management for document embeddings
"""

import os
import time
from typing import List, Dict, Optional, Any
from pinecone import Pinecone, ServerlessSpec
import json


class VectorStore:
    """
    Vector store service using Pinecone

    Features:
    - Namespace-based organization isolation
    - Batch upsert for efficiency
    - Metadata filtering
    - Hybrid search support
    - Production error handling
    """

    # Pinecone limits
    MAX_UPSERT_BATCH_SIZE = 100
    MAX_QUERY_TOP_K = 10000
    DEFAULT_TOP_K = 10

    # Embedding dimensions for text-embedding-3-large
    EMBEDDING_DIMENSION = 3072

    def __init__(self, index_name: str = "flock-knowledge-base"):
        """
        Initialize vector store

        Args:
            index_name: Name of the Pinecone index
        """
        self.index_name = index_name

        # Get Pinecone configuration from environment
        self.api_key = os.environ.get('PINECONE_API_KEY')
        self.environment = os.environ.get('PINECONE_ENVIRONMENT', 'us-east-1')

        if not self.api_key:
            raise ValueError("PINECONE_API_KEY environment variable not set")

        # Initialize Pinecone client
        try:
            self.pc = Pinecone(api_key=self.api_key)
            self._ensure_index_exists()
            self.index = self.pc.Index(self.index_name)
            print(f"✓ Connected to Pinecone index: {self.index_name}")
        except Exception as e:
            raise Exception(f"Failed to initialize Pinecone: {e}")

    def _ensure_index_exists(self):
        """
        Ensure the Pinecone index exists, create if not

        Raises:
            Exception if index creation fails
        """
        try:
            # List existing indexes
            existing_indexes = [index.name for index in self.pc.list_indexes()]

            if self.index_name not in existing_indexes:
                print(f"Index {self.index_name} not found, creating...")

                # Create index with serverless spec (recommended for production)
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.EMBEDDING_DIMENSION,
                    metric='cosine',  # Cosine similarity for text embeddings
                    spec=ServerlessSpec(
                        cloud='aws',
                        region=self.environment
                    )
                )

                # Wait for index to be ready
                print(f"Waiting for index {self.index_name} to be ready...")
                timeout = 60  # 60 seconds timeout
                start_time = time.time()

                while time.time() - start_time < timeout:
                    index_description = self.pc.describe_index(self.index_name)
                    if index_description.status.ready:
                        print(f"✓ Index {self.index_name} is ready")
                        return
                    time.sleep(2)

                raise Exception(f"Index {self.index_name} not ready after {timeout}s")

            else:
                print(f"✓ Index {self.index_name} already exists")

        except Exception as e:
            raise Exception(f"Failed to ensure index exists: {e}")

    def _get_namespace(self, org_id: int) -> str:
        """
        Get namespace for organization

        Args:
            org_id: Organization ID

        Returns:
            Namespace string
        """
        return f"org_{org_id}"

    def _create_vector_id(self, doc_id: int, chunk_idx: int, is_employee: bool = False, user_id: Optional[int] = None) -> str:
        """
        Create a unique vector ID

        Args:
            doc_id: Document ID (or user_id for employees)
            chunk_idx: Chunk index
            is_employee: Whether this is an employee embedding
            user_id: User ID for employee embeddings

        Returns:
            Vector ID string
        """
        if is_employee and user_id:
            return f"employee_{user_id}"
        else:
            return f"doc_{doc_id}_chunk_{chunk_idx}"

    def upsert_document_chunks(
        self,
        org_id: int,
        doc_id: int,
        chunks: List[Dict],
        embeddings: List[List[float]],
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Upsert document chunks to Pinecone

        Args:
            org_id: Organization ID
            doc_id: Document ID
            chunks: List of chunk dictionaries with text, index, tokens, metadata
            embeddings: List of embedding vectors
            metadata: Additional metadata to include

        Returns:
            Dictionary with upsert results
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"Number of chunks ({len(chunks)}) must match embeddings ({len(embeddings)})")

        if not chunks:
            return {'upserted_count': 0, 'message': 'No chunks to upsert'}

        namespace = self._get_namespace(org_id)
        metadata = metadata or {}

        # Prepare vectors for upsert
        vectors = []
        for chunk, embedding in zip(chunks, embeddings):
            vector_id = self._create_vector_id(doc_id, chunk['index'])

            # Combine metadata
            vector_metadata = {
                'doc_id': doc_id,
                'chunk_index': chunk['index'],
                'text': chunk['text'][:1000],  # Limit text in metadata to 1000 chars
                'tokens': chunk['tokens'],
                'org_id': org_id,
                **metadata,
                **chunk.get('metadata', {})
            }

            # Convert metadata values to JSON-serializable types
            vector_metadata = self._sanitize_metadata(vector_metadata)

            vectors.append({
                'id': vector_id,
                'values': embedding,
                'metadata': vector_metadata
            })

        # Upsert in batches
        total_upserted = 0
        batch_size = self.MAX_UPSERT_BATCH_SIZE

        try:
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                self.index.upsert(
                    vectors=batch,
                    namespace=namespace
                )
                total_upserted += len(batch)
                print(f"✓ Upserted batch {i // batch_size + 1}: {len(batch)} vectors to namespace {namespace}")

            return {
                'upserted_count': total_upserted,
                'namespace': namespace,
                'doc_id': doc_id,
                'message': f'Successfully upserted {total_upserted} chunks'
            }

        except Exception as e:
            raise Exception(f"Failed to upsert document chunks: {e}")

    def upsert_employee_embedding(
        self,
        org_id: int,
        user_id: int,
        embedding: List[float],
        metadata: Dict
    ) -> Dict[str, Any]:
        """
        Upsert employee embedding to Pinecone

        Args:
            org_id: Organization ID
            user_id: User ID
            embedding: Embedding vector
            metadata: Employee metadata (name, title, bio, skills, etc.)

        Returns:
            Dictionary with upsert results
        """
        namespace = self._get_namespace(org_id)
        vector_id = self._create_vector_id(None, None, is_employee=True, user_id=user_id)

        # Sanitize metadata
        vector_metadata = {
            'user_id': user_id,
            'org_id': org_id,
            'type': 'employee',
            **metadata
        }
        vector_metadata = self._sanitize_metadata(vector_metadata)

        try:
            self.index.upsert(
                vectors=[{
                    'id': vector_id,
                    'values': embedding,
                    'metadata': vector_metadata
                }],
                namespace=namespace
            )

            print(f"✓ Upserted employee embedding: user_id={user_id}, namespace={namespace}")

            return {
                'upserted_count': 1,
                'namespace': namespace,
                'user_id': user_id,
                'vector_id': vector_id
            }

        except Exception as e:
            raise Exception(f"Failed to upsert employee embedding: {e}")

    def search(
        self,
        org_id: int,
        query_embedding: List[float],
        top_k: int = DEFAULT_TOP_K,
        filters: Optional[Dict] = None,
        include_metadata: bool = True
    ) -> List[Dict]:
        """
        Search vectors in Pinecone

        Args:
            org_id: Organization ID
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Metadata filters (Pinecone filter syntax)
            include_metadata: Whether to include metadata in results

        Returns:
            List of search results with id, score, and metadata
        """
        if top_k > self.MAX_QUERY_TOP_K:
            raise ValueError(f"top_k {top_k} exceeds maximum {self.MAX_QUERY_TOP_K}")

        namespace = self._get_namespace(org_id)

        try:
            # Build query
            query_params = {
                'vector': query_embedding,
                'top_k': top_k,
                'namespace': namespace,
                'include_metadata': include_metadata
            }

            if filters:
                query_params['filter'] = filters

            # Execute query
            start_time = time.time()
            results = self.index.query(**query_params)
            end_time = time.time()

            print(f"✓ Search completed in {(end_time - start_time) * 1000:.2f}ms, found {len(results.matches)} results")

            # Format results
            formatted_results = []
            for match in results.matches:
                result = {
                    'id': match.id,
                    'score': match.score,
                }
                if include_metadata:
                    result['metadata'] = match.metadata

                formatted_results.append(result)

            return formatted_results

        except Exception as e:
            raise Exception(f"Failed to search vectors: {e}")

    def search_documents(
        self,
        org_id: int,
        query_embedding: List[float],
        top_k: int = DEFAULT_TOP_K,
        doc_type: Optional[str] = None,
        min_score: float = 0.7
    ) -> List[Dict]:
        """
        Search for relevant document chunks

        Args:
            org_id: Organization ID
            query_embedding: Query embedding
            top_k: Number of results
            doc_type: Filter by document type (pdf, docx, etc.)
            min_score: Minimum similarity score (0-1)

        Returns:
            List of relevant document chunks
        """
        # Build filters
        filters = {}
        if doc_type:
            filters['doc_type'] = {'$eq': doc_type}

        results = self.search(org_id, query_embedding, top_k, filters)

        # Filter by minimum score
        filtered_results = [r for r in results if r['score'] >= min_score]

        print(f"✓ Found {len(filtered_results)} documents above score threshold {min_score}")

        return filtered_results

    def search_employees(
        self,
        org_id: int,
        query_embedding: List[float],
        top_k: int = 10
    ) -> List[Dict]:
        """
        Search for relevant employees

        Args:
            org_id: Organization ID
            query_embedding: Query embedding
            top_k: Number of results

        Returns:
            List of relevant employees
        """
        filters = {'type': {'$eq': 'employee'}}
        results = self.search(org_id, query_embedding, top_k, filters)

        print(f"✓ Found {len(results)} relevant employees")

        return results

    def delete_document(self, org_id: int, doc_id: int) -> Dict[str, Any]:
        """
        Delete all vectors for a document

        Args:
            org_id: Organization ID
            doc_id: Document ID

        Returns:
            Dictionary with deletion results
        """
        namespace = self._get_namespace(org_id)

        try:
            # Delete by filter (all vectors with matching doc_id)
            self.index.delete(
                filter={'doc_id': {'$eq': doc_id}},
                namespace=namespace
            )

            print(f"✓ Deleted all vectors for doc_id={doc_id} in namespace={namespace}")

            return {
                'deleted': True,
                'doc_id': doc_id,
                'namespace': namespace
            }

        except Exception as e:
            raise Exception(f"Failed to delete document vectors: {e}")

    def delete_employee(self, org_id: int, user_id: int) -> Dict[str, Any]:
        """
        Delete employee embedding

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            Dictionary with deletion results
        """
        namespace = self._get_namespace(org_id)
        vector_id = self._create_vector_id(None, None, is_employee=True, user_id=user_id)

        try:
            self.index.delete(
                ids=[vector_id],
                namespace=namespace
            )

            print(f"✓ Deleted employee embedding: user_id={user_id}")

            return {
                'deleted': True,
                'user_id': user_id,
                'vector_id': vector_id
            }

        except Exception as e:
            raise Exception(f"Failed to delete employee embedding: {e}")

    def delete_namespace(self, org_id: int) -> Dict[str, Any]:
        """
        Delete entire namespace (all vectors for an organization)

        Args:
            org_id: Organization ID

        Returns:
            Dictionary with deletion results
        """
        namespace = self._get_namespace(org_id)

        try:
            self.index.delete(delete_all=True, namespace=namespace)

            print(f"✓ Deleted entire namespace: {namespace}")

            return {
                'deleted': True,
                'namespace': namespace,
                'org_id': org_id
            }

        except Exception as e:
            raise Exception(f"Failed to delete namespace: {e}")

    def get_stats(self, org_id: int) -> Dict[str, Any]:
        """
        Get statistics for an organization's namespace

        Args:
            org_id: Organization ID

        Returns:
            Dictionary with namespace statistics
        """
        namespace = self._get_namespace(org_id)

        try:
            stats = self.index.describe_index_stats()

            namespace_stats = stats.namespaces.get(namespace, {})

            return {
                'namespace': namespace,
                'vector_count': namespace_stats.get('vector_count', 0),
                'total_vectors': stats.total_vector_count,
                'dimension': stats.dimension,
                'index_fullness': stats.index_fullness
            }

        except Exception as e:
            raise Exception(f"Failed to get stats: {e}")

    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """
        Sanitize metadata to ensure it's compatible with Pinecone

        Args:
            metadata: Original metadata

        Returns:
            Sanitized metadata
        """
        sanitized = {}

        for key, value in metadata.items():
            # Skip None values
            if value is None:
                continue

            # Convert lists to JSON strings (Pinecone doesn't support list metadata)
            if isinstance(value, (list, dict)):
                sanitized[key] = json.dumps(value)
            # Keep primitive types
            elif isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            # Convert other types to string
            else:
                sanitized[key] = str(value)

        return sanitized


def get_vector_store(index_name: str = "flock-knowledge-base") -> VectorStore:
    """
    Factory function to get vector store instance

    Args:
        index_name: Pinecone index name

    Returns:
        Configured VectorStore instance
    """
    return VectorStore(index_name=index_name)
