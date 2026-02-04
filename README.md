# CardDAV Birthdays for Home Assistant

This Home Assistant integration connects to a CardDAV server to create sensors for contacts with birthday information. It is designed for users who self-host their address book (e.g., using Radicale) and want to trigger automations based on upcoming birthdays.

## Requirements

*   A CardDAV server (tested with Radicale).
*   Contacts must have a valid `BDAY` property in their vCard data.

## Installation

1.  Copy the `custom_components/carddav_birthdays` directory to your Home Assistant `config/custom_components/` directory.
2.  Restart Home Assistant.
3.  Navigate to **Settings > Devices & Services > Add Integration**.
4.  Search for **CardDAV Birthdays** and select it.
5.  Enter your CardDAV server URL and credentials.

## Features

### Sensors

*   **Per-Contact Sensor**: Creates a sensor for each contact (e.g., `sensor.john_doe_birthday`). The state is the date of their next birthday. Attributes include current age and original birthdate.
*   **Global Sensor**: Creates a single `sensor.next_birthday` entity that tracks the soonest upcoming birthday across all contacts.

### Automation Example

You can use the global sensor to send notifications.

```yaml
alias: "Birthday Notification"
description: "Send a notification at 09:00 if it is someone's birthday"
mode: single
trigger:
  - platform: time
    at: "09:00:00"
condition:
  - condition: template
    value_template: "{{ states('sensor.next_birthday') == now().date() | string }}"
action:
  - service: notify.mobile_app_your_device
    data:
      title: "Birthday Alert"
      message: >
        Today is the birthday of: {{ state_attr('sensor.next_birthday', 'names') | join(', ') }}. 
        Turning {{ state_attr('sensor.next_birthday', 'age_turning') }}.
```
