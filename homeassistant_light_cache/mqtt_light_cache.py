# mqtt_light_cache.py
from datetime import datetime
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
import smtplib
from email.mime.text import MIMEText

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

sys.stdout.reconfigure(line_buffering=True)
logging.info(f"Using paho-mqtt version: {paho.mqtt.__version__}")

DB_FILE = "/data/light_state_cache.db"
STATE_CACHE = {}
UPS_ON_BATTERY = False
RESTORE_DONE = True

try:
    with open("/data/options.json") as f:
        opts = json.load(f)
        MQTT_BROKER = opts.get("mqtt_broker", "core-mosquitto")
        MQTT_PORT = opts.get("mqtt_port", 1883)
        MQTT_USERNAME = opts.get("mqtt_username")
        MQTT_PASSWORD = opts.get("mqtt_password")
        LIGHT_TOPIC = opts.get("light_topic", "light_state_cache/+")
        NUT_TOPIC = opts.get("nut_topic", "NUT/ups/status")
        SEND_EMAIL_ENABLED = opts.get('send_email', False)
        if SEND_EMAIL_ENABLED:
            FROM_EMAIL = opts.get('from_email', '')
            TO_EMAIL = opts.get('to_email', '')
            SMTP_SERVER = opts.get('smtp_server', '')
            SMTP_PORT = opts.get('smtp_port', '')
            SMTP_USER = opts.get('smtp_user', '')
            SMTP_PASSWORD = opts.get('smtp_password', '')
            
except Exception as e:
    logging.error(f"Failed to read options.json: {e}")

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

    global UPS_ON_BATTERY, RESTORE_DONE
    UPS_ON_BATTERY = False
    RESTORE_DONE = True

def on_message(client, userdata, msg):
    global UPS_ON_BATTERY, RESTORE_DONE

    logging.debug(f"Received MQTT message: topic={msg.topic}, payload={msg.payload.decode()}")

    topic = msg.topic
    payload = msg.payload.decode()

    if topic == NUT_TOPIC:
        if 'OB' in payload and not UPS_ON_BATTERY:  #Only handle going to battery once until no longer on battery to prevent charge status changes triggering another alert
            logging.info("[UPS] On battery")
            maybe_send_email('Power lost')
            UPS_ON_BATTERY = True
            RESTORE_DONE = False
        elif 'OL' in payload and UPS_ON_BATTERY:
            logging.info("[UPS] Power restored")
            maybe_send_email('Power restored')
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
        logging.error(f"Failed to set {state} for {entity_id}: {resp.text}")
    else:
        logging.info(f"[RESTORE] Set {state} for {entity_id}")

def maybe_send_email(body):
    try:
        if SEND_EMAIL_ENABLED:
            logging.info(f"Sending email notification to {TO_EMAIL}")
            now = datetime.now().astimezone()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
            msg = MIMEText(f"{timestamp} - {body}")
            msg['Subject'] = 'HomeAssistant Notification'
            msg['From'] = f"Home Assistant Notifications <{FROM_EMAIL}>"
            msg['To'] = TO_EMAIL
        
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def main():
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
