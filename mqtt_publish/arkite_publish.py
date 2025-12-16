import os
import json
import threading
import re
import time
import requests
import paho.mqtt.client as mqtt
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("MQTT_HOST:", os.getenv("MQTT_HOST"), "MQTT_PORT:", os.getenv("MQTT_PORT"), flush=True)

WORKSTATION_IP = "192.168.56.1"

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT"))

API_CALL_URL = f"https://{WORKSTATION_IP}/api/v1/projects/?apiKey=kdfNPsDrz"
UNIT_FETCH_URL = f"https://{WORKSTATION_IP}/api/v1/units"
LOAD_URL = f"https://{WORKSTATION_IP}/api/v1/units/171880875434312/projects/649473381547313964/load"
API_KEY = "kdfNPsDrz"

def detect_state_to_bool(state):
    if state == "ON":
        return True
    return False

def fetch_loaded_project_id():
    url = f"https://{WORKSTATION_IP}/api/v1/units/171880875434312/loadedProject?apiKey={API_KEY}"
    # ↑ adjust path if your Arkite uses a different endpoint name

    try:
        r = requests.get(url, verify=False)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, dict) and data.get("Id"):
            return str(data["Id"])  # normalize to string
    except Exception as e:
        print("Failed to fetch loaded project:", e)

    return None

def extract_step_number(comment):
    if not comment:
        return None
    match = re.search(r"step\s*(\d+)", comment, re.IGNORECASE)
    return int(match.group(1)) if match else None

def fetch_steps_payload():
    print(">>> Fetching Arkite detection steps...")

    loaded_project_id = fetch_loaded_project_id()

    BASE = "https://192.168.56.1/api/v1"
    APIKEY = "kdfNPsDrz"
    UNIT_ID = "171880875434312"

    def get(url):
        r = requests.get(f"{url}?apiKey={APIKEY}", verify=False)
        r.raise_for_status()
        return r.json()

    detection_steps = []

    # 1. Fetch projects
    projects = get(f"{BASE}/projects")

    for proj in projects:
        project_id = proj["Id"]
        project_name = proj["Name"]

        project_variables = get(f"{BASE}/projects/{project_id}/variables")
        detection_variables = {
            v["Id"]: v
            for v in project_variables
            if v.get("CreationType") == "Detection"
        }

        unit_variables = get(f"{BASE}/units/{UNIT_ID}/variables")
        unit_state_map = {
            v["Id"]: v.get("CurrentState")
            for v in unit_variables
        }

        steps = get(f"{BASE}/projects/{project_id}/steps")

        is_project_loaded = (
            loaded_project_id is not None
            and str(project_id) == loaded_project_id
        )

        numbered_step_sequence = {}
        for step in steps:
            if step.get("Name") == "Numbered Step":
                seq = extract_step_number(step.get("Comment"))
                if seq is not None:
                    numbered_step_sequence[step["Id"]] = seq

        # --------------------------------------------------
        # Pass 2: collect detection steps
        # --------------------------------------------------
        for step in steps:

            detection_id = step.get("DetectionId")
            is_material_grab = step.get("StepType") == "MATERIAL_GRAB"

            # Only detection steps
            if not detection_id and not is_material_grab:
                continue

            detection_name = None
            current_state = None
            detection_status = False

            if detection_id and detection_id in detection_variables:
                detection_name = detection_variables[detection_id]["Name"]
                current_state = unit_state_map.get(detection_id)
                detection_status = detect_state_to_bool(current_state)

            # Resolve sequence from parent numbered step
            sequence = None
            parent_id = step.get("ParentStepId")
            if parent_id and parent_id in numbered_step_sequence:
                sequence = numbered_step_sequence[parent_id]

            detection_steps.append({
                "id": step["Id"],
                "name": step.get("Name"),
                "projectId": project_id,
                "projectName": project_name,
                "detectionId": detection_id,
                "detectionName": detection_name,
                "comment": step.get("Comment"),
                "textInstruction": step.get("TextInstruction", {}).get("en-US"),
                "stepType": step.get("StepType"),
                "sequence": sequence,
                "detection_status": detection_status,
                "isProjectLoaded": is_project_loaded
            })

    print(f">>> Detection steps fetched: {len(detection_steps)}")
    return detection_steps

def on_message(client, userdata, msg):
    print(">>> MQTT RAW MESSAGE:", msg.topic, msg.payload.decode(), flush=True) 

    print(f"MQTT update received on {msg.topic}")

def on_connect(client, userdata, flags, reasonCode, properties):
    global connected
    if reasonCode == 0:
        connected = True
        print(">>> MQTT connected")
    if reasonCode == 0:
        print(">>> MQTT connected successfully!", flush=True)
        print(">>> Listening for product updates…", flush=True)
    else:
        print(">>> MQTT connection failed with code", reasonCode, flush=True)

def publish_loop(client):
    while True:
        try:
            steps_payload = fetch_steps_payload()
            client.publish("factory/all_steps", json.dumps(steps_payload))
            print(">>> Published updated steps to factory/all_steps")
        except Exception as e:
            print(">>> ERROR in fetch/publish loop:", e)
        time.sleep(3)  

def main():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    print("< Connecting to MQTT... >", flush=True)
    client.connect(MQTT_HOST, MQTT_PORT)

    client.loop_start()   # MQTT runs independently

    # 🔥 Start 3-second fetch loop in background thread
    t = threading.Thread(target=publish_loop, args=(client,), daemon=True)
    t.start()

    # Keep process alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
