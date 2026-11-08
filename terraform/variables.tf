variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1" # Mumbai — lowest latency for an India-based business
}

variable "instance_type" {
  description = "EC2 instance type. t3.micro and t4g.micro are both free-tier eligible for 750 hrs/month in the first 12 months."
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of an EC2 key pair that already exists in this AWS account/region (create one in the EC2 console first: Key Pairs > Create key pair). Terraform does not create this for you, since the private key must be downloaded once and kept safe."
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to SSH into the instance. Set this to your own IP (e.g. \"203.0.113.5/32\") — never leave it as 0.0.0.0/0."
  type        = string
}

variable "project_name" {
  description = "Name tag applied to all resources, and used as the hostname prefix."
  type        = string
  default     = "ssm-crm"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB. Up to 30GB is free-tier eligible."
  type        = number
  default     = 20
}
