"""
Embedding Service for generating and managing OpenAI embeddings
Includes cost tracking, rate limiting, and production error handling
"""

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime
from openai import OpenAI, RateLimitError, APIError, APIConnectionError
import json


class EmbeddingService:
    """
    Service for generating embeddings with OpenAI API

    Features:
    - Batch processing (up to 100 texts per call)
    - Rate limiting with exponential backoff
    - Cost tracking and budget management
    - Comprehensive error handling
    - Circuit breaker pattern for API failures
    """

    # Pricing per 1K tokens (as of Jan 2025)
    COST_PER_1K_TOKENS = 0.00013  # $0.13 per 1M tokens = $0.00013 per 1K

    # Rate limits (OpenAI limits)
    MAX_BATCH_SIZE = 100  # Maximum texts per API call
    MAX_REQUESTS_PER_MINUTE = 3000
    MAX_TOKENS_PER_MINUTE = 1000000

    # Circuit breaker settings
    MAX_CONSECUTIVE_FAILURES = 5
    CIRCUIT_OPEN_DURATION = 300  # 5 minutes

    def __init__(self, model: str = "text-embedding-3-large"):
        """
        Initialize embedding service

        Args:
            model: OpenAI embedding model (default: text-embedding-3-large)
        """
        self.model = model
        self.api_key = os.environ.get('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)

        # Circuit breaker state
        self.consecutive_failures = 0
        self.circuit_open_until = None

        # Rate limiting state
        self.request_times = []
        self.tokens_used_in_window = []

    def _get_db_connection(self):
        """Get PostgreSQL database connection"""
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    def _check_circuit_breaker(self):
        """
        Check if circuit breaker is open

        Raises:
            Exception if circuit breaker is open
        """
        if self.circuit_open_until:
            if time.time() < self.circuit_open_until:
                raise Exception(
                    f"Circuit breaker is open. Service unavailable until "
                    f"{datetime.fromtimestamp(self.circuit_open_until).isoformat()}"
                )
            else:
                # Circuit breaker timeout expired, reset
                print("Circuit breaker timeout expired, resetting...")
                self.circuit_open_until = None
                self.consecutive_failures = 0

    def _record_failure(self):
        """Record an API failure for circuit breaker"""
        self.consecutive_failures += 1
        print(f"API failure recorded. Consecutive failures: {self.consecutive_failures}")

        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self.circuit_open_until = time.time() + self.CIRCUIT_OPEN_DURATION
            print(f"Circuit breaker opened until {datetime.fromtimestamp(self.circuit_open_until).isoformat()}")

    def _record_success(self):
        """Record a successful API call"""
        if self.consecutive_failures > 0:
            print(f"Resetting consecutive failures (was {self.consecutive_failures})")
        self.consecutive_failures = 0

    def _wait_for_rate_limit(self, estimated_tokens: int):
        """
        Implement rate limiting to stay within OpenAI limits

        Args:
            estimated_tokens: Estimated tokens for this request
        """
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window

        # Clean up old request times
        self.request_times = [t for t in self.request_times if t > window_start]
        self.tokens_used_in_window = [
            (t, tokens) for t, tokens in self.tokens_used_in_window if t > window_start
        ]

        # Check requests per minute
        if len(self.request_times) >= self.MAX_REQUESTS_PER_MINUTE:
            sleep_time = self.request_times[0] - window_start + 1
            print(f"Rate limit: sleeping {sleep_time:.2f}s for RPM limit")
            time.sleep(sleep_time)
            # Refresh window
            current_time = time.time()
            window_start = current_time - 60
            self.request_times = [t for t in self.request_times if t > window_start]

        # Check tokens per minute
        tokens_in_window = sum(tokens for _, tokens in self.tokens_used_in_window)
        if tokens_in_window + estimated_tokens > self.MAX_TOKENS_PER_MINUTE:
            sleep_time = self.tokens_used_in_window[0][0] - window_start + 1
            print(f"Rate limit: sleeping {sleep_time:.2f}s for TPM limit")
            time.sleep(sleep_time)
            # Refresh window
            current_time = time.time()
            window_start = current_time - 60
            self.tokens_used_in_window = [
                (t, tokens) for t, tokens in self.tokens_used_in_window if t > window_start
            ]

        # Record this request
        self.request_times.append(current_time)

    def check_budget(self, org_id: int, estimated_tokens: int) -> Tuple[bool, str]:
        """
        Check if organization has budget for embedding generation

        Args:
            org_id: Organization ID
            estimated_tokens: Estimated tokens to be used

        Returns:
            Tuple of (has_budget: bool, message: str)
        """
        # TODO: Implement organization budget limits
        # For now, allow all requests
        # In future: query organization settings for monthly/daily limits

        estimated_cost = (estimated_tokens / 1000) * self.COST_PER_1K_TOKENS

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # Check usage for current month
            cursor.execute('''
                SELECT SUM(tokens_used) as total_tokens, SUM(estimated_cost) as total_cost
                FROM embedding_usage
                WHERE organization_id = %s
                AND date >= DATE_TRUNC('month', CURRENT_DATE)
            ''', (org_id,))

            result = cursor.fetchone()
            conn.close()

            total_tokens = result['total_tokens'] or 0
            total_cost = result['total_cost'] or 0.0

            # Example budget limit: $100/month
            MONTHLY_BUDGET = 100.0

            if total_cost + estimated_cost > MONTHLY_BUDGET:
                return False, f"Monthly budget exceeded. Current: ${total_cost:.2f}, Limit: ${MONTHLY_BUDGET:.2f}"

            # Warning at 80%
            if total_cost + estimated_cost > MONTHLY_BUDGET * 0.8:
                print(f"WARNING: Organization {org_id} approaching budget limit: ${total_cost:.2f} / ${MONTHLY_BUDGET:.2f}")

            return True, f"Budget OK. Current: ${total_cost:.2f} / ${MONTHLY_BUDGET:.2f}"

        except Exception as e:
            print(f"Error checking budget: {e}")
            # Allow on error (fail open)
            return True, "Budget check failed, allowing request"

    def track_usage(self, org_id: int, tokens_used: int):
        """
        Track embedding usage for cost monitoring

        Args:
            org_id: Organization ID
            tokens_used: Number of tokens used
        """
        cost = (tokens_used / 1000) * self.COST_PER_1K_TOKENS

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO embedding_usage (organization_id, date, tokens_used, api_calls, estimated_cost)
                VALUES (%s, CURRENT_DATE, %s, 1, %s)
                ON CONFLICT (organization_id, date)
                DO UPDATE SET
                    tokens_used = embedding_usage.tokens_used + EXCLUDED.tokens_used,
                    api_calls = embedding_usage.api_calls + 1,
                    estimated_cost = embedding_usage.estimated_cost + EXCLUDED.estimated_cost
            ''', (org_id, tokens_used, cost))

            conn.commit()
            conn.close()

            print(f"Tracked usage: org={org_id}, tokens={tokens_used}, cost=${cost:.6f}")

        except Exception as e:
            print(f"Error tracking usage: {e}")

    def generate_embeddings(
        self,
        texts: List[str],
        org_id: int,
        max_retries: int = 3
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts

        Args:
            texts: List of texts to embed (max 100)
            org_id: Organization ID for budget tracking
            max_retries: Maximum number of retries on failure

        Returns:
            List of embedding vectors

        Raises:
            Exception on failure after retries
        """
        if not texts:
            return []

        if len(texts) > self.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size {len(texts)} exceeds maximum {self.MAX_BATCH_SIZE}")

        # Check circuit breaker
        self._check_circuit_breaker()

        # Estimate tokens (rough estimate: 1 token ≈ 4 characters)
        estimated_tokens = sum(len(text) for text in texts) // 4

        # Check budget
        has_budget, budget_message = self.check_budget(org_id, estimated_tokens)
        if not has_budget:
            raise Exception(f"Budget limit exceeded: {budget_message}")

        # Wait for rate limit if needed
        self._wait_for_rate_limit(estimated_tokens)

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                print(f"Generating embeddings for {len(texts)} texts (attempt {attempt + 1}/{max_retries})")

                # Call OpenAI API
                start_time = time.time()
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts
                )
                end_time = time.time()

                # Extract embeddings
                embeddings = [item.embedding for item in response.data]

                # Get actual token usage from response
                tokens_used = response.usage.total_tokens

                # Record in rate limit window
                self.tokens_used_in_window.append((time.time(), tokens_used))

                # Track usage
                self.track_usage(org_id, tokens_used)

                # Record success
                self._record_success()

                print(f"✓ Generated {len(embeddings)} embeddings in {end_time - start_time:.2f}s, used {tokens_used} tokens")

                return embeddings

            except RateLimitError as e:
                last_error = e
                # Exponential backoff: 2^attempt seconds
                wait_time = 2 ** attempt
                print(f"Rate limit error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                self._record_failure()

            except (APIError, APIConnectionError) as e:
                last_error = e
                print(f"API error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                self._record_failure()

            except Exception as e:
                last_error = e
                print(f"Unexpected error generating embeddings: {e}")
                self._record_failure()
                raise

        # All retries exhausted
        self._record_failure()
        raise Exception(f"Failed to generate embeddings after {max_retries} attempts: {last_error}")

    def generate_embeddings_batched(
        self,
        texts: List[str],
        org_id: int,
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for a large list of texts in batches

        Args:
            texts: List of texts to embed
            org_id: Organization ID
            batch_size: Size of each batch (default 100)

        Returns:
            List of all embeddings
        """
        if not texts:
            return []

        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        print(f"Generating embeddings for {len(texts)} texts in {total_batches} batches")

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1

            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")

            embeddings = self.generate_embeddings(batch, org_id)
            all_embeddings.extend(embeddings)

            # Small delay between batches to be nice to the API
            if i + batch_size < len(texts):
                time.sleep(0.5)

        print(f"✓ Generated {len(all_embeddings)} embeddings total")
        return all_embeddings

    def generate_single_embedding(self, text: str, org_id: int) -> List[float]:
        """
        Convenience method to generate a single embedding

        Args:
            text: Text to embed
            org_id: Organization ID

        Returns:
            Single embedding vector
        """
        embeddings = self.generate_embeddings([text], org_id)
        return embeddings[0] if embeddings else []


def get_embedding_service(model: str = "text-embedding-3-large") -> EmbeddingService:
    """
    Factory function to get embedding service instance

    Args:
        model: OpenAI embedding model

    Returns:
        Configured EmbeddingService instance
    """
    return EmbeddingService(model=model)
