# Tapo Home Assistant Integration

Home Assistant custom component for TP-Link Tapo devices, with support for S200B smart button sensors.

## Features

- Support for Tapo S200B smart button devices
- **Button click detection** - Detects single and double clicks
- Battery status monitoring
- Device information sensors (model, firmware version, MAC address, etc.)
- Local polling (no cloud required)
- Home Assistant events for button presses

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

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Tapo"
4. Enter your Tapo account credentials:
   - Username: Your Tapo account email/username
   - Password: Your Tapo account password
   - Host: IP address of your Tapo Hub (H100) - S200B devices are connected via the hub

## Supported Devices

- S200B Smart Button
  - Supports multiple S200B devices connected to the same hub
  - Each device gets its own sensors and button event detection

## Requirements

- Home Assistant 2023.1 or later
- Tapo Python library (installed automatically)

## Button Click and Rotation Detection

The integration detects button clicks and rotations by polling the trigger logs from the S200B device. When a button is pressed or rotated:

1. **Home Assistant Event**: An event `tapo_button_pressed` is fired with:
   - `click_type`: `single_click`, `double_click`, `rotate_left`, `rotate_right`, or `rotate_left_<angle>`, `rotate_right_<angle>` (if angle is available)
   - `event_id`: Unique ID of the event
   - `timestamp`: Unix timestamp of when the button was pressed/rotated
   - `device_id`: Device identifier (allows distinguishing between multiple S200B devices)
   - `angle` or `steps` or `value`: (optional) Rotation angle/steps if available

2. **Sensor**: Each S200B device has a sensor showing the last event type (named after the device nickname, e.g., "Bouton Salon Last Button Press") and includes:
   - Last event time (ISO format and readable format)
   - Last event ID
   - Last event type (click or rotation)
   - Last rotation degrees and direction (for rotation events)

### Using Button Events in Automations

You can create automations triggered by button presses:

```yaml
automation:
  - alias: "Single Click Action (All Devices)"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: single_click
    action:
      - service: light.toggle
        target:
          entity_id: light.example

  - alias: "Single Click Action (Specific Device)"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: single_click
          device_id: "802E0306A957EED2F9D6EB95824684E2244955F2"  # Your device ID
    action:
      - service: light.toggle
        target:
          entity_id: light.example

  - alias: "Double Click Action"
    trigger:
      - platform: event
        event_type: tapo_button_pressed
        event_data:
          click_type: double_click
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.example
```

## Rotation Events

The S200B button supports rotation events. If rotation events are available in the trigger logs, they will be detected and fired as `tapo_button_pressed` events with:
- `click_type`: `rotate_left` or `rotate_right`
- Additional data: `angle`, `steps`, or `value` (if available)

**Note**: Rotation events depend on the device firmware and may not be available in all trigger logs. If you don't see rotation events, they may not be supported by your device firmware version.

## Notes

The integration polls trigger logs every 1 second to detect button presses and rotations. This provides near real-time detection of single clicks, double clicks, and rotation events.

## Credits

Uses the [tapo](https://github.com/mihai-dinculescu/tapo) library by mihai-dinculescu.

