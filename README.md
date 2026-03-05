# Tapo Home Assistant Integration

Home Assistant custom component for TP-Link Tapo devices, with support for S200B and S200D smart button sensors and button press/rotation events.

## Features

- ✅ Support for Tapo S200B and S200D smart button devices
- ✅ **Button click detection** - Detects single and double clicks
- ✅ **Rotation detection** - Detects left and right rotations with degrees
- ✅ **Multiple device support** - Supports multiple S200B/S200D devices on the same hub
- ✅ Battery status monitoring
- ✅ Device information sensors (model, firmware version, MAC address, signal strength, etc.)
- ✅ Local polling (no cloud required)
- ✅ Home Assistant events for button presses and rotations
- ✅ Near real-time event detection (1 second polling)

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Supported Devices](#supported-devices)
- [Sensors](#sensors)
- [Button Events](#button-events)
- [Rotation Events](#rotation-events)
- [Automations](#automations)
- [Troubleshooting](#troubleshooting)
- [Requirements](#requirements)
- [Credits](#credits)

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Tapo" from HACS
3. Restart Home Assistant
4. Add the integration via Settings > Devices & Services

### Manual Installation

1. Copy the `custom_components/tapo` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration via Settings > Devices & Services

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **"Add Integration"**
3. Search for **"Tapo"**
4. Enter your Tapo account credentials:
   - **Username**: Your Tapo account email/username (case-sensitive)
   - **Password**: Your Tapo account password (case-sensitive)
   - **Host**: IP address of your Tapo Hub (H100) - S200B/S200D devices are connected via the hub

**Important Notes**:
- The IP address should be your **Tapo Hub (H100)**, not the S200B/S200D device itself
- S200B/S200D devices communicate through the hub
- Use the exact credentials from your Tapo app (case-sensitive)
- Make sure your Home Assistant instance can reach the hub on your local network

## Supported Devices

- **S200B/S200D Smart Button**
  - Supports multiple S200B/S200D devices connected to the same hub
  - Each device gets its own sensors and button event detection
  - Each device is identified by its unique `device_id`

## Sensors

Each S200B/S200D device creates the following sensors:

### Device Information Sensors
- **Battery** - Battery percentage (0-100%)
- **Battery Low** - Boolean indicating low battery status
- **Low Battery Warning** - Additional battery warning indicator
- **Model** - Device model information
- **Firmware Version** - Current firmware version
- **Hardware Version** - Hardware version
- **Nickname** - Device nickname (as configured in Tapo app)
- **MAC Address** - Device MAC address
- **Device ID** - Unique device identifier
- **Signal Strength (RSSI)** - Signal strength in dBm
- **Signal Level** - Signal level indicator

### Event Sensor
- **Last Button Press** - Shows the last event type (Single Click, Double Click, Rotate Left, Rotate Right)
  - Attributes include:
    - `last_event_time` - ISO timestamp of last event
    - `last_event_time_readable` - Human-readable timestamp
    - `last_event_id` - Unique event ID
    - `last_event_type` - Type of event
    - `last_rotation_degrees` - (for rotations) Rotation angle
    - `last_rotation_direction` - (for rotations) Rotation direction

## Button Events

The integration detects button clicks and rotations by polling the trigger logs from the S200B/S200D device every **1 second**. When a button is pressed or rotated, a Home Assistant event `tapo_button_pressed` is fired.

### Event Data Structure

All events include:
- `click_type`: Type of event (`single_click`, `double_click`, `rotate_left`, or `rotate_right`)
- `event_id`: Unique ID of the event
- `timestamp`: Unix timestamp of when the button was pressed/rotated
- `device_id`: Device identifier (allows distinguishing between multiple S200B/S200D devices)

Rotation events additionally include:
- `rotation_degrees`: Absolute value of rotation angle (typically 30° per step)
- `direction`: `left` or `right`

### Event Types

| Event Type | Description | Use Case |
|------------|-------------|----------|
| `single_click` | Single button press | Toggle lights, activate scenes |
| `double_click` | Double button press | Activate different scenes, turn off devices |
| `rotate_left` | Counterclockwise rotation | Decrease brightness, volume, temperature |
| `rotate_right` | Clockwise rotation | Increase brightness, volume, temperature |

## Rotation Events

The S200B/S200D button supports rotation events. Each rotation step is typically **30 degrees**.

**Rotation Direction**:
- Positive `rotation_degrees` (e.g., 30) → `rotate_right` (clockwise)
- Negative `rotation_degrees` (e.g., -30) → `rotate_left` (counterclockwise)

### Rotation Event Data

```python
{
    "click_type": "rotate_right",
    "rotation_degrees": 30,
    "direction": "right",
    "device_id": "802E0306A957EED2F9D6EB95824684E2244955F2",
    "event_id": 687,
    "timestamp": 1768607629
}
```

## Automations

### Basic Click Examples

```yaml
automation:
  - alias: "Tapo Single Click - Toggle Light"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: single_click
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room
    mode: single

  - alias: "Tapo Double Click - Activate Scene"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: double_click
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.evening_mode
    mode: single
```

### Device-Specific Examples

```yaml
automation:
  - alias: "Tapo Bouton Salon - Single Click"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: single_click
          device_id: "802E0306A957EED2F9D6EB95824684E2244955F2"  # Your device ID
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room
    mode: single
```

### Rotation Examples

```yaml
automation:
  - alias: "Tapo Rotate Right - Increase Brightness"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: rotate_right
    action:
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          brightness_step: 25
    mode: single

  - alias: "Tapo Rotate Left - Decrease Brightness"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: rotate_left
    action:
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          brightness_step: -25
    mode: single
```

### Complete Control Example

```yaml
automation:
  - alias: "Tapo Complete Light Control"
    description: "Single click toggles, double click turns off, rotate adjusts brightness"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.click_type == 'single_click' }}"
            sequence:
              - service: light.toggle
                target:
                  entity_id: light.living_room
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.click_type == 'double_click' }}"
            sequence:
              - service: light.turn_off
                target:
                  entity_id: light.living_room
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.click_type == 'rotate_right' }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.living_room
                data:
                  brightness_step: 25
          - conditions:
              - condition: template
                value_template: "{{ trigger.event.data.click_type == 'rotate_left' }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.living_room
                data:
                  brightness_step: -25
    mode: single
```

### Finding Your Device ID

To find your device ID for device-specific automations:

1. Go to **Developer Tools** > **Events**
2. In **"Listen to events"**, type: `tapo_button_pressed`
3. Click **"Start Listening"**
4. Press your S200B/S200D button
5. You'll see the event with the `device_id` in the event data

Alternatively, check the attributes of the "Last Button Press" sensor for your device in **Settings** > **Devices & Services**.

### More Examples

For comprehensive automation examples covering all event types and use cases, see [examples/automations.yaml](examples/automations.yaml).

## Troubleshooting

### Authentication Issues

If you encounter `HASH_MISMATCH` or authentication errors:

1. **Verify credentials**: Make sure your username and password are correct (case-sensitive)
2. **Check account type**: Use your Tapo account email (not TP-Link account)
3. **Network connectivity**: Ensure Home Assistant can reach the hub on your local network
4. **Disconnect other devices**: Try disconnecting other TP-Link/Tapo devices from the network temporarily
5. **Hub reset**: As a last resort, try factory resetting the hub

### No Events Detected

If button presses/rotations are not detected:

1. **Check sensor**: Verify the "Last Button Press" sensor updates when you press the button
2. **Check logs**: Enable debug logging and check for errors:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.tapo: debug
   ```
3. **Verify device pairing**: Ensure the S200B/S200D is properly paired with the hub in the Tapo app
4. **Check polling**: Events are polled every 1 second, so there may be a slight delay

### Multiple Devices Not Detected

If you have multiple S200B/S200D devices but only one is detected:

1. **Check hub**: Ensure all devices are properly paired with the hub
2. **Restart integration**: Reload the Tapo integration in Home Assistant
3. **Check logs**: Look for warnings about missing child devices

### Performance

- **Polling frequency**: Events are polled every 1 second per device
- **Network load**: Each device generates 1 request per second to the hub
- **Recommendation**: For setups with many devices (5+), consider increasing the polling interval if needed

## Requirements

- Home Assistant 2023.1 or later
- Tapo Python library (installed automatically via `requirements`)
- Tapo Hub (H100) with S200B/S200D devices paired
- Local network access to the Tapo Hub

## Technical Details

### Polling Intervals

- **Button events**: 1 second (configurable in `button.py`)
- **Sensor data**: 60 seconds (configurable in `sensor.py`)

### Event Detection

The integration uses the `get_trigger_logs()` API method to poll for new events. Events are detected by comparing log IDs - new events have higher IDs than previously processed events.

### Supported Event Types

- `SingleClick` → `single_click`
- `DoubleClick` → `double_click`
- `Rotation` (with `rotation_degrees`) → `rotate_left` or `rotate_right`

## Credits

Uses the [tapo](https://github.com/mihai-dinculescu/tapo) library by mihai-dinculescu.

## License

This integration is provided as-is for use with Home Assistant.
