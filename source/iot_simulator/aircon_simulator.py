import sys
import time
import json
import random
import os
import threading
import urllib.request
import traceback
import csv
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

def download_root_ca(root_ca_path):
    url = 'https://www.amazontrust.com/repository/AmazonRootCA1.pem'
    try:
        print(f"Downloading Amazon Root CA certificate from {url}...")
        urllib.request.urlretrieve(url, root_ca_path)
        print(f"Downloaded Amazon Root CA certificate to {root_ca_path}")
    except Exception as e:
        print(f"Failed to download Root CA certificate: {e}")
        exit(1)

def create_mqtt_client(client_id, endpoint, root_ca_path, private_key_path, certificate_path):
    client = AWSIoTMQTTClient(client_id)
    client.configureEndpoint(endpoint, 8883)
    client.configureCredentials(root_ca_path, private_key_path, certificate_path)
    client.configureAutoReconnectBackoffTime(1, 32, 20)
    client.configureOfflinePublishQueueing(-1)
    client.configureDrainingFrequency(2)
    client.configureConnectDisconnectTimeout(5)
    client.configureMQTTOperationTimeout(5)
    return client

class ACUnitSimulator:
    MIN_PRESSURE_PSI = 50
    MAX_PRESSURE_PSI = 300

    def __init__(self, device_folder, device_name, mqtt_client, write_csv=False):
        self.device_folder = device_folder
        self.device_name = device_name
        self.mqtt_client = mqtt_client
        self.write_csv = write_csv

        # Version counter, starting at 1.
        self.version = 1.0

        # Telemetry parameters.
        # Indoor temperature now set between 12°C and 30°C.
        self.indoor_temperature_c = random.randint(12, 30)
        # Outdoor temperature now set between 22°C and 34°C.
        self.outdoor_temperature_c = random.randint(22, 34)
        # Set a target for outdoor temperature, which will update every 24 hours.
        self.target_outdoor_temperature_c = self.outdoor_temperature_c
        self.next_target_update_hours = 24

        self.setpoint_temperature_c = random.randint(23, 24)
        self.indoor_humidity_percent = random.randint(40, 60)
        self.outdoor_humidity_percent = random.randint(60, 80)
        self.power_consumption_watts = 0
        self.compressor_status = "Off"
        self.fan_speed_rpm = 0
        self.refrigerant_pressure_psi = random.randint(150, 250)
        self.error_code = "None"
        self.filter_status = "Clean"
        self.runtime_hours = 0
        self.mode = "cool"
        self.abnormal_wattage_mode = False

        self.inject_fault = False
        self.fault_type = None
        self.running = True
        self.lock = threading.Lock()
        self.last_error_code = "None"

        # Cache for the shadow state (only tracking selected keys)
        self.last_shadow_state = {}

        self.seconds_since_increase = 0

        # Subscribe to topics.
        command_topic = f"aircon/commands/{self.device_name}"
        try:
            self.mqtt_client.subscribe(command_topic, 1, self.on_command_received)
            print(f"[{self.device_name}] Subscribed to command topic: {command_topic}")
        except Exception as e:
            print(f"[{self.device_name}] Failed to subscribe to command topic: {e}")
            traceback.print_exc()

        delta_topic = f"$aws/things/{self.device_name}/shadow/update/delta"
        try:
            self.mqtt_client.subscribe(delta_topic, 1, self.on_shadow_delta)
            print(f"[{self.device_name}] Subscribed to shadow delta topic: {delta_topic}")
        except Exception as e:
            print(f"[{self.device_name}] Failed to subscribe to shadow delta topic: {e}")
            traceback.print_exc()

        jobs_notify_topic = f"$aws/things/{self.device_name}/jobs/notify"
        try:
            self.mqtt_client.subscribe(jobs_notify_topic, 1, self.on_job_notify)
            print(f"[{self.device_name}] Subscribed to jobs notify topic: {jobs_notify_topic}")
        except Exception as e:
            print(f"[{self.device_name}] Failed to subscribe to jobs notify topic: {e}")
            traceback.print_exc()

        # Publish the initial shadow state.
        self.report_shadow_state()

    def on_command_received(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode('utf-8'))
            action = payload.get('action')
            if action == 'inject_fault':
                self.inject_fault = True
                self.fault_type = payload.get('fault_type')
                print(f"[{self.device_name}] Injecting fault: {self.fault_type}")
            elif action == 'clear_fault':
                self.inject_fault = False
                self.fault_type = None
                print(f"[{self.device_name}] Clearing faults")
            elif action == 'update_filter_status':
                new_status = payload.get('filter_status')
                if new_status in ["Clean", "Needs Cleaning", "Replace"]:
                    self.filter_status = new_status
                    print(f"[{self.device_name}] Updated filter status to: {self.filter_status}")
                else:
                    print(f"[{self.device_name}] Invalid filter status: {new_status}")
            elif action == 'reset_runtime':
                self.runtime_hours = 0
                print(f"[{self.device_name}] Runtime hours reset to zero")
            elif action == 'set_wattage_mode':
                mode = payload.get("wattage_mode")
                if mode == "abnormal":
                    self.abnormal_wattage_mode = True
                    print(f"[{self.device_name}] Wattage mode set to abnormal")
                elif mode == "normal":
                    self.abnormal_wattage_mode = False
                    print(f"[{self.device_name}] Wattage mode set to normal")
                else:
                    print(f"[{self.device_name}] Unknown wattage mode: {mode}")
                # Immediately report updated shadow state.
                self.report_shadow_state()
            elif action == 'disconnect':
                print(f"[{self.device_name}] Received disconnect command. Disconnecting.")
                with self.lock:
                    self.running = False
                disconnect_thread = threading.Thread(target=self.disconnect_mqtt)
                disconnect_thread.start()
            else:
                print(f"[{self.device_name}] Unknown action: {action}")
        except Exception as e:
            print(f"[{self.device_name}] Failed to process command message: {e}")
            traceback.print_exc()

    def disconnect_mqtt(self):
        try:
            self.mqtt_client.disconnect()
            print(f"[{self.device_name}] Disconnected from MQTT broker.")
        except Exception as e:
            print(f"[{self.device_name}] Error during disconnect: {e}")

    def on_shadow_delta(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode('utf-8'))
            print(f"[{self.device_name}] Received shadow delta: {payload}")
            state = payload.get('state', {})
            if 'setpoint_temperature_c' in state:
                self.setpoint_temperature_c = int(state['setpoint_temperature_c'])
                print(f"[{self.device_name}] Updated setpoint temperature to: {self.setpoint_temperature_c}")
            if 'mode' in state:
                if state['mode'] in ['cool', 'off', 'fan_only']:
                    self.mode = state['mode']
                    print(f"[{self.device_name}] Updated mode to: {self.mode}")
                else:
                    print(f"[{self.device_name}] Invalid mode: {state['mode']}")
            self.report_shadow_state()
        except Exception as e:
            print(f"[{self.device_name}] Failed to process shadow delta: {e}")
            traceback.print_exc()

    def on_job_notify(self, client, userdata, message):
        print(f"[{self.device_name}] Received job notification: {message.payload}")
        try:
            payload = json.loads(message.payload.decode('utf-8'))
            jobs_list = payload.get("jobs", [])
            if not jobs_list:
                print(f"[{self.device_name}] No jobs found in notification.")
                return
            for job in jobs_list:
                job_id = job.get("jobId")
                job_document = job.get("jobDocument", {})
                command = job_document.get("command", "")
                print(f"[{self.device_name}] Found job {job_id} with command: {command}")
                if command == "increment":
                    self.process_job(job_id, job_document)
                else:
                    print(f"[{self.device_name}] Unknown job command: {command}")
        except Exception as e:
            print(f"[{self.device_name}] Error processing job notification: {e}")
            traceback.print_exc()

    def process_job(self, job_id, job_document):
        update_topic = f"$aws/things/{self.device_name}/jobs/{job_id}/update"
        try:
            in_progress_payload = {
                "status": "IN_PROGRESS",
                "statusDetails": {"version": str(self.version)}
            }
            self.mqtt_client.publish(update_topic, json.dumps(in_progress_payload), 1)
            print(f"[{self.device_name}] Job {job_id} set to IN_PROGRESS.")
            time.sleep(1)
            increment_value = job_document.get("increment", 1)
            try:
                increment_value = float(increment_value)
            except Exception:
                increment_value = 1.0
            self.version += increment_value
            print(f"[{self.device_name}] Version incremented to {self.version}.")
            succeeded_payload = {
                "status": "SUCCEEDED",
                "statusDetails": {"version": str(self.version)}
            }
            self.mqtt_client.publish(update_topic, json.dumps(succeeded_payload), 1)
            print(f"[{self.device_name}] Job {job_id} completed with status SUCCEEDED.")
            self.report_shadow_state()
        except Exception as e:
            print(f"[{self.device_name}] Failed to process job {job_id}: {e}")
            traceback.print_exc()

    def report_shadow_state(self):
        # Build a dictionary with only the keys we care about.
        current_state = {
            "indoor_temperature_c": int(self.indoor_temperature_c),
            "outdoor_temperature_c": int(self.outdoor_temperature_c),
            "setpoint_temperature_c": int(self.setpoint_temperature_c),
            "mode": self.mode,
            "power_consumption_watts": int(round(self.power_consumption_watts)),
            "compressor_status": self.compressor_status,
            "wattage_mode": "abnormal" if self.abnormal_wattage_mode else "normal"
        }
        # Only publish if one of these values has changed.
        if self.last_shadow_state == current_state:
            return  # No change, do not publish.
        self.last_shadow_state = current_state.copy()
        payload = {"state": {"reported": current_state}}
        try:
            topic = f"$aws/things/{self.device_name}/shadow/update"
            self.mqtt_client.publish(topic, json.dumps(payload), 0)
            print(f"[{self.device_name}] Reported state to shadow: {payload}")
        except Exception as e:
            print(f"[{self.device_name}] Failed to publish shadow update: {e}")
            traceback.print_exc()

    def write_telemetry_to_csv(self, telemetry_data):
        filename = f"{self.device_name}_telemetry.csv"
        file_exists = os.path.isfile(filename)
        try:
            with open(filename, "a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists:
                    header = [
                        "timestamp", "device_name", "indoor_temperature_c",
                        "outdoor_temperature_c", "setpoint_temperature_c", "mode",
                        "power_consumption_watts", "compressor_status", "fan_speed_rpm",
                        "refrigerant_pressure_psi", "error_code", "filter_status",
                        "runtime_hours", "wattage_mode"
                    ]
                    writer.writerow(header)
                row = [
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    telemetry_data.get("device_name", ""),
                    telemetry_data.get("indoor_temperature_c", ""),
                    telemetry_data.get("outdoor_temperature_c", ""),
                    telemetry_data.get("setpoint_temperature_c", ""),
                    telemetry_data.get("mode", ""),
                    telemetry_data.get("power_consumption_watts", ""),
                    telemetry_data.get("compressor_status", ""),
                    telemetry_data.get("fan_speed_rpm", ""),
                    telemetry_data.get("refrigerant_pressure_psi", ""),
                    telemetry_data.get("error_code", ""),
                    telemetry_data.get("filter_status", ""),
                    telemetry_data.get("runtime_hours", ""),
                    "abnormal" if self.abnormal_wattage_mode else "normal"
                ]
                writer.writerow(row)
        except Exception as e:
            print(f"[{self.device_name}] Error writing telemetry to CSV: {e}")

    def generate_telemetry_data(self, interval_seconds):
        self.runtime_hours += interval_seconds / 3600.0

        if self.runtime_hours >= 500 and self.filter_status == "Clean":
            self.filter_status = "Needs Cleaning"
            print(f"[{self.device_name}] Filter status changed to 'Needs Cleaning' after {int(self.runtime_hours)} hours")

        if self.inject_fault:
            if self.fault_type == "high_temperature":
                self.indoor_temperature_c += random.randint(5, 10)
                self.error_code = "E1"
            elif self.fault_type == "low_pressure":
                self.refrigerant_pressure_psi = random.uniform(self.MIN_PRESSURE_PSI, self.MIN_PRESSURE_PSI + 10)
                self.error_code = "E2"
            elif self.fault_type == "compressor_failure":
                self.compressor_status = "Off"
                self.power_consumption_watts = 0
                self.error_code = "E3"
        else:
            self.error_code = "None"

        # Update outdoor temperature gradually toward the target.
        # Update target every 24 hours.
        if self.runtime_hours >= self.next_target_update_hours:
            self.target_outdoor_temperature_c = random.randint(22, 34)
            print(f"[{self.device_name}] New target outdoor temperature set to {self.target_outdoor_temperature_c}")
            self.next_target_update_hours += 24

        # Determine the number of updates in a 24-hour period.
        updates_per_day = (24 * 3600) / interval_seconds
        adjustment = (self.target_outdoor_temperature_c - self.outdoor_temperature_c) / updates_per_day
        self.outdoor_temperature_c += adjustment

        # Adjust indoor temperature gradually when compressor is off.
        if self.compressor_status == "Off" and self.outdoor_temperature_c > self.indoor_temperature_c:
            self.seconds_since_increase += interval_seconds
            if self.seconds_since_increase >= 60:
                self.indoor_temperature_c += 1
                print(f"[{self.device_name}] Indoor temperature increased by 1 to {self.indoor_temperature_c}")
                self.seconds_since_increase -= 60
        else:
            self.seconds_since_increase = 0

        if self.mode == "cool":
            new_compressor_status = "Off" if self.indoor_temperature_c <= self.setpoint_temperature_c else "On"
        else:
            new_compressor_status = "Off"

        if new_compressor_status != self.compressor_status:
            print(f"[{self.device_name}] Compressor changed from {self.compressor_status} to {new_compressor_status}")
            self.compressor_status = new_compressor_status
            self.report_shadow_state()

        if self.compressor_status == "On":
            if self.abnormal_wattage_mode:
                self.power_consumption_watts = random.randint(1250, 1800)
                self.fan_speed_rpm = random.randint(1000, 1500)
                print(f"[{self.device_name}] Abnormal wattage mode active: wattage set to {self.power_consumption_watts}")
            else:
                temp_diff = self.indoor_temperature_c - self.outdoor_temperature_c
                cooling_efficiency = max(0.1, 1 - abs(temp_diff) * 0.05)
                self.indoor_temperature_c -= int(cooling_efficiency * 0.5)
                if self.indoor_temperature_c < self.setpoint_temperature_c:
                    self.indoor_temperature_c = self.setpoint_temperature_c
                temp_excess = max(0, self.indoor_temperature_c - self.setpoint_temperature_c)
                watts = 800 + (temp_excess * 40)
                self.power_consumption_watts = min(1200, watts)
                self.fan_speed_rpm = random.randint(1000, 1500)
        else:
            if self.mode == "off":
                self.power_consumption_watts = 0
                self.fan_speed_rpm = 0
            elif self.mode == "fan_only":
                self.power_consumption_watts = 200
                self.fan_speed_rpm = random.randint(500, 700)
            else:
                self.power_consumption_watts = 0
                self.fan_speed_rpm = random.randint(500, 700)

        self.refrigerant_pressure_psi += random.randint(-2, 2)
        self.refrigerant_pressure_psi = max(self.MIN_PRESSURE_PSI, min(self.MAX_PRESSURE_PSI, self.refrigerant_pressure_psi))
        self.indoor_humidity_percent += random.randint(-1, 1)
        self.outdoor_humidity_percent += random.randint(-1, 1)
        self.indoor_humidity_percent = max(0, min(100, self.indoor_humidity_percent))
        self.outdoor_humidity_percent = max(0, min(100, self.outdoor_humidity_percent))

        # Clamp indoor and outdoor temperatures to their specified ranges.
        self.indoor_temperature_c = max(12, min(30, self.indoor_temperature_c))
        self.outdoor_temperature_c = max(22, min(34, self.outdoor_temperature_c))

        data = {
            "device_name": self.device_name,
            "indoor_temperature_c": int(self.indoor_temperature_c),
            "outdoor_temperature_c": int(self.outdoor_temperature_c),
            "setpoint_temperature_c": int(self.setpoint_temperature_c),
            "mode": self.mode,
            "indoor_humidity_percent": self.indoor_humidity_percent,
            "outdoor_humidity_percent": self.outdoor_humidity_percent,
            "power_consumption_watts": int(round(self.power_consumption_watts)),
            "compressor_status": self.compressor_status,
            "fan_speed_rpm": int(self.fan_speed_rpm),
            "refrigerant_pressure_psi": int(self.refrigerant_pressure_psi),
            "error_code": self.error_code,
            "filter_status": self.filter_status,
            "runtime_hours": int(round(self.runtime_hours))
        }
        return data

    def run(self, topic, interval):
        # Publish initial shadow state.
        self.report_shadow_state()
        error_topic = "aircon/errors"
        try:
            while True:
                with self.lock:
                    if not self.running:
                        break
                telemetry_data = self.generate_telemetry_data(interval)
                message = json.dumps(telemetry_data)
                try:
                    self.mqtt_client.publish(topic, message, 1)
                    print(f"[{self.device_name}] Published telemetry: {message} to topic: {topic}")
                except Exception as e:
                    print(f"[{self.device_name}] Failed to publish telemetry: {e}")
                    traceback.print_exc()

                # Update the shadow if one of the selected telemetry values has changed.
                self.report_shadow_state()

                current_error_code = telemetry_data.get("error_code", "None")
                if current_error_code != "None" and self.last_error_code == "None":
                    error_payload = json.dumps({
                        "device_name": self.device_name,
                        "error_code": current_error_code,
                        "timestamp": time.time()
                    })
                    try:
                        self.mqtt_client.publish(error_topic, error_payload, 1)
                        print(f"[{self.device_name}] Published error: {error_payload} to topic: {error_topic}")
                    except Exception as e:
                        print(f"[{self.device_name}] Failed to publish error: {e}")
                        traceback.print_exc()
                    self.last_error_code = current_error_code
                elif current_error_code == "None":
                    self.last_error_code = "None"

                if self.write_csv:
                    self.write_telemetry_to_csv(telemetry_data)

                time.sleep(interval)
            print(f"[{self.device_name}] Simulator terminated.")
        except KeyboardInterrupt:
            print(f"[{self.device_name}] Terminating due to KeyboardInterrupt...")
            self.disconnect_mqtt()
        except Exception as e:
            print(f"[{self.device_name}] An error occurred: {e}")
            traceback.print_exc()
            self.disconnect_mqtt()

def run_simulator_for_device(device_folder, topic, interval, write_csv):
    try:
        with open(os.path.join(device_folder, 'device_info.json'), 'r') as f:
            device_info = json.load(f)
    except Exception as e:
        print(f"Failed to load device_info.json in {device_folder}: {e}")
        traceback.print_exc()
        return
    device_name = device_info['thingName']
    root_ca_path = device_info['rootCAPath']
    private_key_path = os.path.join(device_folder, f"{device_name}-private.pem.key")
    certificate_path = os.path.join(device_folder, f"{device_name}-certificate.pem.crt")

    if not os.path.isfile(root_ca_path):
        print(f"[{device_name}] Root CA file not found at {root_ca_path}. Attempting to download...")
        download_root_ca(root_ca_path)

    mqtt_client = create_mqtt_client(
        client_id=device_name,
        endpoint=device_info['endpoint'],
        root_ca_path=root_ca_path,
        private_key_path=private_key_path,
        certificate_path=certificate_path
    )
    print(f"[{device_name}] Connecting to AWS IoT Core...")
    try:
        mqtt_client.connect()
        print(f"[{device_name}] Connected!")
    except Exception as e:
        print(f"[{device_name}] Failed to connect: {e}")
        traceback.print_exc()
        return

    ac_simulator = ACUnitSimulator(device_folder, device_name, mqtt_client, write_csv=write_csv)
    ac_simulator.run(topic, interval)

if __name__ == '__main__':
    import argparse
    from PyQt5.QtWidgets import QApplication

    def parse_cli_args():
        parser = argparse.ArgumentParser(description='Air Conditioner Device Simulator')
        parser.add_argument('--devices-folder', type=str, default='devices', help='Path to the devices folder')
        parser.add_argument('--device-name', type=str, help='Name of the device to start')
        parser.add_argument('--topic', type=str, default='aircon/telemetry', help='MQTT topic to publish telemetry to')
        parser.add_argument('--interval', type=float, default=60.0, help='Interval between telemetry data publishes in seconds')
        parser.add_argument('--write-csv', action='store_true', help='Enable writing telemetry data to a local CSV file')
        return parser.parse_args()

    args = parse_cli_args()
    devices_folder = args.devices_folder
    interval = args.interval
    device_folders = []
    for root, dirs, files in os.walk(devices_folder):
        if 'device_info.json' in files:
            if args.device_name:
                if os.path.basename(root) == args.device_name:
                    device_folders.append(root)
            else:
                device_folders.append(root)
    if not device_folders:
        print("No devices found to start.")
        exit(1)
    threads = []
    for device_folder in device_folders:
        device_name = os.path.basename(device_folder)
        print(f"Starting simulator for {device_name}")
        thread = threading.Thread(target=run_simulator_for_device, args=(device_folder, args.topic, interval, args.write_csv))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Terminating all simulators...")
