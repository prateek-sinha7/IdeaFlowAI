output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.app.id
}

output "instance_arn" {
  description = "EC2 instance ARN."
  value       = aws_instance.app.arn
}

output "private_ip" {
  description = "Primary private IP."
  value       = aws_instance.app.private_ip
}

output "public_ip" {
  description = "Public IP attached via the EIP."
  value       = aws_eip.this.public_ip
}

output "eip_allocation_id" {
  description = "Allocation ID of the EIP."
  value       = aws_eip.this.id
}

output "data_volume_id" {
  description = "EBS data volume ID (mounted at /var/lib/postgresql)."
  value       = aws_ebs_volume.data.id
}

output "data_volume_arn" {
  description = "EBS data volume ARN — feed to AWS Backup selection."
  value       = aws_ebs_volume.data.arn
}

output "ami_id" {
  description = "AMI ID resolved at apply time."
  value       = local.effective_ami_id
}
