import threading
import time
import logging

from bridge import main as bridge_main
from subscribe import main as subscribe_main

logging.basicConfig(level=logging.INFO)

def run_bridge():
    bridge_main()

def run_subscribe():
    subscribe_main()

if __name__ == "__main__":
    logging.info("Starting MQTT Arkite bridge + subscriber in one container")

    t1 = threading.Thread(target=run_bridge, daemon=True)
    t2 = threading.Thread(target=run_subscribe, daemon=True)

    t1.start()
    t2.start()

    # Keep container alive
    while True:
        time.sleep(3)
