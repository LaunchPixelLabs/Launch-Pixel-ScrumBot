FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Set execution permission on the startup orchestrator
RUN chmod +x start.sh

# Expose port for the WhatsApp Webhook Flask receiver (if bypassed, otherwise free)
EXPOSE 5001

# Boot both bots in parallel
CMD ["./start.sh"]
