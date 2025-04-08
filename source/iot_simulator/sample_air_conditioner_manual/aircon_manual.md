# Air Conditioner Instruction Manual

## Table of Contents

1. **Introduction**
2. **System Overview**
3. **Hardware & Software Requirements**
4. **Installation & Setup**
5. **Operational Modes**
6. **Telemetry & Data Points**
7. **Command & Control**
8. **Fault Codes & Troubleshooting**
9. **Maintenance & Filter Management**
10. **Runtime & Behavior**
11. **MQTT Communication Topics**
12. **Shadow Updates**
13. **FAQ & Best Practices**
14. **Reference: Simulator Code Summary**

* * *

## 1. Introduction

## This document describes the operation and maintenance of the **MQTT-based Air Conditioner simulator**. It is intended for technicians responsible for:

* Deploying and configuring the AC simulator to publish real-time telemetry to AWS IoT Core.
* Monitoring and troubleshooting the AC unit’s performance.
* Injecting and resolving various faults or simulated errors.
* Managing device runtime and filter status.

>**Note**: This manual applies to a simulated air conditioner. However, the structure and procedures closely mimic those of a real-world IoT-enabled AC unit for training and testing purposes.

* * *

## 2. System Overview

## The simulated AC system is an IoT device that:

* Connects securely to an AWS IoT endpoint via MQTT.
* Publishes telemetry data (e.g., temperatures, humidity, pressure).
* Receives commands to change operating parameters (e.g., setpoint temperature, operational mode).
* Reports device shadow updates to keep AWS IoT in sync with the AC unit’s state.

### Key Features

* **Indoor & Outdoor Temperature/Humidity** measurements.
* **Setpoint Temperature** control.
* **Compressor** on/off simulation based on setpoint requirements.
* **Fan Speed** adjustments (in RPM).
* **Refrigerant Pressure** monitoring.
* **Power Consumption** estimates in watts.
* **Injectable Faults** for testing troubleshooting procedures.
* **Device Shadow** updates for remote state synchronization.

* * *

## 3. Hardware & Software Requirements

1. **AWS IoT Account**: An active AWS account configured to accept MQTT connections for IoT devices.
2. **Python Environment**: Python 3.7+ installed.
3. **AWS IoT SDK for Python**: Required libraries (specifically `AWSIoTPythonSDK`).
4. **Certificates and Keys**:

    * **Root CA (AmazonRootCA1.pem)**
    * **Private Key** (`<device_name>-private.pem.key`)
    * **Certificate** (`<device_name>-certificate.pem.crt`)

1. **Device Information File**: `device_info.json` containing:

```
json
Copy
{
"thingName": "your_device_name",
"endpoint": "your_aws_iot_endpoint",
"rootCAPath": "/path/to/AmazonRootCA1.pem"
}

```

1. **Internet Connectivity**: Required for publishing telemetry and subscribing to commands.

* * *

## 4. Installation & Setup

1. **Organize Certificates**:
    Place the **private key** and **certificate** files in the same directory as the `device_info.json` file for each device.
2. **Update `device_info.json`**:
    Ensure the following keys and values are correct:

    * `thingName`: The name registered in AWS IoT.
    * `endpoint`: The AWS IoT endpoint URL for your region.
    * `rootCAPath`: The full path to the Amazon Root CA file.

1. **Download the Root CA (If Not Present)**:
    If the root CA file is missing, the simulator will attempt to automatically download it from:

```
arduino
Copy
https://www.amazontrust.com/repository/AmazonRootCA1.pem

```

1. **Run the Simulator**:

```
bash
Copy
python ac_simulator.py --devices-folder devices --device-name <DEVICE_NAME> --topic aircon/telemetry --interval 10
```

    * `--devices-folder`: Path to the folder containing the individual device folder(s).
    * `--device-name`: (Optional) The specific device folder name to run. If not specified, simulator runs for all found devices.
    * `--topic`: MQTT topic for telemetry publishing (default: `aircon/telemetry`).
    * `--interval`: Time in seconds between telemetry publishes (default: 10).

* * *

## 5. Operational Modes

## The simulator supports three operational modes:

1. **Cool**:

    * Compressor cycles on/off to maintain the **setpoint temperature**.
    * Fan runs when the compressor is active to circulate cool air.

1. **Fan Only**:

    * Compressor remains off.
    * Fan spins at a consistent RPM to provide ventilation.

1. **Off**:

    * Compressor and fan remain off.
    * The indoor temperature gradually approaches the outdoor temperature.

>**Mode** transitions can be triggered via a device shadow update (See Section 12) or by publishing a command message to the command topic.

* * *

## 6. Telemetry & Data Points

## Every **interval** seconds, the AC unit generates and publishes the following telemetry data:

|Field	|Description	|Example	|
|---	|---	|---	|
|`device_name`	|Name of the AC unit (thing name).	|`"ACUnit1"`	|
|---	|---	|---	|
|`indoor_temperature_c`	|Current indoor temperature (°C).	|24	|
|`outdoor_temperature_c`	|Current outdoor temperature (°C).	|30	|
|`setpoint_temperature_c`	|Desired target indoor temperature (°C).	|23	|
|`mode`	|Current operational mode. (`cool`, `fan_only`, or `off`)	|`"cool"`	|
|`indoor_humidity_percent`	|Current indoor humidity (%).	|45	|
|`outdoor_humidity_percent`	|Current outdoor humidity (%).	|70	|
|`power_consumption_watts`	|Real-time power usage in watts.	|2100.54	|
|`compressor_status`	|Status of compressor (`On` or `Off`).	|`"On"`	|
|`fan_speed_rpm`	|Fan speed in rotations per minute (RPM).	|1200.57	|
|`refrigerant_pressure_psi`	|Current refrigerant pressure in PSI.	|198.75	|
|`error_code`	|Current error/fault code.	|`"None"` or `"E1"`	|
|`filter_status`	|Current state of the air filter (`Clean`, `Needs Cleaning`, `Replace`).	|`"Clean"`	|
|`runtime_hours`	|Total operational hours since last reset.	|10.5	|

* * *

## 7. Command & Control

## Commands can be published to the **command topic**:

```
bash
Copy
aircon/commands/<device_name>
```

Each command is a JSON payload with an `action` field (and optional parameters). For example:

|Action	|JSON Payload Example	|Description	|
|---	|---	|---	|
|`inject_fault`	|`{"action": "inject_fault", "fault_type": "high_temperature"}`	|Injects a fault into the system. Supported `fault_type` values: `high_temperature`, `low_pressure`, `compressor_failure`.	|
|---	|---	|---	|
|`clear_fault`	|`{"action": "clear_fault"}`	|Clears any active faults and resets the error code to `"None"`.	|
|`update_filter_status`	|`{"action": "update_filter_status", "filter_status": "Needs Cleaning"}`	|Updates the filter status to one of: `Clean`, `Needs Cleaning`, or `Replace`.	|
|`reset_runtime`	|`{"action": "reset_runtime"}`	|Resets the runtime counter (`runtime_hours`) to `0`.	|
|`disconnect`	|`{"action": "disconnect"}`	|Instructs the simulator to disconnect from MQTT and terminate.	|

* * *

## 8. Fault Codes & Troubleshooting

## During normal operation, `error_code` remains `"None"`. The following fault types may be injected to simulate errors:

|Fault Type	|Internal Effect	|Error Code	|Troubleshooting Steps	|
|---	|---	|---	|---	|
|`high_temperature`	|Indoor temperature increases drastically by 5 to 10 °C.	|`E1`	|1. Check compressor functionality. <br/>2. Verify refrigerant pressure. <br/>3. Inspect the filter and ensure proper airflow.	|
|---	|---	|---	|---	|
|`low_pressure`	|Refrigerant pressure drops toward the lower threshold (`50 – 60 PSI`).	|`E2`	|1. Check for refrigerant leaks. <br/>2. Verify correct refrigerant charge. <br/>3. Inspect compressor for abnormal sounds or vibrations.	|
|`compressor_failure`	|Compressor stays off, power consumption drops to 0.	|`E3`	|1. Verify power supply to compressor. <br/>2. Check compressor windings/resistance. <br/>3. Test capacitor and relay.	|

### Clearing Faults

### To clear any active fault:

```
json
Copy
{"action": "clear_fault"}

```

This resets `error_code` to `"None"` and returns normal operation.
* * *

## 9. Maintenance & Filter Management

1. **Filter Status Values**:

    * **Clean**: Filter is new or recently maintained.
    * **Needs Cleaning**: Filter has reached recommended runtime hours.
    * **Replace**: Filter is no longer effective and needs replacement.

1. **Auto-Update Mechanism**:
    When the simulator’s `runtime_hours` surpasses 500 hours, the filter status automatically changes from `"Clean"` to `"Needs Cleaning"`. Technicians can manually override by publishing:

```
json
Copy
{
"action": "update_filter_status",
"filter_status": "Replace"
}

```

1. **Runtime Reset**:
    After cleaning or replacing the filter, you may reset the operational hours to zero by publishing:

```
json
Copy
{"action": "reset_runtime"}

```

* * *

## 10. Runtime & Behavior

* Every **telemetry interval** (default: 10 seconds), the AC updates internal calculations:
    * **Runtime Hours**: Increases based on elapsed time (`interval / 3600`).
    * **Indoor Temperature**: Adjusts toward setpoint if compressor is on; otherwise drifts towards outdoor temperature.
    * **Outdoor Temperature**: Varies slightly by ±1 °C periodically.
    * **Power Consumption**:
        * Ranges from **0 W** (off) to around **2000+ W** with compressor under load.
        * **Fan Only** mode consumes around **200 W**.
        * Idle consumes **100 W**.
    * **Refrigerant Pressure**: Random fluctuations within realistic bounds (50–300 PSI).

* * *

## 11. MQTT Communication Topics

1. **Telemetry Publish Topic** (default: `aircon/telemetry`):

    * Simulator publishes AC data at regular intervals.

1. **Command Topic** (`aircon/commands/<device_name>`):

    * Simulator subscribes to commands for controlling or injecting faults.

1. **Device Shadow**:

    * **Shadow Delta Topic**: `$aws/things/<device_name>/shadow/update/delta`
    * **Shadow Update Topic**: `$aws/things/<device_name>/shadow/update`

* * *

## 12. Shadow Updates

## The AC simulator integrates with the AWS IoT Device Shadow. When the device receives a **delta** message, it updates its internal state accordingly. Currently, the simulator listens for:

1. **Setpoint Temperature** (`setpoint_temperature_c`)
2. **Mode** (can be `cool`, `off`, or `fan_only`)

Example **delta message**:

```
json
Copy
{
"state": {
"setpoint_temperature_c": 22,
"mode": "fan_only"
}
}

```

Upon receiving this:

* The simulator changes its setpoint to `22 °C`.
* Sets the mode to `"fan_only"`.
* **Reports** new state back via the shadow **update** topic, which can be viewed in AWS IoT console or consumed by other services.

* * *

## 13. FAQ & Best Practices

1. **How do I simulate a specific error without waiting?**

    * Publish a JSON command with `"action": "inject_fault"` and specify the `fault_type`.

1. **Why does the indoor temperature not reach the setpoint immediately?**

    * The simulator includes a natural drift and a realistic cooling rate. Indoor temperature changes gradually based on the difference between indoor/outdoor temperatures and the setpoint.

1. **Can I run multiple units simultaneously?**

    * Yes, place multiple device folders (each with its own `device_info.json` and certificates) under the `devices` directory. The script starts each device in a separate thread.

1. **What happens if I set the mode to `off` while a fault is injected?**

    * The AC simulator respects the operational mode (i.e., compressor remains off), but the injected fault remains active until you clear it or it times out (in real scenarios). In the simulator, you must explicitly clear it.

* * *

## 14. Reference: Simulator Code Summary

## The core simulator logic (in `ACUnitSimulator`) handles:

* **Initialization**: Loads configuration, sets initial random values for temperature/humidity, and subscribes to command/shadow topics.
* **Command Processing** (`on_command_received`): Handles injected faults, resetting runtime, updating filter status, or disconnect instructions.
* **Shadow Delta Processing** (`on_shadow_delta`): Updates the setpoint temperature or operational mode, then reports back to the shadow.
* **Telemetry Generation** (`generate_telemetry_data`):
    * Applies temperature, humidity, and pressure logic.
    * Adjusts compressor and fan statuses.
    * Injects faults if instructed.
    * Publishes data to the telemetry topic.
* **Execution Loop** (`run`): Continuously publishes telemetry at the specified interval until a disconnect command is received or the program is stopped.

