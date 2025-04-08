import sys
import json
import argparse
import boto3
import certifi
import datetime
from botocore.exceptions import ClientError
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QComboBox, QLabel, QLineEdit, QPlainTextEdit
)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor

# Create the IoT Data client using the CA bundle from certifi
iot_data = boto3.client('iot-data', verify=certifi.where())
# If needed, you can also explicitly specify the endpoint:
# iot_data = boto3.client('iot-data', endpoint_url='https://your-endpoint.amazonaws.com', verify=certifi.where())

class DashboardWindow(QMainWindow):
    def __init__(self, devices):
        super().__init__()
        self.setWindowTitle("Air Conditioner Simulator Dashboard")
        self.setGeometry(100, 100, 950, 650)  # increased width and height for extra column and log window
        self.devices = devices

        # Table to display device shadow statuses.
        # Now 13 columns: 
        # "Action", "Device", "Outdoor Temp (°C)", "Indoor Temp (°C)", "Setpoint (°C)",
        # "Compressor Status", "Mode", "Wattage", "Wattage Mode", "Error Code", "Filter Status",
        # "Runtime (hrs)", "Version"
        self.table = QTableWidget(self)
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            "Action", "Device", "Outdoor Temp (°C)", "Indoor Temp (°C)", "Setpoint (°C)",
            "Compressor Status", "Mode", "Wattage", "Wattage Mode", "Error Code", "Filter Status",
            "Runtime (hrs)", "Version"
        ])

        # Create dropdown for device names
        self.device_label = QLabel("Select Device:", self)
        self.device_dropdown = QComboBox(self)
        self.device_dropdown.addItems(devices)

        # Create dropdown for fault types
        self.fault_label = QLabel("Select Fault Type:", self)
        self.fault_dropdown = QComboBox(self)
        self.fault_dropdown.addItems(["high_temperature", "low_pressure", "compressor_failure"])

        # Create input and button for updating desired temperature
        self.desired_temp_label = QLabel("Desired Temp (°C):", self)
        self.desired_temp_input = QLineEdit(self)
        self.update_temp_button = QPushButton("Update Temp", self)
        self.update_temp_button.clicked.connect(self.update_desired_temp)

        # Create buttons for fault injection and clearing faults
        self.inject_button = QPushButton("Inject Fault", self)
        self.inject_button.clicked.connect(self.inject_fault)
        self.clear_button = QPushButton("Clear Fault", self)
        self.clear_button.clicked.connect(self.clear_fault)

        # New wattage mode controls
        self.wattage_mode_label = QLabel("Wattage Mode:", self)
        self.wattage_mode_dropdown = QComboBox(self)
        self.wattage_mode_dropdown.addItems(["normal", "abnormal"])
        self.set_wattage_mode_button = QPushButton("Set Wattage Mode", self)
        self.set_wattage_mode_button.clicked.connect(self.set_wattage_mode)

        # Layout for controls
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.device_label)
        control_layout.addWidget(self.device_dropdown)
        control_layout.addWidget(self.fault_label)
        control_layout.addWidget(self.fault_dropdown)
        control_layout.addWidget(self.inject_button)
        control_layout.addWidget(self.clear_button)
        control_layout.addWidget(self.desired_temp_label)
        control_layout.addWidget(self.desired_temp_input)
        control_layout.addWidget(self.update_temp_button)
        control_layout.addWidget(self.wattage_mode_label)
        control_layout.addWidget(self.wattage_mode_dropdown)
        control_layout.addWidget(self.set_wattage_mode_button)

        # Create a log widget (QPlainTextEdit) for displaying shadow MQTT messages
        self.log_widget = QPlainTextEdit(self)
        self.log_widget.setReadOnly(True)
        self.log_widget.setFixedHeight(150)
        self.log_buffer = []

        # Main layout: table on top, then control layout, then log area.
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.table)
        main_layout.addLayout(control_layout)
        main_layout.addWidget(QLabel("Shadow MQTT Messages:", self))
        main_layout.addWidget(self.log_widget)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Timer to update the table every 5 minutes (300000 ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_table)
        self.timer.start(300000)  # 300,000 ms = 5 minutes

        # Also update the table immediately at startup
        self.update_table()

    def append_log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.log_buffer.append(log_line)
        if len(self.log_buffer) > 100:
            self.log_buffer = self.log_buffer[-100:]
        self.log_widget.setPlainText("\n".join(self.log_buffer))
        self.log_widget.verticalScrollBar().setValue(self.log_widget.verticalScrollBar().maximum())

    def get_shadow_state(self, device_name):
        try:
            response = iot_data.get_thing_shadow(thingName=device_name)
            payload = response['payload'].read()
            shadow = json.loads(payload)
            # Log the retrieved shadow as formatted JSON
            formatted_shadow = json.dumps(shadow, indent=4)
            self.append_log(f"Shadow for {device_name}:\n{formatted_shadow}")
            reported = shadow.get("state", {}).get("reported", {})
            return reported
        except ClientError as e:
            error_msg = f"Error retrieving shadow for {device_name}: {e}"
            print(error_msg)
            self.append_log(error_msg)
            return {}
        except Exception as e:
            error_msg = f"Unexpected error for {device_name}: {e}"
            print(error_msg)
            self.append_log(error_msg)
            return {}

    def update_table(self):
        self.table.setRowCount(len(self.devices))
        for row, device in enumerate(self.devices):
            # Create "Read Shadow" button for each row in column 0
            read_button = QPushButton("Read Shadow")
            read_button.clicked.connect(lambda _, dev=device, r=row: self.read_shadow_on_demand(dev, r))
            self.table.setCellWidget(row, 0, read_button)

            # Retrieve the shadow for each device (for table update)
            state = self.get_shadow_state(device)
            # Create table items for the remaining columns.
            device_item = QTableWidgetItem(device)
            outdoor_temp = QTableWidgetItem(str(state.get("outdoor_temperature_c", "N/A")))
            indoor_temp = QTableWidgetItem(str(state.get("indoor_temperature_c", "N/A")))
            setpoint = QTableWidgetItem(str(state.get("setpoint_temperature_c", "N/A")))
            compressor_status = QTableWidgetItem(state.get("compressor_status", "N/A"))
            mode = QTableWidgetItem(state.get("mode", "N/A"))
            wattage = QTableWidgetItem(str(state.get("power_consumption_watts", "N/A")))
            wattage_mode = QTableWidgetItem(str(state.get("wattage_mode", "N/A")))
            error = QTableWidgetItem(state.get("error_code", "N/A"))
            filter_status = QTableWidgetItem(state.get("filter_status", "N/A"))
            runtime = QTableWidgetItem(str(state.get("runtime_hours", "N/A")))
            version = QTableWidgetItem(str(state.get("version", "N/A")))

            if error.text() not in ["None", "N/A"]:
                error.setForeground(QColor("red"))

            # Set columns:
            # 0: Action, 1: Device, 2: Outdoor Temp, 3: Indoor Temp, 4: Setpoint,
            # 5: Compressor Status, 6: Mode, 7: Wattage, 8: Wattage Mode, 9: Error Code,
            # 10: Filter Status, 11: Runtime, 12: Version
            self.table.setItem(row, 1, device_item)
            self.table.setItem(row, 2, outdoor_temp)
            self.table.setItem(row, 3, indoor_temp)
            self.table.setItem(row, 4, setpoint)
            self.table.setItem(row, 5, compressor_status)
            self.table.setItem(row, 6, mode)
            self.table.setItem(row, 7, wattage)
            self.table.setItem(row, 8, wattage_mode)
            self.table.setItem(row, 9, error)
            self.table.setItem(row, 10, filter_status)
            self.table.setItem(row, 11, runtime)
            self.table.setItem(row, 12, version)

        self.table.resizeColumnsToContents()

    def read_shadow_on_demand(self, device, row):
        state = self.get_shadow_state(device)
        self.table.item(row, 2).setText(str(state.get("outdoor_temperature_c", "N/A")))
        self.table.item(row, 3).setText(str(state.get("indoor_temperature_c", "N/A")))
        self.table.item(row, 4).setText(str(state.get("setpoint_temperature_c", "N/A")))
        self.table.item(row, 5).setText(state.get("compressor_status", "N/A"))
        self.table.item(row, 6).setText(state.get("mode", "N/A"))
        self.table.item(row, 7).setText(str(state.get("power_consumption_watts", "N/A")))
        self.table.item(row, 8).setText(str(state.get("wattage_mode", "N/A")))
        error_text = state.get("error_code", "N/A")
        error_item = QTableWidgetItem(error_text)
        if error_text not in ["None", "N/A"]:
            error_item.setForeground(QColor("red"))
        self.table.setItem(row, 9, error_item)
        self.table.item(row, 10).setText(state.get("filter_status", "N/A"))
        self.table.item(row, 11).setText(str(state.get("runtime_hours", "N/A")))
        self.table.item(row, 12).setText(str(state.get("version", "N/A")))
        self.append_log(f"On-demand shadow read for {device} completed.")

    def inject_fault(self):
        device_name = self.device_dropdown.currentText()
        fault_type = self.fault_dropdown.currentText()
        payload = {"action": "inject_fault", "fault_type": fault_type}
        self.send_command(device_name, payload)

    def clear_fault(self):
        device_name = self.device_dropdown.currentText()
        payload = {"action": "clear_fault"}
        self.send_command(device_name, payload)

    def update_desired_temp(self):
        device_name = self.device_dropdown.currentText()
        temp_str = self.desired_temp_input.text().strip()
        try:
            desired_temp = int(temp_str)
        except ValueError:
            self.append_log("Invalid temperature value entered.")
            return
        payload = {
            "state": {
                "desired": {
                    "setpoint_temperature_c": desired_temp
                }
            }
        }
        try:
            response = iot_data.update_thing_shadow(
                thingName=device_name,
                payload=json.dumps(payload)
            )
            self.append_log(f"Updated desired temperature for {device_name} to {desired_temp}. Response: {response}")
        except Exception as e:
            self.append_log(f"Error updating desired temperature for {device_name}: {e}")

    def set_wattage_mode(self):
        device_name = self.device_dropdown.currentText()
        wattage_mode = self.wattage_mode_dropdown.currentText()  # either "normal" or "abnormal"
        payload = {"action": "set_wattage_mode", "wattage_mode": wattage_mode}
        self.send_command(device_name, payload)

    def send_command(self, device_name, payload):
        topic = f"aircon/commands/{device_name}"
        try:
            iot_data.publish(topic=topic, qos=1, payload=json.dumps(payload))
            self.append_log(f"Published command to {topic}: {json.dumps(payload)}")
        except Exception as e:
            self.append_log(f"Error publishing command to {topic}: {e}")

def parse_cli_args():
    parser = argparse.ArgumentParser(description="Air Conditioner Simulator Dashboard (Shadow-based)")
    parser.add_argument("--device-prefix", type=str, default="aircon",
                        help="Prefix for device names (default: aircon)")
    parser.add_argument("--count", type=int, default=2,
                        help="Number of devices (default: 2)")
    return parser.parse_args()

def generate_device_names(prefix, count):
    return [f"{prefix}_{i}" for i in range(1, count+1)]

if __name__ == '__main__':
    args = parse_cli_args()
    devices = generate_device_names(args.device_prefix, args.count)

    app = QApplication(sys.argv)
    window = DashboardWindow(devices)
    window.show()
    sys.exit(app.exec_())
