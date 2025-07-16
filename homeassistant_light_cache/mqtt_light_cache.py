# mqtt_light_cache.py
import time
import os
import sqlite3
import threading
import json
import paho.mqtt.client as mqtt
import paho.mqtt
import requests
import sys
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


sys.stdout.reconfigure(line_buffering=True)
logging.info(f"Using paho-mqtt version: {paho.mqtt.__version__}")

MQTT_BROKER = "core-mosquitto"
MQTT_PORT = 1883
LIGHT_TOPIC = "light_state_cache/+"
NUT_TOPIC = "NUT/ups/status"
DB_FILE = "/config/light_state_cache.db"
STATE_CACHE = {}
UPS_ON_BATTERY = False
RESTORE_DONE = True

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS light_state (
                entity_id TEXT PRIMARY KEY,
                state TEXT,
                updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
conn.commit()

def save_state(entity_id, state):
    c.execute("REPLACE INTO light_state (entity_id, state) VALUES (?, ?)", (entity_id, state))
    conn.commit()

def restore_states(client):
    logging.info("Waiting 10 seconds to allow lights to connect to network...")
    time.sleep(10)
    logging.info("Restoring light states...")

    c.execute("SELECT entity_id, state FROM light_state")
    rows = c.fetchall()

    for entity_id, state in rows:
        retries = 0
        success = False
        while retries < 12:
            set_light_state(entity_id, state)
            logging.info(f"[RESTORE] Sent {state} to {entity_id}, attempt {retries+1}")
            success = True
            break
        if success:
            logging.info(f"[RESTORE] Success for {entity_id}")
        else:
            logging.info(f"[RESTORE] Timeout for {entity_id}")

    global RESTORE_DONE
    RESTORE_DONE = True

def on_message(client, userdata, msg):
    global UPS_ON_BATTERY, RESTORE_DONE

    logging.debug(f"Received MQTT message: topic={msg.topic}, payload={msg.payload.decode()}")

    topic = msg.topic
    payload = msg.payload.decode()

    if topic == NUT_TOPIC:
        if "OB" in payload:
            logging.info("[UPS] On battery")
            UPS_ON_BATTERY = True
            RESTORE_DONE = False
        elif "OL" in payload and UPS_ON_BATTERY:
            logging.info("[UPS] Power restored")
            UPS_ON_BATTERY = False
            threading.Thread(target=restore_states, args=(client,)).start()

    elif "light_state_cache/light" in topic:
        entity_id = topic.partition("light_state_cache/")[2]
        if not UPS_ON_BATTERY and RESTORE_DONE:
            save_state(entity_id, payload)
            logging.info(f"[MQTT] Saved state for {entity_id} = {payload}")

def on_connect(client, userdata, flags, rc, properties=None):
    logging.info(f"[MQTT] Connected with result code {rc}")
    client.subscribe(LIGHT_TOPIC)
    client.subscribe(NUT_TOPIC)

def set_light_state(entity_id, state):
    token = os.environ.get("SUPERVISOR_TOKEN")
    url = f"http://supervisor/core/api/services/light/turn_{state}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "entity_id": entity_id
    }

    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code != 200:
        logging.info(f"[ERROR] Failed to set {state} for {entity_id}: {resp.text}")
    else:
        logging.info(f"[RESTORE] Set {state} for {entity_id}")

def main():
    try:
        with open("/data/options.json") as f:
            opts = json.load(f)
            MQTT_USERNAME = opts.get("mqtt_username")
            MQTT_PASSWORD = opts.get("mqtt_password")
    except Exception as e:
        logging.error(f"Failed to read options.json: {e}")

    logging.debug("Creating MQTT client...")
    client = mqtt.Client()

    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    logging.debug("Connecting to MQTT broker...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        logging.error(f"MQTT connect failed: {e}")
        return

    logging.debug("Starting MQTT loop...")
    try:
        client.loop_forever()
    except Exception as e:
        logging.error(f"MQTT loop failed: {e}")

if __name__ == "__main__":
    main()
