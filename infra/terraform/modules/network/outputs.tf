output "vpc_id" {
  description = "ID of the project VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "Primary CIDR of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_id" {
  description = "ID of the single public subnet."
  value       = aws_subnet.public.id
}

output "public_route_table_id" {
  description = "ID of the public route table."
  value       = aws_route_table.public.id
}

output "app_security_group_id" {
  description = "ID of the security group attached to the EC2 instance."
  value       = aws_security_group.app.id
}

output "endpoints_security_group_id" {
  description = "ID of the security group attached to interface endpoints."
  value       = aws_security_group.endpoints.id
}

output "interface_endpoint_ids" {
  description = "Map of service name -> VPC interface endpoint ID."
  value       = { for k, v in aws_vpc_endpoint.interface : k => v.id }
}

output "s3_gateway_endpoint_id" {
  description = "ID of the S3 gateway endpoint."
  value       = aws_vpc_endpoint.s3.id
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway."
  value       = aws_internet_gateway.this.id
}

output "flow_logs_log_group_name" {
  description = "Name of the CloudWatch log group receiving VPC flow logs."
  value       = aws_cloudwatch_log_group.flow_logs.name
}

output "flow_logs_log_group_arn" {
  description = "ARN of the CloudWatch log group receiving VPC flow logs."
  value       = aws_cloudwatch_log_group.flow_logs.arn
}

output "flow_logs_iam_role_arn" {
  description = "ARN of the IAM role used by the VPC flow-logs service to write to CloudWatch."
  value       = aws_iam_role.flow_logs.arn
}
