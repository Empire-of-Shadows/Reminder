FROM python:3.13-slim

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GIT_REF=Dev

# Clone from public repo
RUN git clone --depth 1 --branch "${GIT_REF}" https://github.com/Empire-of-Shadows/reminder.git .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir -p logs

# Add environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "Reminder.py"]
