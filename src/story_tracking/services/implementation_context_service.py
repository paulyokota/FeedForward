"""
Implementation Context Service

Generates hybrid implementation context by:
1. Retrieving similar stories/orphans/evidence via vector search
2. Synthesizing actionable guidance using OpenAI

Issue: #180
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openai import OpenAI, OpenAIError

from ...research.unified_search import UnifiedSearchService
from ..models import (
    ImplementationContext,
    ImplementationContextCandidate,
    ImplementationContextFile,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TOP_K = 10
DEFAULT_MIN_SIMILARITY = 0.5
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 15


class ImplementationContextService:
    """
    Generates implementation context for stories.

    Two-phase approach:
    1. Retrieval: Vector search for top-K similar candidates
    2. Synthesis: OpenAI generates implementation guidance

    Usage:
        service = ImplementationContextService(search_service)
        context = service.generate(story_title, theme_data)
    """

    def __init__(
        self,
        search_service: UnifiedSearchService,
        model: str = DEFAULT_MODEL,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the service.

        Args:
            search_service: UnifiedSearchService for vector search
            model: OpenAI model for synthesis
            top_k: Number of candidates to retrieve
            min_similarity: Minimum similarity threshold for candidates
            timeout: Timeout for OpenAI calls in seconds
        """
        self.search_service = search_service
        self.model = model
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.timeout = timeout
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def generate(
        self,
        story_title: str,
        theme_data: Dict[str, Any],
    ) -> ImplementationContext:
        """
        Generate implementation context for a story.

        Args:
            story_title: The story title
            theme_data: Aggregated theme data (symptoms, product_area, etc.)

        Returns:
            ImplementationContext with synthesis results
        """
        start_time = time.time()

        # Phase 1: Retrieval
        retrieval_start = time.time()
        query = self._build_retrieval_query(story_title, theme_data)
        candidates = self._retrieve_candidates(query)
        retrieval_duration_ms = int((time.time() - retrieval_start) * 1000)

        logger.info(
            f"Implementation context retrieval: "
            f"{len(candidates)} candidates in {retrieval_duration_ms}ms"
        )

        # Handle no candidates case (deterministic fallback)
        if not candidates:
            return ImplementationContext(
                summary="No prior art found. This appears to be a novel issue.",
                relevant_files=[],
                next_steps=[],
                prior_art_references=[],
                candidates_retrieved=0,
                top_k=self.top_k,
                retrieval_query=query,
                retrieval_duration_ms=retrieval_duration_ms,
                model=self.model,
                synthesis_duration_ms=0,
                synthesized_at=datetime.now(timezone.utc),
                source="none",
                success=True,
                error=None,
                schema_version="1.0",
            )

        # Phase 2: Synthesis
        synthesis_start = time.time()
        try:
            context = self._synthesize_context(
                story_title, theme_data, candidates, query, retrieval_duration_ms
            )
            synthesis_duration_ms = int((time.time() - synthesis_start) * 1000)

            # Update timing
            context.synthesis_duration_ms = synthesis_duration_ms
            context.synthesized_at = datetime.now(timezone.utc)

            total_duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"Implementation context generated: "
                f"{len(context.relevant_files)} files, "
                f"{len(context.next_steps)} steps in {total_duration_ms}ms"
            )

            return context

        except Exception as e:
            synthesis_duration_ms = int((time.time() - synthesis_start) * 1000)
            logger.warning(f"Implementation context synthesis failed: {e}")

            return ImplementationContext(
                summary="",
                relevant_files=[],
                next_steps=[],
                prior_art_references=[],
                candidates_retrieved=len(candidates),
                top_k=self.top_k,
                retrieval_query=query,
                retrieval_duration_ms=retrieval_duration_ms,
                model=self.model,
                synthesis_duration_ms=synthesis_duration_ms,
                synthesized_at=datetime.now(timezone.utc),
                source="hybrid",
                success=False,
                error=str(e),
                schema_version="1.0",
            )

    def _build_retrieval_query(
        self,
        story_title: str,
        theme_data: Dict[str, Any],
    ) -> str:
        """
        Build query text for vector search.

        Combines story title with symptoms and product area for better retrieval.
        """
        parts = [story_title]

        # Add product area if available
        product_area = theme_data.get("product_area")
        if product_area:
            parts.append(f"Product area: {product_area}")

        # Add symptoms if available
        symptoms = theme_data.get("symptoms", [])
        if symptoms:
            symptoms_text = ", ".join(symptoms[:5])  # Limit to 5 symptoms
            parts.append(f"Symptoms: {symptoms_text}")

        # Add user intent if available
        user_intent = theme_data.get("user_intent")
        if user_intent:
            parts.append(f"User intent: {user_intent}")

        return " | ".join(parts)

    def _retrieve_candidates(
        self,
        query: str,
    ) -> List[ImplementationContextCandidate]:
        """
        Retrieve top-K similar candidates via vector search.

        Searches across Coda pages, Coda themes, and Intercom content.
        Applies min_similarity as a hard filter.
        """
        candidates = []

        try:
            # Search using UnifiedSearchService
            # Returns List[UnifiedSearchResult] - Pydantic models, not dicts
            results = self.search_service.search(
                query=query,
                limit=self.top_k,
                min_similarity=self.min_similarity,
                source_types=["coda_page", "coda_theme"],  # Focus on Coda for prior art
            )

            for result in results:
                # Access Pydantic model attributes directly (not .get())
                candidates.append(
                    ImplementationContextCandidate(
                        source_type="evidence",  # Coda content is evidence
                        source_id=result.source_id,
                        title=result.title,
                        snippet=result.snippet[:500],  # Limit snippet size
                        similarity=result.similarity,
                        metadata={
                            "source_type": result.source_type,
                            "url": result.url,
                        },
                    )
                )

        except Exception as e:
            logger.warning(f"Implementation context retrieval failed: {e}")
            # Return empty list on failure - synthesis will handle gracefully

        return candidates

    def _synthesize_context(
        self,
        story_title: str,
        theme_data: Dict[str, Any],
        candidates: List[ImplementationContextCandidate],
        retrieval_query: str,
        retrieval_duration_ms: int,
    ) -> ImplementationContext:
        """
        Use OpenAI to synthesize implementation guidance.

        Args:
            story_title: The story title
            theme_data: Aggregated theme data
            candidates: Retrieved candidates from vector search
            retrieval_query: The query used for retrieval
            retrieval_duration_ms: Time spent on retrieval

        Returns:
            ImplementationContext with synthesized guidance
        """
        from ...prompts.implementation_context import (
            IMPLEMENTATION_CONTEXT_SYSTEM_PROMPT,
            build_implementation_context_prompt,
        )

        # Build user prompt
        user_prompt = build_implementation_context_prompt(
            story_title=story_title,
            product_area=theme_data.get("product_area", ""),
            symptoms=theme_data.get("symptoms", []),
            candidates=[c.model_dump() for c in candidates],
        )

        # Call OpenAI
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": IMPLEMENTATION_CONTEXT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,  # Lower temperature for more deterministic output
            max_tokens=1000,
            timeout=self.timeout,
        )

        # Parse response
        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned empty content")

        # Extract JSON from response
        parsed = self._parse_synthesis_response(content)

        # Build ImplementationContext
        relevant_files = [
            ImplementationContextFile(
                path=f.get("path", ""),
                rationale=f.get("rationale", ""),
                priority=f.get("priority", "medium"),
            )
            for f in parsed.get("relevant_files", [])
        ]

        return ImplementationContext(
            summary=parsed.get("summary", ""),
            relevant_files=relevant_files,
            next_steps=parsed.get("next_steps", []),
            prior_art_references=parsed.get("prior_art_references", []),
            candidates_retrieved=len(candidates),
            top_k=self.top_k,
            retrieval_query=retrieval_query,
            retrieval_duration_ms=retrieval_duration_ms,
            model=self.model,
            synthesis_duration_ms=0,  # Will be updated by caller
            synthesized_at=None,  # Will be updated by caller
            source="hybrid",
            success=True,
            error=None,
            schema_version="1.0",
        )

    def _parse_synthesis_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response.

        Handles cases where JSON is wrapped in markdown code blocks.
        """
        # Try direct JSON parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        import re

        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Return empty structure on parse failure
        logger.warning(f"Failed to parse synthesis response as JSON: {content[:200]}")
        return {
            "summary": content[:500] if content else "",
            "relevant_files": [],
            "next_steps": [],
            "prior_art_references": [],
        }
