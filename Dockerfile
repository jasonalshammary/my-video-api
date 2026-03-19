FROM python:3.11-slim

# Install system dependencies for curl_cffi
RUN apt-get update && apt-get install -y \
    curl \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Rename your main script to app.py if it isn't already
# Or just run it directly
CMD ["python", "vidrock_master.py"]
