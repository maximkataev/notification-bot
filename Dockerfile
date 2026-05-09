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

# Install Playwright Chromium browser
RUN python3 -m playwright install chromium

# Install Doppler CLI
RUN curl -Ls https://cli.doppler.com/install.sh | sh

# Copy app code
COPY . .

# Create data directory
RUN mkdir -p /app/data /app/logs

# Run with Doppler
CMD ["doppler", "run", "--", "python", "src/bot/main.py"]
