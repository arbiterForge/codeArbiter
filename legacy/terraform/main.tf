# main.tf — OpenTofu root module for cove-apps-fusion.
# TODO: replace with real resource definitions.
#
# Run:
#   tofu -chdir=terraform init
#   tofu -chdir=terraform plan
#   tofu -chdir=terraform apply

terraform {
  required_version = "~> 1.8"
  required_providers {
    aws = {
      source  = "registry.opentofu.org/hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # TODO: configure remote state backend.
  # backend "s3" {
  #   bucket = "cove-tfstate"
  #   key    = "cove-apps-fusion/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region to deploy resources into."
  type        = string
  default     = "us-east-1"
}
