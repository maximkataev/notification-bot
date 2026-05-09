FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including Playwright requirements)
RUN apt-get update && apt-get install -y \
    curl \
    libglib2.0-0 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libdbus-1-3 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser + system deps
RUN python -m playwright install --with-deps chromium

# Install Doppler CLI
RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg && \
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" -- https://cli.doppler.com/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy app code
COPY . .

# Create data directory
RUN mkdir -p /app/data /app/logs

# Run with Doppler
CMD ["doppler", "run", "--", "python", "-m", "src.bot.main"]