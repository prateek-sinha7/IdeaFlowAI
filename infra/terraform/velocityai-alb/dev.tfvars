# VelocityAI ALB layer — dev environment (NON-SECRET config only).
#
# Values below come from live AWS inspection of the existing dev VPC/instance
# (see session history / .planning). certificate_arn and trusted_ingress_cidrs
# still need operator confirmation before first apply — see the placeholders
# and the two-step rollout note in main.tf.
#
# Consumed as: terraform -chdir=infra/terraform/velocityai-alb apply \
#   -var-file=dev.tfvars -var="expected_account_id=$ACCOUNT_ID" \
#   -var="certificate_arn=$CERT_ARN" -var="alarm_email=$ALERT_EMAIL"
#
# Init with the matching per-environment state key:
#   terraform init -backend-config="key=velocityai/dev/alb.tfstate" ...

environment = "dev"
aws_region  = "eu-central-1"

# Live VPC + application subnets (excludes the /28 TGW-attachment subnets).
vpc_id = "vpc-0535cb2c8b9dadcb4"
subnet_ids = [
  "subnet-06dfc3faca84c9673", # velocityai-euc1-app-a, eu-central-1c
  "subnet-085f1421d35d8fbdf", # velocityai-euc1-app-b, eu-central-1a
]

# Live dev EC2 instance.
instance_id = "i-0f8c285633f222b7b"

# CHANGE ME: replace with the approved corporate VPN/TGW-routed CIDR(s).
# The value below is a single workstation's current VPN IP — fine for the
# very first connectivity test, NOT a durable team-wide rule.
trusted_ingress_cidrs = ["10.6.77.104/32"]

# log_bucket_name left unset — auto-derives to
# velocityai-dev-alb-logs-265331052706-euc1
