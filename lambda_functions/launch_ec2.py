import boto3
import base64
import random
import time
import json
import os

iam = boto3.client('iam')

def check_ec2_ecr_policy_exists():
    policy_exists = False
    policy_name = "ec2_ecr_interactions"
    response = iam.list_policies(Scope='All',PolicyUsageFilter='PermissionsPolicy')
    for policy in response['Policies']:
        if policy['PolicyName'] == policy_name:
            return True
    return False

def check_ec2_s3_policy_exists():
    policy_exists = False
    policy_name = "ec2_s3_interactions"
    response = iam.list_policies(Scope='All',PolicyUsageFilter='PermissionsPolicy')
    for policy in response['Policies']:
        if policy['PolicyName'] == policy_name:
            return True
    return False

def create_and_attach_ec2_ecr_policy():
    flag = check_ec2_ecr_policy_exists()
    if flag is False:
        response = iam.create_policy(
                PolicyName="ec2_ecr_interactions",
                PolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "ecr:GetAuthorizationToken",
                                "ecr:BatchCheckLayerAvailability",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchGetImage"
                            ],
                            "Resource": "*"
                        }
                    ]
                }
            )
        )
        result = iam.attach_role_policy(RoleName="ec2_multi_role",PolicyArn=response['Policy']['Arn'])
        return result

def create_and_attach_ec2_s3_policy():
    flag = check_ec2_s3_policy_exists()
    if flag is False:
        response = iam.create_policy(
                PolicyName="ec2_s3_interactions",
                PolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "s3:*",
                            ],
                            "Resource": "*"
                        }
                    ]
                }
            )
        )
        result = iam.attach_role_policy(RoleName="ec2_multi_role",PolicyArn=response['Policy']['Arn'])
        return result

def create_iam_role():
    try:
        response = iam.get_role(RoleName='ec2_multi_role')
    except iam.exceptions.NoSuchEntityException:
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        response = iam.create_role(
            RoleName='ec2_multi_role',
            AssumeRolePolicyDocument=json.dumps(trust_policy)
        )

    return response['Role']['Arn']

def create_instance_profile(role_arn):
    iam = boto3.client('iam')
    try:
        response = iam.get_instance_profile(InstanceProfileName="ec2_instance_profile")
        if response:
            return response['InstanceProfile']['Arn']
    except:
        response = iam.create_instance_profile(InstanceProfileName='ec2_instance_profile')
        iam.add_role_to_instance_profile(
            InstanceProfileName='ec2_instance_profile',
            RoleName='ec2_multi_role'
        )
        instance_profile = iam.get_instance_profile(InstanceProfileName="ec2_instance_profile")
        instance_profile_arn = instance_profile['InstanceProfile']['Arn']
        return instance_profile_arn

def get_account_id():
    sts = boto3.client('sts')
    identity = sts.get_caller_identity()
    account_id = identity['Account']
    return account_id

def lambda_handler(event, context):
    role_arn = create_iam_role()
    result = create_and_attach_ec2_ecr_policy()
    result = create_and_attach_ec2_s3_policy()
    account_id = get_account_id()
    instance_profile_arn = create_instance_profile(role_arn)
    ec2_client = boto3.client('ec2')
    region = os.environ['AWS_REGION']
    ecr_repo = "ml-code-repository"
    ecr_repo_tag = "latest"
    container_name = "training-instance"
    salt = int(time.time())
    # Create a new key pair
    key_pair_name = f'EC2KeyPair-{salt}'
    key_pair = ec2_client.create_key_pair(KeyName=key_pair_name)

    #:TODO Save this key in secrets manager
    print(f"Private key for {key_pair_name}:")
    print(key_pair['KeyMaterial'])

    # security group for handling EC2 inbound and outbound rules
    security_group_name = f'ec2-security-group-{salt}'
    security_group = ec2_client.create_security_group(
        GroupName=security_group_name,
        Description='Security group created by Lambda function to handle EC2 operations'
    )
    security_group_id = security_group['GroupId']

    # Fetch the default VPC ID automatically by filtering VPCs by the isDefault attribute
    vpcs_response = ec2_client.describe_vpcs(
        Filters=[{'Name': 'isDefault', 'Values': ['true']}]
    )
    
    if not vpcs_response['Vpcs']:
        raise ValueError('No default VPC found')

    vpc_id = vpcs_response['Vpcs'][0]['VpcId']
    # Fetch the list of associated subnets for the VPC
    subnets_response = ec2_client.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    subnet_ids = [subnet['SubnetId'] for subnet in subnets_response['Subnets']]

    # Select a random subnet ID
    selected_subnet_id = random.choice(subnet_ids)
    # Add ingress rules to the EC2 security group
    ec2_client.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ]
    )
    user_data = f'''#!/bin/bash
    touch /tmp/user_data.log
    echo "Starting user data script" > /tmp/user_data.log
    sudo yum update -y
    echo "Installed yum update" >> /tmp/user_data.log
    sudo yum -y install docker
    echo "install docker done" >> /tmp/user_data.log
    sudo service docker start
    echo "docker started" >> /tmp/user_data.log
    sudo yum install -y python3-pip
    echo "pip installed" >> /tmp/user_data.log
    sudo pip3 install boto3
    echo "boto3 installed" >> /tmp/user_data.log
    yum install -y awscli
    echo "aws cli installed" >> /tmp/user_data.log
    usermod -aG docker ec2-user
    echo "delegate ec2-user as sudoer" >> /tmp/user_data.log
    export AWS_REGION={region}
    aws ecr get-login-password --region {region} | sudo docker login --username AWS --password-stdin {account_id}.dkr.ecr.{region}.amazonaws.com
    echo "Logged into ECR" >> /tmp/user_data.log
    sudo docker pull {account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo}:{ecr_repo_tag}
    echo "Pulled image from ECR" >> /tmp/user_data.log
    docker run -d --name {container_name} {account_id}.dkr.ecr.{region}.amazonaws.com/{ecr_repo}:{ecr_repo_tag}
    echo "Executed docker as container" >> /tmp/user_data.log
    container_id=$(docker ps -aqf "name=${container_name}")
    echo "Container ID: $container_id" >> /tmp/user_data.log
    docker cp $container_id:/tmp/artifacts.salt /tmp/
    echo "Copying the artifacts salt from container to host" >> /tmp/user_data.log
    salt=$(cat artifacts.salt)
    echo "salt - $salt" >> /tmp/user_data.log
    docker cp $container_id:/tmp/ml-artifacts-$salt/ /tmp/
    echo "Copying the file from container to host" >> /tmp/user_data.log
    mkdir /tmp/copied
    echo "/tmp/copied created" >> /tmp/user_data.log
    recent_dir=$(ls -ltd /tmp/*/ | head -n1 | awk '{{print $NF}}') && cp -r "${{recent_dir}}"* /tmp/copied/
    echo "copied artifacts to /tmp/copied" >> /tmp/user_data.log
    aws s3 cp /tmp/copied s3://ml-code-artifacts-dbs/
    echo "copied artifacts to S3" >> /tmp/user_data.log
    '''
    instance = ec2_client.run_instances(
        ImageId='ami-0889a44b331db0194',
        InstanceType='t2.micro',
        IamInstanceProfile={'Arn': instance_profile_arn},
        MinCount=1,
        MaxCount=1,
        KeyName=key_pair_name,
        SecurityGroupIds=[security_group_id],
        SubnetId=selected_subnet_id,
        UserData=user_data,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'ml-instance'
                    },
                    {
                        'Key': 'Environment',
                        'Value': 'Dev'
                    }
                ]
            }
        ]
    )

    print(f'Launched instance: {instance["Instances"][0]["InstanceId"]}')
    return instance["Instances"][0]["InstanceId"]


