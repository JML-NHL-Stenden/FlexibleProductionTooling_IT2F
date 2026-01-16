import os
import json
import threading
import re
import time
import logging
import requests
import paho.mqtt.client as mqtt
import urllib3
import psycopg2
import psycopg2.extras

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(message)s'
)
log = logging.getLogger('arkite-publish')

# =========================
# CONFIG
# =========================

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT"))

# Database connection for fetching projects and their linked Arkite units
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

log.info("MQTT Configuration: %s:%s", MQTT_HOST, MQTT_PORT)
log.info("Database: %s@%s:%s/%s", DB_USER, DB_HOST, DB_PORT, DB_NAME)

# =========================
# HELPERS
# =========================

def get_db_connection():
    """Establish and return a database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Exception as e:
        log.error("Failed to connect to database: %s", e)
        return None


def fetch_projects_with_units():
    """Fetch all projects that have a linked Arkite unit with complete credentials"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Join projects with their linked Arkite units
        cursor.execute("""
            SELECT 
                p.id as project_id,
                p.name as project_name,
                u.id as unit_db_id,
                u.name as unit_name,
                u.unit_id,
                u.api_base,
                u.api_key
            FROM product_module_project p
            INNER JOIN product_module_arkite_unit u ON p.arkite_unit_id = u.id
            WHERE u.active = true
            AND u.api_base IS NOT NULL
            AND u.api_key IS NOT NULL
            AND u.unit_id IS NOT NULL
        """)
        projects = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Strip whitespace from credentials
        for proj in projects:
            proj['unit_id'] = proj['unit_id'].strip() if proj['unit_id'] else None
            proj['api_base'] = proj['api_base'].strip() if proj['api_base'] else None
            proj['api_key'] = proj['api_key'].strip() if proj['api_key'] else None
        
        return projects
    except Exception as e:
        log.error("Failed to fetch projects from database: %s", e)
        if conn:
            conn.close()
        return []


def detect_state_to_bool(state):
    return state == "ON"


def extract_step_number(text: str | None):
    if not text:
        return None

    marker = re.search(r"<~\s*(\d+)\s*~>", text)
    if marker:
        return int(marker.group(1))

    step = re.search(r"step\s*(\d+)", text, re.IGNORECASE)
    if step:
        return int(step.group(1))

    return None


def extract_detection_id_from_name(name: str | None):
    if not name:
        return None
    match = re.search(r"<\[\s*(\d+)\s*\]>", name)
    return match.group(1) if match else None


def get(url, api_key):
    """Make authenticated request to Arkite API with the provided credentials"""
    if not url or not api_key:
        raise ValueError("Invalid URL or API key")
    
    # Ensure credentials are clean
    url = url.strip()
    api_key = api_key.strip()
    
    full_url = f"{url}?apiKey={api_key}"
    try:
        r = requests.get(full_url, verify=False, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        log.error("API request failed: %s", e)
        log.debug("Endpoint: %s?apiKey=***REDACTED***", url)
        raise


def fetch_loaded_project_id(api_base, api_key, unit_id):
    """Fetch the currently loaded project ID for a unit
    
    NOTE: This endpoint is not supported in all Arkite deployments.
    Returns None if unavailable (which is fine - the feature is optional).
    """
    # Disabled: /units endpoints not available in this Arkite instance
    return None

# =========================
# CORE LOGIC
# =========================

def fetch_steps_payload(api_base, api_key, unit_id, arkite_project_id=None):
    """Fetch detection steps from Arkite API using provided credentials"""
    log.info("Fetching detection steps for unit %s", unit_id)

    # Try to fetch loaded project, but don't fail if unavailable
    loaded_project_id = None
    try:
        loaded_project_id = fetch_loaded_project_id(api_base, api_key, unit_id)
    except Exception as e:
        log.debug("Could not fetch loaded project for unit %s (optional)", unit_id)

    detection_steps = []

    try:
        projects = get(f"{api_base}/projects", api_key)
    except Exception as e:
        log.error("Failed to fetch projects for unit %s: %s", unit_id, e)
        return detection_steps
    
    # Fetch unit variables (optional - not all Arkite deployments support this)
    # Disabled: /units endpoints not available in this Arkite instance
    unit_variables = []

    unit_state_by_name = {
        v["Name"]: v.get("CurrentState")
        for v in unit_variables
        if v.get("Name")
    }

    for proj in projects:
        project_id = proj["Id"]

        try:
            project_detections = get(f"{api_base}/projects/{project_id}/detections", api_key)
            detection_by_id = {
                d["Id"]: d
                for d in project_detections
                if d.get("Id") and d.get("Name")
            }

            steps = get(f"{api_base}/projects/{project_id}/steps", api_key)
        except Exception as e:
            log.error("Failed to fetch data for project %s: %s", project_id, e)
            continue

        is_project_loaded = (
            loaded_project_id is not None
            and str(project_id) == loaded_project_id
        )

        for step in steps:
            step_name = step.get("Name")

            if step_name and "<#>" in step_name:
                continue

            detection_id = (
                step.get("DetectionId")
                or extract_detection_id_from_name(step.get("Name"))
            )

            is_material_grab = step.get("StepType") == "MATERIAL_GRAB"
            if not detection_id and not is_material_grab:
                continue

            detection_status = False
            detection_name = None
            if detection_id and detection_id in detection_by_id:
                detection_name = detection_by_id[detection_id]["Name"]
                current_state = unit_state_by_name.get(detection_name)
                detection_status = detect_state_to_bool(current_state)

            if step_name and "<#>" in step_name:
                continue
            
            detection_steps.append({
                "id": step["Id"],
                "name": step_name,
                "projectId": project_id,
                "projectName": proj["Name"],
                "sequence": extract_step_number(step.get("Name")),
                "step_type": step.get("StepType"),
                "isProjectLoaded": is_project_loaded,
                "detectionName" : detection_name,
                "detectionId": detection_id,
                "detection_status": detection_status,
            })

    log.info("Successfully fetched %d detection steps for unit %s", len(detection_steps), unit_id)
    return detection_steps

# =========================
# MQTT
# =========================

import hashlib

def on_connect(client, userdata, flags, reasonCode, properties):
    if reasonCode == 0:
        log.info("Connected to MQTT broker")
    else:
        log.error("MQTT connection failed with code: %s", reasonCode)

# Track last published state to avoid redundant publishes
last_published_state = {}  # Key: unit_id, Value: hash of payload

def publish_loop(client):
    """Main loop: fetch projects with linked units and publish their detection steps"""
    global last_published_state
    
    while True:
        try:
            projects = fetch_projects_with_units()
            
            if not projects:
                log.warning("No projects with linked Arkite units found in database")
                time.sleep(30)
                continue
            
            # Fetch and publish steps for each project/unit combination
            for proj in projects:
                unit_id = proj['unit_id']
                api_base = proj['api_base']
                api_key = proj['api_key']
                project_name = proj['project_name']
                
                try:
                    payload = fetch_steps_payload(api_base, api_key, unit_id)
                    
                    # Only publish if payload has changed
                    payload_json = json.dumps(payload, sort_keys=True)
                    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
                    
                    if last_published_state.get(unit_id) != payload_hash:
                        # Payload changed - publish it
                        topic = f"factory/units/{unit_id}/steps"
                        client.publish(topic, payload_json)
                        last_published_state[unit_id] = payload_hash
                        log.info("Published %d steps for project '%s' to topic '%s' (data changed)", len(payload), project_name, topic)
                    else:
                        # No change - just log debug info
                        log.debug("Detection steps unchanged for unit %s (skipping publish)", unit_id)
                        
                except Exception as e:
                    log.error("Failed to fetch steps for project '%s' (unit %s): %s", project_name, unit_id, e)
            
        except Exception as e:
            log.error("Unexpected error in publish loop: %s", e)
        
        # Longer interval - only check every 30 seconds instead of 1 second
        time.sleep(30)


# =========================
# MAIN
# =========================

def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect

    log.info("Starting Arkite detection steps publisher")
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()

    threading.Thread(
        target=publish_loop,
        args=(client,),
        daemon=True
    ).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
