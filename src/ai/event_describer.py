"""Generate event descriptions using ChatGPT with user profile and event details."""

import logging
from typing import Dict, List, Optional
import httpx
from openai import AsyncOpenAI
from src.utils.doppler import get_secret
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def generate_event_descriptions(
    events: List[Dict],
    user_profile = None  # Can be Dict or UserProfile dataclass
) -> List[Dict]:
    """Generate ChatGPT descriptions for all events (280 chars max).

    Args:
        events: List of event dictionaries
        user_profile: Optional user profile (dict or UserProfile dataclass)

    Returns:
        List of events with generated descriptions
    """
    try:
        # Get API key - may fail if not in proper environment
        try:
            api_key = get_secret("OPENAI_API_KEY")
        except Exception as e:
            logger.warning(f"Could not fetch OpenAI API key ({e}), skipping description generation")
            return events

        if not api_key:
            logger.warning("OpenAI API key not found, skipping description generation")
            return events

        client = AsyncOpenAI(api_key=api_key)

        # Convert dataclass to dict if needed
        profile_dict = None
        if user_profile:
            if hasattr(user_profile, '__dataclass_fields__'):
                # It's a dataclass
                profile_dict = {
                    'preferences': getattr(user_profile, 'preferences', ''),
                    'wake_time': getattr(user_profile, 'wake_time', ''),
                    'sleep_time': getattr(user_profile, 'sleep_time', ''),
                    'timezone': getattr(user_profile, 'timezone', ''),
                }
            else:
                # It's already a dict
                profile_dict = user_profile

        updated_events = []

        for event in events:
            # Skip if already has description
            if event.get("description") and len(event.get("description", "")) > 50:
                updated_events.append(event)
                continue

            try:
                description = await _generate_single_description(
                    client, event, profile_dict
                )
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


async def _fetch_event_content(url: str) -> Optional[str]:
    """Fetch and extract relevant content from event URL."""
    if not url or not url.startswith('http'):
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Parse HTML and extract text
            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style tags
            for tag in soup(['script', 'style']):
                tag.decompose()

            # Get text and clean it up
            text = soup.get_text(separator=' ', strip=True)

            # Return first 1000 chars of meaningful content
            return text[:1000] if text else None

    except Exception as e:
        logger.debug(f"Could not fetch event URL {url}: {e}")
        return None


async def _generate_single_description(
    client: AsyncOpenAI,
    event: Dict,
    user_profile: Optional[Dict] = None
) -> str:
    """Generate a single event description (280 chars max) using event content and user profile."""
    title = event.get("title", "Event")
    category = event.get("category", "other")
    location = event.get("location", "Tbilisi")
    existing_desc = event.get("description", "")
    url = event.get("url", "")
    date = event.get("date", "")
    time = event.get("time", "")
    source = event.get("source", "")

    # Try to fetch event page content
    event_content = await _fetch_event_content(url)

    # Build user context from profile
    user_context = ""
    if user_profile:
        preferences = user_profile.get("preferences", "")
        if preferences:
            user_context = f"\nUser preferences/interests: {preferences}"

    # Build the prompt with all available information
    prompt = f"""Generate a compelling, informative description in Russian for this Tbilisi event.
The description must be maximum 280 characters and suitable for potential attendees.

EVENT DETAILS:
Title: {title}
Category: {category}
Date: {date}
Time: {time}
Location: {location}
Source: {source}
Event website/link available: {"Yes" if url else "No"}

EXISTING DETAILS:
{existing_desc if existing_desc else "None"}

EVENT PAGE CONTENT (if available):
{event_content[:500] if event_content else "Not available"}
{user_context}

YOUR TASK:
1. Write a concise, enticing description in Russian (maximum 280 characters)
2. Focus on what makes this event interesting and worth attending
3. Include key details: type, atmosphere, or unique features if relevant
4. Match the user's interests if profile provided
5. DO NOT add ellipsis (...) or any text after the description
6. Write ONLY the description text, nothing else

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
