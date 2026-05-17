"""Generate event descriptions using ChatGPT."""

import logging
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)


async def generate_event_descriptions(events: List[Dict]) -> List[Dict]:
    """Generate ChatGPT descriptions for all events (280 chars max).

    Args:
        events: List of event dictionaries

    Returns:
        List of events with generated descriptions
    """
    try:
        # Get API key - may fail if not in proper environment
        try:
            api_key = await get_secret("OPENAI_API_KEY")
        except Exception as e:
            logger.warning(f"Could not fetch OpenAI API key ({e}), skipping description generation")
            return events

        if not api_key:
            logger.warning("OpenAI API key not found, skipping description generation")
            return events

        client = AsyncOpenAI(api_key=api_key)

        updated_events = []

        for event in events:
            # Skip if already has description
            if event.get("description") and len(event.get("description", "")) > 50:
                updated_events.append(event)
                continue

            try:
                description = await _generate_single_description(client, event)
                event["description"] = description
            except Exception as e:
                logger.warning(f"Failed to generate description for {event.get('title', 'Unknown')}: {e}")
                # Keep original or empty description
                pass

            updated_events.append(event)

        return updated_events

    except Exception as e:
        logger.error(f"Error generating event descriptions: {e}")
        return events  # Return unchanged events


async def _generate_single_description(client: AsyncOpenAI, event: Dict) -> str:
    """Generate a single event description (280 chars max)."""
    title = event.get("title", "Event")
    category = event.get("category", "other")
    location = event.get("location", "Tbilisi")
    existing_desc = event.get("description", "")

    prompt = f"""Write a compelling, informative description in Russian for this Tbilisi event (maximum 280 characters).

Event Title: {title}
Category: {category}
Location: {location}
Current details: {existing_desc}

Requirements:
- Write ONLY the description, nothing else
- Make it engaging and enticing for potential attendees
- Include key information (what to expect, why attend)
- Maximum 280 characters (strict limit, no more)
- In Russian language
- Do NOT add ellipsis or "..." at the end

Description:"""

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0.7
    )

    description = response.choices[0].message.content.strip()

    # Truncate to 280 chars without ellipsis
    if len(description) > 280:
        description = description[:280]

    return description
