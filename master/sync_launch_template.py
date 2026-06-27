#!/usr/bin/env python3
"""
Script to sync launch template "orchestration-slave" from ap-south-1 (Mumbai) 
to all AWS regions.

If the template doesn't exist in a region, it will be copied from Mumbai.
If it exists, it will be replaced to match the Mumbai version.

IMPORTANT: 
- Removes BlockDeviceMappings (snapshot overrides) when creating templates in 
  other regions, since snapshots don't exist across regions.
- Removes security group references and creates a new region-specific security 
  group in each target region with:
  * Inbound: Port 22 (SSH) open to all IPs (0.0.0.0/0)
  * Outbound: All traffic open to all IPs (0.0.0.0/0)
- Removes key pair references (KeyName) as they are region-specific.
- The AMI will be dynamically resolved by the launch code, so this is safe.
"""

import os
import time
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Dict, Any, Optional, Tuple

# Load environment variables
load_dotenv()

# Launch template ID from environment
LAUNCH_TEMPLATE_ID = os.getenv('LAUNCH_TEMPLATE_ID')
SOURCE_REGION = "ap-south-1"


def get_ec2_client(region: str):
    """Get EC2 client for a specific region."""
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    if aws_access_key_id and aws_secret_access_key:
        return boto3.client(
            'ec2',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region
        )
    else:
        return boto3.client('ec2', region_name=region)


def get_latest_ubuntu_ami(ec2_client, region: str) -> Optional[str]:
    """Get the latest Ubuntu 22.04 AMI for the region."""
    # Try different AMI name patterns as fallback
    ami_patterns = [
        'ubuntu/images/hvm-ssd/ubuntu-22.04-amd64-server-*',
        'ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*',
        'ubuntu/images/hvm-ssd/ubuntu-22.04-*-amd64-server-*',
    ]
    
    for pattern in ami_patterns:
        try:
            response = ec2_client.describe_images(
                Owners=['099720109477'],  # Canonical (Ubuntu)
                Filters=[
                    {'Name': 'name', 'Values': [pattern]},
                    {'Name': 'state', 'Values': ['available']},
                ]
            )
            
            if 'Images' in response and len(response['Images']) > 0:
                # Sort by creation date, most recent first
                images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
                latest_ami = images[0]['ImageId']
                return latest_ami
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            print(f"    Error with pattern '{pattern}': {error_code} - {error_msg}")
            continue
        except Exception as e:
            print(f"    Unexpected error with pattern '{pattern}': {str(e)}")
            continue
    
    # If all patterns failed, try without name filter as last resort
    try:
        response = ec2_client.describe_images(
            Owners=['099720109477'],  # Canonical (Ubuntu)
            Filters=[
                {'Name': 'description', 'Values': ['*Ubuntu*22.04*']},
                {'Name': 'state', 'Values': ['available']},
            ]
        )
        
        if 'Images' in response and len(response['Images']) > 0:
            # Filter for 22.04 and sort by creation date
            ubuntu_2204_images = [
                img for img in response['Images']
                if '22.04' in img.get('Name', '') or '22.04' in img.get('Description', '')
            ]
            if ubuntu_2204_images:
                images = sorted(ubuntu_2204_images, key=lambda x: x['CreationDate'], reverse=True)
                latest_ami = images[0]['ImageId']
                print(f"    Found AMI using description filter: {latest_ami}")
                return latest_ami
    except Exception as e:
        print(f"    Error with description filter: {str(e)}")
    
    print(f"    No Ubuntu 22.04 AMI found in {region}")
    return None


def get_all_regions() -> list:
    """Get all available AWS regions."""
    try:
        ec2_client = get_ec2_client(SOURCE_REGION)
        response = ec2_client.describe_regions()
        return [region['RegionName'] for region in response['Regions']]
    except Exception as e:
        print(f"Error getting regions: {str(e)}")
        raise


def get_default_vpc(ec2_client) -> Optional[str]:
    """Get the default VPC ID for the region."""
    try:
        response = ec2_client.describe_vpcs(
            Filters=[{'Name': 'isDefault', 'Values': ['true']}]
        )
        if response['Vpcs']:
            return response['Vpcs'][0]['VpcId']
        
        # If no default VPC, get the first available VPC
        response = ec2_client.describe_vpcs()
        if response['Vpcs']:
            return response['Vpcs'][0]['VpcId']
        
        return None
    except Exception as e:
        print(f"Error getting VPC: {str(e)}")
        return None


def get_or_create_security_group(ec2_client, region: str, sg_name: str = "orchestration-slave-sg") -> Optional[str]:
    """Get or create a security group for the launch template.
    
    Security group rules:
    - Inbound: Port 22 (SSH) open to all IPs (0.0.0.0/0)
    - Outbound: All traffic open to all IPs (0.0.0.0/0)
    """
    try:
        # First, try to find existing security group
        try:
            response = ec2_client.describe_security_groups(
                Filters=[{'Name': 'group-name', 'Values': [sg_name]}]
            )
            if response['SecurityGroups']:
                sg_id = response['SecurityGroups'][0]['GroupId']
                print(f"  [{region}] Using existing security group: {sg_id}")
                return sg_id
        except ClientError:
            pass
        
        # Get default VPC
        vpc_id = get_default_vpc(ec2_client)
        if not vpc_id:
            print(f"  [{region}] ✗ No VPC found in region")
            return None
        
        print(f"  [{region}] Creating security group in VPC: {vpc_id}")
        
        # Create security group
        response = ec2_client.create_security_group(
            GroupName=sg_name,
            Description="Security group for orchestration-slave launch template (auto-created)",
            VpcId=vpc_id
        )
        sg_id = response['GroupId']
        
        # Add inbound rule: SSH (port 22) from anywhere
        try:
            ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH from anywhere'}]
                    }
                ]
            )
        except ClientError as e:
            # Ignore duplicate ingress rule errors
            if e.response.get('Error', {}).get('Code') != 'InvalidPermission.Duplicate':
                raise
        
        # Add outbound rule: All traffic to anywhere
        # Note: AWS security groups have a default egress rule allowing all traffic,
        # so this might already exist - we'll handle the duplicate error gracefully
        try:
            ec2_client.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': '-1',  # All protocols
                        'FromPort': -1,
                        'ToPort': -1,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'All outbound traffic'}]
                    }
                ]
            )
        except ClientError as e:
            # Default egress rule already allows all traffic, so duplicate is expected
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'InvalidPermission.Duplicate':
                # This is fine - the default rule already allows all outbound traffic
                pass
            else:
                # Re-raise if it's a different error
                raise
        
        print(f"  [{region}] ✓ Created security group: {sg_id}")
        return sg_id
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        
        # If security group already exists (race condition), try to get it
        if error_code == 'InvalidGroup.Duplicate':
            try:
                response = ec2_client.describe_security_groups(
                    Filters=[{'Name': 'group-name', 'Values': [sg_name]}]
                )
                if response['SecurityGroups']:
                    sg_id = response['SecurityGroups'][0]['GroupId']
                    print(f"  [{region}] Security group already exists: {sg_id}")
                    return sg_id
            except:
                pass
        
        print(f"  [{region}] ✗ Error creating security group: {error_code} - {error_msg}")
        return None
    except Exception as e:
        print(f"  [{region}] ✗ Error with security group: {str(e)}")
        return None


def get_launch_template_data_and_name(ec2_client, template_id: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Get the latest version of a launch template by ID and return both data and name."""
    try:
        # Get the latest version of the launch template by ID
        response = ec2_client.describe_launch_template_versions(
            LaunchTemplateId=template_id,
            Versions=['$Latest']
        )
        
        if 'LaunchTemplateVersions' in response and len(response['LaunchTemplateVersions']) > 0:
            version = response['LaunchTemplateVersions'][0]
            template_data = version['LaunchTemplateData']
            template_name = version['LaunchTemplateName']
            return (template_data, template_name)
        
        return None
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"  Error code: {error_code}, Message: {error_msg}")
        
        # If not found, list available templates for debugging
        try:
            list_response = ec2_client.describe_launch_templates()
            templates = list_response.get('LaunchTemplates', [])
            print(f"  Available launch templates in this region:")
            for template in templates:
                print(f"    - {template['LaunchTemplateName']} (ID: {template['LaunchTemplateId']})")
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting launch template data: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def template_exists(ec2_client, template_name: str) -> bool:
    """Check if a launch template exists in the region."""
    try:
        ec2_client.describe_launch_templates(LaunchTemplateNames=[template_name])
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidLaunchTemplateName.NotFoundException':
            return False
        raise
    except Exception as e:
        print(f"Error checking if template exists: {str(e)}")
        raise


def delete_launch_template(ec2_client, template_name: str) -> bool:
    """Delete a launch template."""
    try:
        ec2_client.delete_launch_template(LaunchTemplateName=template_name)
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"Error deleting launch template: {error_code} - {error_msg}")
        return False
    except Exception as e:
        print(f"Error deleting launch template: {str(e)}")
        return False


def create_launch_template(ec2_client, template_name: str, template_data: Dict[str, Any], region: str) -> bool:
    """Create a launch template with the given data, using the latest Ubuntu AMI for the region.
    
    IMPORTANT: 
    - Removes BlockDeviceMappings to avoid snapshot references that don't exist in other regions
    - Removes security group references and creates a new region-specific security group
    - Removes key pair references (KeyName) as they are region-specific
    - The AMI will be dynamically resolved by the launch code
    """
    try:
        # Copy all fields from template_data
        create_data = template_data.copy()
        
        # CRITICAL: Remove BlockDeviceMappings to avoid snapshot references
        # Snapshots don't exist across regions, so we must remove storage overrides
        if "BlockDeviceMappings" in create_data:
            print(f"  [{region}] Removing BlockDeviceMappings (snapshot overrides)...")
            del create_data["BlockDeviceMappings"]
        
        # CRITICAL: Remove security group references (they don't exist in other regions)
        # We'll create a new security group for this region
        if "SecurityGroupIds" in create_data:
            print(f"  [{region}] Removing SecurityGroupIds (region-specific)...")
            del create_data["SecurityGroupIds"]
        
        if "SecurityGroups" in create_data:
            print(f"  [{region}] Removing SecurityGroups (region-specific)...")
            del create_data["SecurityGroups"]
        
        # CRITICAL: Remove key pair references (they don't exist in other regions)
        if "KeyName" in create_data:
            print(f"  [{region}] Removing KeyName (region-specific)...")
            del create_data["KeyName"]
        
        # Get or create security group for this region
        print(f"  [{region}] Getting/creating security group...")
        sg_id = get_or_create_security_group(ec2_client, region)
        
        if not sg_id:
            print(f"  [{region}] ✗ Failed to get/create security group")
            return False
        
        # Add the new security group to template data
        create_data['SecurityGroupIds'] = [sg_id]
        
        # Get the latest Ubuntu AMI for this region
        print(f"  [{region}] Getting latest Ubuntu 22.04 AMI...")
        latest_ami = get_latest_ubuntu_ami(ec2_client, region)
        
        if not latest_ami:
            print(f"  [{region}] ✗ Failed to get latest Ubuntu AMI")
            return False
        
        # Replace the ImageId with the latest Ubuntu AMI for this region
        create_data['ImageId'] = latest_ami
        print(f"  [{region}] Using AMI: {latest_ami}")
        
        ec2_client.create_launch_template(
            LaunchTemplateName=template_name,
            LaunchTemplateData=create_data,
            VersionDescription="Snapshot-free, region-specific security group auto-created version"
        )
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"Error creating launch template: {error_code} - {error_msg}")
        return False
    except Exception as e:
        print(f"Error creating launch template: {str(e)}")
        return False


def sync_template_to_region(region: str, template_data: Dict[str, Any], template_name: str) -> bool:
    """Sync the launch template to a specific region."""
    try:
        ec2_client = get_ec2_client(region)
        
        # Check if template exists
        exists = template_exists(ec2_client, template_name)
        
        if exists:
            print(f"  [{region}] Template exists, deleting old version...")
            if not delete_launch_template(ec2_client, template_name):
                print(f"  [{region}] Failed to delete existing template")
                return False
            # Wait a moment for deletion to propagate
            time.sleep(1)
        
        # Create the template
        print(f"  [{region}] Creating launch template...")
        if create_launch_template(ec2_client, template_name, template_data, region):
            print(f"  [{region}] ✓ Successfully synced launch template")
            return True
        else:
            print(f"  [{region}] ✗ Failed to create launch template")
            return False
            
    except Exception as e:
        print(f"  [{region}] ✗ Error syncing template: {str(e)}")
        return False


def main():
    """Main function to sync launch template across all regions."""
    print(f"Syncing launch template from {SOURCE_REGION} to all AWS regions...")
    print("=" * 70)
    
    try:
        # Check if template ID is configured
        if not LAUNCH_TEMPLATE_ID:
            print("✗ LAUNCH_TEMPLATE_ID not found in environment variables")
            print("  Please set LAUNCH_TEMPLATE_ID in your .env file or environment")
            return
        
        # Get source template data
        print(f"\n[1/3] Fetching launch template from {SOURCE_REGION}...")
        print(f"  Using template ID: {LAUNCH_TEMPLATE_ID}")
        source_ec2_client = get_ec2_client(SOURCE_REGION)
        
        result = get_launch_template_data_and_name(source_ec2_client, LAUNCH_TEMPLATE_ID)
        
        if not result:
            print(f"\n✗ Launch template with ID '{LAUNCH_TEMPLATE_ID}' not found in {SOURCE_REGION}")
            print(f"  Please verify the template ID and that you have permissions to access it.")
            return
        
        template_data, template_name = result
        print(f"✓ Found launch template '{template_name}' (ID: {LAUNCH_TEMPLATE_ID}) in {SOURCE_REGION}")
        
        # Get all regions
        print(f"\n[2/3] Getting list of all AWS regions...")
        regions = get_all_regions()
        print(f"✓ Found {len(regions)} regions")
        
        # Sync to all regions (excluding source region)
        print(f"\n[3/3] Syncing launch template '{template_name}' to all regions...")
        print("-" * 70)
        
        success_count = 0
        fail_count = 0
        skipped_count = 0
        
        for region in regions:
            if region == SOURCE_REGION:
                print(f"  [{region}] Skipping source region")
                skipped_count += 1
                continue
            
            if sync_template_to_region(region, template_data, template_name):
                success_count += 1
            else:
                fail_count += 1
        
        # Summary
        print("-" * 70)
        print(f"\nSummary:")
        print(f"  ✓ Successfully synced: {success_count} regions")
        print(f"  ✗ Failed: {fail_count} regions")
        print(f"  ⊘ Skipped: {skipped_count} region ({SOURCE_REGION})")
        print(f"  Total regions processed: {len(regions) - skipped_count}")
        
    except NoCredentialsError:
        print("✗ AWS credentials not configured")
        print("Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()

