# VPC Connectivity Test Script

A Python script that automatically tests VPC connectivity by deploying temporary test instances across all subnets and verifying routing and internet access.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.7+
- Required IAM permissions (see below)

## Installation

1. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure AWS credentials are configured:
```bash
aws configure
```

## Usage

### Basic Usage
```bash
python test_vpc_connectivity.py <vpc-id>
```

### With Custom Region
```bash
python test_vpc_connectivity.py <vpc-id> --region us-west-2
```

### Examples
```bash
# Test VPC in default region (us-east-1)
python test_vpc_connectivity.py vpc-0123456789abcdef0

# Test VPC in specific region
python test_vpc_connectivity.py vpc-0123456789abcdef0 --region ap-southeast-2
```

## What It Tests

The script performs comprehensive connectivity testing:

1. **VPC Analysis**: Identifies all subnets and determines public/private status
2. **Instance Deployment**: Launches t4g.nano spot instances in each subnet
3. **Internet Connectivity**: Tests HTTPS access from each subnet
4. **Inter-Subnet Connectivity**: Tests ping between all subnet pairs
5. **Automatic Cleanup**: Removes all created resources after testing

## Test Results

Results are saved to a JSON file: `vpc_connectivity_test_<vpc-id>_<timestamp>.json`

The report includes:
- Summary statistics (passed/failed tests)
- Detailed results for each connectivity test
- Instance and subnet information
- Timestamps and error details

## Required IAM Permissions

Your AWS credentials need the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeVpcs",
                "ec2:DescribeSubnets",
                "ec2:DescribeRouteTables",
                "ec2:DescribeImages",
                "ec2:DescribeInstances",
                "ec2:DescribeSpotInstanceRequests",
                "ec2:RequestSpotInstances",
                "ec2:TerminateInstances",
                "ec2:CreateSecurityGroup",
                "ec2:DeleteSecurityGroup",
                "ec2:AuthorizeSecurityGroupIngress",
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:CreateInstanceProfile",
                "iam:DeleteInstanceProfile",
                "iam:AddRoleToInstanceProfile",
                "iam:RemoveRoleFromInstanceProfile",
                "ssm:DescribeInstanceInformation",
                "ssm:SendCommand",
                "ssm:GetCommandInvocation"
            ],
            "Resource": "*"
        }
    ]
}
```

## Cost Considerations

- Uses t4g.nano spot instances (typically $0.001-0.003/hour)
- Test duration: ~10-15 minutes
- Estimated cost per test: $0.01-0.05
- All resources are automatically cleaned up

## Limitations

- Requires spot instance availability in target AZs
- Uses ARM-based instances (t4g.nano)
- Tests basic connectivity only (ping and HTTPS)
- Requires SSM agent functionality

## Troubleshooting

### Common Issues

1. **Spot Instance Unavailable**: Script will fail if spot instances aren't available
   - Solution: Try different region or wait and retry

2. **IAM Permissions**: Ensure your credentials have all required permissions
   - Solution: Attach the policy above to your IAM user/role

3. **SSM Agent Timeout**: Instances may take time to register with SSM
   - Solution: Script waits up to 10 minutes automatically

4. **VPC Not Found**: Ensure VPC ID is correct and in specified region
   - Solution: Verify VPC ID with `aws ec2 describe-vpcs`

### Debug Mode

For verbose output, modify the script to include debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Cleanup

The script automatically cleans up all resources on completion or failure. If cleanup fails, manually remove:

1. EC2 instances with names starting with "vpc-test-"
2. Security groups with names starting with "vpc-test-sg-"
3. IAM roles/profiles with names starting with "vpc-test-"
