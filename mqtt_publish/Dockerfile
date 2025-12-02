# mqtt_publish/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app
COPY . .

CMD ["sh", "-c", "python arkite_publish.py"]