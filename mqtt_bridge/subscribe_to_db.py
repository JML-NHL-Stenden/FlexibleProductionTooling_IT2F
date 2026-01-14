import os
import time
import json
import hashlib
import logging
import psycopg2
import paho.mqtt.client as mqtt
import threading
import re

# =========================
# Logging
# =========================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mqtt-all-steps-upsert")

# =========================
# PostgreSQL CONFIG
# =========================
max_retries = 5
for attempt in range(1, max_retries + 1):
    try:
        db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", 5432)),
            user=os.getenv("DB_USER", "odoo"),
            password=os.getenv("DB_PASS", "odoo"),
            database=os.getenv("DB_NAME", "odoo"),
        )
        log.info("Connected to Postgres on attempt %s/%s", attempt, max_retries)
        break
    except psycopg2.OperationalError as e:
        log.warning("Postgres not ready yet (attempt %s/%s): %s", attempt, max_retries, e)
        time.sleep(3)
else:
    log.error("Could not connect to Postgres after %s attempts.", max_retries)
    raise SystemExit(1)

db_cur = db_conn.cursor()


def clean_instruction_title(title: str) -> str:
    if not title:
        return title

    # remove <~...~> and <[...]> blocks
    title = re.sub(r"<~.*?~>", "", title)
    title = re.sub(r"<\[.*?\]>", "", title)

    return title.strip()

# =========================
# MQTT CONFIG
# =========================
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "factory/all_steps"

last_payload_hash = None
client = None

def track_project_time(project_db_id):
    log.info("[TIMER] Started timer for project %s", project_db_id)

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "odoo"),
        password=os.getenv("DB_PASS", "odoo"),
        database=os.getenv("DB_NAME", "odoo"),
    )
    cur = conn.cursor()

    try:
        while True:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_completed THEN 1 ELSE 0 END) AS completed
                FROM public.product_module_instruction
                WHERE project_id = %s;
            """, (project_db_id,))
            total, completed = cur.fetchone()

            log.info("Total %s steps compelted for project %s", total,project_db_id)

            if completed == 0:
                status = 'not_started'
            elif completed < total:
                status = 'in_progress'
            else:
                status = 'done'

            cur.execute("""
                UPDATE public.product_module_project
                SET status = %s
                WHERE id = %s;
            """, (status, project_db_id))

            if status == 'done':
                conn.commit()
                log.info("[TIMER] Project %s DONE — stopping timer", project_db_id)
                break

            if status == 'in_progress':
                cur.execute("""
                    UPDATE public.product_module_project
                    SET active_completion_time = active_completion_time + 1
                    WHERE id = %s;
                """, (project_db_id,))

            conn.commit()
            time.sleep(1)

    finally:
        conn.close()
        with active_project_timers_lock:
            active_project_timers.discard(project_db_id)

active_project_timers = set()
active_project_timers_lock = threading.Lock()
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

    # avoid processing duplicate payload
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if h == last_payload_hash:
        return
    last_payload_hash = h

    try:
        steps = json.loads(payload)
    except Exception as e:
        log.error("[MQTT] JSON parse error: %s", e)
        return

    projects = {}
    for step in steps:
        projects.setdefault(step["projectId"], []).append(step)

    for project_id, project_steps in projects.items():
        project_name = project_steps[0]["projectName"]

        # UPSERT project
        log.info("!Project id: %s,", project_id)
        try:
            db_cur.execute("""
                INSERT INTO public.product_module_project (arkite_project_id, name, status, active_completion_time)
                VALUES (%s, %s, 'not_started', 0)
                ON CONFLICT (arkite_project_id) DO UPDATE
                SET name = EXCLUDED.name
                RETURNING id;
            """, (project_id, project_name))
            project_db_id = db_cur.fetchone()[0]
            db_conn.commit()
        except Exception as e:
            db_conn.rollback()
            log.error("[DB] Error upserting project %s: %s", project_name, e)
            continue

        # UPSERT steps
        for step in project_steps:
            clean_title = clean_instruction_title(step["name"])
            log.info("--step id: %s", step["id"])
            is_completed_now = (
                step.get("detection_status", False)
                and step.get("isProjectLoaded", False)
            )
                
            try:
                db_cur.execute("""
                    INSERT INTO public.product_module_instruction_step
                    (arkite_step_id, name, step_type, project_id, sequence, detection_status, is_project_loaded, is_completed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (arkite_step_id) DO UPDATE
                    SET
                        name = EXCLUDED.name,
                        step_type = EXCLUDED.step_type,
                        project_id = EXCLUDED.project_id,
                        sequence = EXCLUDED.sequence,
                        detection_status = EXCLUDED.detection_status,
                        is_project_loaded = EXCLUDED.is_project_loaded,
                        is_completed = public.product_module_instruction_step.is_completed
                                    OR (EXCLUDED.detection_status AND EXCLUDED.is_project_loaded);
                """, (
                    step["id"],
                    step["name"],
                    step["step_type"],
                    project_db_id,
                    step["sequence"],
                    step.get("detection_status", False),
                    step.get("isProjectLoaded", False),
                    step.get("detection_status", False) and step.get("isProjectLoaded", False)
                ))
                db_conn.commit()
            except Exception as e:
                db_conn.rollback()
                log.error("[DB] Error upserting step %s: %s", step["name"], e)
                continue

            try:
                db_cur.execute("""
                    INSERT INTO public.product_module_instruction
                    (step_id, title, sequence, project_id, detection_name, detection_id, detection_status, is_completed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (step_id) DO UPDATE
                    SET
                        title = EXCLUDED.title,
                        sequence = EXCLUDED.sequence,
                        project_id = EXCLUDED.project_id,
                        detection_name = EXCLUDED.detection_name,
                        detection_id = EXCLUDED.detection_id,
                        detection_status = EXCLUDED.detection_status,
                        is_completed = public.product_module_instruction.is_completed
                            OR EXCLUDED.is_completed;
                """, (
                    step["id"],
                    clean_title,
                    step["sequence"],
                    project_db_id,
                    step["detectionName"],
                    step["detectionId"],
                    step.get("detection_status", False),
                    is_completed_now
                ))
                db_conn.commit()
            except Exception as e:
                db_conn.rollback()
                log.error("[DB] Error upserting instruction %s: %s", step["name"], e)

        with active_project_timers_lock:
            if project_db_id not in active_project_timers:
                active_project_timers.add(project_db_id)
                threading.Thread(
                    target=track_project_time,
                    args=(project_db_id,),
                    daemon=True
                ).start()
    log.info("[DB] Processed %d projects from payload.", len(projects))

# =========================
# MQTT SETUP
# =========================
def setup_mqtt():
    global client
    client = mqtt.Client(client_id="mqtt-all-steps-upsert")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

# =========================
# MAIN
# =========================
def main():
    log.info("=== MQTT → All Steps Upsert ===")
    setup_mqtt()
    while True:
        time.sleep(3)  # idle loop every 3 seconds

if __name__ == "__main__":
    main()