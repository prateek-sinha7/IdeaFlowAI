output "all_group_arn" {
  description = "ARN of the top-level all-of-VelocityAI Resource Group."
  value       = aws_resourcegroups_group.all.arn
}

output "all_group_name" {
  description = "Name of the top-level all-of-VelocityAI Resource Group."
  value       = aws_resourcegroups_group.all.name
}

output "per_component_group_arns" {
  description = "Map of component name -> Resource Group ARN."
  value       = { for k, v in aws_resourcegroups_group.per_component : k => v.arn }
}

output "per_component_group_names" {
  description = "Map of component name -> Resource Group name."
  value       = { for k, v in aws_resourcegroups_group.per_component : k => v.name }
}
