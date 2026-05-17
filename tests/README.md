# Unit Tests

This directory contains all unit and integration tests for the notification bot.

## Test Files

### Core Digest Tests

**[`test_digest.py`](test_digest.py)** — Morning digest orchestration
- Tests end-to-end morning digest generation
- Validates all components integrate correctly
- Checks message assembly and formatting

**[`test_digest_format.py`](test_digest_format.py)** — Message formatting
- Tests section formatting (weather, tasks, rates)
- Validates emoji usage and spacing
- Checks Markdown link formatting

### Exchange Rates Tests

**[`test_forex_rates.py`](test_forex_rates.py)** — Rate fetching
- Tests BTC/USD and ETH/USD via CoinGecko
- Tests USD→EUR and USD→RUB via exchangerate-api
- Validates 24h and 30d change calculations
- Tests timeout handling and fallback behavior

**[`test_rate_format.py`](test_rate_format.py)** — Rate display formatting
- Tests decimal formatting (5 decimals max)
- Tests trailing zero removal (`1.18000` → `1.18`)
- Tests large number formatting with commas
- Tests percentage change arrow direction (↑ / ↓)

### GWP (Georgian Water & Power) Tests

**[`test_gwp.py`](test_gwp.py)** — Basic GWP scraper
- Tests website fetching and HTML parsing
- Tests basic work detection on Vazha Iverievi street
- Tests error handling and timeout behavior

**[`test_gwp_detailed.py`](test_gwp_detailed.py)** — Detailed parsing
- Tests multiple HTML selectors
- Tests title extraction from various heading formats
- Tests fallback text extraction if headings missing

**[`test_gwp_all_streets.py`](test_gwp_all_streets.py)** — Street name variants
- Tests case-insensitive matching
- Tests Georgian script variants: ვაზა ივერიელი, ვაჟა ივერელი
- Tests English transliteration: `vazha iverievi`, `vazha iverelis`
- Tests both scheduled and unscheduled works URLs

### News Tests

**[`test_news_processor.py`](test_news_processor.py)** — News selection logic
- Tests keyword-based filtering (no AI)
- Tests real RSS feed parsing
- Tests 12-hour window filtering
- Tests exclusion keyword enforcement
- Validates user preference injection

### Task Tests

**[`test_task_explanations.py`](test_task_explanations.py)** — Task explanation generation
- Tests GPT-4o explanation generation
- Tests Russian language output
- Tests 10-15 word format per task
- Tests fallback behavior if generation fails

### Monitoring Tests

**[`test_openai_balance.py`](test_openai_balance.py)** — OpenAI balance monitor
- Tests balance retrieval from OpenAI API
- Tests low-balance warning ($0.50 threshold)
- Tests fallback if API key lacks permissions

**[`test_webhook_secret.py`](test_webhook_secret.py)** — Webhook security
- Tests HMAC-SHA256 validation
- Tests webhook signature verification
- Tests rejection of invalid requests

## Running Tests

### All Tests
```bash
python3 -m pytest tests/ -v
```

### Single Test File
```bash
python3 -m pytest tests/test_digest.py -v
```

### Specific Test
```bash
python3 -m pytest tests/test_digest.py::test_morning_digest -v
```

### With Coverage
```bash
python3 -m pytest tests/ --cov=src --cov-report=html
```

### Watch Mode (requires pytest-watch)
```bash
ptw tests/
```

## Test Dependencies

Add to `requirements-dev.txt`:
```
pytest>=7.0
pytest-asyncio>=0.21
pytest-cov>=4.0
pytest-mock>=3.10
```

Install:
```bash
pip install -r requirements-dev.txt
```

## Writing New Tests

### Async Test Pattern
```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### Mocking External APIs
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    with patch('module.external_call', new_callable=AsyncMock) as mock:
        mock.return_value = {"data": "test"}
        result = await function_under_test()
        assert result == expected
        mock.assert_called_once()
```

### Fixtures
```python
@pytest.fixture
def sample_task():
    return Task(
        id=1,
        what="Test task",
        when_date="2026-05-17",
        is_urgent=False
    )
```

## Debugging Tests

### Verbose Output
```bash
python3 -m pytest tests/ -vv
```

### Show Print Statements
```bash
python3 -m pytest tests/ -s
```

### Stop on First Failure
```bash
python3 -m pytest tests/ -x
```

### Run Last Failed
```bash
python3 -m pytest tests/ --lf
```

## CI/CD Integration

Add to GitHub Actions `.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/ --cov=src
```

---

See also: [CLAUDE.md Testing & Validation](../CLAUDE.md#testing--validation)
