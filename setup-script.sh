#!/bin/bash

set -eo pipefail

# -- S3 BUCKET CREATION --

# Generate a UUID
uuid=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Create the bucket name
bucket_name="iot-qnabot-onecall-$uuid"

# Create the S3 bucket using AWS CLI
aws s3api create-bucket --bucket $bucket_name --region us-east-1

# -- COPY FILES TO S3 BUCKET --

# Create "anomaly-ml-model/model-artifacts/" prefix
aws s3api put-object --bucket $bucket_name --key anomaly-ml-model/model-artifacts/

# Create "anomaly-ml-model/training-data/" prefix and copy the files
cd ./source/training_data/
aws s3 cp training_data.csv s3://$bucket_name/anomaly-ml-model/training-data/training_data.csv

# Create "knowledge-base/" prefix and copy the file
cd ../kb_doc/
aws s3 cp Troubleshooting_Guide.docx s3://$bucket_name/knowledge-base/Troubleshooting_Guide.docx

# Create "telemetry/firehose-streaming-data/" prefix
cd ../../
aws s3api put-object --bucket $bucket_name --key telemetry/firehose-streaming-data/

# Create "telemetry/aggregated-telemetry/" prefix
aws s3api put-object --bucket $bucket_name --key telemetry/aggregated-telemetry/

# Create "telemetry/inference-output/" prefix
aws s3api put-object --bucket $bucket_name --key telemetry/inference-output/

# Create "telemetry/processed-output/" prefix
aws s3api put-object --bucket $bucket_name --key telemetry/processed-output/

# Zip the Bedrock Agent Lambda functions required for the Bedrock Agent and upload to S3 bucket 
cd ./source/lambda/bedrock_agent_functions/iot-qnabot-onecall-user-query
zip iot-qnabot-onecall-user-query.zip lambda_function.py
aws s3 cp iot-qnabot-onecall-user-query.zip s3://$bucket_name/deployment/source/lambda/

cd ../iot-qnabot-onecall-triage
zip iot-qnabot-onecall-triage.zip lambda_function.py
aws s3 cp iot-qnabot-onecall-triage.zip s3://$bucket_name/deployment/source/lambda/

# Zip the Lambda function and the lambda layer required for the index creation in Amazon OpenSearch Serverless collection
cd ../../vector_index_creation
rm -rf python; mkdir python
cd python
pip3 install --target . -r ../requirements.txt
cd ..
zip -r lambda_layer.zip python
zip -r create_vector_index.zip cfnresponse.py index.py python

aws s3 cp create_vector_index.zip s3://$bucket_name/deployment/source/lambda/
aws s3 cp lambda_layer.zip s3://$bucket_name/deployment/source/lambda/

#iot-qnabot-onecall-anomaly-handler
cd ../iot-qnabot-onecall-anomaly-handler
zip iot-qnabot-onecall-anomaly-handler.zip index.py
aws s3 cp iot-qnabot-onecall-anomaly-handler.zip s3://$bucket_name/deployment/source/lambda/

#iot-qnabot-onecall-anomaly-inference
cd ../iot-qnabot-onecall-anomaly-inference
zip iot-qnabot-onecall-anomaly-inference.zip lambda_function.py utils.py
aws s3 cp iot-qnabot-onecall-anomaly-inference.zip s3://$bucket_name/deployment/source/lambda/

#iot-qnabot-onecall-clean-inference-output
cd ../iot-qnabot-onecall-clean-inference-output
zip iot-qnabot-onecall-clean-inference-output.zip lambda_function.py
aws s3 cp iot-qnabot-onecall-clean-inference-output.zip s3://$bucket_name/deployment/source/lambda/

#iot-qnabot-onecall-custom-hook
cd ../iot-qnabot-onecall-custom-hook
zip iot-qnabot-onecall-custom-hook.zip CustomPYHook.py
aws s3 cp iot-qnabot-onecall-custom-hook.zip s3://$bucket_name/deployment/source/lambda/

#iot-qnabot-onecall-error-handler
cd ../iot-qnabot-onecall-error-handler
zip iot-qnabot-onecall-error-handler.zip lambda_function.py
aws s3 cp iot-qnabot-onecall-error-handler.zip s3://$bucket_name/deployment/source/lambda/

#Copy IoT simulator content
cd ../..
aws s3 cp iot_simulator/ s3://$bucket_name/deployment/source/iot_simulator/ --recursive

#Copy cloudformation scripts
cd ..
aws s3 cp deployment/ s3://$bucket_name/deployment/cfn_script/ --recursive


echo "============================================================================================================================"
echo "SUCCESS: Following S3 bucket is created and deployment files are uploaded: ${bucket_name}"
echo "============================================================================================================================"