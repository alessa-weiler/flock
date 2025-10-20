"""
Smart Text Chunker with tiktoken for accurate token counting
Splits text into chunks while preserving structure and context
"""

import re
import tiktoken
from typing import List, Dict, Optional


class SmartChunker:
    """
    Smart text chunking with token-aware splitting and overlap

    Features:
    - Accurate token counting with tiktoken
    - Preserves document structure (paragraphs, sentences)
    - Configurable chunk size and overlap
    - Metadata preservation for context
    """

    def __init__(self, chunk_size: int = 1000, overlap: int = 200, model: str = "text-embedding-3-large"):
        """
        Initialize chunker with configuration

        Args:
            chunk_size: Target size of each chunk in tokens (default: 1000)
            overlap: Number of tokens to overlap between chunks (default: 200)
            model: Model name for tokenizer (default: text-embedding-3-large)
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap cannot be negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.model = model

        # Initialize tiktoken encoder
        # Use cl100k_base encoding which is used by text-embedding-3-* models
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            raise Exception(f"Failed to initialize tiktoken encoder: {e}")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        try:
            return len(self.encoder.encode(text))
        except Exception as e:
            print(f"Warning: Failed to count tokens: {e}")
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4

    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Handle empty or whitespace-only text
        if not text or not text.strip():
            return []

        # Split on sentence boundaries (., !, ?) followed by space and capital letter
        # Also handle common abbreviations (Dr., Mr., Mrs., etc.)
        sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s+(?=[A-Z])', text)

        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def split_into_paragraphs(self, text: str) -> List[str]:
        """
        Split text into paragraphs (separated by double newlines)

        Args:
            text: Text to split

        Returns:
            List of paragraphs
        """
        if not text or not text.strip():
            return []

        # Split on double newlines
        paragraphs = re.split(r'\n\s*\n', text)

        # Filter out empty paragraphs
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def chunk_text(self, text: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        Chunk text into token-sized pieces with overlap

        Args:
            text: Text to chunk
            metadata: Optional metadata to include with each chunk

        Returns:
            List of chunk dictionaries with text, index, tokens, and metadata
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        chunks = []

        # First, try to split by paragraphs to preserve structure
        paragraphs = self.split_into_paragraphs(text)

        if not paragraphs:
            # Fallback: treat entire text as one paragraph
            paragraphs = [text]

        # Process paragraphs into chunks
        current_chunk_text = ""
        current_chunk_tokens = 0
        chunk_index = 0

        for para_idx, paragraph in enumerate(paragraphs):
            # Split paragraph into sentences
            sentences = self.split_into_sentences(paragraph)

            if not sentences:
                # If no sentences detected, treat paragraph as single sentence
                sentences = [paragraph]

            for sentence in sentences:
                sentence_tokens = self.count_tokens(sentence)

                # Handle very long sentences (longer than chunk_size)
                if sentence_tokens > self.chunk_size:
                    # If we have accumulated text, save it as a chunk first
                    if current_chunk_text:
                        chunks.append({
                            'text': current_chunk_text.strip(),
                            'index': chunk_index,
                            'tokens': current_chunk_tokens,
                            'metadata': {
                                **metadata,
                                'chunk_type': 'standard',
                                'paragraph_range': f'{para_idx}'
                            }
                        })
                        chunk_index += 1
                        current_chunk_text = ""
                        current_chunk_tokens = 0

                    # Split long sentence by characters as fallback
                    words = sentence.split()
                    temp_chunk = ""
                    temp_tokens = 0

                    for word in words:
                        word_tokens = self.count_tokens(word + " ")
                        if temp_tokens + word_tokens > self.chunk_size:
                            if temp_chunk:
                                chunks.append({
                                    'text': temp_chunk.strip(),
                                    'index': chunk_index,
                                    'tokens': temp_tokens,
                                    'metadata': {
                                        **metadata,
                                        'chunk_type': 'oversized_split',
                                        'paragraph_range': f'{para_idx}'
                                    }
                                })
                                chunk_index += 1
                            temp_chunk = word + " "
                            temp_tokens = word_tokens
                        else:
                            temp_chunk += word + " "
                            temp_tokens += word_tokens

                    if temp_chunk:
                        current_chunk_text = temp_chunk
                        current_chunk_tokens = temp_tokens

                    continue

                # Check if adding this sentence would exceed chunk_size
                if current_chunk_tokens + sentence_tokens > self.chunk_size:
                    # Save current chunk
                    if current_chunk_text:
                        chunks.append({
                            'text': current_chunk_text.strip(),
                            'index': chunk_index,
                            'tokens': current_chunk_tokens,
                            'metadata': {
                                **metadata,
                                'chunk_type': 'standard',
                                'paragraph_range': f'{para_idx}'
                            }
                        })
                        chunk_index += 1

                    # Start new chunk with overlap
                    if self.overlap > 0 and chunks:
                        # Get last N tokens from previous chunk for overlap
                        overlap_text = self._get_overlap_text(current_chunk_text, self.overlap)
                        current_chunk_text = overlap_text + " " + sentence + " "
                        current_chunk_tokens = self.count_tokens(current_chunk_text)
                    else:
                        current_chunk_text = sentence + " "
                        current_chunk_tokens = sentence_tokens
                else:
                    # Add sentence to current chunk
                    current_chunk_text += sentence + " "
                    current_chunk_tokens += sentence_tokens

        # Don't forget the last chunk
        if current_chunk_text.strip():
            chunks.append({
                'text': current_chunk_text.strip(),
                'index': chunk_index,
                'tokens': current_chunk_tokens,
                'metadata': {
                    **metadata,
                    'chunk_type': 'standard',
                    'paragraph_range': f'{len(paragraphs)-1}'
                }
            })

        return chunks

    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """
        Get the last N tokens from text for overlap

        Args:
            text: Source text
            overlap_tokens: Number of tokens to extract

        Returns:
            Text containing approximately overlap_tokens tokens
        """
        if not text or overlap_tokens <= 0:
            return ""

        # Encode text to tokens
        tokens = self.encoder.encode(text)

        # Get last N tokens
        if len(tokens) <= overlap_tokens:
            return text

        overlap_token_ids = tokens[-overlap_tokens:]

        # Decode back to text
        overlap_text = self.encoder.decode(overlap_token_ids)

        return overlap_text

    def chunk_document(self, document_text: str, document_metadata: Dict) -> List[Dict]:
        """
        Convenience method to chunk a full document with metadata

        Args:
            document_text: Full document text
            document_metadata: Document metadata (filename, doc_id, etc.)

        Returns:
            List of chunks with enriched metadata
        """
        base_metadata = {
            'doc_id': document_metadata.get('doc_id'),
            'filename': document_metadata.get('filename'),
            'doc_type': document_metadata.get('doc_type'),
            'upload_date': document_metadata.get('upload_date'),
        }

        chunks = self.chunk_text(document_text, metadata=base_metadata)

        # Add total chunk count to each chunk
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk['metadata']['total_chunks'] = total_chunks

        return chunks


def get_chunker(chunk_size: int = 1000, overlap: int = 200) -> SmartChunker:
    """
    Factory function to get a configured chunker instance

    Args:
        chunk_size: Target chunk size in tokens
        overlap: Overlap size in tokens

    Returns:
        Configured SmartChunker instance
    """
    return SmartChunker(chunk_size=chunk_size, overlap=overlap)
