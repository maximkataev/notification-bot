"""Recommend interesting content with AI review in Russian.

Strategy:
1. Fetch all content from parsers (YouTube, podcasts, music - EN + RU)
2. AI selects fresh content, prioritizing Russian
3. AI writes review in Russian
4. Return with REAL working link (no hallucinations)

RULE: NO HARDCODED FALLBACKS & NO HALLUCINATED LINKS
"""

import logging
from typing import Optional, Dict, Any
from src.workers.content_parser import get_content_recommendation_with_review

logger = logging.getLogger(__name__)


async def get_content_recommendation() -> Optional[Dict[str, Any]]:
    """
    Recommend fresh content with AI review in Russian.

    Returns:
        {
            "type": "video" | "podcast" | "music",
            "title": str,
            "creator": str,
            "review": str (Russian review from AI),
            "url": str,
            "platform": str,
            "language": "ru" | "en",
            "emoji": str
        }
        or None if no suitable content found
    """
    try:
        logger.info("Getting content recommendation with AI review...")

        # Fetch all content + AI selection + Russian review
        recommendation = await get_content_recommendation_with_review()

        if not recommendation:
            logger.warning("No content available for recommendation")
            return None

        # Add emoji based on type
        emojis = {"video": "🎥", "podcast": "🎙️", "music": "🎵"}
        recommendation["emoji"] = emojis.get(recommendation.get("type"), "📺")

        logger.info(
            f"✓ Selected: {recommendation['type']} - {recommendation['title'][:40]} by {recommendation['creator']}"
        )
        if recommendation.get("review"):
            logger.info(f"  Review: {recommendation['review'][:60]}")

        return recommendation

    except Exception as e:
        logger.warning(f"Failed to get content recommendation: {type(e).__name__}: {e}")
        return None
