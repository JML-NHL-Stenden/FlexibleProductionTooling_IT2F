# mqtt_publish/publisher.py
import os
import json
import time
import logging
import hashlib
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.extras


# =========================
# Environment / Config
# =========================
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Topics
MQTT_TOPIC_CODES = os.getenv("MQTT_TOPIC_CODES", "factory/products/all_product_codes")
# NOTE: This topic publishes data GROUPED BY CATEGORY
MQTT_TOPIC_DETAILS = os.getenv("MQTT_TOPIC_DETAILS", "factory/products/all_product_details")
# Arkite QR trigger topic
MQTT_TOPIC_QR = os.getenv("MQTT_TOPIC_QR", "arkite/trigger/QR")

# Pretty JSON output (set PRETTY_JSON=true for indented payloads)
PRETTY_JSON = os.getenv("PRETTY_JSON", "false").lower() in ("1", "true", "yes", "y")

# Base URL to expose Odoo images (optional)
# e.g. for in-Docker consumers: http://odoo:8069
#      for host/laptop tools:  http://localhost:8069
ODOO_BASE_URL = (os.getenv("ODOO_BASE_URL", "") or "").rstrip("/")

# DB
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "odoo")
DB_USER = os.getenv("DB_USER", "odoo")
DB_PASS = os.getenv("DB_PASS", "odoo")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "5"))  # seconds
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


# =========================
# Logging
# =========================
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s  [%(levelname)s]  %(message)s")
log = logging.getLogger("mqtt-publish-product-data")


# =========================
# MQTT Setup
# =========================
try:
    from paho.mqtt.client import CallbackAPIVersion
    mqtt_client = mqtt.Client(
        client_id="mqtt-publish-product-data",
        protocol=mqtt.MQTTv5,
        callback_api_version=CallbackAPIVersion.VERSION2,
    )
except Exception:
    mqtt_client = mqtt.Client(client_id="mqtt-publish-product-data", protocol=mqtt.MQTTv5)

mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()


# =========================
# DB Helpers
# =========================
def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


# =========================
# SQL (Codes)
# =========================
SQL_PRODUCT_CODES = """
SELECT DISTINCT product_code
FROM public.product_module_product
WHERE product_code IS NOT NULL AND product_code <> ''
ORDER BY product_code;
"""


# =========================
# SQL (Arkite QR mappings)
# =========================
# NOTE: only latest entry (by id) will be published
SQL_ARKITE_QR = """
SELECT
    ap.id,
    ap.product_name,
    ap.product_code,
    ap.qr_text
FROM public.product_module_arkite_project ap
JOIN public.product_module_product p
      ON p.id = ap.product_id
WHERE ap.product_name IS NOT NULL
  AND ap.qr_text IS NOT NULL
  AND ap.product_code IS NOT NULL
ORDER BY ap.id DESC
LIMIT 1;
"""


# =========================
# Auto-detect M2M relation table + columns
# =========================
def detect_m2m_table_and_cols():
    """
    Detects the Many2Many relation table between:
      - public.product_module_product
      - public.product_module_type
    and returns (full_table_name, left_col, right_col)
    where left_col is the 'type' FK and right_col is the 'product' FK.
    """
    candidates = [
        # most common default (table name order product → type)
        ("public.product_module_product_product_module_type_rel",
         "product_module_type_id", "product_module_product_id"),
        # same table but columns could be swapped depending on Odoo version
        ("public.product_module_product_product_module_type_rel",
         "product_module_product_id", "product_module_type_id"),
        # alternate naming (type → product)
        ("public.product_module_type_product_module_product_rel",
         "product_module_type_id", "product_module_product_id"),
        ("public.product_module_type_product_module_product_rel",
         "product_module_product_id", "product_module_type_id"),
    ]
    q_exist = """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema='public' AND table_name=%s
    """
    q_cols = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name=%s
    """
    with get_conn() as conn, conn.cursor() as cur:
        for t, c1, c2 in candidates:
            tname = t.split(".", 1)[1]
            cur.execute(q_exist, (tname,))
            if cur.fetchone():
                cur.execute(q_cols, (tname,))
                cols = {r[0] for r in cur.fetchall()}
                if c1 in cols and c2 in cols:
                    log.info("Detected M2M table: %s (cols: %s, %s)", t, c1, c2)
                    # Normalize: LEFT = type FK, RIGHT = product FK
                    if "type_id" in c1 and "product_id" in c2:
                        return t, c1, c2
                    else:
                        return t, c2, c1
    # Fallback to most common default
    log.warning("M2M auto-detect failed; using default guess.")
    return ("public.product_module_product_product_module_type_rel",
            "product_module_type_id", "product_module_product_id")


# =========================
# SQL (Grouped by Category) – built after M2M detection
# =========================
def build_sql_by_category(m2m_rel_table: str, left_col: str, right_col: str) -> str:
    return f"""
WITH att AS (
    SELECT DISTINCT ON (res_id)
        res_id,
        id AS attachment_id
    FROM public.ir_attachment
    WHERE res_model = 'product_module.instruction'
      AND res_field = 'image'
    ORDER BY res_id, id DESC
),
base AS (
    SELECT
        p.id,
        p.name,
        p.product_code,
        i.id            AS instr_id,
        i.sequence      AS instr_sequence,
        i.title         AS instr_title,
        i.description   AS instr_description,
        CASE
            WHEN %(odoo_base_url)s <> '' AND a.attachment_id IS NOT NULL THEN
                %(odoo_base_url)s || '/web/image/' || a.attachment_id::text
            WHEN %(odoo_base_url)s <> '' AND i.id IS NOT NULL THEN
                %(odoo_base_url)s || '/web/image/product_module.instruction/' || i.id::text || '/image'
            ELSE NULL
        END AS instr_image_url
    FROM public.product_module_product p
    LEFT JOIN public.product_module_instruction i
        ON i.product_id = p.id
    LEFT JOIN att a
        ON a.res_id = i.id
    WHERE p.product_code IS NOT NULL AND p.product_code <> ''
),
prod_details AS (
    SELECT
        b.id,
        b.name,
        b.product_code,
        COALESCE(
            json_agg(
                json_build_object(
                    'sequence', b.instr_sequence,
                    'title', b.instr_title,
                    'description', b.instr_description,
                    'image_url', b.instr_image_url
                )
                ORDER BY b.instr_sequence, b.instr_id
            ) FILTER (WHERE b.instr_id IS NOT NULL),
            '[]'::json
        ) AS instructions
    FROM base b
    GROUP BY b.id, b.name, b.product_code
)
SELECT
    t.id        AS category_id,
    t.name      AS category_name,
    COALESCE(
        json_agg(
            json_build_object(
                'id', pd.id,
                'name', pd.name,
                'product_code', pd.product_code,
                'qr_text', pd.product_code,
                'instructions', pd.instructions
            )
            ORDER BY pd.product_code
        ) FILTER (WHERE pd.id IS NOT NULL),
        '[]'::json
    ) AS products
FROM public.product_module_type t
LEFT JOIN {m2m_rel_table} rel
    ON rel.{left_col} = t.id
LEFT JOIN prod_details pd
    ON pd.id = rel.{right_col}
GROUP BY t.id, t.name
ORDER BY t.name;
"""


# =========================
# Fetchers
# =========================
def fetch_product_codes():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(SQL_PRODUCT_CODES)
        rows = cur.fetchall()
        return [r["product_code"] for r in rows]


def fetch_details_grouped_by_category():
    m2m_rel_table, left_col, right_col = detect_m2m_table_and_cols()
    sql = build_sql_by_category(m2m_rel_table, left_col, right_col)
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, {"odoo_base_url": ODOO_BASE_URL})
        rows = cur.fetchall()
        categories = []
        for r in rows:
            categories.append(
                {
                    "category_id": r["category_id"],
                    "category_name": r["category_name"],
                    "products": r["products"],  # list of product objects
                }
            )
        return categories


def fetch_arkite_qr_rows():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(SQL_ARKITE_QR)
        return cur.fetchall()


def delete_arkite_qr_rows(row_ids):
    """Delete Arkite QR rows by id after publishing."""
    if not row_ids:
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public.product_module_arkite_project WHERE id = ANY(%s)",
            (row_ids,),
        )
        log.info("Deleted %d Arkite QR rows from DB", cur.rowcount)


# =========================
# Payload Builders
# =========================
def payload_for_codes(codes):
    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "count": len(codes),
        "product_codes": codes,
        "source": {"db": DB_NAME, "table": "public.product_module_product"},
    }


def payload_for_details_grouped(categories):
    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "count": len(categories),
        "categories": categories,
        "fields": ["category_id", "category_name", "products[*]"],
        "source": {
            "db": DB_NAME,
            "tables": [
                "public.product_module_type",
                "public.product_module_product",
                "public.product_module_instruction",
                # M2M rel table name is runtime-detected; included as info below
            ],
        },
        "odoo_base_url": ODOO_BASE_URL or None,
    }


def payload_for_arkite_qr(rows):
    items = []
    for r in rows:
        items.append(
            {
                "product_name": r["product_name"],
                "product_code": r["product_code"],
                "qr_text": r["qr_text"],
            }
        )
    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "count": len(items),
        "items": items,
        "source": {"db": DB_NAME, "table": "public.product_module_arkite_project"},
    }


# =========================
# Hashing (avoid republishing unchanged data)
# =========================
def hash_strings(items):
    m = hashlib.sha256()
    for c in items:
        m.update((c or "").encode("utf-8"))
        m.update(b"\x00")
    return m.hexdigest()


def hash_categories(items):
    m = hashlib.sha256()
    for cat in items:
        m.update(str(cat.get("category_id")).encode("utf-8"))
        m.update(b"\x1e")
        m.update((cat.get("category_name") or "").encode("utf-8"))
        m.update(b"\x1f")
        m.update(json.dumps(cat.get("products") or [], separators=(",", ":"), sort_keys=True).encode("utf-8"))
        m.update(b"\x00")
    return m.hexdigest()


# =========================
# Helpers
# =========================
def dumps(payload):
    if PRETTY_JSON:
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


# =========================
# Main Publisher Loop
# =========================
def publish_all_product_data():
    last_hash_codes = None
    last_hash_details = None
    ci_mode = os.getenv("CI") == "true" or "--dry-run" in os.sys.argv

    while True:
        try:
            # 1) Codes-only topic
            codes = fetch_product_codes()
            h_codes = hash_strings(codes)
            if h_codes != last_hash_codes:
                mqtt_client.publish(MQTT_TOPIC_CODES, dumps(payload_for_codes(codes)), qos=1, retain=True)
                log.info("Published %d product codes to '%s'", len(codes), MQTT_TOPIC_CODES)
                last_hash_codes = h_codes
            else:
                log.debug("No change in product codes; skipping publish.")

            # 2) Details topic (GROUPED BY CATEGORY)
            categories = fetch_details_grouped_by_category()
            h_details = hash_categories(categories)
            if h_details != last_hash_details:
                mqtt_client.publish(
                    MQTT_TOPIC_DETAILS,
                    dumps(payload_for_details_grouped(categories)),
                    qos=1,
                    retain=True,
                )
                log.info(
                    "Published %d categories (grouped details) to '%s'",
                    len(categories),
                    MQTT_TOPIC_DETAILS,
                )
                last_hash_details = h_details
            else:
                log.debug("No change in grouped details; skipping publish.")

            # 3) Arkite QR mappings topic (name + QR code) – publish latest and delete
            arkite_rows = fetch_arkite_qr_rows()
            if arkite_rows:
                mqtt_client.publish(
                    MQTT_TOPIC_QR,
                    dumps(payload_for_arkite_qr(arkite_rows)),
                    qos=1,
                    retain=True,  # keep last QR on broker even after DB delete
                )
                log.info(
                    "Published %d Arkite QR entries to '%s'",
                    len(arkite_rows),
                    MQTT_TOPIC_QR,
                )
                delete_arkite_qr_rows([r["id"] for r in arkite_rows])
            else:
                log.debug("No Arkite QR entries to publish.")

        except Exception as e:
            log.error("Error while publishing product data: %s", e, exc_info=True)

        if ci_mode:
            log.info("CI/dry-run mode: exiting after one iteration")
            break

        time.sleep(CHECK_INTERVAL)


# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    publish_all_product_data()
