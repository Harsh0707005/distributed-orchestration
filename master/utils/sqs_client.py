import boto3
import json
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError
from config.settings import AWS_SQS_URL_WEBSITES, AWS_SQS_URL_PRIORITY_WEBSITES

sqs_client = None

def get_sqs_client():
    global sqs_client
    if sqs_client is None:
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'ap-south-1')
        
        if aws_access_key_id and aws_secret_access_key:
            sqs_client = boto3.client(
                'sqs',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=aws_region
            )
        else:
            sqs_client = boto3.client('sqs', region_name=aws_region)
    return sqs_client

def send_website_to_sqs(website_data: Dict[str, Any], queue_url: Optional[str] = None) -> bool:
    try:
        if queue_url is None:
            queue_url = AWS_SQS_URL_WEBSITES
        
        is_priority_queue = (queue_url == AWS_SQS_URL_PRIORITY_WEBSITES)
        
        if not queue_url:
            queue_name = "AWS_SQS_URL_PRIORITY_WEBSITES" if is_priority_queue else "AWS_SQS_URL_WEBSITES"
            print(f"{queue_name} not configured, skipping SQS push")
            return False
        
        client = get_sqs_client()
        message_body = json.dumps(website_data)
        
        response = client.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body
        )
        
        queue_type = "priority" if is_priority_queue else "regular"
        print(f"Successfully sent website {website_data.get('url')} to {queue_type} SQS queue. MessageId: {response.get('MessageId')}")
        return True
    except NoCredentialsError:
        print("AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file")
        return False
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'AccessDenied':
            print(f"AWS SQS Access Denied: The AWS credentials don't have permission to send messages to the queue.")
            print(f"Please ensure your IAM user/role has 'sqs:SendMessage' permission for queue: {queue_url}")
        else:
            print(f"AWS SQS error ({error_code}): {str(e)}")
        return False
    except Exception as e:
        print(f"Error sending website to SQS: {str(e)}")
        return False

