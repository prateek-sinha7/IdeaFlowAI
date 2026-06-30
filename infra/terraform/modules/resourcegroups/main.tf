resource "aws_resourcegroups_group" "all" {
  name        = "${var.name_prefix}-all"
  description = "All VelocityAI resources in environment ${var.environment}."

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "Project"
          Values = ["velocityai"]
        },
        {
          Key    = "Environment"
          Values = [var.environment]
        }
      ]
    })
  }

  tags = {
    Name      = "${var.name_prefix}-all"
    Component = "monitoring"
  }
}

resource "aws_resourcegroups_group" "per_component" {
  for_each = var.components

  name        = "${var.name_prefix}-${each.key}"
  description = "VelocityAI ${each.key} resources ${var.description_separator} ${each.value}"

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "Project"
          Values = ["velocityai"]
        },
        {
          Key    = "Environment"
          Values = [var.environment]
        },
        {
          Key    = "Component"
          Values = [each.key]
        }
      ]
    })
  }

  tags = {
    Name      = "${var.name_prefix}-${each.key}"
    Component = "monitoring"
  }
}
