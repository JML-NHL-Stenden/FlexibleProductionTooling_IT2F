# mqtt_bridge/bridge.py
import os
import time
import logging

# Try to import paho-mqtt, but don't fail the container if it's missing
try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

# --- Logging ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mqtt-bridge")

# --- Environment (defaults keep it generic/no-op) ---
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "")  # empty means: don't subscribe
IDLE_INTERVAL_SEC = float(os.getenv("IDLE_INTERVAL_SEC", "5"))

client = None

def on_connect(cli, _ud, _flags, rc, _props=None):
    if rc == 0:
        log.info("Connected to MQTT at %s:%s", MQTT_HOST, MQTT_PORT)
        if MQTT_TOPIC:
            cli.subscribe(MQTT_TOPIC)
            log.info("Subscribed to topic: %s", MQTT_TOPIC)
        else:
            log.info("No topic configured (MQTT_TOPIC empty) — running idle.")
    else:
        log.warning("MQTT connect returned code %s", rc)

def on_message(_cli, _ud, msg):
    # Default bridge does nothing; just logs receipt
    try:
        payload = msg.payload.decode("utf-8", errors="ignore")
    except Exception:
        payload = "<binary>"
    log.info("Message on %s: %s", msg.topic, payload)

def setup_mqtt():
    global client
    if mqtt is None:
        log.info("paho-mqtt not installed; running without MQTT.")
        return
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="default-bridge")
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        log.warning("Could not connect to MQTT (%s). Continuing idle.", e)
        client = None

def main():
    setup_mqtt()

    if os.getenv("CI") == "true":
        log.info("CI mode: skipping idle loop")
        return

    # Idle loop to keep the container healthy even with no MQTT
    while True:
        time.sleep(IDLE_INTERVAL_SEC)

if __name__ == "__main__":
    main()
