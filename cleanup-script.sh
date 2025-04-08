#!/bin/bash

# Check if bucket name is provided
if [ -z "$1" ]; then
    echo "Error: S3 bucket name is required"
    echo "Usage: $0 <bucket-name>"
    exit 1
fi


bucket_name=$1

# Empty the bucket first
aws s3 rm s3://$bucket_name --recursive

# Delete the bucket
aws s3api delete-bucket --bucket $bucket_name