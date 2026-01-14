import os
import time
import json
import hashlib
import logging

import requests
import urllib3
import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.extras

# =========================
# Logging
# =========================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mqtt-arkite-bridge")

# =========================
# DATABASE CONFIG
# =========================
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )

def get_arkite_unit_config():
    """Get Arkite configuration from the first active unit in Odoo database"""
    try:
        with get_db_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT unit_id, api_base, api_key, template_name
                FROM public.product_module_arkite_unit
                WHERE active = true
                ORDER BY id
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return None  # Return None instead of raising error
            
            return {
                'unit_id': row['unit_id'],
                'api_base': row['api_base'],
                'api_key': row['api_key'],
                'template_name': row['template_name']
            }
    except Exception as e:
        log.error(f"Failed to get Arkite unit config from database: {e}")
        return None

# =========================
# GLOBAL CONFIG VARIABLES
# =========================

API_BASE = None
API_KEY = None
TEMPLATE_PROJECT_NAME = None
UNIT_ID = None
CONFIG_LOADED = False

def load_configuration():
    """Load Arkite configuration from database. Returns True if loaded successfully."""
    global API_BASE, API_KEY, TEMPLATE_PROJECT_NAME, UNIT_ID, CONFIG_LOADED
    
    config = get_arkite_unit_config()
    if config:
        API_BASE = config['api_base']
        API_KEY = config['api_key']
        TEMPLATE_PROJECT_NAME = config['template_name']
        UNIT_ID = int(config['unit_id'])
        CONFIG_LOADED = True
        log.info("Successfully loaded Arkite configuration for unit: %s", config['unit_id'])
        return True
    else:
        CONFIG_LOADED = False
        return False

# Disable SSL warnings for self-signed Arkite cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# MQTT CONFIG
# =========================

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC_QR", "arkite/trigger/QR")

IDLE_INTERVAL_SEC = float(os.getenv("IDLE_INTERVAL_SEC", "1"))

# Track last processed payload to avoid repeating the same action
last_payload_hash = None

client = None


# =========================
# ARKITE API CALLS
# =========================

def get_project_id_by_name(project_name: str):
    url = f"{API_BASE}/projects/"
    params = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json"}

    log.info("[ARKITE] Fetching project list for '%s'...", project_name)
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as e:
        log.error("[ARKITE] ERROR fetching projects: %s", e)
        return None

    log.info("[ARKITE] GET /projects STATUS: %s", response.status_code)
    if not response.ok:
        log.error("[ARKITE] Server refused request: %s", response.text)
        return None

    try:
        data = response.json()
    except Exception as e:
        log.error("[ARKITE] JSON parse error: %s", e)
        return None

    if not isinstance(data, list):
        log.error("[ARKITE] Bad format for projects response: %s", data)
        return None

    for proj in data:
        name = proj.get("Name") or proj.get("ProjectName")
        if name == project_name:
            pid = proj.get("Id") or proj.get("ProjectId")
            log.info("[ARKITE] Found project '%s' with ID %s", project_name, pid)
            return pid

    log.warning("[ARKITE] Project '%s' not found.", project_name)
    return None


def create_project(project_name: str):
    """
    Creates a new Arkite project with the given name.

    Currently this is a plain create with Name + UnitIds.
    Arkite still requires the workstation/unit to be online to load it.
    """
    url = f"{API_BASE}/projects/"
    params = {"apiKey": API_KEY}

    payload = [
        {
            "Name": project_name,
            "Comment": "Created by MQTT QR bridge",
            "UnitIds": [UNIT_ID],
        }
    ]

    headers = {"Content-Type": "application/json"}

    log.info("[ARKITE] Creating project: %s", project_name)

    try:
        response = requests.post(
            url,
            params=params,
            json=payload,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as e:
        log.error("[ARKITE] ERROR creating project: %s", e)
        return None

    log.info("[ARKITE] CREATE STATUS: %s", response.status_code)
    log.debug("[ARKITE] CREATE RESPONSE: %s", response.text)

    # Even if status is 500/400, Arkite sometimes still has the project in list
    time.sleep(1)
    return get_project_id_by_name(project_name)


def rename_project(project_id: int, new_name: str):
    """
    PATCH /projects/{projectId}
    to change the name of the duplicated project.
    """
    url = f"{API_BASE}/projects/{project_id}"
    params = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json"}
    payload = {
        "Name": new_name
    }

    log.info("[ARKITE] Renaming project %s to '%s'", project_id, new_name)

    try:
        response = requests.patch(
            url,
            params=params,
            json=payload,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as e:
        log.error("[ARKITE] ERROR renaming project: %s", e)
        return False

    log.info("[ARKITE] RENAME STATUS: %s", response.status_code)
    log.debug("[ARKITE] RENAME RESPONSE: %s", response.text)

    if 200 <= response.status_code < 300:
        return True

    log.warning("[ARKITE] Rename project returned non-2xx.")
    return False


def duplicate_project_via_api(template_id: int, new_project_name: str):
    """
    Use the real Arkite duplicate endpoint:

        POST /projects/{projectId}/duplicate/

    Swagger shows this endpoint but does not document a request body,
    so we call it WITHOUT JSON payload and with apiKey as query param.

    Then:
      - Parse the returned Project object (or list) to get the new ID.
      - PATCH that project to set Name=new_project_name.
    """
    url = f"{API_BASE}/projects/{template_id}/duplicate/"
    params = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json"}

    log.info(
        "[ARKITE] Attempting duplicate of template ID %s into '%s'",
        template_id,
        new_project_name,
    )

    try:
        # No JSON body – according to Swagger, this call just takes path + apiKey
        response = requests.post(
            url,
            params=params,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as e:
        log.error("[ARKITE] ERROR in duplicate_project_via_api: %s", e)
        return None

    log.info("[ARKITE] DUPLICATE STATUS: %s", response.status_code)
    log.debug("[ARKITE] DUPLICATE RESPONSE: %s", response.text)

    if not (200 <= response.status_code < 300):
        return None

    # Try to decode the returned project
    try:
        data = response.json()
    except Exception as e:
        log.error("[ARKITE] JSON parse error for duplicate response: %s", e)
        return None

    # It might return a single project or a list
    if isinstance(data, list) and data:
        proj = data[0]
    else:
        proj = data

    new_id = proj.get("Id") or proj.get("ProjectId")
    if not new_id:
        log.error("[ARKITE] Duplicate response has no project Id/ProjectId: %s", data)
        return None

    # Rename duplicated project to our desired name
    rename_project(new_id, new_project_name)

    return new_id


def duplicate_template_project(template_name: str, new_project_name: str):
    """
    Idempotent 'duplicate template' function per project name:

    - If a project with new_project_name already exists, reuse it.
    - Otherwise:
        - Looks up the template project ID by name.
        - Calls POST /projects/{projectId}/duplicate/ (no JSON body).
        - Patches name to new_project_name.
        - Falls back to plain create_project() if duplicate fails.
    """
    existing_id = get_project_id_by_name(new_project_name)
    if existing_id:
        log.info(
            "[ARKITE] Project '%s' already exists with ID %s. Reusing existing project.",
            new_project_name,
            existing_id,
        )
        return existing_id

    template_id = get_project_id_by_name(template_name)
    if not template_id:
        log.warning(
            "[ARKITE] Template '%s' not found. Falling back to plain create.",
            template_name,
        )
        return create_project(new_project_name)

    log.info(
        "[ARKITE] Template '%s' has ID %s.",
        template_name,
        template_id,
    )

    project_id = duplicate_project_via_api(template_id, new_project_name)
    if project_id:
        log.info(
            "[ARKITE] Duplicate via API successful, new project ID: %s",
            project_id,
        )
        return project_id

    log.warning(
        "[ARKITE] Duplicate via API failed. "
        "Falling back to create_project('%s').",
        new_project_name,
    )
    return create_project(new_project_name)


def load_project_on_unit(unit_id, project_id):
    url = f"{API_BASE}/units/{unit_id}/projects/{project_id}/load/"
    params = {"apiKey": API_KEY}
    headers = {"Content-Type": "application/json"}

    log.info("[ARKITE] Loading project ID %s on unit %s", project_id, unit_id)

    try:
        response = requests.post(
            url,
            params=params,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as e:
        log.error("[ARKITE] ERROR loading project: %s", e)
        return None

    log.info("[ARKITE] LOAD STATUS: %s", response.status_code)
    log.debug("[ARKITE] LOAD RESPONSE: %s", response.text)
    return response


def wait_and_load_project(unit_id, project_id, max_retries=20, delay_seconds=5):
    """
    Try to load a project on a unit, being patient while Arkite / workstation is
    still connecting. We only give up after max_retries attempts.

    We treat several 400 error messages as "unit/workstation not ready yet"
    and keep retrying, so we don't stop too early right when Arkite is coming online.
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        log.info("[ARKITE] Load attempt %s/%s", attempt, max_retries)
        resp = load_project_on_unit(unit_id, project_id)

        if resp is None:
            last_error = "No response from Arkite server"
        elif 200 <= resp.status_code < 300:
            log.info("[ARKITE] Project loaded successfully.")
            return
        else:
            text = (resp.text or "").lower()
            last_error = f"{resp.status_code}: {resp.text}"

            # All of these are considered "not ready yet, retry later"
            if (
                "unit not connected" in text
                or "try loading this project on the workstation first" in text
                or "workstation" in text
            ):
                log.warning(
                    "[ARKITE] Unit/workstation not ready yet. Waiting %s seconds before retry...",
                    delay_seconds,
                )
                time.sleep(delay_seconds)
                continue

            # Any other 4xx/5xx: still retry, but log as unexpected
            log.warning(
                "[ARKITE] Unexpected error while loading project (will retry): %s",
                resp.text,
            )
            time.sleep(delay_seconds)
            continue

    log.error(
        "[ARKITE] Failed to load project %s on unit %s after %s attempts. Last error: %s",
        project_id,
        unit_id,
        max_retries,
        last_error,
    )


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
          "product_code": "12345",
          "qr_text": "12345"
        }
      ],
      "source": {...}
    }
    Returns (product_name, product_code, qr_text) or (None, None, None) on error.
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

    # CHOOSE NAME STRATEGY:
    # Here we prefer product_name and fall back to qr_text.
    new_project_name = product_name or qr_text

    log.info(
        "[ARKITE] QR trigger received. Product='%s', Code='%s', QR='%s'.",
        product_name,
        product_code,
        qr_text,
    )
    log.info("[ARKITE] New project name will be: %s", new_project_name)

    project_id = duplicate_template_project(TEMPLATE_PROJECT_NAME, new_project_name)
    if project_id:
        wait_and_load_project(UNIT_ID, project_id)
    else:
        log.error("[ARKITE] Could not create/resolve project '%s'", new_project_name)


# =========================
# MQTT SETUP & MAIN LOOP
# =========================

def setup_mqtt():
    global client
    client = mqtt.Client(
        client_id="mqtt-arkite-bridge",
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()


def main():
    log.info("=== MQTT → Arkite Bridge (in Docker) ===")
    log.info("Broker: %s:%s | Topic: %s", MQTT_HOST, MQTT_PORT, MQTT_TOPIC)
    log.info("Waiting for Arkite unit configuration...")

    # Wait for configuration to be available
    while not CONFIG_LOADED:
        if load_configuration():
            break
        log.info("No Arkite unit configured yet. Waiting %d seconds before checking again...", IDLE_INTERVAL_SEC)
        time.sleep(IDLE_INTERVAL_SEC)

    log.info(
        "Configuration loaded! Template: %s | Unit ID: %s",
        TEMPLATE_PROJECT_NAME,
        UNIT_ID,
    )

    setup_mqtt()

    if os.getenv("CI") == "true":
        log.info("CI mode: skipping idle loop")
        return

    while True:
        time.sleep(IDLE_INTERVAL_SEC)


if __name__ == "__main__":
    main()
