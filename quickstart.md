# Quick Start Guide

This guide provides step-by-step instructions to deploy the Frugal VPC CloudFormation template with four different configuration options.

## Prerequisites

- AWS CLI configured with appropriate permissions
- CloudFormation deployment permissions
- EC2 and VPC permissions for the target region

## Deployment Options

### Option 1: Single AZ with Spot Instances (Maximum Cost Savings)

**Best for:** Development, testing, and non-critical workloads where cost is the primary concern.

**Monthly Cost:** ~$3-4 (up to 93% savings vs NAT Gateway)

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-dev \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=dev-vpc \
    ParameterKey=NumberOfAZs,ParameterValue=1 \
    ParameterKey=UseSpotInstances,ParameterValue=true \
  --capabilities CAPABILITY_IAM \
  --region ap-southeast-2
```

### Option 2: Single AZ with On-Demand Instances (Balanced Cost/Reliability)

**Best for:** Small production workloads, proof-of-concepts, and environments requiring consistent availability.

**Monthly Cost:** ~$6-8 (85-90% savings vs NAT Gateway)

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-prod \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=prod-vpc \
    ParameterKey=NumberOfAZs,ParameterValue=1 \
    ParameterKey=UseSpotInstances,ParameterValue=false \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Option 3: Multi-AZ with On-Demand Instances (Production High Availability)

**Best for:** Production workloads requiring high availability and fault tolerance across multiple availability zones.

**Monthly Cost:** ~$18-24 for 3 AZs (85-90% savings vs NAT Gateway)

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-ha \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=ha-vpc \
    ParameterKey=NumberOfAZs,ParameterValue=3 \
    ParameterKey=UseSpotInstances,ParameterValue=false \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Option 4: Multi-AZ with Spot Instances (Dev Multi-AZ)

**Best for:** Development environments that require multiple AZs (e.g., for services like RDS or ELB that need 2+ AZs) but where spot interruptions are acceptable.

**Monthly Cost:** ~$9-12 for 3 AZs (up to 93% savings vs NAT Gateway)

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-dev-multiaz \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=dev-multiaz-vpc \
    ParameterKey=NumberOfAZs,ParameterValue=2 \
    ParameterKey=UseSpotInstances,ParameterValue=true \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

## Deployment Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd frugal-vpc
   ```

2. **Choose your deployment option** from the three options above and run the corresponding command.

3. **Monitor the deployment:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name <your-stack-name> \
     --query 'Stacks[0].StackStatus'
   ```

4. **Verify the deployment:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name <your-stack-name> \
     --query 'Stacks[0].Outputs'
   ```

## Post-Deployment Verification

### Check NAT Instance Status
```bash
aws ec2 describe-instances \
  --filters "Name=tag:Role,Values=NAT-Instance" \
           "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].{InstanceId:InstanceId,State:State.Name,AZ:Placement.AvailabilityZone}'
```

### Verify Route Tables
```bash
aws ec2 describe-route-tables \
  --filters "Name=tag:Name,Values=*private-rt*" \
  --query 'RouteTables[].{RouteTableId:RouteTableId,Routes:Routes[?DestinationCidrBlock==`0.0.0.0/0`]}'
```

### Test Internet Connectivity
Launch a test instance in a private subnet and verify it can reach the internet through the NAT instance.

## Configuration Parameters

| Parameter | Description | Default | Options |
|-----------|-------------|---------|---------|
| `InstanceName` | Name prefix for resources | `frugal-vpc` | Any valid string |
| `NumberOfAZs` | Number of availability zones | `2` | `1`, `2`, or `3` |
| `UseSpotInstances` | Use spot instances in all AZs | `false` | `true` or `false` |
| `VpcCidr` | CIDR block for the VPC | `10.0.0.0/16` | Any valid CIDR |
| `SubnetSize` | Subnet size (CIDR suffix) | `24` | `16` to `28` |
| `PythonScriptUrl` | Custom script URL | Base64 no-op | Any valid URL |

## Custom CIDR Configuration Examples

### Example 1: Custom CIDR Range with Standard Subnets
**Use Case:** Corporate network integration with specific IP ranges

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-corporate \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=corp-vpc \
    ParameterKey=VpcCidr,ParameterValue=172.31.0.0/16 \
    ParameterKey=SubnetSize,ParameterValue=24 \
    ParameterKey=NumberOfAZs,ParameterValue=2 \
  --capabilities CAPABILITY_IAM
```

### Example 2: Large VPC with Bigger Subnets
**Use Case:** High-density workloads requiring many IP addresses per subnet

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-large \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=large-vpc \
    ParameterKey=VpcCidr,ParameterValue=172.16.0.0/16 \
    ParameterKey=SubnetSize,ParameterValue=22 \
    ParameterKey=NumberOfAZs,ParameterValue=3 \
  --capabilities CAPABILITY_IAM
```

### Example 3: Small Development VPC
**Use Case:** Development environment with minimal IP requirements

```bash
aws cloudformation create-stack \
  --stack-name frugal-vpc-dev-small \
  --template-body file://frugal_vpc.yaml \
  --parameters \
    ParameterKey=InstanceName,ParameterValue=dev-small-vpc \
    ParameterKey=VpcCidr,ParameterValue=192.168.100.0/24 \
    ParameterKey=SubnetSize,ParameterValue=28 \
    ParameterKey=NumberOfAZs,ParameterValue=1 \
    ParameterKey=UseSpotInstances,ParameterValue=true \
  --capabilities CAPABILITY_IAM
```

## Cleanup

To delete the stack and all resources:

```bash
aws cloudformation delete-stack --stack-name <your-stack-name>
```

## Troubleshooting

### NAT Instance Not Starting
- Check CloudWatch logs for the Lambda function
- Verify IAM permissions for the NAT instance role
- Check security group rules

### No Internet Access from Private Subnets
- Verify NAT instance is running and healthy
- Check route table entries point to the correct NAT instance
- Confirm source/destination check is disabled on NAT instances

### High Costs
- Ensure you're using t4g.nano instances (ARM-based)
- Consider enabling spot instances for additional savings
- Monitor data transfer costs separately

## Support

For issues and questions:
1. Check CloudWatch logs for the route updater Lambda function
2. Review VPC Flow Logs for network troubleshooting
3. Verify Auto Scaling Group health checks
