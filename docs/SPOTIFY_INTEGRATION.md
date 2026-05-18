# Spotify Integration — Album of the Day

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Morning Digest (scheduler.py)             │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
         ┌──────────▼──────────┐  ┌────▼─────────────┐
         │ Content Recommender │  │ Album of the Day │
         │  (fresh videos)     │  │   (NEW)          │
         └─────────────────────┘  └────┬─────────────┘
                    │                   │
         ┌──────────▼──────────────────▼────────┐
         │    content_parser.py                 │
         │ ┌────────────────────────────────┐   │
         │ │ fetch_fresh_content()          │   │  YouTube, Podcasts
         │ │ _select_and_describe()         │   │  (24h window)
         │ │ _recommend_music_album()       │   │
         │ │ get_album_of_day()    ◄────────┼─ NEW
         │ └────────────────────────────────┘   │
         └─────────────────────────────────────┘
                    │
         ┌──────────┴───────────┐
         │                      │
    ┌────▼──────┐       ┌──────▼─────┐
    │ OpenAI    │       │  Spotify   │
    │ GPT-4o    │       │   API      │
    │           │       │            │
    │ Recommend │       │ Search &   │
    │ album     │       │ Validate   │
    └────┬──────┘       └──────┬─────┘
         │                     │
         │      Album info     │
         └─────────────┬───────┘
                       │
              ┌────────▼────────┐
              │  Telegram Bot   │
              │  (send_message) │
              └─────────────────┘
```

---

## Data Flow

### 1. Album Recommendation via GPT

```
Input: (nothing — automated)
  │
  ├─► GPT-4o Prompt:
  │   "Recommend 1 album for morning focus (analyst/engineer)"
  │   "Must be real and known"
  │
  └─► Output (JSON):
      {
        "album": "Music for Airports",
        "artist": "Brian Eno",
        "description": "Ambient classic for deep work"
      }
```

### 2. Spotify Search & Validation

```
Input: album="Music for Airports", artist="Brian Eno"
  │
  ├─► Step 1: Get Spotify Token
  │   POST https://accounts.spotify.com/api/token
  │   ├─ Client ID
  │   ├─ Client Secret
  │   └─► Returns: Bearer Token
  │
  ├─► Step 2: Search Album
  │   GET https://api.spotify.com/v1/search
  │   ├─ Query: "album:Music for Airports artist:Brian Eno"
  │   ├─ Type: album
  │   └─► Returns: Spotify album data
  │
  └─► Step 3: Extract URL
      response.albums.items[0].external_urls.spotify
      └─► "https://open.spotify.com/album/..."
```

### 3. Integration into Digest

```
Morning Digest Timeline:
  │
  ├─ 8:00:00 Start scheduler
  ├─ 8:00:05 Load tasks, weather, profile
  ├─ 8:00:10 Generate greeting + news
  ├─ 8:00:20 Fetch exchange rates + football
  ├─ 8:00:25 Content recommendation (20s timeout)
  │   └─ If fails: skip section (graceful degradation)
  ├─ 8:00:45 Album of the day (15s timeout) ◄─ NEW
  │   ├─ Call GPT for recommendation (3s)
  │   ├─ Get Spotify token (1s)
  │   ├─ Search album on Spotify (2s)
  │   └─ If Spotify unavailable: return None (skip section)
  ├─ 8:01:00 Memes + format message
  └─ 8:01:05 Send to Telegram (split if >4000 chars)

Total time: ~25-30 seconds
```

---

## Function Signatures

### Get Album of the Day

```python
async def get_album_of_day() -> Optional[Dict[str, Any]]:
    """
    Recommend album via GPT + search on Spotify.
    
    Returns:
        {
            "type": "music",
            "title": str (album name),
            "creator": str (artist name),
            "url": str (Spotify link),
            "review": str (Russian description),
            "platform": "spotify",
            "language": "ru"
        }
        or None if failed/unavailable
    """
```

### Get Spotify Token

```python
async def _spotify_get_access_token() -> Optional[str]:
    """
    Get Spotify API Bearer token via Client Credentials.
    
    Requires (from Doppler):
        SPOTIFY_CLIENT_ID
        SPOTIFY_CLIENT_SECRET
    
    Returns: Token string or None
    """
```

### Search Album on Spotify

```python
async def _spotify_search_album(
    album: str,
    artist: str,
    access_token: str
) -> Optional[str]:
    """
    Search Spotify for album URL.
    
    Returns: Spotify public URL or None if not found
    """
```

### Validate Credentials

```python
async def _spotify_validate_credentials() -> bool:
    """Test if Spotify credentials are valid."""
```

---

## Error Handling

### Timeout Scenarios

| Component | Timeout | Action |
|-----------|---------|--------|
| `get_album_of_day()` | 15s | Skip album section |
| `_spotify_get_access_token()` | 5s | Return None |
| `_spotify_search_album()` | 5s | Return None |
| GPT recommendation | implicit | Handled by OpenAI SDK |

### Missing Credentials

```
❌ Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET
  ├─ _spotify_get_access_token() returns None
  ├─ Album search skipped
  └─ Digest sends without album section (graceful)
```

### Album Not Found

```
Album recommended by GPT: "Unknown Album" by "Fake Artist"
  ├─ Spotify search returns: [] (no results)
  └─ Album section skipped (not added to digest)
```

---

## Configuration

### 1. Get Spotify Credentials

Visit: https://developer.spotify.com/dashboard

Steps:
1. Log in / Create account (free)
2. Create New App
3. Accept terms
4. Copy **Client ID** and **Client Secret**

### 2. Add to Doppler

```bash
doppler secrets set SPOTIFY_CLIENT_ID <your-id>
doppler secrets set SPOTIFY_CLIENT_CLIENT_SECRET <your-secret>
```

### 3. Verify

```bash
python3 scripts/test_spotify.py
```

---

## OAuth Flow Type

**Client Credentials Flow** (server-to-server)

```
┌─────────────────┐
│  Our Bot        │
│  (server)       │
└────────┬────────┘
         │
         │ POST /token
         │ { client_id, client_secret }
         ▼
┌─────────────────┐
│ Spotify Auth    │
└────────┬────────┘
         │
         │ Returns: Bearer Token
         ▼
┌─────────────────┐
│  Our Bot        │
│  (with token)   │
└────────┬────────┘
         │
         │ GET /search?q=album
         │ Header: Authorization: Bearer <token>
         ▼
┌─────────────────┐
│ Spotify API     │
└────────┬────────┘
         │
         │ Returns: Album data
         ▼
┌─────────────────┐
│ Our Bot         │
│ (with URL)      │
└─────────────────┘
```

**Key difference from Authorization Code Flow**:
- No user login needed
- No redirect URI actually used (though required in app settings)
- Server-to-server only

---

## Performance

| Step | Duration | Notes |
|------|----------|-------|
| GPT Recommendation | ~3s | Parallel with other tasks |
| Get Spotify Token | ~1s | HTTP request + JSON parse |
| Search Album | ~2s | HTTP request + search |
| **Total** | **~6s** | Timeout 15s (plenty of buffer) |

---

## Graceful Degradation

If Spotify unavailable:
- ✓ Digest still sends
- ✓ Album section skipped
- ✓ No error message to user
- ✓ Logs show warning

Example log:
```
🎵 Getting album of the day...
🎶 GPT recommended: 'Music for Airports' by Brian Eno
⚠️  Spotify credentials missing (SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET)
⊘ Album not found on Spotify: 'Music for Airports' by Brian Eno
⊘ Could not get album of the day
```

---

## Testing

### Test Spotify Setup

```bash
PYTHONPATH=. doppler run --project notifications-bot --config dev -- \
  python3 scripts/test_spotify.py
```

Expected output:
```
✓ Validation: Spotify credentials valid
✓ Search: Abbey Road found on Spotify
✓ Album of Day: Music for Airports (with URL)
```

### Test in Live Digest

Manually trigger:
```bash
PYTHONPATH=. doppler run --project notifications-bot --config dev -- \
  python3 -c "
import asyncio
from src.bot.main import bot
from src.bot.scheduler import morning_digest
asyncio.run(morning_digest(bot, 71488343))
"
```

Check for:
- Album section in message
- Spotify link clickable
- Proper formatting

---

## Monitoring

### Logs to Watch

```
✓ Album of day: [album] by [artist]
⚠️  Album not found on Spotify
⏱️  Album of the day: timeout (15s)
💥 Album of day error: [error type]
```

### Metrics (future)

Could track:
- Album recommendation success rate
- Spotify search hit rate
- API response times

---

## Future Enhancements

1. **Cache Spotify token** — Reuse for multiple searches
2. **Album preview** — Include preview link from Spotify API
3. **User preferences** — Remember favorite artists
4. **Playlist of the day** — Instead of single album
5. **Streaming stats** — Show trending albums

---

**Status**: ✓ Integrated into digest  
**Fallback**: ✓ Graceful (skips section if unavailable)  
**Testing**: ✓ Test suite available  
**Production Ready**: ⚠️ Needs Spotify credentials
