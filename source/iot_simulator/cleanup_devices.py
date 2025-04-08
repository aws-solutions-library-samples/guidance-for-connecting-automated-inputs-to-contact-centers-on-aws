import boto3
import os
import json
import argparse
import shutil

def delete_device(device_folder, policy_name):
    # Initialize AWS IoT client
    iot = boto3.client('iot')

    # Load device info
    with open(os.path.join(device_folder, 'device_info.json'), 'r') as f:
        device_info = json.load(f)

    thing_name = device_info['thingName']
    certificate_id = device_info['certificateId']
    certificate_arn = device_info['certificateArn']

    print(f"Cleaning up device: {thing_name}")

    # Detach the certificate from the thing
    try:
        iot.detach_thing_principal(thingName=thing_name, principal=certificate_arn)
        print(f"Detached certificate from thing: {thing_name}")
    except Exception as e:
        print(f"Error detaching certificate from thing: {e}")

    # Detach the policy from the certificate
    try:
        iot.detach_policy(policyName=policy_name, target=certificate_arn)
        print(f"Detached policy '{policy_name}' from certificate")
    except Exception as e:
        print(f"Error detaching policy from certificate: {e}")

    # Update the certificate status to INACTIVE
    try:
        iot.update_certificate(certificateId=certificate_id, newStatus='INACTIVE')
        print("Set certificate status to INACTIVE")
    except Exception as e:
        print(f"Error updating certificate status: {e}")

    # Delete the certificate
    try:
        iot.delete_certificate(certificateId=certificate_id, forceDelete=True)
        print(f"Deleted certificate: {certificate_id}")
    except Exception as e:
        print(f"Error deleting certificate: {e}")

    # Delete the thing
    try:
        iot.delete_thing(thingName=thing_name)
        print(f"Deleted thing: {thing_name}")
    except Exception as e:
        print(f"Error deleting thing: {e}")

    # Delete the device folder
    try:
        shutil.rmtree(device_folder)
        print(f"Deleted device folder: {device_folder}")
    except Exception as e:
        print(f"Error deleting device folder: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Cleanup demo devices using the naming standard.'
    )
    parser.add_argument('--devices-folder', type=str, default='devices',
                        help='Path to the devices folder')
    parser.add_argument('--device-prefix', type=str, default='aircon',
                        help='Device prefix used in device names')
    parser.add_argument('--policy-name', type=str,
                        help='Name of the IoT policy (overrides auto-generated name)')
    parser.add_argument('--keep-policy', action='store_true',
                        help='Keep the policy after cleanup (default is to delete)')

    args = parser.parse_args()

    # Derive the policy name if not explicitly provided
    policy_name = args.policy_name if args.policy_name else f"{args.device_prefix.capitalize()}DevicePolicy"

    devices_folder = args.devices_folder

    # Find all device folders that contain device_info.json
    device_folders = []
    for root, dirs, files in os.walk(devices_folder):
        if 'device_info.json' in files:
            device_folders.append(root)

    if not device_folders:
        print("No devices found to clean up.")
    else:
        for device_folder in device_folders:
            delete_device(device_folder, policy_name)

    # Delete the policy by default, unless --keep-policy is specified
    if not args.keep_policy:
        iot = boto3.client('iot')

        # Detach the policy from all certificates
        try:
            response = iot.list_targets_for_policy(policyName=policy_name)
            targets = response.get('targets', [])
            for target in targets:
                iot.detach_policy(policyName=policy_name, target=target)
                print(f"Detached policy '{policy_name}' from target: {target}")
        except Exception as e:
            print(f"Error detaching policy from targets: {e}")

        # Delete the policy
        try:
            iot.delete_policy(policyName=policy_name)
            print(f"Deleted policy: {policy_name}")
        except Exception as e:
            print(f"Error deleting policy: {e}")
    else:
        print(f"Policy '{policy_name}' retained as per --keep-policy flag.")

    print("Cleanup completed.")

if __name__ == '__main__':
    main()
