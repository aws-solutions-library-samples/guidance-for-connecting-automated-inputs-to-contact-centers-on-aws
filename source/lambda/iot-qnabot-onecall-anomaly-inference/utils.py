import pandas as pd
import json
from datetime import datetime, timedelta
import boto3
import io
from io import StringIO
import csv

def get_files_from_previous_hour(bucket_name):
    # Create an S3 client
    s3 = boto3.client('s3')

    # Get the current time and calculate the previous hour
    current_time = datetime.now()
    previous_hour = current_time - timedelta(hours=1)
    print("previous hour : ", previous_hour)
    # Format the prefix
    prefix = previous_hour.strftime('telemetry/firehose-streaming-data/%Y/%m/%d/%H/')

    print(f"Searching for files with prefix: {prefix}")

    # List objects in the bucket with the specified prefix
    paginator = s3.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    file_list = []

    # Iterate through pages and collect file names
    for page in page_iterator:
        if 'Contents' in page:
            for obj in page['Contents']:
                file_list.append(obj['Key'])

    return file_list

def create_dataframe_from_s3_files(bucket_name, file_list):
    s3 = boto3.client('s3')
    all_data = []

    for file in file_list:
        try:
            # Read the file content from S3
            response = s3.get_object(Bucket=bucket_name, Key=file)
            file_content = response['Body'].read().decode('utf-8')

            # Process each line as a separate JSON object
            for line in file_content.splitlines():
                if line.strip():  # Skip empty lines
                    try:
                        json_data = json.loads(line)
                        json_data['timestamp'] = datetime.utcnow().isoformat()
                        all_data.append(json_data)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON in file {file}, line: {line}")
                        print(f"Error details: {str(e)}")

        except Exception as e:
            print(f"Error processing file {file}: {str(e)}")

    # Create DataFrame from all collected data
    if all_data:
        df = pd.DataFrame(all_data)
        df['power_consumption_watts'] = pd.to_numeric(df['power_consumption_watts'], downcast='integer')

        return df
    else:
        print("No valid data found in the files.")
        return None

def send_dataframe_to_s3(df, bucket_name, prefix):
    """
    Send a DataFrame to S3 as a CSV file.
    
    :param df: pandas DataFrame to send
    :param bucket_name: Name of the S3 bucket
    :param prefix: S3 prefix (folder) to store the file
    """
    s3 = boto3.client('s3')
    new_columns = ['timestamp', 'device_name', 'indoor_temperature_c',
       'outdoor_temperature_c', 'setpoint_temperature_c', 'mode',
       'power_consumption_watts', 'compressor_status', 'fan_speed_rpm',
       'refrigerant_pressure_psi', 'error_code', 'filter_status',
       'runtime_hours']

    # Reorder the columns
    df = df.reindex(columns=new_columns)
    df["error_code"] = df["error_code"].fillna(value="None")

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Create a buffer
    csv_buffer = StringIO()
    
    # Write the DataFrame to the buffer
    df.to_csv(csv_buffer, index=False, header=False))
    
    # Generate a timestamp for the file name
    timestamp = datetime.now().strftime("%Y/%m/%d/%H")
    
    # Create the S3 object key (file path)
    s3_key = f"{prefix}/{timestamp}/processed_data.csv"
    
    # Upload the file to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=csv_buffer.getvalue()
    )
    
    print(f"DataFrame successfully sent to S3: s3://{bucket_name}/{s3_key}")
    return s3_key

def create_sagemaker_batch_inference_job(s3_bucket, input_s3_path, model_name):
    sagemaker = boto3.client('sagemaker')
    timestamp = datetime.now().strftime("%Y%m%d-%H")
    output_path = datetime.now().strftime("%Y/%m/%d/%H")

    sagemaker.create_transform_job(
        TransformJobName=f'transform-job-{timestamp}',
        ModelName= model_name,
        MaxConcurrentTransforms=1,
        MaxPayloadInMB=6,
        BatchStrategy='MultiRecord',
        TransformInput={
            'DataSource': {
                'S3DataSource': {
                    'S3DataType': 'S3Prefix',
                    'S3Uri': f's3://{s3_bucket}/{input_s3_path}'
                }
            },
            'ContentType': 'text/csv',
            'SplitType': 'Line'
        },
        TransformOutput={
            'S3OutputPath': f's3://{s3_bucket}/telemetry/inference-output/{output_path}',
            "Accept": 'text/csv',
            'AssembleWith': 'Line'
        },
        TransformResources={
            'InstanceType': 'ml.m5.xlarge',
            'InstanceCount': 1
        },
        DataProcessing={
            'InputFilter': '$[:12]',
            #'OutputFilter': '$[:-2]',
            'JoinSource': 'Input'
        }
    )