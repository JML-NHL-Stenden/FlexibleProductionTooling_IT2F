# mqtt_bridge/Dockerfile

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY subscribe_step_to_db.py .
CMD ["python", "-u", "subscribe_step_to_db.py"]
