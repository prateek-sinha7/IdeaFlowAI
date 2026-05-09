variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod (used in tags)."
  type        = string
}

variable "route53_zone_name" {
  description = "Existing Route 53 hosted zone name (e.g. example.com). This module ONLY looks the zone up; it does NOT create one. The zone must already exist in the account."
  type        = string
}

variable "app_subdomain" {
  description = "Subdomain (without trailing dot, without zone) where the app is reachable, e.g. 'flowin' resolves to flowin.<route53_zone_name>. Set apex_record=true to ignore this and use the zone apex."
  type        = string
  default     = "flowin"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$", var.app_subdomain))
    error_message = "app_subdomain must be one or more DNS labels (lowercase alnum + hyphens), e.g. 'flowin' or 'app.flowin'. Use apex_record=true for the zone apex."
  }
}

variable "apex_record" {
  description = "If true, create the A-record at the apex of the zone (ignores app_subdomain). Default false."
  type        = bool
  default     = false
}

variable "eip_address" {
  description = "Elastic IP address (string form) the A-record points at."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.eip_address))
    error_message = "eip_address must look like 1.2.3.4."
  }
}

variable "ttl_seconds" {
  description = "TTL on the A-record. 60 during go-live, raise to 300 once stable."
  type        = number
  default     = 60

  validation {
    condition     = var.ttl_seconds >= 30 && var.ttl_seconds <= 86400
    error_message = "ttl_seconds must be between 30 and 86400."
  }
}
