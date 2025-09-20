# mqtt_publish/publisher.py
import os
import time
import logging

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None  # allow container to start even if lib missing

# --- Basic logging ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("publisher")

# --- Environment (all optional/defaulted) ---
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "test/default")
PUBLISH_INTERVAL_SEC = float(os.getenv("PUBLISH_INTERVAL_SEC", "5"))

client = None

def setup_mqtt():
    global client
    if mqtt is None:
        log.info("paho-mqtt not available; running without MQTT.")
        return
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="default-publisher")
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        log.info("MQTT ready at %s:%s (topic=%s)", MQTT_HOST, MQTT_PORT, MQTT_TOPIC)
    except Exception as e:
        log.warning("MQTT not connected (%s). Continuing without publishing.", e)
        client = None

def main():
    setup_mqtt()
    # Idle loop; keeps container alive without doing anything.
    while True:
        # Optional no-op publish to confirm container is healthy (only if MQTT is up)
        if client:
            try:
                client.publish(MQTT_TOPIC, payload="", qos=0, retain=False)
            except Exception as e:
                log.debug("Publish skipped: %s", e)
        time.sleep(PUBLISH_INTERVAL_SEC)

if __name__ == "__main__":
    main()
