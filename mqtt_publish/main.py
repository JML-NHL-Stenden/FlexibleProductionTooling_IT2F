import threading
import time
import logging

from publish import publish_all_product_data as publish_main
from arkite_publish import main as arkite_publish_main

logging.basicConfig(level=logging.INFO)

def run_publish():
    publish_main()

def run_arkite_publish():
    arkite_publish_main()

if __name__ == "__main__":
    logging.info("Starting MQTT Arkite publish + DB publish in one container")

    t1 = threading.Thread(target=run_publish, daemon=True)
    t2 = threading.Thread(target=run_arkite_publish, daemon=True)
    t1.start()
    t2.start()

    # Keep container alive
    while True:
        time.sleep(3)
