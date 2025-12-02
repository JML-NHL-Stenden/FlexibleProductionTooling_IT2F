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

    # 1. Projects
    projects = get(f"{BASE}/projects")

    # Vars for final result
    final_steps = []

    # 5. Variables (for detection state)
    variables = get(f"{BASE}/units/171880875434312/variables")
    variable_map = {v["Name"]: v["CurrentState"] for v in variables}

    for proj in projects:

        projectId = proj["Id"]
        projectName = proj["Name"]

        # 2. Processes
        processes = get(f"{BASE}/projects/{projectId}/processes")

        # 3. Detections
        detections = get(f"{BASE}/projects/{projectId}/detections")
        detection_map = {d["Id"]: d for d in detections}

        for proc in processes:

            processId = proc["Id"]
            processName = proc["Name"]

            # 4. Steps
            steps = get(
                f"{BASE}/projects/{projectId}/processes/{processId}/steps"
            )

            for step in steps:

                detection_id = step.get("DetectionId")
                detection_name = None
                current_state = None
                is_detected = False

                if detection_id and detection_id in detection_map:
                    detection_name = detection_map[detection_id]["Name"]
                    current_state = variable_map.get(detection_name)
                    is_detected = detect_state_to_bool(current_state)

                if detection_id != None:
                    final_steps.append({
                        "stepId": step["Id"],
                        "stepName": step["Name"],
                        "textInstruction": step["TextInstruction"].get("en-US"),
                        "projectId": projectId,
                        "projectName": projectName,
                        "processId": processId,
                        "processName": processName,
                        "detectionId": detection_id,
                        "detectionName": detection_name,
                        "is_detected": is_detected,
                        "stepType": step["StepType"],
                        "index": step["Index"],
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
