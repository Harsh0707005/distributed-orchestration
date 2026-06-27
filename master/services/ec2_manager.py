import os
import boto3
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError, NoCredentialsError

def get_ec2_client(region: Optional[str] = None):
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = region or os.getenv('AWS_REGION', 'ap-south-1')
    
    if aws_access_key_id and aws_secret_access_key:
        return boto3.client(
            'ec2',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
    else:
        return boto3.client('ec2', region_name=aws_region)

def launch_instance_from_template(
    launch_template_id: Optional[str] = None,
    launch_template_name: Optional[str] = None,
    region: Optional[str] = None,
    min_count: int = 1,
    max_count: int = 1,
    tags: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Launch an instance from a launch template.
    
    Args:
        launch_template_id: Launch template ID (optional if launch_template_name is provided)
        launch_template_name: Launch template name (optional if launch_template_id is provided)
        region: AWS region to launch in (defaults to AWS_REGION env var or ap-south-1)
        min_count: Minimum number of instances
        max_count: Maximum number of instances
        tags: Tags to apply to the instance
    """
    try:
        ec2_client = get_ec2_client(region)
        
        # Build launch template specification
        launch_template_spec = {}
        if launch_template_id:
            launch_template_spec['LaunchTemplateId'] = launch_template_id
        elif launch_template_name:
            launch_template_spec['LaunchTemplateName'] = launch_template_name
        else:
            raise ValueError("Either launch_template_id or launch_template_name must be provided")
        
        kwargs = {
            'LaunchTemplate': launch_template_spec,
            'MinCount': min_count,
            'MaxCount': max_count
        }

        if tags:
            tag_list = [{'Key': k, 'Value': v} for k, v in tags.items()]
            kwargs['TagSpecifications'] = [
                {
                    'ResourceType': 'instance',
                    'Tags': tag_list
                }
            ]

        response = ec2_client.run_instances(**kwargs)
        
        if 'Instances' in response and len(response['Instances']) > 0:
            instance = response['Instances'][0]
            instance_id = instance['InstanceId']
            private_ip = instance.get('PrivateIpAddress', 'pending')
            public_ip = instance.get('PublicIpAddress', 'pending')
            
            return {
                'instance_id': instance_id,
                'private_ip': private_ip,
                'public_ip': public_ip,
                'state': instance['State']['Name'],
                'launch_time': instance.get('LaunchTime'),
                'region': region or os.getenv('AWS_REGION', 'ap-south-1')
            }
        
        return None
        
    except NoCredentialsError:
        print("AWS credentials not configured")
        raise Exception("AWS credentials not configured")
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"AWS EC2 error ({error_code}): {error_msg}")
        raise Exception(f"AWS EC2 error: {error_msg}")
    except Exception as e:
        print(f"Error launching EC2 instance: {str(e)}")
        raise Exception(f"Error launching EC2 instance: {str(e)}")

def get_instance_details(instance_id: str) -> Optional[Dict[str, Any]]:
    try:
        ec2_client = get_ec2_client()
        
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        
        if 'Reservations' in response and len(response['Reservations']) > 0:
            if 'Instances' in response['Reservations'][0] and len(response['Reservations'][0]['Instances']) > 0:
                instance = response['Reservations'][0]['Instances'][0]
                
                return {
                    'instance_id': instance['InstanceId'],
                    'private_ip': instance.get('PrivateIpAddress', 'N/A'),
                    'public_ip': instance.get('PublicIpAddress', 'N/A'),
                    'state': instance['State']['Name'],
                    'launch_time': instance.get('LaunchTime')
                }
        
        return None
        
    except Exception as e:
        print(f"Error getting instance details: {str(e)}")
        raise Exception(f"Error getting instance details: {str(e)}")

def terminate_instance(instance_id: str, region: Optional[str] = None) -> bool:
    """
    Terminate an EC2 instance.
    
    Args:
        instance_id: The EC2 instance ID
        region: AWS region where the instance is located (defaults to AWS_REGION env var or ap-south-1)
    """
    try:
        ec2_client = get_ec2_client(region)
        
        response = ec2_client.terminate_instances(InstanceIds=[instance_id])
        
        if 'TerminatingInstances' in response and len(response['TerminatingInstances']) > 0:
            return True
        
        return False
        
    except Exception as e:
        print(f"Error terminating instance: {str(e)}")
        raise Exception(f"Error terminating instance: {str(e)}")

