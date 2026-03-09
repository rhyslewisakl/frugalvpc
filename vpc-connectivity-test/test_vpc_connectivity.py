#!/usr/bin/env python3
"""
VPC Connectivity Test Script - Fixed Version
Tests routing and connectivity for a given VPC by deploying test instances
"""

import boto3
import json
import time
import sys
import argparse
import uuid
import base64
from datetime import datetime
from typing import List, Dict, Any
import atexit

class VPCConnectivityTester:
    def __init__(self, vpc_id: str, region: str = 'ap-southeast-2'):
        self.vpc_id = vpc_id
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.ssm = boto3.client('ssm', region_name=region)
        self.iam = boto3.client('iam', region_name=region)
        self.resource_groups = boto3.client('resource-groups', region_name=region)
        
        # Generate UUID for resource tagging
        self.test_uuid = str(uuid.uuid4())
        self.tag_key = "FrugalVPCConnectivityTest"
        
        # Track resources for cleanup
        self.created_resources = {
            'instances': [],
            'security_groups': [],
            'iam_roles': [],
            'instance_profiles': [],
            'resource_group': None
        }
        
        # Register cleanup on exit
        atexit.register(self.cleanup_resources)
        
        self.test_results = []
        
    def run_test(self):
        """Main test execution"""
        print(f"Starting VPC connectivity test for {self.vpc_id}")
        print(f"Test UUID: {self.test_uuid}")
        
        try:
            # 1. Create resource group
            self.create_resource_group()
            
            # 2. Analyze VPC
            subnets = self.analyze_vpc()
            
            # 3. Create IAM resources
            self.create_iam_resources()
            
            # 4. Create security group
            sg_id = self.create_security_group()
            
            # 5. Launch test instances
            instances = self.launch_test_instances(subnets, sg_id)
            
            # 6. Wait for instances to be ready
            self.wait_for_instances_ready(instances)
            
            # 7. Run connectivity tests
            self.run_connectivity_tests(instances)
            
            # 8. Generate report
            self.generate_report()
            
        except Exception as e:
            print(f"Test failed: {e}")
            self.test_results.append({
                'test': 'Overall Test',
                'status': 'FAILED',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        finally:
            # 9. Cleanup
            self.cleanup_resources()
    
    def create_resource_group(self):
        """Create resource group for tracking test resources"""
        print("Creating resource group...")
        
        group_name = f"frugal-vpc-test-{self.test_uuid[:8]}"
        
        try:
            response = self.resource_groups.create_group(
                Name=group_name,
                Description=f"Resources for Frugal VPC connectivity test {self.test_uuid}",
                ResourceQuery={
                    'Type': 'TAG_FILTERS_1_0',
                    'Query': json.dumps({
                        'ResourceTypeFilters': ['AWS::AllSupported'],
                        'TagFilters': [{
                            'Key': self.tag_key,
                            'Values': [self.test_uuid]
                        }]
                    })
                },
                Tags={
                    self.tag_key: self.test_uuid,
                    'Purpose': 'VPC Connectivity Test'
                }
            )
            
            self.created_resources['resource_group'] = group_name
            print(f"Created resource group: {group_name}")
            
        except Exception as e:
            print(f"Warning: Could not create resource group: {e}")
    
    def get_common_tags(self):
        """Get common tags for all resources"""
        return [
            {'Key': self.tag_key, 'Value': self.test_uuid},
            {'Key': 'Purpose', 'Value': 'VPC Connectivity Test'},
            {'Key': 'VPC', 'Value': self.vpc_id}
        ]
    
    def analyze_vpc(self) -> List[Dict]:
        """Analyze VPC and get subnet information"""
        print("Analyzing VPC subnets...")
        
        response = self.ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
        )
        
        subnets = []
        public_count = 0
        private_count = 0
        
        for subnet in response['Subnets']:
            # Check if subnet is public by looking at route table
            rt_response = self.ec2.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}
                ]
            )
            
            is_public = False
            for rt in rt_response['RouteTables']:
                for route in rt['Routes']:
                    if (route.get('DestinationCidrBlock') == '0.0.0.0/0' and 
                        route.get('GatewayId', '').startswith('igw-')):
                        is_public = True
                        break
            
            subnet_info = {
                'subnet_id': subnet['SubnetId'],
                'cidr': subnet['CidrBlock'],
                'az': subnet['AvailabilityZone'],
                'is_public': is_public,
                'type': 'public' if is_public else 'private'
            }
            subnets.append(subnet_info)
            
            if is_public:
                public_count += 1
            else:
                private_count += 1
        
        print(f"Found {public_count} public and {private_count} private subnets")
        return subnets
    
    def create_iam_resources(self):
        """Create minimal IAM role for test instances"""
        print("Creating IAM resources...")
        
        role_name = f'vpc-test-role-{int(time.time())}'
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }
        
        self.iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Minimal role for VPC connectivity testing',
            Tags=self.get_common_tags()
        )
        
        # Attach SSM policy for remote commands
        self.iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
        )
        
        # Create instance profile
        profile_name = f'vpc-test-profile-{int(time.time())}'
        self.iam.create_instance_profile(
            InstanceProfileName=profile_name,
            Tags=self.get_common_tags()
        )
        self.iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name,
            RoleName=role_name
        )
        
        self.created_resources['iam_roles'].append(role_name)
        self.created_resources['instance_profiles'].append(profile_name)
        
        # Wait for IAM propagation
        time.sleep(10)
        
        return profile_name
    
    def create_security_group(self) -> str:
        """Create security group for test instances"""
        print("Creating security group...")
        
        sg_name = f'vpc-test-sg-{int(time.time())}'
        
        response = self.ec2.create_security_group(
            GroupName=sg_name,
            Description='Security group for VPC connectivity testing',
            VpcId=self.vpc_id,
            TagSpecifications=[{
                'ResourceType': 'security-group',
                'Tags': self.get_common_tags()
            }]
        )
        
        sg_id = response['GroupId']
        self.created_resources['security_groups'].append(sg_id)
        
        # Allow ICMP (ping) between test instances only
        self.ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'icmp',
                    'FromPort': -1,
                    'ToPort': -1,
                    'UserIdGroupPairs': [{'GroupId': sg_id}]
                }
            ]
        )
        
        return sg_id
    
    def launch_test_instances(self, subnets: List[Dict], sg_id: str) -> List[Dict]:
        """Launch spot instances in each subnet"""
        print("Launching test instances...")
        
        instances = []
        profile_name = self.created_resources['instance_profiles'][0]
        
        for subnet in subnets:
            print(f"Launching instance in {subnet['type']} subnet {subnet['subnet_id']}")
            
            # No user data needed since AL2023 has SSM agent pre-installed
            response = self.ec2.request_spot_instances(
                SpotPrice='0.01',
                InstanceCount=1,
                LaunchSpecification={
                    'ImageId': self.get_latest_ami(),
                    'InstanceType': 't4g.nano',
                    'SecurityGroupIds': [sg_id],
                    'SubnetId': subnet['subnet_id'],
                    'IamInstanceProfile': {'Name': profile_name}
                },
                TagSpecifications=[{
                    'ResourceType': 'spot-instances-request',
                    'Tags': self.get_common_tags()
                }]
            )
            
            spot_request_id = response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
            
            # Wait for spot request fulfillment
            instance_id = self.wait_for_spot_fulfillment(spot_request_id)
            
            if instance_id:
                # Tag the instance
                self.ec2.create_tags(
                    Resources=[instance_id],
                    Tags=self.get_common_tags()
                )
                
                instance_info = {
                    'instance_id': instance_id,
                    'subnet_id': subnet['subnet_id'],
                    'subnet_type': subnet['type'],
                    'az': subnet['az'],
                    'private_ip': None
                }
                instances.append(instance_info)
                self.created_resources['instances'].append(instance_id)
        
        return instances
    
    def get_latest_ami(self) -> str:
        """Get latest Amazon Linux 2023 ARM AMI"""
        response = self.ec2.describe_images(
            Owners=['amazon'],
            Filters=[
                {'Name': 'name', 'Values': ['al2023-ami-*-arm64']},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        # Sort by creation date and get latest
        images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
        return images[0]['ImageId']
    
    def wait_for_spot_fulfillment(self, spot_request_id: str) -> str:
        """Wait for spot instance request to be fulfilled"""
        print(f"Waiting for spot request {spot_request_id}...")
        
        for _ in range(30):  # 5 minute timeout
            for retry in range(3):  # Retry up to 3 times for slow responses
                try:
                    response = self.ec2.describe_spot_instance_requests(
                        SpotInstanceRequestIds=[spot_request_id]
                    )
                    break
                except self.ec2.exceptions.ClientError as e:
                    if 'InvalidSpotInstanceRequestID.NotFound' in str(e) and retry < 2:
                        print(f"Spot request not found, retrying in 10s... (attempt {retry + 1}/3)")
                        time.sleep(10)
                        continue
                    raise e
            
            request = response['SpotInstanceRequests'][0]
            state = request['State']
            
            if state == 'active':
                return request['InstanceId']
            elif state == 'failed':
                raise Exception(f"Spot request failed: {request.get('Fault', {}).get('Message', 'Unknown')}")
            
            time.sleep(10)
        
        raise Exception("Spot request timeout")
    
    def wait_for_instances_ready(self, instances: List[Dict]):
        """Wait for all instances to be running and SSM ready"""
        print("Waiting for instances to be ready...")
        
        instance_ids = [i['instance_id'] for i in instances]
        
        # Wait for running state
        waiter = self.ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=instance_ids)
        
        # Get private IPs
        response = self.ec2.describe_instances(InstanceIds=instance_ids)
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                for inst_info in instances:
                    if inst_info['instance_id'] == instance['InstanceId']:
                        inst_info['private_ip'] = instance['PrivateIpAddress']
        
        # Wait for SSM agent
        print("Waiting for SSM agent...")
        for _ in range(60):  # 10 minute timeout
            try:
                response = self.ssm.describe_instance_information(
                    Filters=[{'Key': 'InstanceIds', 'Values': instance_ids}]
                )
                
                if len(response['InstanceInformationList']) == len(instance_ids):
                    print("All instances ready for SSM")
                    break
            except:
                pass
            
            time.sleep(10)
    
    def run_connectivity_tests(self, instances: List[Dict]):
        """Run connectivity tests between instances"""
        print("Running connectivity tests...")
        
        for source_instance in instances:
            # Test internet connectivity
            self.test_internet_connectivity(source_instance)
            
            # Test connectivity to other instances
            for target_instance in instances:
                if source_instance != target_instance:
                    self.test_instance_connectivity(source_instance, target_instance)
    
    def test_internet_connectivity(self, instance: Dict):
        """Test internet connectivity from instance"""
        instance_id = instance['instance_id']
        subnet_type = instance['subnet_type']
        
        print(f"Testing internet connectivity from {subnet_type} instance {instance_id}")
        
        try:
            response = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName='AWS-RunShellScript',
                Parameters={
                    'commands': [
                        'curl -s --max-time 10 https://amazon.com > /dev/null && echo "SUCCESS" || echo "FAILED"'
                    ]
                }
            )
            
            command_id = response['Command']['CommandId']
            
            # Wait for command completion
            time.sleep(15)
            
            output_response = self.ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
            
            status = 'SUCCESS' if 'SUCCESS' in output_response['StandardOutputContent'] else 'FAILED'
            
            self.test_results.append({
                'test': f'Internet connectivity from {subnet_type} subnet',
                'source_instance': instance_id,
                'source_subnet': instance['subnet_id'],
                'target': 'amazon.com',
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'output': output_response['StandardOutputContent'].strip()
            })
            
        except Exception as e:
            self.test_results.append({
                'test': f'Internet connectivity from {subnet_type} subnet',
                'source_instance': instance_id,
                'status': 'ERROR',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def test_instance_connectivity(self, source: Dict, target: Dict):
        """Test connectivity between two instances"""
        source_id = source['instance_id']
        target_ip = target['private_ip']
        
        print(f"Testing connectivity from {source['subnet_type']} to {target['subnet_type']}")
        
        try:
            response = self.ssm.send_command(
                InstanceIds=[source_id],
                DocumentName='AWS-RunShellScript',
                Parameters={
                    'commands': [
                        f'ping -c 3 -W 5 {target_ip} > /dev/null && echo "SUCCESS" || echo "FAILED"'
                    ]
                }
            )
            
            command_id = response['Command']['CommandId']
            
            # Wait for command completion
            time.sleep(10)
            
            output_response = self.ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=source_id
            )
            
            status = 'SUCCESS' if 'SUCCESS' in output_response['StandardOutputContent'] else 'FAILED'
            
            self.test_results.append({
                'test': f'Ping connectivity {source["subnet_type"]} -> {target["subnet_type"]}',
                'source_instance': source_id,
                'source_subnet': source['subnet_id'],
                'target_instance': target['instance_id'],
                'target_ip': target_ip,
                'target_subnet': target['subnet_id'],
                'status': status,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.test_results.append({
                'test': f'Ping connectivity {source["subnet_type"]} -> {target["subnet_type"]}',
                'source_instance': source_id,
                'target_instance': target['instance_id'],
                'status': 'ERROR',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def generate_report(self):
        """Generate test results report"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'vpc_connectivity_test_{self.vpc_id}_{timestamp}.json'
        
        report = {
            'vpc_id': self.vpc_id,
            'test_uuid': self.test_uuid,
            'test_timestamp': datetime.now().isoformat(),
            'region': self.region,
            'summary': {
                'total_tests': len(self.test_results),
                'passed': len([r for r in self.test_results if r['status'] == 'SUCCESS']),
                'failed': len([r for r in self.test_results if r['status'] in ['FAILED', 'ERROR']])
            },
            'test_results': self.test_results
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nTest report saved to: {filename}")
        print(f"Summary: {report['summary']['passed']}/{report['summary']['total_tests']} tests passed")
        
        # Print summary to console
        print("\nTest Results Summary:")
        for result in self.test_results:
            status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
            print(f"{status_icon} {result['test']}: {result['status']}")
    
    def find_remaining_resources(self):
        """Find any remaining resources with our test tag"""
        print(f"\nSearching for remaining resources with tag {self.tag_key}={self.test_uuid}...")
        
        remaining_resources = []
        
        # Check EC2 instances
        try:
            response = self.ec2.describe_instances(
                Filters=[{'Name': f'tag:{self.tag_key}', 'Values': [self.test_uuid]}]
            )
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] != 'terminated':
                        remaining_resources.append(f"EC2 Instance: {instance['InstanceId']} ({instance['State']['Name']})")
        except Exception as e:
            print(f"Error checking instances: {e}")
        
        # Check security groups
        try:
            response = self.ec2.describe_security_groups(
                Filters=[{'Name': f'tag:{self.tag_key}', 'Values': [self.test_uuid]}]
            )
            for sg in response['SecurityGroups']:
                remaining_resources.append(f"Security Group: {sg['GroupId']}")
        except Exception as e:
            print(f"Error checking security groups: {e}")
        
        if remaining_resources:
            print("⚠️  Found remaining resources:")
            for resource in remaining_resources:
                print(f"  - {resource}")
        else:
            print("✅ No remaining resources found")
    
    def cleanup_resources(self):
        """Clean up all created resources"""
        # Prevent duplicate cleanup
        if hasattr(self, '_cleanup_done'):
            return
        self._cleanup_done = True
        
        print("\nCleaning up resources...")
        
        # Terminate instances first
        if self.created_resources['instances']:
            try:
                print(f"Terminating {len(self.created_resources['instances'])} instances...")
                self.ec2.terminate_instances(InstanceIds=self.created_resources['instances'])
                
                # Wait for instances to terminate
                print("Waiting for instances to terminate...")
                waiter = self.ec2.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=self.created_resources['instances'])
                print("✅ Instances terminated")
            except Exception as e:
                print(f"❌ Error terminating instances: {e}")
        
        # Delete security groups
        for sg_id in self.created_resources['security_groups']:
            try:
                self.ec2.delete_security_group(GroupId=sg_id)
                print(f"✅ Deleted security group {sg_id}")
            except Exception as e:
                print(f"❌ Error deleting security group {sg_id}: {e}")
        
        # Remove IAM resources (in correct order)
        for profile_name in self.created_resources['instance_profiles']:
            try:
                # Remove role from profile first
                if self.created_resources['iam_roles']:
                    self.iam.remove_role_from_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=self.created_resources['iam_roles'][0]
                    )
                
                self.iam.delete_instance_profile(InstanceProfileName=profile_name)
                print(f"✅ Deleted instance profile {profile_name}")
            except Exception as e:
                print(f"❌ Error deleting instance profile {profile_name}: {e}")
        
        for role_name in self.created_resources['iam_roles']:
            try:
                # Detach policies first
                self.iam.detach_role_policy(
                    RoleName=role_name,
                    PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
                )
                
                self.iam.delete_role(RoleName=role_name)
                print(f"✅ Deleted IAM role {role_name}")
            except Exception as e:
                print(f"❌ Error deleting IAM role {role_name}: {e}")
        
        # Delete resource group
        if self.created_resources['resource_group']:
            try:
                self.resource_groups.delete_group(GroupName=self.created_resources['resource_group'])
                print(f"✅ Deleted resource group {self.created_resources['resource_group']}")
            except Exception as e:
                print(f"❌ Error deleting resource group: {e}")
        
        # Check for any remaining resources
        self.find_remaining_resources()
        
        print("Cleanup completed")

def main():
    parser = argparse.ArgumentParser(description='Test VPC connectivity')
    parser.add_argument('vpc_id', help='VPC ID to test')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    
    args = parser.parse_args()
    
    tester = VPCConnectivityTester(args.vpc_id, args.region)
    tester.run_test()

if __name__ == '__main__':
    main()
