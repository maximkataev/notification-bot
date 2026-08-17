"""Detect news items that tell the same story, so the digest never repeats one.

Two different things cause repeats, and they need different tests:

1. The SAME item reaching two pools. BBC News feeds both the politics and the culture
   pool, The Guardian feeds business, art and fashion — so the main selector, which
   concatenates its five pools, was regularly offered one story twice under two
   indices. Exact URL match catches this with no risk of a false merge.

2. The same event told by different outlets ("Burnham exchanged messages with
   impersonator of top Trump aide" / "Burnham exchanged messages with person posing
   as Trump's chief of staff"). Only title overlap can catch this, so the thresholds
   below are deliberately conservative: silently dropping a genuinely distinct story
   is worse than letting one near-duplicate through, and ChatGPT is separately told
   in each selector prompt not to pick two angles on the same event.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set

# Function words carry no topical signal, so they must not prop up a similarity score.
_STOPWORDS = {
    # English
    "the", "and", "for", "with", "from", "that", "this", "his", "her", "its", "their",
    "has", "have", "had", "was", "were", "are", "will", "would", "could", "should",
    "say", "says", "said", "after", "before", "into", "over", "out", "off", "not",
    "but", "you", "your", "our", "who", "why", "how", "what", "when", "where", "all",
    "new", "more", "most", "than", "then", "they", "them", "can", "may", "one", "two",
    "about", "against", "amid", "among", "been", "being", "does", "did", "get", "got",
    "just", "like", "made", "make", "now", "only", "other", "some", "such", "these",
    "those", "under", "very", "way", "week", "year", "years", "day", "days",
    # Russian
    "для", "что", "как", "это", "его", "она", "они", "был", "была", "были", "быть",
    "все", "уже", "или", "год", "года", "лет", "при", "над", "под", "изза", "без",
    "から", "также", "после", "перед", "может", "могут", "будет", "будут", "если",
    "чем", "тем", "так", "там", "тут", "где", "кто", "чего", "этот", "эта", "эти",
    "на", "не", "по", "из", "во", "со", "об", "от", "до", "за", "же", "ли", "бы",
}

# Below this many meaningful tokens a title is too thin to compare safely.
_MIN_TOKENS = 4
# Share of the shorter title's tokens that must also appear in the longer one.
_CONTAINMENT_THRESHOLD = 0.55
# Overlap must include at least this many longer words, so that two unrelated stories
# sharing only common short words ("trump", "eu", "bank") are not merged.
_MIN_STRONG_SHARED = 2
_STRONG_TOKEN_LEN = 5


def _normalize_url(url: str) -> str:
    """Strip scheme, query, fragment and trailing slash so tracking params don't hide a repeat."""
    if not url:
        return ""
    cleaned = re.sub(r"^https?://", "", url.strip().lower())
    cleaned = cleaned.split("?")[0].split("#")[0]
    cleaned = re.sub(r"^www\.", "", cleaned)
    return cleaned.rstrip("/")


def story_tokens(title: str) -> Set[str]:
    """Meaningful lowercase words of a headline, used to compare two headlines."""
    if not title:
        return set()
    # Unicode-aware split: keeps Cyrillic/Georgian words, drops punctuation and
    # possessives ("Trump's" -> "trump" + "s", the latter dropped as too short).
    words = re.findall(r"[^\W_]+", title.lower(), flags=re.UNICODE)
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def is_same_story(tokens_a: Set[str], tokens_b: Set[str]) -> bool:
    """True if two headlines look like the same event told twice."""
    if len(tokens_a) < _MIN_TOKENS or len(tokens_b) < _MIN_TOKENS:
        return False

    shared = tokens_a & tokens_b
    if not shared:
        return False

    containment = len(shared) / min(len(tokens_a), len(tokens_b))
    if containment < _CONTAINMENT_THRESHOLD:
        return False

    strong_shared = sum(1 for t in shared if len(t) >= _STRONG_TOKEN_LEN)
    return strong_shared >= _MIN_STRONG_SHARED


class StoryDeduper:
    """Remembers the stories already accepted and reports repeats.

    Used while building a selector's candidate list (so ChatGPT is never offered the
    same story twice) and again in the scheduler across the separately-selected
    blocks (main / crypto / stocks / regional), which draw from overlapping wires.
    """

    def __init__(self) -> None:
        self._urls: Set[str] = set()
        self._titles: List[Set[str]] = []

    def is_duplicate(self, item: Dict[str, Any]) -> bool:
        """True if `item` repeats a story already accepted (without recording it)."""
        url = _normalize_url(item.get("url", ""))
        if url and url in self._urls:
            return True

        tokens = story_tokens(item.get("title", ""))
        return any(is_same_story(tokens, seen) for seen in self._titles)

    def add(self, item: Dict[str, Any]) -> None:
        """Record `item` as accepted."""
        url = _normalize_url(item.get("url", ""))
        if url:
            self._urls.add(url)
        tokens = story_tokens(item.get("title", ""))
        if tokens:
            self._titles.append(tokens)

    def accept(self, item: Dict[str, Any]) -> bool:
        """Record and accept `item`, or return False if it repeats an accepted story."""
        if self.is_duplicate(item):
            return False
        self.add(item)
        return True


def dedupe_stories(
    items: Iterable[Dict[str, Any]], deduper: Optional[StoryDeduper] = None
) -> List[Dict[str, Any]]:
    """Return `items` with repeated stories removed, keeping the first of each."""
    deduper = deduper or StoryDeduper()
    return [item for item in items if deduper.accept(item)]
