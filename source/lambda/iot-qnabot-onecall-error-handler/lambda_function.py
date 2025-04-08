import boto3
import json
import os
import uuid

bedrock_runtime = boto3.client('bedrock-agent-runtime')

def lambda_handler(event, context):
    print('Received event:', event)

    device_id = event["device_name"] 
    error_code = event["error_code"] 
    time_stamp = str(event["timestamp"])
    #unique_id = str(uuid.uuid4())

    #input_text = "Please take action based on the error details: {'unique_id':" + unique_id + ",   'device_id':" +  device_id + ",   'error_code':" + error_code +",   'time_stamp':" + time_stamp + "}"
    input_text = "Please take action based on the error details: {'device_id':" +  device_id + ",   'error_code':" + error_code +",   'time_stamp':" + time_stamp + "}"
    
    print(input_text)

    agent_id = os.environ.get('BEDROCK_AGENT_ID')
    agent_alias_id = os.environ.get('BEDROCK_AGENT_ALIAS_ID')
    
    response = bedrock_runtime.invoke_agent(
        agentId=agent_id,
        agentAliasId=agent_alias_id,
        sessionId=str(uuid.uuid4()),
        inputText=input_text
    )

    completion = ""

    for event in response.get("completion"):
        chunk = event["chunk"]
        completion = completion + chunk["bytes"].decode()
    
    print("Completion status: " + json.dumps (completion))

    return {
        'statusCode': 200,
        'body': json.dumps (completion)
    }
