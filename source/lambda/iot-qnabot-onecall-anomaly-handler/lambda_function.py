import boto3
import json
import os
import uuid
import datetime
import io
import pandas as pd
import awswrangler as wr
import time

bedrock_runtime = boto3.client('bedrock-agent-runtime')
s3 = boto3.client('s3')

def lambda_handler(event, context):

  evaluation_period_hours = int(os.environ.get('TELEMETRY_EVALUATION_PERIOD_HOURS'))
  telemetry_s3Bucket = os.environ.get('TELEMETRY_ANOMALY_S3_BUCKET')
  current_datetime = datetime.datetime.now()
  start_datetime = (current_datetime - datetime.timedelta(hours=evaluation_period_hours)).strftime("%Y-%m-%dT%H:00:00.000")
  end_datetime = (current_datetime - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:59:00.000")

  print("Current datetime", current_datetime)
  print("Evaluation Start datetime: ", start_datetime)
  print("Evaluation End datetime: ", end_datetime)

  s3Paths = []

  #Get all the files in S3 to process
  for x in range(evaluation_period_hours):
    previous_hour = current_datetime - datetime.timedelta(hours=(x+1))
    prefix = previous_hour.strftime("telemetry/processed-output/%Y/%m/%d/%H")

    print("S3 prefix: ", prefix)

    #  Read all CSV files from S3
    response = s3.list_objects_v2(Bucket=telemetry_s3Bucket, Prefix=prefix)

    if 'Contents' not in response:
        print("No files found in path {}/{}!".format(telemetry_s3Bucket, prefix))
        return {
            'statusCode': 200,
            'body': 'Success'
        }

    for obj in response['Contents']:
        if obj['Key'].endswith('.csv'):
            print("Adding file to list of files to process: ", obj['Key'])
            s3Paths.append("s3://" + telemetry_s3Bucket + "/" + obj['Key'])
  
  # Read CSV files into Pandas dataframe
  telemetryData = wr.s3.read_csv(s3Paths)

  # Check if error_code is null or empty
  is_all_null = telemetryData['error_code'].isnull().all()

  if is_all_null:
    print("No errors and warnings found! Nothing to report!")
    return {
        'statusCode': 200,
        'body': 'Success'
    }

  # Select all rows except when error_code starts with E
  telemetryWarningData = telemetryData[~telemetryData['error_code'].str.startswith('E', na=False)]

  # Group rows by device name and get counts of each group
  telemetryDataCountByDevice = telemetryWarningData.filter(items=['device_name']).groupby(['device_name']).value_counts()

  # Select anomalies and groups rows by device name and error code with warnings
  telemetryAnamoliesCountByDeviceAndWarning = telemetryWarningData[telemetryWarningData['anomaly']=='abnormal'].filter(items=['device_name','error_code','timestamp']).groupby(['device_name','error_code'], as_index=False).agg(
      count = ('timestamp', 'count')
  )

  if telemetryAnamoliesCountByDeviceAndWarning.empty:
    print("No anomalies found! Nothing to report!")
    return {
        'statusCode': 200,
        'body': 'Success'
    }

  agent_id = os.environ.get('BEDROCK_AGENT_ID')
  agent_alias_id = os.environ.get('BEDROCK_AGENT_ALIAS_ID')
  anomaly_threshold = int(os.environ.get('TELEMETRY_ANOMALY_THRESHOLD'))

  print("Anomaly threshold: ", anomaly_threshold)
  
  for index, row in telemetryAnamoliesCountByDeviceAndWarning.iterrows():

    warning_rate = row['count']/telemetryDataCountByDevice[row['device_name']] * 100
    print("Device: ", row['device_name'])
    print("Warning rate: ", warning_rate)

    if warning_rate >= anomaly_threshold:
        anomalyEventJson = {
            "device_id": row['device_name'],
            "error_code": row['error_code'],
            "time_stamp": time.time(),
            "start_end_datetime": start_datetime + "," + end_datetime
        }
    else:
        print("Warning rate {} is less than anomaly threshold {} for device {} , skipping!".format(warning_rate, anomaly_threshold, row['device_name']))
        continue

    anomalyEventPrompt = "Please take action based on the anomaly details: " + json.dumps(anomalyEventJson)
    print(anomalyEventPrompt)

    try:
        print("Calling Bedrock agent to report anomalies!")
        # Invoke Bedrock agent with details of every anomaly
        response = bedrock_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=str(uuid.uuid4()),
            inputText=anomalyEventPrompt
        )

        # Sleep for 5 seconds to avoid Bedrock agent API call throttling
        time.sleep(5)
    except:
        raise RuntimeError('Error calling Bedrock agent to report anomalies!')

  return {
      'statusCode': 200,
      'body': 'Success'
  }