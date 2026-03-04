terraform {
  backend "s3" {
    # TODO: Replace these with your actual S3 bucket and DynamoDB table
    bucket         = "smartscale-s3-bucket"
    key            = "smart-scaling-guardian/terraform.tfstate"
    region         = "us-east-2"
    dynamodb_table = "smartscale-locks"
    encrypt        = true
  }
}

