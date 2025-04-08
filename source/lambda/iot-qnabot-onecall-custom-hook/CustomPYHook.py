import traceback
import boto3
import json
import logging
import time
import os
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#Environment Variables
AGENT_ID = os.environ['AGENT_ID']
AGENT_ALIAS_ID = os.environ['AGENT_ALIAS_ID']
#DYNAMODB_TABLE = os.environ['DYNAMODB_TABLE']

def query_device_data(device_type):
    try:
        dynamodb = boto3.client('dynamodb')
        
        response = dynamodb.get_item(
            TableName='iot-qnabot-onecall-device-data',
            Key={'deviceid': {'S': device_type}},
            ConsistentRead=False
        )
        
        # Check if item exists
        if 'Item' not in response:
            logger.info(f"No device found with ID: {device_type}")
            return None
        
        # Convert DynamoDB AttributeValue to standard dictionary
        item = response['Item']
        converted_data = {
            key: value['S'] 
            for key, value in item.items() 
            if 'S' in value
        }
        
        logger.info(f"Device data retrieved: {json.dumps(converted_data, indent=2)}")
        return converted_data
    
    except ClientError as e:
        logger.error(f"DynamoDB error: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error querying device data: {str(e)}")
        return None

def handle_device_info(event):
    """
    Handle the IOT.DeviceInfo intent by querying and formatting device information.
    
    Args:
        event (dict): The Lambda event object containing request details
        
    Returns:
        dict: Updated event object with response message
    """
    try:
        # Extract device type from slots
        device_type = (
            event.get('req', {})
            .get('slots', {})
            .get('DeviceType', '')
        )
        
        if not device_type:
            raise ValueError("No device type provided")
        
        # Query device data
        device_data = query_device_data(device_type)
        
        # Handle case where no data is found
        if not device_data:
            event['res']['message'] = f"No data found for device {device_type}"
            logger.info(f"event {json.dumps(event,indent=2)}")
            return event
        
        # Format response with device details
        message = f"""Device Details for {device_type}:
                    Address: {device_data.get('device_location_address', 'N/A')}
                    City: {device_data.get('device_location_city', 'N/A')}
                    State: {device_data.get('device_location_state', 'N/A')}
                    Zip: {device_data.get('device_location_zip', 'N/A')}
                    Country: {device_data.get('device_location_country', 'N/A')}
                    Site Owner: {device_data.get('siteowner', 'N/A')}
                    Site Owner Contact: {device_data.get('siteownercontact', 'N/A')}"""
        
        event['res']['message'] = message
        event['res']['session']['appContext']['altMessages']['markdown'] = message
        logger.info(f"{json.dumps(event,indent=2)}")
        return event
        
    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        event['res']['message'] = str(ve)
        return event
    except Exception as e:
        logger.error(f"Error processing device info: {str(e)}", exc_info=True)
        event['res']['message'] = "An error occurred while processing your request"
        return event

def format_to_markdown(text):
    """
    Convert a plain text string into Markdown format based on basic syntax rules.
    
    Args:
        text (str): The input text to be formatted into Markdown.
    
    Returns:
        str: The text formatted in Markdown.
    """
    # Split the text into lines for processing
    lines = text.strip().split('\n')
    markdown_lines = []
    in_list = False  # Track if we're in a list
    
    for line in lines:
        line = line.strip()
        if not line:
            # Preserve empty lines as paragraph breaks
            markdown_lines.append('')
            in_list = False  # Reset list state after a blank line
            continue

        # Detect headers (assuming lines starting with 'Header:' or all caps are headers)
        if line.startswith('Header:') or line.isupper():
            header_text = line.replace('Header:', '').strip()
            markdown_lines.append(f'## {header_text}')
            in_list = False
            continue

        # Detect lists (lines starting with '-', '*', or numbers like '1.')
        if line.startswith(('-', '*')) or (line.split('.')[0].isdigit() and line.split('.')[1].strip()):
            if line.startswith(('-', '*')):
                # Unordered list
                markdown_lines.append(f'- {line[1:].strip()}')
                in_list = True
            else:
                # Ordered list
                num, content = line.split('.', 1)
                markdown_lines.append(f'{num.strip()}. {content.strip()}')
                in_list = True
            continue

        # Detect bold/italic (e.g., words surrounded by * or ** in the original text)
        import re
        line = re.sub(r'\*\*(.+?)\*\*', r'**\1**', line)  # Preserve existing bold
        line = re.sub(r'\*(.+?)\*', r'*\1*', line)        # Preserve existing italic
        # Simple heuristic: capitalize words in quotes as bold
        line = re.sub(r'"([^"]+)"', r'**\1**', line)

        # Detect links (e.g., text with http:// or https://)
        line = re.sub(r'(https?://[^\s]+)', r'[\1](\1)', line)

        # Detect code (e.g., text in backticks or prefixed with 'Code:')
        if line.startswith('Code:'):
            code_content = line.replace('Code:', '').strip()
            markdown_lines.append(f'```\n{code_content}\n```')
            in_list = False
        elif '`' in line:
            # Inline code
            line = re.sub(r'`([^`]+)`', r'`\1`', line)
            markdown_lines.append(line)
            in_list = False
        else:
            # Regular paragraph or continuation of list
            if in_list:
                markdown_lines.append(f'  {line}')  # Indent as list continuation
            else:
                markdown_lines.append(line)

    # Join lines with proper Markdown spacing
    return '\n\n'.join(markdown_lines)

def handle_iot_anomaly(event, context, logger):
    """
    Handle IOT.Anomaly events by invoking Bedrock agent and processing the response.
    
    Args:
        event (dict): The event object containing request details
        context (object): Lambda context object
        logger (Logger): Logger instance for logging
    
    Returns:
        dict: Modified event object with response message
    """
    logger.info("Processing IOT.Anomaly event")
    
    try:
        # Initialize Bedrock agent client
        bedrock_agent = boto3.client('bedrock-agent-runtime')
        logger.debug("Bedrock agent client initialized")
        
        # Extract input transcript and session ID from event
        input_transcript = (event.get('req', {})
            .get('_event', {})
            .get('inputTranscript', ''))
        
        session_id = (event.get('req', {})
            .get('_event', {})
            .get('sessionId', ''))

        # Prepare request parameters
        request_parameters = {
            'agentId': AGENT_ID,
            'agentAliasId': AGENT_ALIAS_ID,
            'sessionId': session_id,
            'inputText': input_transcript
        }
        logger.info(f"Request parameters prepared: {json.dumps(request_parameters, indent=2)}")
        
        # Invoke Bedrock agent and get response
        response = bedrock_agent.invoke_agent(**request_parameters)
        complete_response = process_bedrock_response(response, logger)
        
        # Update event with response
        if complete_response:
            event['res']['message'] = complete_response
            event['res']['session']['appContext']['altMessages']['markdown'] = complete_response
            logger.info("Response message set successfully")
        else:
            event['res']['message'] = "No response received from the agent"
            logger.warning("No response content to set")
            
    except Exception as e:
        logger.error(f"Error invoking Bedrock agent: {str(e)}")
        logger.error(f"Error details: {traceback.format_exc()}")
        event['res']['message'] = f"Error processing anomaly detection request: {str(e)}"
    
    logger.info(f"Final event object: {json.dumps(event, indent=2)}")
    return event

def process_bedrock_response(response, logger):
    """
    Process the streaming response from Bedrock agent.
    
    Args:
        response (dict): Response from Bedrock agent
        logger (Logger): Logger instance for logging
    
    Returns:
        str: Concatenated response text
    """
    complete_response = ""
    chunk_count = 0
    logger.info("Starting to process response stream...")
    
    for agent_event in response['completion']:
        chunk_count += 1
        logger.debug(f"Processing chunk {chunk_count}")
        
        if 'chunk' in agent_event:
            chunk_obj = agent_event['chunk']
            
            if 'bytes' in chunk_obj:
                chunk_text = chunk_obj['bytes'].decode('utf-8')
                logger.debug(f"Decoded chunk text: {chunk_text}")
                complete_response += chunk_text
            else:
                logger.warning("No 'bytes' found in chunk object")
        else:
            logger.warning("No 'chunk' found in agentEvent")
    
    logger.info(f"Stream processing complete. Total chunks processed: {chunk_count}")
    logger.info(f"Final Bedrock agent response: {complete_response}")
    
    return complete_response

def handle_markdown(event):
    markdown_text = "# AWS QnABotThe Q and A Bot uses [Amazon Lex](https://aws.amazon.com/lex) and [Alexa](https://developer.amazon.com/alexa) to provide a natural language interface for your FAQ knowledge base.Now your users can just ask a *question* and get a quick and relevant *answer*."
    # Update the event with the formatted Markdown text
    event['res']['message'] = markdown_text
    event['res']['result']['alt']['markdown'] = markdown_text
    event['res']['session']['appContext']['altMessages']['markdown'] = markdown_text
    logger.info(f"event message being sent back: {json.dumps(event,indent=2)}")
    return event

def handler(event, context):
    logger.info(f"handler event: {json.dumps(event,indent=2)}")
    try:
        #Look for 'qid': 'IOT.DeviceInfo'
        qid = (
            event.get('res', {})
            .get('result', {})
            .get('qid', {})
        )

        if (qid == 'IOT.DeviceInfo'):
            return handle_device_info(event)
        elif (qid == 'IOT.Anomaly'):
            return handle_iot_anomaly(event, context, logger)
        elif (qid == 'IOT.TestMarkdown'):
            return handle_markdown(event)
        else:
            event['res']['message'] = f"Unknown QID: {qid}"
            return event
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        event['res']['message'] = "An error occurred processing the request"
        logger.info(f"{json.dumps(event,indent=2)}")
        return event
