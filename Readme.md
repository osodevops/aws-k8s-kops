KOPS Cluster Creation Automation (for AWS)
---

## Overview
This docker container will automatically rebuild a Kubernetes cluster on AWS by making use of [KOPS](https://github.com/kubernetes/kops), [Terraform](https://www.terraform.io/), and [Amazon S3](https://aws.amazon.com/s3).

### High-level Overview
In order to deploy the cluster, the container (and script within will perform the following steps):

* Pull a private SSH Key from a shared S3 Bucket. (ENV Variable _SSH_S3_BUCKET_NAME & SSH_S3_KEY_)
* Creates a AWS user named 'kops'
* Creates a AWS group called 'kops', with the following permissions:
    * AmazonEC2FullAccess
    * AmazonRoute53FullAccess
    * AmazonS3FullAccess
    * IAMFullAccess
    * AmazonVPCFullAccess
* Adds a NS record to an *ALREADY EXISTING Hosted Zone* 
    * EXAMPLE: ENV Variable _CLUSTER_NAME_ (ex foo) and _BASE_DOMAIN_ (ex bar.com) would create a NS record foo.bar.com underneath the hosted zone 'bar.com' in Route 53 (AWS)
* Creates a terraform remote state file.
* Creates an S3 Bucket that will be used to store the state of both Terraform, and KOPS.
* If script has never been run before, a 'kops create cluster' will be run.  If it has been run before, a 'kops update cluster'.  Both of these scripts will save the output into terraform files.
* Script will then run 'terraform init', followed by 'terraform apply'

### Before Running...
Before running, there are two steps which need to be taken: Populating the AWS credentials/config, and populating the enviornment variables.

#### AWS Credentials
* Copy the 'credentials' and 'config' AWS files that are typically found in $HOME/.aws into the folder /aws-credentials.  If you do not havev these files, please see [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-config-files.html)

#### Environment Variables
The file 'variables.env' are to be used to configure some site specific settings.  Please see below for an overview of these variables:
* S3_BUCKET
    * The name of the S3_BUCKET where you wish to store the KOPS/Terraform State
* S3_REGION
    * The region of above mentioned bucket
* GIT_REPO
    * The GIT repository that will source control the terraform files that are generated during the Kops Update/Create.
* SSH_S3_BUCKET_NAME
    * The bucket that contains the private SSH keys that will be used for EC2 Instance Creation.
* SSH_S3_KEY
    * The key name in above mentioned bucket that points to the actual private key.
* BASE_DOMAIN
    * The 'parent domain' of the cluster.  For example, for a cluster named foo.bar.com, the BASE_DOMAIN would be 'bar.com'
* CLUSTER_NAME
    * The child name of the domain.  For example, for a cluster named foo.bar.com, the CLUSTER_NAME would be 'foo'
* ZONES
    * What zone this cluster will be created in i.e. _eu-west-1a_
    
#### How to run

##### Docker Build
```docker build . -t <<BUILD_NAME>>:latest```

##### Docker Run
```docker run --env-file variables.env -it -v $(pwd)/app:/app -v $(pwd)/aws-credentials:/root/.aws <<BUILD_NAME>>:latest python /app/build-cluster.py```

 
 ##### NOTE:
 Terraform files are generated, and saved to _/app/terraform-git/foo.bar.com/_.  As these files change, they should be pushed up to GIT (this folder will be located in the GIT branch defined by the variable 'GIT_REPO')