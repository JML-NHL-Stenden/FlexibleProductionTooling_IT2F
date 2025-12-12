import time
import json
import keyboard
import psycopg2
from psycopg2 import OperationalError
import paho.mqtt.client as mqtt
from datetime import datetime, timezone

# =========================
# PostgreSQL SETTINGS
# =========================
DB_HOST = "localhost"
DB_PORT = 15432      # from docker ps: 0.0.0.0:15432->5432/tcp
DB_NAME = "odoo"
DB_USER = "odoo"
DB_PASSWORD = "odoo"

# =========================
# MQTT SETTINGS
# =========================
MQTT_HOST = "localhost"      # Mosquitto mapped as 0.0.0.0:1883->1883/tcp
MQTT_PORT = 1883
MQTT_TOPIC = "arkite/trigger/QR"

RECONNECT_INTERVAL_SEC = 5

mqtt_client = None


# =========================
# DB HELPERS
# =========================

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def wait_for_db():
    while True:
        print(f"[DB] Testing connection to {DB_HOST}:{DB_PORT} ...")
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            print("[DB] Connection OK.\n")
            return
        except Exception as e:
            print("[DB] Connection FAILED:")
            print(e)
            print(f"[DB] Retrying in {RECONNECT_INTERVAL_SEC}s...\n")
            time.sleep(RECONNECT_INTERVAL_SEC)


def ensure_db_connected():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return
    except Exception:
        wait_for_db()


def find_product_by_qr(qr_code: str):
    query = """
        SELECT id, name, product_code
        FROM public.product_module_product
        WHERE product_code = %s
        LIMIT 1;
    """
    ensure_db_connected()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (qr_code,))
            return cur.fetchone()


# =========================
# MQTT HELPERS
# =========================

def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected.")
    else:
        print(f"[MQTT] Connect failed (rc={rc}). Will retry every {RECONNECT_INTERVAL_SEC}s.")


def _on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[MQTT] Disconnected unexpectedly (rc={rc}). Will retry every {RECONNECT_INTERVAL_SEC}s.")
    else:
        print("[MQTT] Disconnected.")


def setup_mqtt() -> bool:
    global mqtt_client
    print(f"[MQTT] Connecting (async) to {MQTT_HOST}:{MQTT_PORT} ...")
    try:
        mqtt_client = mqtt.Client(client_id="qr-db-keyboard-publisher")
        mqtt_client.on_connect = _on_connect
        mqtt_client.on_disconnect = _on_disconnect

        mqtt_client.reconnect_delay_set(
            min_delay=RECONNECT_INTERVAL_SEC,
            max_delay=RECONNECT_INTERVAL_SEC
        )

        mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()

        print(f"[MQTT] Async connect started. Will retry every {RECONNECT_INTERVAL_SEC}s until broker is up.\n")
        return True
    except Exception as e:
        print("[MQTT] Connection setup FAILED:")
        print(e)
        print()
        return False


def publish_to_arkite(product_name: str, product_code: str, qr_text: str):
    """
    Publish a message to arkite/trigger/QR.
    Format matches what your Arkite agent expects.
    """
    if mqtt_client is None:
        print("[MQTT] Client not initialized, cannot publish.")
        return

    if not mqtt_client.is_connected():
        print(f"[MQTT] Not connected. Will retry automatically every {RECONNECT_INTERVAL_SEC}s. Skipping publish.\n")
        return

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": 1,
        "items": [
            {
                "product_name": product_name,
                "product_code": product_code,
                "qr_text": qr_text,
            }
        ],
        "source": {
            "device": "zebra-ds22xx",
            "origin": "python-qr-db-checker",
        },
    }

    try:
        mqtt_client.publish(MQTT_TOPIC, json.dumps(payload), qos=0, retain=False)
        print(f"[MQTT] Published to {MQTT_TOPIC}: {payload}")
    except Exception as e:
        print(f"[MQTT] Publish failed: {e}")


# =========================
# GLOBAL KEYBOARD HOOK
# =========================

buffer = ""
last_event_time = None
MAX_PAUSE_SEC = 0.5  # if pause between keys > 0.5s, start a new buffer


def handle_key(event):
    global buffer, last_event_time

    # we only care about key-down events
    if event.event_type != "down":
        return

    now = event.time
    if last_event_time is not None:
        # reset buffer if user paused too long (likely a new input)
        if now - last_event_time > MAX_PAUSE_SEC:
            buffer = ""
    last_event_time = now

    # end of scan sequence
    if event.name == "enter":
        code = buffer
        buffer = ""

        if not code:
            return

        print(f"[SCAN] Received sequence: '{code}'")

        # optional: special exit code
        if code.lower() in ("exit", "quit"):
            print("[MAIN] 'exit' code scanned. Press Ctrl+C to stop script.")
            return

        # 1) Check DB (auto-retry every 5s until DB is up)
        while True:
            try:
                row = find_product_by_qr(code)
                break
            except OperationalError as e:
                print(f"[DB] Connection error: {e}")
                print(f"[DB] Retrying in {RECONNECT_INTERVAL_SEC}s...\n")
                time.sleep(RECONNECT_INTERVAL_SEC)
            except Exception as e:
                print(f"[DB] Error while querying database: {e}\n")
                return

        if row is None:
            print(f"[RESULT] QR '{code}' NOT found in product_module_product.\n")
            # NOT found → do NOT publish to Arkite
            return

        prod_id, name, product_code = row
        print(
            f"[RESULT] QR '{code}' FOUND: "
            f"id={prod_id}, name='{name}', product_code='{product_code}'"
        )

        # 2) Publish to Arkite if found
        publish_to_arkite(name, product_code, code)
        print()
        return

    # collect simple character keys (ignore ctrl, shift, etc.)
    if len(event.name) == 1:
        buffer += event.name


def main():
    print("=== QR → PostgreSQL → Arkite (keyboard hook, Windows) ===")
    print("Listening globally for key input (scanner + keyboard).")
    print("Press Ctrl+C in this window to stop.\n")

    wait_for_db()

    if not setup_mqtt():
        return

    # requires admin on Windows
    keyboard.hook(handle_key)

    # block forever
    keyboard.wait()


if __name__ == "__main__":
    main()