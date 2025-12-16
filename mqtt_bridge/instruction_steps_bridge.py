import os
import json
import time
import psycopg2
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "factory/all_steps"

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

def get_conn():
    retries = 10
    while retries:
        try:
            return psycopg2.connect(
                host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
            )
        except psycopg2.OperationalError:
            print("Postgres not ready, retrying in 2 seconds...")
            retries -= 1
            time.sleep(2)
    raise Exception("Could not connect to Postgres after multiple retries")

def ensure_tables():
    create_product_sql = """
    CREATE TABLE IF NOT EXISTS product_module_product (
        id BIGINT PRIMARY KEY,
        name TEXT,
        product_code TEXT,
        description TEXT
    );
    """
    create_instruction_sql = """
    CREATE TABLE IF NOT EXISTS product_module_instruction (
        id SERIAL PRIMARY KEY,
        product_id BIGINT REFERENCES product_module_product(id) ON DELETE CASCADE,
        sequence INT,
        title TEXT,
        description TEXT
    );
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(create_product_sql)
        cur.execute(create_instruction_sql)
        conn.commit()
        print("Ensured tables exist.")

def insert_or_update_product(product_id, product_name):
    with get_conn() as conn, conn.cursor() as cur:
        # Try update first
        cur.execute("UPDATE product_module_product SET name=%s WHERE id=%s", (product_name, product_id))
        if cur.rowcount == 0:
            # Insert if not exists
            cur.execute("INSERT INTO product_module_product (id, name, product_code) VALUES (%s, %s, %s)", (product_id, product_name, "ABCDEFG"))
        conn.commit()

def insert_or_update_instruction(product_id, step):
    """
    Inserts instruction with ID = detection_step.id, or updates if already exists.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO product_module_instruction (id, product_id, sequence, title, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                product_id = EXCLUDED.product_id,
                sequence = EXCLUDED.sequence,
                title = EXCLUDED.title,
                description = EXCLUDED.description
        """, (
            step["id"],                  # Use detection_step.id as PK
            product_id,
            step.get("sequence"),
            step.get("name"),
            step.get("textInstruction")
        ))
        conn.commit()

def insert_or_update_progress(product_id, completed_steps, total_steps):
    """Insert new progress or update existing row for product_id."""
    with get_conn() as conn, conn.cursor() as cur:
        # Try to update first
        cur.execute("""
            UPDATE product_module_progress
            SET completed_steps = %s,
                total_steps = %s
            WHERE product_id = %s
        """, (completed_steps, total_steps, product_id))
        if cur.rowcount == 0:
            # Insert if not exists
            cur.execute("""
                INSERT INTO product_module_progress (name, product_id, completed_steps, total_steps)
                VALUES (%s, %s, %s, %s)
            """, (f"Workstation for {product_id}", product_id, completed_steps, total_steps))
        conn.commit()

def compute_progress(steps):
    """Return dict of product_id -> {'completed': X, 'total': Y}"""
    progress = {}
    for s in steps:
        pid = s["projectId"]
        if pid not in progress:
            progress[pid] = {"completed": 0, "total": 0}
        progress[pid]["total"] += 1
        if s.get("detection_status"):
            progress[pid]["completed"] += 1
    return progress

def on_message(client, userdata, msg):
    try:
        steps = json.loads(msg.payload)
    except json.JSONDecodeError:
        print("Invalid JSON payload")
        return

    print(f"Received {len(steps)} steps from MQTT")

    # Group by project
    projects = {}
    for s in steps:
        proj_id = s["projectId"]
        if proj_id not in projects:
            projects[proj_id] = {
                "name": s["projectName"],
                "steps": []
            }
        projects[proj_id]["steps"].append(s)

    for proj_id, proj_data in projects.items():
        insert_or_update_product(proj_id, proj_data["name"])
        for step in proj_data["steps"]:
            insert_or_update_instruction(proj_id, step)

    progress_stats = compute_progress(steps)
    for pid, stats in progress_stats.items():
        insert_or_update_progress(pid, stats["completed"], stats["total"])
        print(f"Progress tracked for product {pid}: {stats}")

    print(f"Inserted/updated products and instructions for {len(projects)} projects")

def on_connect(client, userdata, flags, reasonCode, properties):
    if reasonCode == 0:
        print("Connected to MQTT")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        print("Failed to connect to MQTT, reason:", reasonCode)

def main():
    ensure_tables()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_forever()

if __name__ == "__main__":
    main()
