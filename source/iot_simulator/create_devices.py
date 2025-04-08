import boto3
import os
import json
import argparse
import urllib.request

def download_root_ca(root_ca_path):
    # URL to download the Amazon Root CA 1 certificate
    url = 'https://www.amazontrust.com/repository/AmazonRootCA1.pem'
    try:
        print(f"Downloading Amazon Root CA certificate from {url}...")
        urllib.request.urlretrieve(url, root_ca_path)
        print(f"Downloaded Amazon Root CA certificate to {root_ca_path}")
    except Exception as e:
        print(f"Failed to download Root CA certificate: {e}")
        exit(1)

def create_device(device_name, policy_name):
    iot = boto3.client('iot')

    # Create the thing (device)
    iot.create_thing(thingName=device_name)

    # Create keys and certificate
    cert_response = iot.create_keys_and_certificate(setAsActive=True)

    certificate_arn = cert_response['certificateArn']
    certificate_id = cert_response['certificateId']
    certificate_pem = cert_response['certificatePem']
    public_key = cert_response['keyPair']['PublicKey']
    private_key = cert_response['keyPair']['PrivateKey']

    # Attach policy to certificate
    iot.attach_policy(policyName=policy_name, target=certificate_arn)

    # Attach certificate to the thing
    iot.attach_thing_principal(thingName=device_name, principal=certificate_arn)

    # Save the certs and keys into files
    device_folder = os.path.join('devices', device_name)
    os.makedirs(device_folder, exist_ok=True)

    with open(os.path.join(device_folder, f'{device_name}-certificate.pem.crt'), 'w') as f:
        f.write(certificate_pem)

    with open(os.path.join(device_folder, f'{device_name}-private.pem.key'), 'w') as f:
        f.write(private_key)

    with open(os.path.join(device_folder, f'{device_name}-public.pem.key'), 'w') as f:
        f.write(public_key)

    # Download Root CA certificate into the device folder
    root_ca_path = os.path.join(device_folder, 'AmazonRootCA1.pem')
    if not os.path.isfile(root_ca_path):
        download_root_ca(root_ca_path)

    # Save device info to JSON
    endpoint = iot.describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress']

    device_info = {
        'thingName': device_name,
        'certificateId': certificate_id,
        'certificateArn': certificate_arn,
        'endpoint': endpoint,
        'rootCAPath': root_ca_path
    }

    with open(os.path.join(device_folder, 'device_info.json'), 'w') as f:
        json.dump(device_info, f, indent=4)

def create_policy(policy_name, device_prefix):
    iot = boto3.client('iot')

    # Get the AWS region and account ID
    region = boto3.session.Session().region_name
    account_id = boto3.client('sts').get_caller_identity().get('Account')

    # Build the policy document using the device prefix for topic ARNs.
    # Additional ARNs for jobs have been added below.
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "iot:Connect",
                "Resource": f"arn:aws:iot:{region}:{account_id}:client/${{iot:Connection.Thing.ThingName}}"
            },
            {
                "Effect": "Allow",
                "Action": "iot:Publish",
                "Resource": [
                    f"arn:aws:iot:{region}:{account_id}:topic/{device_prefix}/telemetry",
                    f"arn:aws:iot:{region}:{account_id}:topic/$aws/things/${{iot:Connection.Thing.ThingName}}/shadow/update",
                    f"arn:aws:iot:{region}:{account_id}:topic/{device_prefix}/errors",
                    # Allow publishing job status updates (wildcard for jobId)
                    f"arn:aws:iot:{region}:{account_id}:topic/$aws/things/${{iot:Connection.Thing.ThingName}}/jobs/*/update"
                ]
            },
            {
                "Effect": "Allow",
                "Action": "iot:Subscribe",
                "Resource": [
                    f"arn:aws:iot:{region}:{account_id}:topicfilter/{device_prefix}/commands/${{iot:Connection.Thing.ThingName}}",
                    f"arn:aws:iot:{region}:{account_id}:topicfilter/$aws/things/${{iot:Connection.Thing.ThingName}}/shadow/update/delta",
                    # Allow subscribing to job notifications
                    f"arn:aws:iot:{region}:{account_id}:topicfilter/$aws/things/${{iot:Connection.Thing.ThingName}}/jobs/notify"
                ]
            },
            {
                "Effect": "Allow",
                "Action": "iot:Receive",
                "Resource": [
                    f"arn:aws:iot:{region}:{account_id}:topic/{device_prefix}/commands/${{iot:Connection.Thing.ThingName}}",
                    f"arn:aws:iot:{region}:{account_id}:topic/$aws/things/${{iot:Connection.Thing.ThingName}}/shadow/update/delta",
                    # Allow receiving messages on the jobs notifications topic
                    f"arn:aws:iot:{region}:{account_id}:topic/$aws/things/${{iot:Connection.Thing.ThingName}}/jobs/notify"
                ]
            }
        ]
    }

    try:
        iot.get_policy(policyName=policy_name)
        print(f"Policy '{policy_name}' already exists.")
    except iot.exceptions.ResourceNotFoundException:
        iot.create_policy(policyName=policy_name, policyDocument=json.dumps(policy_document))
        print(f"Created policy '{policy_name}'.")

def main():
    parser = argparse.ArgumentParser(description='Create demo IoT devices with a naming standard.')
    parser.add_argument('--count', type=int, required=True, help='Number of devices to create')
    parser.add_argument('--device-prefix', type=str, default='aircon', help='Prefix for device names')
    # If you prefer to allow an override for the policy name, you can uncomment the following:
    # parser.add_argument('--policy-name', type=str, help='Name of the IoT policy (overrides auto-generated name)')
    args = parser.parse_args()

    # Derive the policy name from the device prefix if not explicitly provided.
    # Uncomment the line below if you wish to allow an override.
    # policy_name = args.policy_name if args.policy_name else f"{args.device_prefix.capitalize()}DevicePolicy"
    policy_name = f"{args.device_prefix.capitalize()}DevicePolicy"

    # Create the policy if it doesn't exist
    create_policy(policy_name, args.device_prefix)

    for i in range(1, args.count + 1):
        device_name = f"{args.device_prefix}_{i}"
        print(f"Creating device: {device_name}")
        create_device(device_name, policy_name)

if __name__ == '__main__':
    main()
