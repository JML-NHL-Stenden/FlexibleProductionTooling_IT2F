# mqtt_publish/publisher.py
import time
import json
import logging

import paho.mqtt.client as mqtt

# --- Basic logging ---
logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("publisher")

# --- Hard-coded settings (testing only) ---
MQTT_HOST = "192.168.56.1"          # change to your broker's IP if needed
MQTT_PORT = 1883
MQTT_TOPIC = "factory/products/PM-20250929111456-638C16CC/instructions"

# Hard-coded JSON payload
PAYLOAD = {
    "qr_code": "PM-20250929111456-638C16CC",
    "product_name": "Laptop",
    "instructions": [
        {
            "title": "Assembly",
            "steps": [
                "Unpack all components from the box",
                "Insert battery into the laptop",
                "Tighten bottom cover screws with Phillips screwdriver",
                "Attach keyboard and screen assembly"
            ],
            "tools": [
                "Phillips Screwdriver",
                "Anti-static Wrist Strap"
            ]
        },
        {
            "title": "Quality Check",
            "steps": [
                "Power on the laptop",
                "Verify BIOS boot",
                "Run hardware diagnostic test"
            ],
            "tools": [
                "Multimeter",
                "USB Diagnostic Stick"
            ]
        }
    ]
}

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test-publisher")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    payload_str = json.dumps(PAYLOAD, separators=(",", ":"))
    log.info("Publishing to topic %s", MQTT_TOPIC)
    client.publish(MQTT_TOPIC, payload=payload_str, qos=0, retain=True)

    # Give broker time to process before exit
    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    log.info("Done. Message published.")

if __name__ == "__main__":
    main()
