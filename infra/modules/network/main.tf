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
  description = "Flowin EC2 instance security group (single-EC2 stack)"
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

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoint_services)

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.public.id]
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = {
    Name      = "${var.name_prefix}-${each.value}-endpoint"
    Component = "network"
  }
}

# --- S3 gateway endpoint ----------------------------------------------------

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]

  tags = {
    Name      = "${var.name_prefix}-s3-endpoint"
    Component = "network"
  }
}
