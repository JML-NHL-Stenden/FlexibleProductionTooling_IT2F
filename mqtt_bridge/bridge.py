import os
import json
import psycopg2
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "factory/all_steps"

def get_conn():
    retries = 10
    while retries:
        try:
            return psycopg2.connect(
                host=os.getenv("DB_HOST", "db"),
                port=int(os.getenv("DB_PORT", "5432")),
                dbname=os.getenv("DB_NAME", "odoo"),
                user=os.getenv("DB_USER", "odoo"),
                password=os.getenv("DB_PASS", "odoo"),
            )
        except psycopg2.OperationalError as e:
            print("Postgres not ready, retrying in 2 seconds...")
            retries -= 1
            time.sleep(2)
    raise Exception("Could not connect to Postgres after multiple retries")

def ensure_table_exists():
    create_sql = """
    CREATE TABLE IF NOT EXISTS detections_steps (
        step_id BIGINT PRIMARY KEY,
        step_name TEXT,
        project_id BIGINT,
        project_name TEXT,
        detection_id BIGINT,
        detection_name TEXT,
        is_detected BOOLEAN,
        text_instruction TEXT,
        step_type TEXT,
        material_id BIGINT
    );
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(create_sql)
        conn.commit()
        print(" Table 'arkite_steps' ensured to exist")

def insert_steps(steps):
    with get_conn() as conn, conn.cursor() as cur:
        for s in steps:
            cur.execute("""
                INSERT INTO detections_steps (
                    step_id, step_name, project_id, project_name, 
                    detection_id, detection_name, is_detected, text_instruction, step_type,
                    material_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (step_id) DO UPDATE SET
                    is_detected = EXCLUDED.is_detected,
                    text_instruction = EXCLUDED.text_instruction
            """, (
                s["stepId"], s["stepName"], s["projectId"], s["projectName"], s["detectionId"], s["detectionName"],
                s["is_detected"], s["textInstruction"], s["stepType"], s["materialId"]
            ))
        conn.commit()

def on_message(client, userdata, msg):
    steps = json.loads(msg.payload)
    insert_steps(steps)
    print(f"Inserted/updated {len(steps)} steps into DB")

def on_connect(client, userdata, flags, reasonCode, properties):
    if reasonCode == 0:
        print("Connected to MQTT")
        client.subscribe(MQTT_TOPIC)

def main():
    ensure_table_exists()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_forever()

if __name__ == "__main__":
    main()