import os
import time
import json
import hashlib
import logging
from pathlib import Path

import paho.mqtt.client as mqtt
import psutil
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

# =========================
# Logging
# =========================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("arkite-agent")


# =========================
# Helper: read from OS env or .env
# =========================

def get_from_env_or_envfile(key: str, default: str | None = None) -> str | None:
    """
    1) Try Windows environment variable.
    2) Then try .env files in:
       - automation/.env  (same folder as this script)
       - repo-root/.env   (one level above)
    3) Fall back to default if nothing found.
    """
    val = os.getenv(key)
    if val is not None:
        return val

    env_paths = [
        Path(__file__).resolve().parent / ".env",          # automation/.env
        Path(__file__).resolve().parent.parent / ".env",   # repo/.env (optional)
    ]

    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()

    return default


# =========================
# MQTT CONFIG
# =========================

_raw_host = get_from_env_or_envfile("MQTT_HOST", None)
if not _raw_host:
    _raw_host = "localhost"  # last-resort default

MQTT_HOST = _raw_host
MQTT_PORT = int(get_from_env_or_envfile("MQTT_PORT", "1883"))
MQTT_TOPIC = get_from_env_or_envfile("MQTT_TOPIC_QR", "arkite/trigger/QR")

IDLE_INTERVAL_SEC = float(get_from_env_or_envfile("IDLE_INTERVAL_SEC", "1"))

last_payload_hash = None
client = None


# =========================
# Arkite credentials
# =========================

ARKITE_USER = get_from_env_or_envfile("ARKITE_USER", "Admin")
ARKITE_PASS = get_from_env_or_envfile("ARKITE_PASS", "Arkite3600")


# =========================
# ARKITE EXE & LOGIN
# =========================

def is_arkite_running() -> bool:
    for p in psutil.process_iter(attrs=["name"]):
        name = p.info.get("name") or ""
        if "Arkite Workstation.exe" in name:
            return True
    return False


def find_arkite_exe() -> str | None:
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ]

    for root in roots:
        if not root:
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if "Arkite Workstation.exe" in filenames:
                exe_path = os.path.join(dirpath, "Arkite Workstation.exe")
                log.info("[ARKITE] Found Arkite exe at: %s", exe_path)
                return exe_path
    return None


def get_or_start_arkite_app(exe_path: str):
    app = Application(backend="uia")
    try:
        app.connect(path=exe_path)
        log.info("[ARKITE] Attached to existing Arkite instance.")
        return app, True
    except Exception:
        log.info("[ARKITE] No existing Arkite instance. Starting a new one...")
        return app.start(exe_path), False


def open_and_login_arkite():
    """
    1) If Arkite is already running -> do nothing.
    2) Else find the EXE, start it, and type username + password.
    """
    if is_arkite_running():
        log.info("[ARKITE] Arkite already running, skipping open/login.")
        return

    exe_path = find_arkite_exe()
    if not exe_path:
        log.error("[ARKITE] Arkite Workstation.exe not found in Program Files.")
        return

    app, _already_running = get_or_start_arkite_app(exe_path)

    log.info("[ARKITE] Waiting for login screen...")
    time.sleep(10)

    try:
        dlg = app.top_window()
        dlg.set_focus()
        time.sleep(0.5)

        log.info("[ARKITE] Sending login keystrokes...")
        # Adjust TAB count depending on your login screen
        send_keys("{TAB 3}", pause=0.05)
        send_keys(ARKITE_USER)
        send_keys("{TAB}", pause=0.05)
        send_keys(ARKITE_PASS)
        send_keys("{ENTER}", pause=0.05)

        log.info("[ARKITE] Waiting for workstation to load after login...")
        time.sleep(15)

        log.info("[ARKITE] Arkite should now be logged in.")
    except Exception as e:
        log.error("[ARKITE] ERROR automating login: %s", e)


# =========================
# MQTT PARSING
# =========================

def parse_qr_message(payload: str):
    """
    Expects payload like:
    {
      "timestamp": "...",
      "count": 1,
      "items": [
        {
          "product_name": "Road Lamp",
          "product_code": "123456",
          "qr_text": "123456"
        }
      ],
      "source": {...}
    }
    We only care that qr_text exists to trigger.
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        log.error("[MQTT] JSON parse error: %s | payload: %s", e, payload)
        return None, None, None

    items = data.get("items") or []
    if not items:
        log.warning("[MQTT] No 'items' in payload.")
        return None, None, None

    item = items[0]
    product_name = item.get("product_name")
    product_code = item.get("product_code")
    qr_text = item.get("qr_text")

    if not qr_text:
        log.warning("[MQTT] 'qr_text' missing in first item.")
        return None, None, None

    return product_name, product_code, qr_text


# =========================
# MQTT CALLBACKS
# =========================

def on_connect(cli, _userdata, _flags, rc, _props=None):
    if rc == 0:
        log.info("Connected to MQTT at %s:%s", MQTT_HOST, MQTT_PORT)
        cli.subscribe(MQTT_TOPIC)
        log.info("Subscribed to topic: %s", MQTT_TOPIC)
    else:
        log.warning("MQTT connect returned code %s", rc)


def on_message(_cli, _userdata, msg):
    global last_payload_hash

    try:
        payload = msg.payload.decode("utf-8", errors="ignore").strip()
    except Exception:
        payload = "<binary>"

    log.info("[MQTT] Received on %s: %s", msg.topic, payload)

    # Avoid repeating the exact same action for identical payload
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if h == last_payload_hash:
        log.info("[MQTT] Payload unchanged since last run; ignoring.")
        return
    last_payload_hash = h

    product_name, product_code, qr_text = parse_qr_message(payload)
    if not qr_text:
        log.info("[MQTT] Ignored message (no valid qr_text).")
        return

    log.info(
        "[ARKITE] QR trigger received. Product='%s', Code='%s', QR='%s'.",
        product_name,
        product_code,
        qr_text,
    )
    log.info("[ARKITE] Triggering Arkite open + login.")
    open_and_login_arkite()


# =========================
# MQTT SETUP & MAIN LOOP
# =========================

def setup_mqtt():
    global client
    # Use v5 client; ignore deprecation warnings from older default API
    try:
        from paho.mqtt.client import CallbackAPIVersion
        client = mqtt.Client(
            client_id="arkite-agent",
            protocol=mqtt.MQTTv5,
            callback_api_version=CallbackAPIVersion.VERSION2,
        )
    except Exception:
        client = mqtt.Client(
            client_id="arkite-agent",
            protocol=mqtt.MQTTv5,
        )

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()


def main():
    log.info(
        "=== Arkite Agent (Windows) ===\n"
        "Broker: %s:%s | Topic: %s",
        MQTT_HOST,
        MQTT_PORT,
        MQTT_TOPIC,
    )

    setup_mqtt()

    while True:
        time.sleep(IDLE_INTERVAL_SEC)


if __name__ == "__main__":
    main()
