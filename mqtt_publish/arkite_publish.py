import os
import json
import threading
import re
import time
import requests
import paho.mqtt.client as mqtt
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# CONFIG
# =========================

API_BASE = "https://192.168.56.1/api/v1"
API_KEY = "kdfNPsDrz"
UNIT_ID = "171880875434312" # SINGLE UNIT

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT"))

print("MQTT_HOST:", MQTT_HOST, "MQTT_PORT:", MQTT_PORT, flush=True)

# =========================
# HELPERS
# =========================

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


def get(url):
    r = requests.get(f"{url}?apiKey={API_KEY}", verify=False)
    r.raise_for_status()
    return r.json()


def fetch_loaded_project_id():
    try:
        data = get(f"{API_BASE}/units/{UNIT_ID}/loadedProject")
        if isinstance(data, dict) and data.get("Id"):
            return str(data["Id"])
    except Exception as e:
        print("Failed to fetch loaded project:", e)
    return None

# =========================
# CORE LOGIC
# =========================

def fetch_steps_payload():
    print(">>> Fetching Arkite detection steps...")

    loaded_project_id = fetch_loaded_project_id()

    detection_steps = []

    projects = get(f"{API_BASE}/projects")
    unit_variables = get(f"{API_BASE}/units/{UNIT_ID}/variables")

    unit_state_by_name = {
        v["Name"]: v.get("CurrentState")
        for v in unit_variables
        if v.get("Name")
    }

    for proj in projects:
        project_id = proj["Id"]

        project_detections = get(f"{API_BASE}/projects/{project_id}/detections")
        detection_by_id = {
            d["Id"]: d
            for d in project_detections
            if d.get("Id") and d.get("Name")
        }

        steps = get(f"{API_BASE}/projects/{project_id}/steps")

        is_project_loaded = (
            loaded_project_id is not None
            and str(project_id) == loaded_project_id
        )

        for step in steps:
            detection_id = (
                step.get("DetectionId")
                or extract_detection_id_from_name(step.get("Name"))
            )

            is_material_grab = step.get("StepType") == "MATERIAL_GRAB"
            if not detection_id and not is_material_grab:
                continue

            detection_status = False
            if detection_id and detection_id in detection_by_id:
                detection_name = detection_by_id[detection_id]["Name"]
                current_state = unit_state_by_name.get(detection_name)
                detection_status = detect_state_to_bool(current_state)

            detection_steps.append({
                "id": step["Id"],
                "name": step.get("Name"),
                "projectId": project_id,
                "projectName": proj["Name"],
                "sequence": extract_step_number(step.get("Name")),
                "step_type": step.get("StepType"),
                "isProjectLoaded": is_project_loaded,
                "detectionName" : detection_name,
                "detectionId": detection_id,
                "detection_status": detection_status,
            })

    print(f">>> Detection steps fetched: {len(detection_steps)}")
    return detection_steps

# =========================
# MQTT
# =========================

def on_connect(client, userdata, flags, reasonCode, properties):
    if reasonCode == 0:
        print(">>> MQTT connected successfully!", flush=True)
    else:
        print(">>> MQTT connection failed:", reasonCode, flush=True)


def publish_loop(client):
    while True:
        try:
            payload = fetch_steps_payload()
            client.publish("factory/all_steps", json.dumps(payload))
            print(">>> Published updated steps to factory/all_steps")
        except Exception as e:
            print(">>> ERROR in fetch/publish loop:", e)
        time.sleep(1)

# =========================
# MAIN
# =========================

def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect

    print("< Connecting to MQTT... >", flush=True)
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
