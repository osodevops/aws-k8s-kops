#!/usr/bin/env python

import json
import boto3
import botocore
import time
import os
from subprocess import call

S3_BUCKET = os.getenv('S3_BUCKET')
S3_REGION = os.getenv('S3_REGION')
GIT_REPO = os.getenv('GIT_REPO')
SSH_S3_BUCKET_NAME = os.getenv('SSH_S3_BUCKET_NAME')
SSH_S3_KEY = os.getenv('SSH_S3_KEY')
BASE_DOMAIN = os.getenv('BASE_DOMAIN')
CLUSTER_NAME = os.getenv('CLUSTER_NAME')
ZONES = os.getenv('ZONES')
NODE_SIZE = os.getenv('NODE_SIZE')
MASTER_SIZE = os.getenv('MASTER_SIZE')
ROOT_DIR = os.getcwd()
FQDN_CLUSTER_NAME = CLUSTER_NAME + '.' + BASE_DOMAIN


def main():
    pull_ssh()
    setup_iam()
    configure_dns()
    initialise_bucket()
    kops_create_update()
    terraform_apply()


def pull_ssh():
    print 'Attempting to pull SSH Private key from' + SSH_S3_BUCKET_NAME
    s3 = boto3.resource('s3')
    home_dir = os.path.expanduser('~')
    download_location = home_dir + '/.ssh/id_rsa'
    try:
        s3.Bucket(SSH_S3_BUCKET_NAME).download_file(SSH_S3_KEY, download_location)
        call(['chmod', '400', download_location])
        print "SSH Key downloaded successfully to " + download_location
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("SSH Key does not exist.  Exiting")
        else:
            raise


def setup_iam():
    print('Creating KOPS user and group on AWS')
    iam_client = boto3.client('iam')
    group_name = 'kops'
    user_name = 'kops'
    iam_policies = [
        'AmazonEC2FullAccess',
        'AmazonRoute53FullAccess',
        'AmazonS3FullAccess',
        'IAMFullAccess',
        'AmazonVPCFullAccess']

    try:
        iam_client.create_group(GroupName=group_name)
    except Exception as e:
        print e
        pass

    try:
        for policy in iam_policies:
            policy_string = 'arn:aws:iam::aws:policy/' + policy
            iam_client.attach_group_policy(GroupName=group_name, PolicyArn=policy_string)
    except Exception as e:
        print 'ERROR: ' + str(e)
        pass

    try:
        iam_client.create_user(UserName=user_name)
    except Exception as e:
        print 'ERROR: ' + str(e)
        pass

    try:
        iam_client.add_user_to_group(GroupName=group_name, UserName=user_name)
    except Exception as e:
        print 'ERROR: ' + str(e)
        pass

    try:
        iam_client.create_access_key(UserName=user_name)
    except Exception as e:
        print 'ERROR: ' + str(e)
        pass


def configure_dns():
    parent_zone_id = ''
    route53_client = boto3.client('route53')
    new_sub_domain = CLUSTER_NAME + '.' + BASE_DOMAIN
    parent_zones = route53_client.list_hosted_zones_by_name(DNSName=BASE_DOMAIN)
    print 'Parent Zone!' + str(parent_zones)

    for zone in parent_zones['HostedZones']:
        if BASE_DOMAIN in zone['Name']:
            parent_zone_id = zone['Id']
    # TODO: What to do if:
    # botocore.errorfactory.InvalidChangeBatch: An error occurred (InvalidChangeBatch) when calling the
    # ChangeResourceRecordSets operation: Tried to create resource record set [name='boom.mccullya.co.uk.', type='NS']
    # but it already exists

    # If the parent doesn't exist; this will create it
    if not parent_zone_id:
        caller_reference = str(time.time() * 1000)
        route53_client.create_hosted_zone(Name=new_sub_domain, CallerReference=caller_reference)
    else:
        # Add the NS records to the already existing parent domain.
        try:
            route53_client.change_resource_record_sets(
                HostedZoneId=parent_zone_id,
                ChangeBatch={
                    'Comment': 'Creating new record set for KOPS deployment',
                    'Changes': [
                        {
                            'Action': 'CREATE',
                            'ResourceRecordSet': {
                                'Name': new_sub_domain,
                                'Type': 'NS',
                                'TTL': 300,
                                'ResourceRecords': [
                                    {
                                        "Value": "ns-1.awsdns-1.co.uk"
                                    },
                                    {
                                        "Value": "ns-2.awsdns-2.org"
                                    },
                                    {
                                        "Value": "ns-3.awsdns-3.com"
                                    },
                                    {
                                        "Value": "ns-4.awsdns-4.net"
                                    }
                                ]
                            }
                        },
                    ]
                }
            )
        except Exception as e:
            print 'NOTICE: Skipping Resource Record set because:'
            print e
            pass


def initialise_bucket():
    call(['git', 'clone', GIT_REPO, 'terraform-git'])
    call(['mkdir', '-p', './terraform-git/' + FQDN_CLUSTER_NAME])
    key_name = FQDN_CLUSTER_NAME + '/terraform/terraform.tstate'
    terraform_s3 = dict()
    terraform_s3['terraform'] = dict()
    terraform_s3['terraform']['backend'] = dict()
    terraform_s3['terraform']['backend']['s3'] = {
        'bucket': S3_BUCKET,
        'key': key_name,
        'region': S3_REGION
    }
    bucket_file = './terraform-git/' + FQDN_CLUSTER_NAME + '/s3_bucket.tf'
    with open(bucket_file, 'w') as outfile:
        json.dump(terraform_s3, outfile, indent=2, sort_keys=True)


# Create the KOPS state files on S3, push generated terraform files up to predetermined GIT bucket
def kops_create_update():
    # Look to see if cluster already exists
    s3 = boto3.client('s3')
    exists = False
    all_objects = s3.list_objects(Bucket=S3_BUCKET)
    try:
        for folder in all_objects['Contents']:
            if exists:
                break
            if FQDN_CLUSTER_NAME in folder['Key'].split('/')[0]:
                exists = True
    except Exception as e:
        print(e)
        exists = False

    # If the key is KOPS_STATE is already there, update.  Otherwise, create.
    if exists:
        print 'KOPS_STATE exists, running KOPS UPDATE...'
        call(['kops', 'update', 'cluster',
              FQDN_CLUSTER_NAME,
              '--yes',
              '--state=s3://' + S3_BUCKET,
              '--out=./terraform-git/' + FQDN_CLUSTER_NAME,
              '--target=terraform'])
    else:
        print 'Running KOPS Create to create Kubernetes Cluster...'
        call(['kops', 'create', 'cluster',
              '--name=' + FQDN_CLUSTER_NAME,
              '--state=s3://' + S3_BUCKET,
              '--dns-zone=' + BASE_DOMAIN,
              '--out=./terraform-git/' + FQDN_CLUSTER_NAME,
              '--target=terraform',
              '--cloud=aws',
              '--node-size=' + NODE_SIZE,
              '--master-size=' + MASTER_SIZE,
              '--zones=' + ZONES])


def terraform_apply():
    os.chdir('/tmp')
    call(['aws', 's3', 'sync', 's3://' + S3_BUCKET, '.'])
    call(['mv', FQDN_CLUSTER_NAME, str(ROOT_DIR) + '/terraform-git/' + FQDN_CLUSTER_NAME + '/' + 'KOPS_STATE'])
    os.chdir(str(ROOT_DIR) + '/terraform-git/' + FQDN_CLUSTER_NAME)
    print('Initializing Terraform...')
    call(['terraform', 'init'])
    print('Implementing Terraform...')
    call(['terraform', 'apply'])


if __name__ == '__main__':
    main()