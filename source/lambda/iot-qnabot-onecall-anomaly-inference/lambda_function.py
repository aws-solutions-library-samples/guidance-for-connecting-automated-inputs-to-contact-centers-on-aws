import json
import utils
import os

def lambda_handler(event, context):
    
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    model_name = os.environ.get('ANOMALY_ML_MODEL_NAME')

    files = utils.get_files_from_previous_hour(bucket_name)
    df = utils.create_dataframe_from_s3_files(bucket_name, files)
    s3_prefix = utils.send_dataframe_to_s3(df, bucket_name, "telemetry/aggregated-telemetry")
    utils.create_sagemaker_batch_inference_job(bucket_name, s3_prefix, model_name)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
