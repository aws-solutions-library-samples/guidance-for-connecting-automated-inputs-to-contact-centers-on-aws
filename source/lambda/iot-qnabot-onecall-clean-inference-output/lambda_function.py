import json
import pandas as pd
import boto3
import io
import numpy as np
from datetime import datetime

s3 = boto3.client('s3')

def lambda_handler(event, context):

    print("event : ", event)

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    # Check if the file has the correct extension
    if not key.endswith('.csv.out'):
        print(f"Skipping file {key} as it doesn't have the .csv.out extension")
        return
    
    try:
        # Read the CSV file from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        file_content = response['Body'].read()
        
        # Load the CSV data into a pandas DataFrame
        df = pd.read_csv(io.BytesIO(file_content))
        
        # Perform preprocessing
        df = preprocess_data(df)
        
        # Save the preprocessed data back to S3
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)

        timestamp = datetime.now().strftime("%Y/%m/%d/%H")
        s3.put_object(Bucket=bucket, Key=f"telemetry/processed-output/{timestamp}/inference_output.csv", Body=csv_buffer.getvalue())
        
        print(f"Successfully preprocessed and saved {key}")
    
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        raise
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }


def preprocess_data(df):
    df = df.iloc[:, :-2]
    print("columns : " , df.columns)

    if 'normal' in df.columns:
        df = df.rename(columns={'normal': 'anomaly'})
    else:
        print("Column 'normal' not found in the DataFrame")

    #df['warning'] = df['anomaly'].apply(lambda x: 'W1' if x != 'normal' else '')
    # Assuming your dataframe is called 'df'
    df['error_code'] = np.where(
        (df['error_code'].isna() | (df['error_code'] == 'None')) & (df['anomaly'] != 'normal'),
        'W1',
        df['error_code']
    )

    # Replace any remaining NaN values with 'None'
    df['error_code'] = df['error_code'].fillna('None')
    
    # Add W1 for the anomaly rows :
    #df['error_code'] = df.apply(lambda row: 'W1' if row['anomaly'] != 'normal' and pd.notna(row['error_code']) else row['error_code'], axis=1)


    return df