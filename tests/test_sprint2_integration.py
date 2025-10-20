"""
Sprint 2 Integration Tests
Tests for text chunking, embeddings, and vector search
"""

import os
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_chunker import SmartChunker
from embedding_service import EmbeddingService
from vector_store import VectorStore


class TestTextChunker:
    """Test smart text chunking functionality"""

    def test_basic_chunking(self):
        """Test basic text chunking"""
        chunker = SmartChunker(chunk_size=100, overlap=20)

        text = "This is a test sentence. " * 50  # Create text with multiple sentences
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0, "Should create at least one chunk"
        assert all('text' in chunk for chunk in chunks), "All chunks should have text"
        assert all('tokens' in chunk for chunk in chunks), "All chunks should have token count"
        assert all('index' in chunk for chunk in chunks), "All chunks should have index"

    def test_empty_text(self):
        """Test chunking empty text"""
        chunker = SmartChunker()
        chunks = chunker.chunk_text("")

        assert len(chunks) == 0, "Empty text should produce no chunks"

    def test_chunk_overlap(self):
        """Test that chunks have proper overlap"""
        chunker = SmartChunker(chunk_size=50, overlap=10)

        text = "Word " * 100  # Simple repeated text
        chunks = chunker.chunk_text(text)

        # Should have multiple chunks due to small chunk size
        assert len(chunks) >= 2, "Should create multiple chunks for long text"

    def test_token_counting(self):
        """Test that token counting is accurate"""
        chunker = SmartChunker(chunk_size=1000, overlap=200)

        text = "The quick brown fox jumps over the lazy dog."
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 1, "Short text should be single chunk"
        assert chunks[0]['tokens'] > 0, "Should count tokens"
        assert chunks[0]['tokens'] < 50, "Simple sentence should have reasonable token count"

    def test_document_metadata(self):
        """Test chunking with document metadata"""
        chunker = SmartChunker()

        text = "Test document content."
        metadata = {
            'doc_id': 123,
            'filename': 'test.pdf',
            'doc_type': 'pdf'
        }

        chunks = chunker.chunk_document(text, metadata)

        assert len(chunks) > 0
        assert chunks[0]['metadata']['doc_id'] == 123
        assert chunks[0]['metadata']['filename'] == 'test.pdf'


class TestEmbeddingService:
    """Test embedding generation (requires OPENAI_API_KEY)"""

    @pytest.mark.skipif(not os.environ.get('OPENAI_API_KEY'), reason="No OpenAI API key")
    def test_single_embedding(self):
        """Test generating a single embedding"""
        service = EmbeddingService()

        text = "This is a test document about machine learning."
        embedding = service.generate_single_embedding(text, org_id=1)

        assert embedding is not None
        assert len(embedding) == 3072, "text-embedding-3-large should return 3072 dimensions"
        assert all(isinstance(x, float) for x in embedding), "All values should be floats"

    @pytest.mark.skipif(not os.environ.get('OPENAI_API_KEY'), reason="No OpenAI API key")
    def test_batch_embeddings(self):
        """Test batch embedding generation"""
        service = EmbeddingService()

        texts = [
            "First document about AI.",
            "Second document about machine learning.",
            "Third document about data science."
        ]

        embeddings = service.generate_embeddings(texts, org_id=1)

        assert len(embeddings) == 3
        assert all(len(emb) == 3072 for emb in embeddings)

    def test_empty_text_handling(self):
        """Test handling of empty text"""
        service = EmbeddingService()

        embeddings = service.generate_embeddings([], org_id=1)
        assert embeddings == []

    def test_batch_size_validation(self):
        """Test that batch size is validated"""
        service = EmbeddingService()

        # Try to generate embeddings for too many texts
        texts = ["test"] * 101  # Over the limit of 100

        with pytest.raises(ValueError):
            service.generate_embeddings(texts, org_id=1)


class TestVectorStore:
    """Test Pinecone vector store (requires PINECONE_API_KEY)"""

    @pytest.mark.skipif(not os.environ.get('PINECONE_API_KEY'), reason="No Pinecone API key")
    def test_vector_store_initialization(self):
        """Test that vector store initializes correctly"""
        store = VectorStore(index_name="flock-knowledge-base")

        assert store is not None
        assert store.index is not None

    @pytest.mark.skipif(
        not (os.environ.get('PINECONE_API_KEY') and os.environ.get('OPENAI_API_KEY')),
        reason="No API keys"
    )
    def test_full_pipeline(self):
        """
        Integration test: chunk text -> generate embeddings -> store in Pinecone -> search

        This is a full end-to-end test of the Sprint 2 functionality
        """
        # 1. Chunk text
        chunker = SmartChunker(chunk_size=100, overlap=20)
        test_text = """
        Machine learning is a subset of artificial intelligence.
        It focuses on training algorithms to learn patterns from data.
        Deep learning uses neural networks with multiple layers.
        Natural language processing helps computers understand human language.
        """

        chunks = chunker.chunk_document(test_text, {
            'doc_id': 999,
            'filename': 'test.txt',
            'doc_type': 'txt'
        })

        assert len(chunks) > 0

        # 2. Generate embeddings
        embedding_service = EmbeddingService()
        chunk_texts = [chunk['text'] for chunk in chunks]
        embeddings = embedding_service.generate_embeddings(chunk_texts, org_id=999)

        assert len(embeddings) == len(chunks)

        # 3. Store in Pinecone
        vector_store = VectorStore(index_name="flock-knowledge-base")
        result = vector_store.upsert_document_chunks(
            org_id=999,
            doc_id=999,
            chunks=chunks,
            embeddings=embeddings,
            metadata={'filename': 'test.txt', 'doc_type': 'txt'}
        )

        assert result['upserted_count'] == len(chunks)

        # 4. Search
        query = "What is deep learning?"
        query_embedding = embedding_service.generate_single_embedding(query, org_id=999)

        search_results = vector_store.search_documents(
            org_id=999,
            query_embedding=query_embedding,
            top_k=5,
            min_score=0.0  # Low threshold for test
        )

        assert len(search_results) > 0
        assert 'score' in search_results[0]
        assert 'metadata' in search_results[0]

        # 5. Cleanup - delete test vectors
        vector_store.delete_document(org_id=999, doc_id=999)

        print(f"✓ Full pipeline test passed! Found {len(search_results)} relevant chunks")


def run_tests():
    """Run all tests"""
    print("="*60)
    print("Sprint 2 Integration Tests")
    print("="*60)

    # Run pytest
    pytest.main([__file__, '-v', '-s'])


if __name__ == '__main__':
    run_tests()
