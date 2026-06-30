locals {
  # Endpoint service names follow the pattern com.amazonaws.<region>.<service>.
  interface_endpoint_services = [
    "bedrock",
    "bedrock-runtime",
    "ssm",
    "ssmmessages",
    "ec2messages",
    "logs",
  ]

  # Endpoint policy for the interface endpoints. Pins aws:PrincipalAccount to
  # the deploying account so a leaked credential from another account can't use
  # this endpoint to reach Bedrock / SSM / Logs from inside our VPC. Action /
  # Resource stay wide-open — the IAM role on the EC2 already constrains what
  # the principal may actually do, this is defence-in-depth at the network
  # boundary.
  interface_endpoint_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "*"
      Resource  = "*"
      Condition = {
        StringEquals = { "aws:PrincipalAccount" = var.account_id }
      }
    }]
  })

  # S3 gateway endpoint policy. Two statements:
  #
  #  (1) Project bucket access — pins aws:PrincipalAccount AND scopes
  #      Resource to the project's backup bucket so traffic over the gateway
  #      can only address that bucket. pg_dump / skills-backup uploads work;
  #      a misconfigured client can't reach a stranger's bucket via this
  #      endpoint. Falls back to Resource:* if backup_bucket_arn is empty
  #      (e.g. early in localstack apply where the bucket isn't yet
  #      plumbed); the principal-account pin remains effective.
  #
  #  (2) ECR layer bucket access — `docker pull` of KMS-encrypted ECR
  #      images retrieves layers via a presigned URL to an AWS-owned bucket
  #      named `prod-<region>-starport-layer-bucket`. Because the gateway
  #      endpoint sits on the route table, all S3 traffic from the VPC
  #      flows through it; without an explicit allow, the GET on the layer
  #      bucket returns 403 and every `docker compose pull` fails. Resource
  #      is locked to the regional starport bucket only (no wildcard S3
  #      escape), and the aws:PrincipalAccount pin still blocks foreign
  #      accounts from using this endpoint to pivot.
  s3_endpoint_policy_resources = (
    var.backup_bucket_arn == ""
    ? ["*"]
    : [var.backup_bucket_arn, "${var.backup_bucket_arn}/*"]
  )

  s3_endpoint_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowProjectBucketAccess"
        Effect    = "Allow"
        Principal = "*"
        Action    = "*"
        Resource  = local.s3_endpoint_policy_resources
        Condition = {
          StringEquals = { "aws:PrincipalAccount" = var.account_id }
        }
      },
      {
        Sid       = "AllowEcrLayerBucketRead"
        Effect    = "Allow"
        Principal = "*"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::prod-${var.region}-starport-layer-bucket",
          "arn:aws:s3:::prod-${var.region}-starport-layer-bucket/*"
        ]
        # No aws:PrincipalAccount condition here. ECR generates a presigned
        # S3 URL signed by its own service-linked role; when our EC2 GETs
        # that URL, the VPC endpoint evaluates `aws:PrincipalAccount` against
        # the URL's STS identity (ECR's account, not ours) and denies. The
        # AWS-owned starport-layer-bucket is only reachable via legitimate
        # ECR-signed URLs anyway, so Resource is the only constraint we need
        # — there's no "stranger's bucket" attack surface to defend against
        # (this bucket name is AWS-internal and not user-writable).
      }
    ]
  })
}

# --- VPC --------------------------------------------------------------------

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name      = "${var.name_prefix}-vpc"
    Component = "network"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name      = "${var.name_prefix}-igw"
    Component = "network"
  }
}

# --- Default VPC SG + default route table — locked down ---------------------
#
# The README's "no aws_*default*" rule is a guard against account-wide
# defaults (the account-level default VPC, the default S3 BPA, etc.). The two
# resources below are the documented exception: `aws_default_security_group`
# and `aws_default_route_table` operate ONLY on this VPC's defaults — they
# adopt the default SG / RT that AWS auto-creates inside the VPC at creation
# time and replace its ingress/egress (or its routes) with empty sets.
#
# Why bother — we never reference the default SG in any of our resources, so
# nothing rides on it today. But a future change might land an ENI directly
# in this VPC without specifying a security group, and AWS would attach the
# default SG (which by default permits all-ingress from itself + all-egress
# to anywhere). Same hazard for the default RT: if someone associates a new
# subnet without specifying a route table, AWS uses the default. Wiping both
# to empty makes those a noisy fail-fast rather than a silent open door.
resource "aws_default_security_group" "vpc_default" {
  vpc_id = aws_vpc.this.id

  # No ingress, no egress — empty by design.
  tags = {
    Name      = "${var.name_prefix}-default-sg-locked"
    Component = "network"
    Note      = "Locked down — DO NOT use; place resources in the explicit app SG instead."
  }
}

resource "aws_default_route_table" "vpc_default" {
  default_route_table_id = aws_vpc.this.default_route_table_id

  # No routes — empty by design.
  tags = {
    Name      = "${var.name_prefix}-default-rt-locked"
    Component = "network"
    Note      = "Locked down — explicit aws_route_table.public is what subnets actually use."
  }
}

# --- Public subnet ----------------------------------------------------------

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false # we use an EIP, no auto-assign

  tags = {
    Name      = "${var.name_prefix}-public-${var.availability_zone}"
    Component = "network"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name      = "${var.name_prefix}-public-rt"
    Component = "network"
  }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# --- Application security group --------------------------------------------

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app-sg"
  description = "VelocityAI EC2 instance security group (single-EC2 stack)"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name      = "${var.name_prefix}-app-sg"
    Component = "network"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "app_http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP from world (redirect + ACME http-01)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-ingress-http"
  }
}

resource "aws_vpc_security_group_ingress_rule" "app_https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS / WSS from world"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-ingress-https"
  }
}

resource "aws_vpc_security_group_ingress_rule" "app_ssh" {
  for_each = toset(var.ssh_allowed_cidrs)

  security_group_id = aws_security_group.app.id
  description       = "SSH from approved bastion CIDR ${each.value}"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value

  tags = {
    Name = "${var.name_prefix}-app-ingress-ssh-${replace(each.value, "/", "-")}"
  }
}

resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS to anywhere (apt, GitHub, Bedrock fallback, S3 fallback)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-egress-https"
  }
}

resource "aws_vpc_security_group_egress_rule" "app_http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP to anywhere (apt, ACME, OCSP)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-egress-http"
  }
}

resource "aws_vpc_security_group_egress_rule" "app_dns_udp" {
  security_group_id = aws_security_group.app.id
  description       = "DNS over UDP"
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-egress-dns-udp"
  }
}

resource "aws_vpc_security_group_egress_rule" "app_dns_tcp" {
  security_group_id = aws_security_group.app.id
  description       = "DNS over TCP"
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.name_prefix}-app-egress-dns-tcp"
  }
}

resource "aws_vpc_security_group_egress_rule" "app_self" {
  security_group_id            = aws_security_group.app.id
  description                  = "VPC-internal egress to interface endpoints (HTTPS)"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.endpoints.id

  tags = {
    Name = "${var.name_prefix}-app-egress-self-endpoints"
  }
}

# --- Endpoint security group (separate, used by interface endpoints) -------

resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-endpoints-sg"
  description = "Security group attached to VPC interface endpoints; only the app SG may reach 443/tcp."
  vpc_id      = aws_vpc.this.id

  tags = {
    Name      = "${var.name_prefix}-endpoints-sg"
    Component = "network"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_app" {
  security_group_id            = aws_security_group.endpoints.id
  description                  = "HTTPS from the app SG"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.app.id

  tags = {
    Name = "${var.name_prefix}-endpoints-ingress-from-app"
  }
}

# Endpoints don't need explicit egress for this design (return traffic is
# handled by the security group's stateful tracking on AWS-managed ENIs).
# We keep the SG with no explicit egress (default: deny).

# --- Interface endpoints ----------------------------------------------------
#
# Each endpoint carries an explicit policy that pins aws:PrincipalAccount.
# Without an explicit policy, the AWS default is "*" / "*" / "*" (any
# principal, any action, any resource), making the endpoint a defence-in-depth
# gap. See locals.interface_endpoint_policy above for the full statement.
resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoint_services)

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.public.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  policy              = local.interface_endpoint_policy

  tags = {
    Name      = "${var.name_prefix}-${each.value}-endpoint"
    Component = "network"
  }
}

# --- S3 gateway endpoint ----------------------------------------------------
#
# Carries the same aws:PrincipalAccount pin and additionally scopes Resource
# to the project's backup bucket (when var.backup_bucket_arn is supplied).
# See locals.s3_endpoint_policy.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]
  policy            = local.s3_endpoint_policy

  tags = {
    Name      = "${var.name_prefix}-s3-endpoint"
    Component = "network"
  }
}

# --- VPC flow logs ----------------------------------------------------------
#
# Captures every flow (accept/reject) on the project VPC into a
# project-owned, KMS-encrypted CloudWatch log group. Lets the project-side
# incident response reconstruct flows after an EC2 compromise without
# depending on the org-wide GuardDuty data plane.
#
# Three resources:
#   * aws_iam_role.flow_logs         — service role for vpc-flow-logs
#   * aws_iam_role_policy.flow_logs  — narrow CW Logs write permission
#   * aws_cloudwatch_log_group.flow_logs — destination, KMS-encrypted, prevent_destroy
#   * aws_flow_log.vpc               — the capture binding itself
data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    sid     = "AllowVPCFlowLogsAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }

    # Confused-deputy guard: the assumer must be acting on behalf of THIS
    # account. Without this, any other account's vpc-flow-logs principal
    # could (in principle) ride this trust policy.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "flow_logs" {
  name               = "${var.name_prefix}-vpc-flow-logs"
  description        = "Allows the VPC flow-logs service to write to the project's CloudWatch log group."
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json

  tags = {
    Name      = "${var.name_prefix}-vpc-flow-logs"
    Component = "network"
  }
}

resource "aws_cloudwatch_log_group" "flow_logs" {
  # Path matches the monitoring module's `/velocityai/${var.environment}/<suffix>`
  # convention so all CW log groups for the project share a tree (CW Logs
  # console becomes a tidy `/velocityai/prod/...` listing). Suffix is constant
  # `vpc-flow-logs`.
  name              = "/velocityai/${var.environment}/vpc-flow-logs"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = {
    Name      = "${var.name_prefix}-vpc-flow-logs"
    Component = "network"
  }

  lifecycle {
    # Flow logs carry forensic data; recreating the group loses the historical
    # stream. Same pattern as the monitoring module's log groups.
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "flow_logs" {
  name = "${var.name_prefix}-vpc-flow-logs-write"
  role = aws_iam_role.flow_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
      ]
      # Stream-level resource scope — `${arn}:*` matches any log stream
      # below the group. The group itself isn't a write target.
      Resource = "${aws_cloudwatch_log_group.flow_logs.arn}:*"
    }]
  })
}

resource "aws_flow_log" "vpc" {
  iam_role_arn         = aws_iam_role.flow_logs.arn
  log_destination_type = "cloud-watch-logs"
  log_destination      = aws_cloudwatch_log_group.flow_logs.arn
  traffic_type         = "ALL"
  vpc_id               = aws_vpc.this.id

  tags = {
    Name      = "${var.name_prefix}-vpc-flow-log"
    Component = "network"
  }
}
