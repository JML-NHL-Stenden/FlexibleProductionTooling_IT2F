# mqtt_bridge/Dockerfile

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY instruction_steps_bridge.py .
CMD ["python", "instruction_steps_bridge.py"]
