# Home Assistant Light Cache Add-on

This custom Home Assistant add-on tracks and restores the states of MQTT-based lights in case of a power outage, using a UPS for power status detection. It ensures that light states are persisted while the UPS is on battery and are restored precisely when power returns.

## Features

- 🧠 Caches the state (`on` / `off`) of MQTT-controlled lights
- 🔌 Detects power state changes via MQTT-published UPS status
- 💡 Automatically restores light states when power is restored
- 🔁 Built-in retry logic for reliable state restoration
- 🔒 Supports secure MQTT with username/password authentication
- 📦 Minimal footprint — runs on a slim Python container

## How It Works

1. Listens to MQTT messages on the topic `light_state_cache/+` for light state changes.
2. Stores light state changes in a local SQLite database.
3. Monitors UPS status via MQTT topic `NUT/ups/status`:
   - On "On Battery", stops caching changes.
   - On "Online", restores all previously stored light states.
4. Sends restoration commands to Home Assistant using the Supervisor API.

## MQTT Topics

| Topic                  | Description                         |
|------------------------|-------------------------------------|
| `light_state_cache/+`  | Light state changes (`on` or `off`) |
| `NUT/ups/status`       | UPS status (`Online`, `On Battery`) |

## Configuration

The following options are available in the add-on’s UI or `config.json`:

```json
{
  "mqtt_username": "your_mqtt_username",
  "mqtt_password": "your_mqtt_password"
}
