import boto3
import json
import subprocess
import os
import shutil
import time
import uuid

salt = str(uuid.uuid4()).split("-")[3]
IAM_USERNAME = f"ssp191191{salt}"
CODECOMMIT_ENDPOINT = "git-codecommit.*.amazonaws.com"
REPO_URL = "ssh://git-codecommit.us-east-1.amazonaws.com/v1/repos/ml-code-repo"
LOCAL_DIR = f"{os.getcwd()}/code_files/"
CLONE_DIR = f"/tmp/aws_code_{salt}/"
CODE_DIR = CLONE_DIR + "ml-code-repo/"

def read_public_key():
    with open('.secret','r') as file:
        PUBLIC_KEY = file.read()
        return PUBLIC_KEY

iam_client = boto3.client('iam')
iam_client.create_user(
    UserName=IAM_USERNAME,
)

# Attach the AWSCodeCommitPowerUser policy to the user
iam_client.attach_user_policy(
    UserName=IAM_USERNAME,
    PolicyArn="arn:aws:iam::aws:policy/AWSCodeCommitPowerUser"
)

public_key = read_public_key()
response = iam_client.upload_ssh_public_key(
    UserName=IAM_USERNAME,
    SSHPublicKeyBody=public_key
)

KEY_ID = response['SSHPublicKey']['SSHPublicKeyId']
ssh_config = f"Host {CODECOMMIT_ENDPOINT}\n  User {KEY_ID}\n  IdentityFile ~/.ssh/id_rsa\n"
with open(f"{os.path.expanduser('~/.ssh/config')}", "a") as file:
    file.write(ssh_config)

subprocess.check_output(['git', 'clone', REPO_URL, CLONE_DIR])
subprocess.check_output(['git', 'init'], cwd=CLONE_DIR)

for filename in os.listdir(LOCAL_DIR):
    source = os.path.join(LOCAL_DIR, filename)
    destination = os.path.join(CLONE_DIR, filename)
    shutil.copy2(source, destination)

subprocess.check_output(['git', 'add', '.'], cwd=CLONE_DIR)
subprocess.check_output(['git', 'commit', '-m', 'Init Files'], cwd=CLONE_DIR)
subprocess.check_output(['git', 'push'], cwd=CLONE_DIR)
