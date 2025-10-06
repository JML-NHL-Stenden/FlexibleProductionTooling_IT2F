import os
import psycopg2
import select
import paho.mqtt.client as mqtt
import json

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
conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

cur = conn.cursor()
cur.execute("LISTEN new_instruction;")

# Connect to MQTT
mqtt_client = mqtt.Client()
mqtt_client.connect(mqtt_host, mqtt_port, 60)

print(f"Connected to MQTT broker at {mqtt_host}:{mqtt_port}")

print("Listening for Postgres notifications...")

while True:
    if select.select([conn], [], [], 5) == ([], [], []):
        continue
    conn.poll()
    while conn.notifies:
        notify = conn.notifies.pop(0)
        payload = json.loads(notify.payload)
        print(f"📢 New instruction from DB: {payload}")

        topic = f"factory/instructions/{payload['product_code']}"
        mqtt_client.publish(topic, json.dumps(payload))
