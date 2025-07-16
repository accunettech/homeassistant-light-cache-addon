FROM python:3.11-slim

WORKDIR /app

# Install SQLite and other system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY mqtt_light_cache.py run.sh ./
RUN chmod +x run.sh

# Start your app
CMD ["./run.sh"]

