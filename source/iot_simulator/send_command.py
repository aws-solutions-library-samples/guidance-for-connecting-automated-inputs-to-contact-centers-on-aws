import json
import argparse
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

def send_command(device_name, action, fault_type=None, filter_status=None, endpoint=None, root_ca_path=None, cert_path=None, key_path=None):
    client = AWSIoTMQTTClient("command_sender")
    client.configureEndpoint(endpoint, 8883)
    client.configureCredentials(root_ca_path, key_path, cert_path)

    client.configureAutoReconnectBackoffTime(1, 32, 20)
    client.configureOfflinePublishQueueing(-1)
    client.configureDrainingFrequency(2)
    client.configureConnectDisconnectTimeout(10)
    client.configureMQTTOperationTimeout(5)

    client.connect()
    command_topic = f"aircon/commands/{device_name}"

    payload = {"action": action}
    if fault_type:
        payload["fault_type"] = fault_type
    if filter_status:
        payload["filter_status"] = filter_status

    client.publish(command_topic, json.dumps(payload), 1)
    print(f"Sent command to {device_name}: {payload}")
    client.disconnect()

def main():
    parser = argparse.ArgumentParser(description='Send commands to device simulator.')
    parser.add_argument('--device-name', type=str, required=True, help='Name of the device')
    parser.add_argument('--action', type=str, choices=['inject_fault', 'clear_fault', 'update_filter_status'], required=True, help='Action to perform')
    parser.add_argument('--fault-type', type=str, choices=['high_temperature', 'low_pressure', 'compressor_failure'], help='Type of fault to inject')
    parser.add_argument('--filter-status', type=str, choices=['Clean', 'Needs Cleaning', 'Replace'], help='Filter status to update')
    parser.add_argument('--endpoint', type=str, required=True, help='AWS IoT endpoint')
    parser.add_argument('--root-ca', type=str, required=True, help='Path to root CA certificate')
    parser.add_argument('--cert', type=str, required=True, help='Path to client certificate')
    parser.add_argument('--key', type=str, required=True, help='Path to private key')

    args = parser.parse_args()

    send_command(
        device_name=args.device_name,
        action=args.action,
        fault_type=args.fault_type,
        filter_status=args.filter_status,
        endpoint=args.endpoint,
        root_ca_path=args.root_ca,
        cert_path=args.cert,
        key_path=args.key
    )

if __name__ == '__main__':
    main()
