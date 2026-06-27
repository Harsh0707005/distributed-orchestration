import boto3
import json
import os
from typing import Dict, Any
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

load_dotenv()

AWS_SQS_URL_BATCHES = os.getenv('AWS_SQS_URL_BATCHES')
AWS_SQS_URL_PRIORITY_BATCHES = os.getenv('AWS_SQS_URL_PRIORITY_BATCHES')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')

sqs_client = None

def get_sqs_client():
    global sqs_client
    if sqs_client is None:
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            sqs_client = boto3.client(
                'sqs',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
        else:
            sqs_client = boto3.client('sqs', region_name=AWS_REGION)
    return sqs_client

def send_batch_to_sqs(batch_data: Dict[str, Any], priority: bool = False) -> bool:
    try:
        queue_url = AWS_SQS_URL_PRIORITY_BATCHES if priority else AWS_SQS_URL_BATCHES
        queue_name = "AWS_SQS_URL_PRIORITY_BATCHES" if priority else "AWS_SQS_URL_BATCHES"
        
        if not queue_url:
            print(f"{queue_name} not configured, skipping SQS push")
            return False
        
        client = get_sqs_client()
        message_body = json.dumps(batch_data)
        
        response = client.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body
        )
        
        queue_type = "priority" if priority else "regular"
        identifier = batch_data.get('batch_name') or batch_data.get('url', 'unknown')
        print(f"Successfully sent {queue_type} batch {identifier} to SQS. MessageId: {response.get('MessageId')}")
        return True
    except NoCredentialsError:
        print("AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file")
        return False
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'AccessDenied':
            print(f"AWS SQS Access Denied: The AWS credentials don't have permission to send messages to the queue.")
            print(f"Please ensure your IAM user/role has 'sqs:SendMessage' permission for queue: {AWS_SQS_URL_BATCHES}")
        else:
            print(f"AWS SQS error ({error_code}): {str(e)}")
        return False
    except Exception as e:
        print(f"Error sending batch to SQS: {str(e)}")
        return False

