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
CREATE TABLE IF NOT EXISTS steps (
    id SERIAL PRIMARY KEY,
    step_name TEXT,
    completed BOOLEAN
);
""")
conn.commit()

# Define MQTT callbacks
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code", rc)
    client.subscribe("factory/products/created_step")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"📥 Raw payload: {payload}")

        # Handle possible nested array shapes
        flat_payload = {}

        if isinstance(payload, list):
            # Case 1: [{'step_name':...}, {'completed':...}]
            if len(payload) == 2 and all(isinstance(x, dict) for x in payload):
                flat_payload = {
                    "step_name": payload[0].get("step_name"),
                    "completed": payload[1].get("completed")
                }

            # Case 2: [{'step_name':..., 'completed':...}] (one dict inside list)
            elif len(payload) == 1 and isinstance(payload[0], dict):
                flat_payload = payload[0]

            else:
                raise ValueError("Unexpected array structure in payload")

        elif isinstance(payload, dict):
            # Case 3: direct object
            flat_payload = payload

        else:
            raise ValueError("Unexpected payload type")

        # Normalize completed flag
        step_name = flat_payload.get("step_name", "Unknown Step")
        completed = bool(flat_payload.get("completed", 0))

        # Insert into Postgres
        cur.execute(
            "INSERT INTO steps (step_name, completed) VALUES (%s, %s);",
            (step_name, completed)
        )
        conn.commit()

        print(f"✅ Inserted step: {step_name}, completed={completed}")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

mqtt_client.connect(mqtt_host, mqtt_port, 60)
print(f"Listening for Arkite messages on {mqtt_host}:{mqtt_port}...")
mqtt_client.loop_forever()
