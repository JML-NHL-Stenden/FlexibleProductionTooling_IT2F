import json, logging, re
import paho.mqtt.client as mqtt
import psycopg2

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mqtt-bridge")

# ---- Hard-coded config ----
MQTT_HOST = "mqtt"                 # broker service name in compose
MQTT_PORT = 1883
MQTT_TOPIC = "factory/products/+/instructions"
MQTT_CLIENT_ID = "mqtt-bridge"

PG_HOST = "db"
PG_PORT = 5432
PG_DB   = "dummy_db"
PG_USER = "odoo"
PG_PASS = "odoo"
# --------------------------------------------

def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS
    )

def ensure_tables_exist():
    ddl = """
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        qr_code TEXT UNIQUE,              -- now TEXT
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS instructions (
        id SERIAL PRIMARY KEY,
        product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS instruction_steps (
        id SERIAL PRIMARY KEY,
        instruction_id INT NOT NULL REFERENCES instructions(id) ON DELETE CASCADE,
        step_no INT NOT NULL,
        step_text TEXT NOT NULL,
        UNIQUE (instruction_id, step_no)
    );
    CREATE TABLE IF NOT EXISTS tools (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS instruction_tools (
        instruction_id INT NOT NULL REFERENCES instructions(id) ON DELETE CASCADE,
        tool_id INT NOT NULL REFERENCES tools(id) ON DELETE RESTRICT,
        PRIMARY KEY (instruction_id, tool_id)
    );
    """
    with get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl); conn.commit()

def parse_qr_from_topic(topic: str):
    m = re.match(r"^factory/products/([^/]+)/instructions$", topic)
    return m.group(1) if m else None

def handle_payload(topic: str, payload: str):
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("Invalid JSON on %s: %s", topic, payload[:120]); return

    qr = obj.get("qr_code") or parse_qr_from_topic(topic)
    product_name = obj.get("product_name", "Unknown Product")
    instructions = obj.get("instructions", [])
    if not qr:
        log.warning("No QR code found; skipping."); return

    with get_pg_conn() as conn:
        cur = conn.cursor()

        # upsert product by TEXT qr_code
        cur.execute("""
            INSERT INTO products (qr_code, name)
            VALUES (%s, %s)
            ON CONFLICT (qr_code) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """, (qr, product_name))
        product_id = cur.fetchone()[0]

        for instr in instructions:
            title = instr.get("title", "Untitled")
            steps = instr.get("steps", [])
            tools = instr.get("tools", [])

            cur.execute(
                "INSERT INTO instructions (product_id, title) VALUES (%s, %s) RETURNING id",
                (product_id, title),
            )
            instruction_id = cur.fetchone()[0]

            for idx, step_text in enumerate(steps, start=1):
                cur.execute("""
                    INSERT INTO instruction_steps (instruction_id, step_no, step_text)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (instruction_id, step_no)
                    DO UPDATE SET step_text = EXCLUDED.step_text
                """, (instruction_id, idx, step_text))

            for tool_name in tools:
                cur.execute(
                    "INSERT INTO tools (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id",
                    (tool_name,),
                )
                row = cur.fetchone()
                if row:
                    tool_id = row[0]
                else:
                    cur.execute("SELECT id FROM tools WHERE name=%s", (tool_name,))
                    tool_id = cur.fetchone()[0]

                cur.execute(
                    "INSERT INTO instruction_tools (instruction_id, tool_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (instruction_id, tool_id),
                )

        conn.commit()
        log.info("Saved product=%s (QR=%s), instructions=%d", product_name, qr, len(instructions))

def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        log.info("Connected to MQTT at %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe(MQTT_TOPIC)
        log.info("Subscribed: %s", MQTT_TOPIC)
    else:
        log.error("Connect failed rc=%s", rc)

def on_message(client, userdata, msg):
    log.info("Message on %s (%d bytes)", msg.topic, len(msg.payload or b""))
    handle_payload(msg.topic, msg.payload.decode("utf-8", "ignore"))

def main():
    ensure_tables_exist()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()

if __name__ == "__main__":
    main()
