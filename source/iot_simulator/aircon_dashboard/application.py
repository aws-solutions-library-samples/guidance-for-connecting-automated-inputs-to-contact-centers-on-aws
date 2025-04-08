from flask import Flask, render_template, request, jsonify, url_for
import boto3, certifi, json, datetime
from botocore.exceptions import ClientError

app = Flask(__name__)

# Create the IoT Data client using certifi’s CA bundle.
iot_data = boto3.client('iot-data', verify=certifi.where())

# Global in-memory log for shadow activity.
shadow_log = []

def log_shadow_activity(device, message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {device}: {message}"
    shadow_log.append(log_line)
    if len(shadow_log) > 100:
        del shadow_log[0]

def get_shadow_state(device):
    try:
        response = iot_data.get_thing_shadow(thingName=device)
        payload = response['payload'].read()
        shadow = json.loads(payload)
        log_shadow_activity(device, f"Retrieved shadow:\n{json.dumps(shadow, indent=2)}")
        reported = shadow.get("state", {}).get("reported", {})
        return reported
    except ClientError as e:
        error_msg = f"Error retrieving shadow: {e}"
        log_shadow_activity(device, error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        log_shadow_activity(device, error_msg)
        return {"error": error_msg}

@app.route('/')
def index():
    # Use query parameters to set device prefix and count.
    device_prefix = request.args.get('device_prefix', 'aircon')
    try:
        count = int(request.args.get('count', 2))
    except ValueError:
        count = 2
    devices = [f"{device_prefix}_{i}" for i in range(1, count+1)]
    
    shadows = {}
    for device in devices:
        shadows[device] = get_shadow_state(device)
    return render_template('index.html', devices=devices, shadows=shadows)

@app.route('/read_shadows')
def read_shadows():
    device_prefix = request.args.get('device_prefix', 'aircon')
    try:
        count = int(request.args.get('count', 2))
    except ValueError:
        count = 2
    devices = [f"{device_prefix}_{i}" for i in range(1, count+1)]
    
    shadows = {}
    for device in devices:
        shadows[device] = get_shadow_state(device)
    return jsonify(shadows)

@app.route('/update_temp', methods=['POST'])
def update_temp():
    device = request.form.get('device')
    try:
        desired_temp = int(request.form.get('desired_temp'))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid temperature value."}), 400
    payload = {"state": {"desired": {"setpoint_temperature_c": desired_temp}}}
    try:
        response = iot_data.update_thing_shadow(thingName=device, payload=json.dumps(payload))
        log_shadow_activity(device, f"Updated desired temp to {desired_temp}. Response: {response}")
        return jsonify({"status": "success", "message": f"Desired temp for {device} updated."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/command', methods=['POST'])
def send_command():
    device = request.form.get('device')
    action = request.form.get('action')
    payload = {}
    if action == 'inject_fault':
        payload = {"action": "inject_fault", "fault_type": request.form.get('fault_type')}
    elif action == 'clear_fault':
        payload = {"action": "clear_fault"}
    elif action == 'set_wattage_mode':
        wattage_mode = request.form.get('wattage_mode')
        payload = {"action": "set_wattage_mode", "wattage_mode": wattage_mode}
    else:
        return jsonify({"status": "error", "message": "Unknown action."}), 400

    topic = f"aircon/commands/{device}"
    try:
        iot_data.publish(topic=topic, qos=1, payload=json.dumps(payload))
        log_shadow_activity(device, f"Published command to {topic}: {json.dumps(payload)}")
        return jsonify({"status": "success", "message": f"Command sent to {device}."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/shadow_logs')
def get_shadow_logs():
    return jsonify(shadow_log)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
