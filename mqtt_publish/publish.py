# mqtt_publish/publisher.py
import os
import json
import time
import logging
import hashlib
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.extras

# --- Configuration ---
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_PUB_TOPIC = os.getenv("MQTT_TOPIC", "factory/products/all_product_codes")  # single message with all codes

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "5"))  # seconds
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Logging ---
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s  [%(levelname)s]  %(message)s")
log = logging.getLogger("mqtt-publish-product-codes")

# --- SQL (distinct product_code list) ---
SQL_PRODUCT_CODES = """
SELECT DISTINCT product_code
FROM public.product_module_product
WHERE product_code IS NOT NULL AND product_code <> ''
ORDER BY product_code;
"""

# --- MQTT Setup ---
mqtt_client = mqtt.Client(client_id="mqtt-publish-product-codes", protocol=mqtt.MQTTv5)
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

# --- DB Connection ---
def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )

def fetch_product_codes():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(SQL_PRODUCT_CODES)
        rows = cur.fetchall()
        return [r["product_code"] for r in rows]

def payload_for_codes(codes):
    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "count": len(codes),
        "product_codes": codes,
        "source": {
            "db": DB_NAME,
            "table": "public.product_module_product"
        }
    }

def hash_codes(codes):
    m = hashlib.sha256()
    for c in codes:
        m.update(c.encode("utf-8"))
        m.update(b"\x00")
    return m.hexdigest()

def publish_all_product_codes():
    last_hash = None
    ci_mode = os.getenv("CI") == "true" or "--dry-run" in os.sys.argv
    while True:
        try:
            codes = fetch_product_codes()
            current_hash = hash_codes(codes)

            # Publish only if changed (or first run)
            if current_hash != last_hash:
                payload = payload_for_codes(codes)
                msg = json.dumps(payload, separators=(",", ":"))
                mqtt_client.publish(MQTT_PUB_TOPIC, msg, qos=1, retain=True)
                log.info("Published %d product codes to '%s'", len(codes), MQTT_PUB_TOPIC)
                last_hash = current_hash
            else:
                log.debug("No change in product codes; skipping publish.")

        except Exception as e:
            log.error("Error while publishing product codes: %s", e, exc_info=True)

        if ci_mode:
            log.info("CI/dry-run mode: exiting after one iteration")
            break

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    publish_all_product_codes()
