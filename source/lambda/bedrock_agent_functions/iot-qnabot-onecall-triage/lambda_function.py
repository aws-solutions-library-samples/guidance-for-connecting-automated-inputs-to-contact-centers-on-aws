import json
import boto3
import datetime
import os
import uuid

def lambda_handler(event, context):
    try:

        agent = event['agent']
        actionGroup = event['actionGroup']
        function = event['function']
        parameters = event.get('parameters', [])

        # Create a dictionary from the parameters list
        params_dict = {param['name']: param['value'] for param in parameters}

        if 'unique_id' in params_dict:
            unique_id = params_dict['unique_id']
        else:
            unique_id = str(uuid.uuid4())  

        device_id = params_dict['device_id'] 
        error_code = params_dict['error_code']
        time_stamp_epoch = float(params_dict['time_stamp'])
        dt = datetime.datetime.fromtimestamp(time_stamp_epoch)
        time_stamp = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-2]
        troubleshooting_steps = params_dict['troubleshooting_steps']
        if 'start_end_datetime' in params_dict:
            start_end_datetime = params_dict['start_end_datetime']
        else:
            start_end_datetime = ''

        if function == 'log_ticket':
            # Connect to DynamoDB for the maintenance database
            dynamodb = boto3.resource('dynamodb')
            table_name = os.environ.get('IOT_DEVICE_ERROR_TABLE')
            table = dynamodb.Table(table_name)
            
            ## Store data into DynamoDB
            if start_end_datetime != '':
                start_str, end_str = start_end_datetime.split(',')
                start_datetime = datetime.datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S.%f")
                end_datetime = datetime.datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S.%f")
                table.put_item(
                Item={
                    'unique_id': unique_id,
                    'device_id': device_id,
                    'error_code': error_code,
                    'time_stamp': time_stamp,
                    'troubleshooting_steps': troubleshooting_steps,
                    'anomaly_start': start_datetime.isoformat(),
                    'anomaly_end': end_datetime.isoformat()
                }
                )
            else:
                table.put_item(
                Item={
                    'unique_id': unique_id,
                    'device_id': device_id,
                    'error_code': error_code,
                    'time_stamp': time_stamp,
                    'troubleshooting_steps': troubleshooting_steps
                }
                )
            action = f"Logged ticket in DynamoDB successfully - unique_id: {unique_id}, device_id: {device_id}"
            print(action)

            # Send Email  - working code via SES, with Identity spin up in Connect
        
            ses = boto3.client('ses')
            email_subject = "Aircon Maintenance Ticket"
            email_body = f"Ticket details:\n\nUnique ID: {unique_id}\nDevice ID: {device_id}\nError Code: {error_code}\nTime Stamp: {time_stamp}\nTroubleshooting Steps: {troubleshooting_steps}"
            ses.send_email(
                Source=os.environ.get('SENDER_EMAIL_ID'),
                Destination={
                    'ToAddresses': [
                        os.environ.get('RECIPIENT_EMAIL_ID'),
                    ]
                },
                Message={
                    'Subject': {
                        'Data': email_subject
                    },
                    'Body': {
                        'Text': {
                            'Data': email_body
                        }
                    }
                }
            )
            

        elif function == 'call_operator':

            # Connect to Amazon Connect
            connect = boto3.client('connect')

            params = {
                'ContactFlowId': os.environ.get('CONTACT_FLOW_ID'),
                'DestinationPhoneNumber': os.environ.get('DESTINATION_PHONE_NO'),  
                'InstanceId': os.environ.get('INSTANCE_ID'),
                'SourcePhoneNumber': os.environ.get('SOURCE_PHONE_NO'),
                'TrafficType': 'GENERAL',
                'Attributes': {
                    'UniqueID' : unique_id,
                    'deviceID' : device_id,
                    'errorCode' : error_code,
                    'troubleshootingSteps' : troubleshooting_steps,
                    'recipientEmail' : os.environ.get('RECIPIENT_EMAIL_ID')
                                    
                }    
            }

            connect.start_outbound_voice_contact(**params)

            action = "Placed a call to the site operator"
            print(action)


        elif function == 'clear_fault':
            # Retrieve the IoT Data endpoint from an environment variable
            iot_data_endpoint = os.environ.get('IOT_DATA_ENDPOINT')

            # Construct the topic using the device identifier
            topic = f"aircon/commands/{device_id}"
        
            # Define the JSON payload to clear fault codes
            payload = json.dumps({"action": "clear_fault"})

            # Create the IoT Data client using the custom endpoint URL
            client = boto3.client('iot-data', endpoint_url=iot_data_endpoint)

            # Publish the clear_fault command to the specific device's topic
            client.publish(
                topic=topic,
                qos=1,
                payload=payload
            )
            print(f"Published to {topic}: {payload}")
            action = "Cleared fault from the IoT device"
            print(action)
            

        else:
            action = "No action needs to be taken"
            print(action)

        responseBody =  {
            "TEXT": {
                "body": "The function {} was called successfully! Following action is taken: {}".format(function,action)
            }
        }

        action_response = {
            'actionGroup': actionGroup,
            'function': function,
            'functionResponse': {
                'responseBody': responseBody
            }

        }

        function_response = {'response': action_response, 'messageVersion': event['messageVersion']}
        print("Response: {}".format(function_response))

        return function_response
    except Exception as e:
        print("Error occurred:", str(e))
        return {
            'statusCode': 500,
            'body': json.dumps('Error occurred while processing the request')
        }
