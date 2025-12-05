import os
import json
import threading

import time
import requests
import paho.mqtt.client as mqtt


print("MQTT_HOST:", os.getenv("MQTT_HOST"), "MQTT_PORT:", os.getenv("MQTT_PORT"), flush=True)

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT"))

API_CALL_URL = "https://192.168.56.1/api/v1/projects/?apiKey=jtXRqckD5"
UNIT_FETCH_URL = "https://192.168.56.1/api/v1/units"
LOAD_URL = "https://192.168.56.1/api/v1/units/171880875434312/projects/649473381547313964/load"
API_KEY = "kdfNPsDrz"

def detect_state_to_bool(state):
    if state == "ON":
        return True
    return False

def fetch_steps_payload():
    print(">>> Fetching Arkite steps...")

    BASE = "https://192.168.56.1/api/v1"
    APIKEY = "kdfNPsDrz"

    def get(url):
        r = requests.get(f"{url}?apiKey={APIKEY}", verify=False)
        return r.json()

    final_steps = []

    # 1. Fetch all projects
    projects = get(f"{BASE}/projects")

    for proj in projects:
        projectId = proj["Id"]
        projectName = proj["Name"]

        # 2. Fetch project-level variables
        project_variables = get(f"{BASE}/projects/{projectId}/variables")

        # Keep ONLY Detection-created variables
        detection_variables = {
            v["Id"]: v
            for v in project_variables
            if v["CreationType"] == "Detection"
        }

        # 3. Fetch actual variable states from the unit
        unit_variables = get(f"{BASE}/units/171880875434312/variables")
        unit_state_map = {v["Id"]: v["CurrentState"] for v in unit_variables}

        # 4. Fetch steps (NO processes)
        steps = get(f"{BASE}/projects/{projectId}/steps")

        for step in steps:

            detection_id = step.get("DetectionId")
            detection_name = None
            current_state = None
            is_detected = False

            if detection_id and detection_id in detection_variables:
                detection_name = detection_variables[detection_id]["Name"]
                current_state = unit_state_map.get(detection_id)

                # Convert ON/OFF/UNKNOWN → boolean
                is_detected = (current_state == "ON")

            final_steps.append({
                "stepId": step["Id"],
                "stepName": step["Name"],
                "textInstruction": step["TextInstruction"].get("en-US"),
                "projectId": projectId,
                "projectName": projectName,
                "detectionId": detection_id,
                "detectionName": detection_name,
                "is_detected": is_detected,
                "stepType": step["StepType"],
                "materialId": step["MaterialId"]
            })

    print(">>> Steps fetched:", len(final_steps))
    return final_steps

def on_message(client, userdata, msg):
    print(">>> MQTT RAW MESSAGE:", msg.topic, msg.payload.decode(), flush=True) 

    print(f"MQTT update received on {msg.topic}")

def on_connect(client, userdata, flags, reasonCode, properties):
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
