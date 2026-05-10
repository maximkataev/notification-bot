FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Doppler CLI
RUN apt-get update && apt-get install -y \
    curl \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && curl -sLf --retry 3 --tlsv1.2 --proto "=https" -- https://cli.doppler.com/install.sh | sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy app code
COPY . .

# Create data/log directories
RUN mkdir -p /app/data /app/logs

# Run with Doppler
CMD ["doppler", "run", "--", "python", "-m", "src.bot.main"]