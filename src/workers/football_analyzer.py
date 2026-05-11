"""Analyze football matches with AI commentary and standings context."""

import logging
from typing import Optional, List, Dict, Any
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)


async def get_match_analysis(
    matches: List[Dict[str, Any]], max_matches: int = 3
) -> Dict[int, str]:
    """
    Generate brief AI commentary for matches.

    Args:
        matches: List of match dicts with keys: home, away, time, league
        max_matches: Max number of matches to analyze (default 3)

    Returns:
        Dict mapping match index (0-based) to AI commentary string (1 sentence, ~20 words)
    """
    if not matches or len(matches) == 0:
        return {}

    # Limit to max_matches
    matches_to_analyze = matches[:max_matches]

    # Build prompt for AI analysis
    match_list = ""
    for i, match in enumerate(matches_to_analyze, 1):
        home = match.get("home", "Unknown")
        away = match.get("away", "Unknown")
        league = match.get("league", "")
        match_list += f"{i}. {home} vs {away} ({league})\n"

    prompt = f"""Analyze these football matches and provide brief 1-sentence commentary for each (max 20 words).
Focus on expected outcome, playing style contrast, or key context.

Matches:
{match_list}

Format your response as:
Match 1: [brief analysis]
Match 2: [brief analysis]
Match 3: [brief analysis]

Keep it concise, informative, and in Russian."""

    try:
        logger.info(f"Calling AI to analyze {len(matches_to_analyze)} football matches")

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": "You are a football analyst providing brief match insights.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        response_text = response.choices[0].message.content or ""
        logger.info(f"✓ AI match analysis received: {len(response_text)} chars")

        # Parse response - should be "Match N: [analysis]" format
        analysis_dict = {}
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            # Try to extract match number and analysis
            if line.startswith("Match ") or line.startswith("Матч "):
                # Handle both "Match 1:" and "Матч 1:" formats
                try:
                    # Find the colon separator
                    colon_idx = line.find(":")
                    if colon_idx > 0:
                        # Extract match number (1-based from user perspective)
                        match_num_str = line[
                            6:colon_idx
                        ].strip()  # Skip "Match " or "Матч "
                        match_num = int(match_num_str)
                        analysis = line[colon_idx + 1 :].strip()

                        if 1 <= match_num <= len(matches_to_analyze) and analysis:
                            analysis_dict[match_num - 1] = (
                                analysis  # Convert to 0-based index
                            )
                except (ValueError, IndexError):
                    continue

        logger.info(f"✓ Parsed match analysis: {len(analysis_dict)} matches")
        return analysis_dict

    except Exception as e:
        logger.error(f"Failed to analyze matches: {type(e).__name__}: {e}")
        return {}
