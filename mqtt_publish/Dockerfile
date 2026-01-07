# mqtt_publish/Dockerfile

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY progress_publish.py .
CMD ["python", "progress_publish.py"]
