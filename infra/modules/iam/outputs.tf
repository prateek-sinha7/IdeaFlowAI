output "instance_role_name" {
  description = "Name of the EC2 instance role."
  value       = aws_iam_role.instance.name
}

output "instance_role_arn" {
  description = "ARN of the EC2 instance role."
  value       = aws_iam_role.instance.arn
}

output "instance_profile_name" {
  description = "Name of the instance profile to pass to aws_instance.iam_instance_profile."
  value       = aws_iam_instance_profile.instance.name
}

output "instance_profile_arn" {
  description = "ARN of the instance profile."
  value       = aws_iam_instance_profile.instance.arn
}
