import os
import psycopg2
import json
import paho.mqtt.client as mqtt

# Read environment variables
db_host = os.getenv("DB_HOST", "db")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "odoo")
db_user = os.getenv("DB_USER", "odoo")
db_pass = os.getenv("DB_PASS", "odoo")

mqtt_host = os.getenv("MQTT_HOST", "mqtt")
mqtt_port = int(os.getenv("MQTT_PORT", "1883"))

# Connect to PostgreSQL
conn = psycopg2.connect(
    dbname=db_name,
    user=db_user,
    password=db_pass,
    host=db_host,
    port=db_port
)
cur = conn.cursor()

# Ensure table exists (optional)
cur.execute("""
CREATE TABLE IF NOT EXISTS arkite_steps (
    id SERIAL PRIMARY KEY,
    step_name TEXT,
    completed BOOLEAN
);
""")
conn.commit()

# Define MQTT callbacks
def on_connect(client, userdata, flags, rc):
    print("✅ Connected to MQTT broker with result code", rc)
    client.subscribe("factory/products/created_step")

def on_message(client, userdata, msg):
    try:
        payload_raw = msg.payload.decode()
        print(f"📥 Received message on {msg.topic}: {payload_raw}")

        # Expecting something like: [{"step_name": "Step 1"},{"completed": 0}]
        payload = json.loads(payload_raw)

        # Extract values safely
        step_name = payload[0].get("step_name", "Unknown Step")
        completed = bool(payload[1].get("completed", 0))

        # Insert into Postgres
        cur.execute(
            "INSERT INTO arkite_steps (step_name, completed) VALUES (%s, %s);",
            (step_name, completed)
        )
        conn.commit()
        print(f" Inserted step: {step_name}, completed={completed}")

    except Exception as e:
        print(f" Error: {e}")
        conn.rollback()

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

mqtt_client.connect(mqtt_host, mqtt_port, 60)
print(f"Listening for Arkite messages on {mqtt_host}:{mqtt_port}...")
mqtt_client.loop_forever()
