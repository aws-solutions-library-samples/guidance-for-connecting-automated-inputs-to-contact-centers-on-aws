
import json
import boto3
import datetime
import os
import csv

def get_ticket_data(unique_id, device_id):
    #implement code to fetch ticket data from DynamoDB
    # Connect to DynamoDB for the maintenance database
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('IOT_DEVICE_ERROR_TABLE') #'iot-qna-bot-device-error' 
    table = dynamodb.Table(table_name)

    # Define the partition key and sort key values
    partition_key_value = unique_id
    sort_key_value = device_id

    # Perform the query
    response = table.query(
        KeyConditionExpression='#pk = :pkval AND #sk = :skval',
        ExpressionAttributeNames={
            '#pk': 'unique_id',
            '#sk': 'device_id'
        },
        ExpressionAttributeValues={
            ':pkval': partition_key_value,
            ':skval': sort_key_value
        }
    )

    ticket_data = []
    # Process the results
    items = response['Items']
    for item in items:
        #print(item)
        ticket_data.append(item)

    return ticket_data

def get_device_telemetry_data(device_id, start_datetime, end_datetime):
    s3 = boto3.client('s3')
    telemetry_s3Bucket = os.environ.get('TELEMETRY_ANOMALY_S3_BUCKET')
    
    start_datetime_obj = datetime.datetime.fromisoformat(start_datetime)
    end_datetime_obj = datetime.datetime.fromisoformat(end_datetime)
 
    time_difference_hrs = int((end_datetime_obj - start_datetime_obj).total_seconds() / 3600)
    time_difference_hrs = 1 # REMOVE THIS 

    #Get all the s3 paths to process
    s3paths = []
    for x in range(time_difference_hrs):
        s3paths.append((end_datetime_obj - datetime.timedelta(hours=(x))).strftime("telemetry/processed-output/%Y/%m/%d/%H"))

    print(s3paths)

    telemetry_data = []

    #Loop through all the S3 prefixes
    for path in s3paths:
        print("S3 path: ", path)

        #  Read all CSV files from S3
        response = s3.list_objects_v2(Bucket=telemetry_s3Bucket, Prefix=path)
        for obj in response['Contents']:
            if obj['Key'].endswith('.csv'):
                print("Reading file: ", obj['Key'])
                telemtery_csv_data = s3.get_object(Bucket=telemetry_s3Bucket, Key=obj['Key'])["Body"].read().decode('utf-8').splitlines()
                telemtery_csvreader = csv.reader(telemtery_csv_data)
                next(telemtery_csvreader) #skip the header

                for row in telemtery_csvreader:
                    device_name = row[1]
                    if device_name == device_id:
                        indoor_temperature_c = row[2]
                        outdoor_temperature_c = row[3]
                        setpoint_temperature_c = row[4]
                        mode = row[5]
                        power_consumption_watts = row[6]
                        compressor_status = row[7]
                        fan_speed_rpm = row[8]
                        refrigerant_pressure_psi = row[9]
                        error_code = row[10]
                        filter_status = row[11]
                        timestamp = row[0]                        
                        
                        telemetry_data.append({
                            'device_id': device_id,
                            'indoor_temperature_c': indoor_temperature_c,
                            'outdoor_temperature_c': outdoor_temperature_c,
                            'setpoint_temperature_c': setpoint_temperature_c,
                            'mode': mode,
                            #'indoor_humidity_percent': indoor_humidity_percent,
                            #'outdoor_humidity_percent': outdoor_humidity_percent,
                            'watts': power_consumption_watts,
                            'compressor_status': compressor_status,
                            'fan_speed_rpm': fan_speed_rpm,
                            'refrigerant_pressure_psi': refrigerant_pressure_psi,
                            'error_code': error_code,
                            'filter_status': filter_status,
                            'timestamp': timestamp
                            })
                 
    return telemetry_data


def lambda_handler(event, context):
    try:
        print(event)
        agent = event['agent']
        actionGroup = event['actionGroup']
        function = event['function']
        parameters = event.get('parameters', [])

        # Create a dictionary from the parameters list
        params_dict = {param['name']: param['value'] for param in parameters}

        
        unique_id = params_dict['unique_id']  
        device_id = params_dict['device_id'] 

        if function == 'fetch_ticket_data':
            ticket_data = get_ticket_data(unique_id, device_id)
            action = "Fetched ticket data: " + str(ticket_data) 
            print(action)

        elif function == 'fetch_telemetry_data':
            ticket_data = get_ticket_data(unique_id, device_id)

            start_datetime = (ticket_data[0]['anomaly_start'])
            end_datetime = (ticket_data[0]['anomaly_end'])

            telemetry_data = get_device_telemetry_data(device_id, start_datetime, end_datetime)
            print(telemetry_data)
            
            action = "Fetched telemetry data : " + str(telemetry_data) 
            print(action)

        else:
            action = "No action needs to be taken"
            print(action)

        # Execute your business logic here. For more information, refer to: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html
        responseBody =  {
            "TEXT": {
                #"body": "The function {} was called successfully!".format(function)
                "body": action
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
    