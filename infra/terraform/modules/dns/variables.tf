variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod (used in tags)."
  type        = string
}

variable "use_nip_io" {
  description = <<-EOT
    If true, derive the public hostname from var.eip_address via nip.io
    (e.g. 1-2-3-4.nip.io for EIP 1.2.3.4) instead of looking up a Route 53
    hosted zone and creating an A record under it. nip.io is on the Public
    Suffix List so Let's Encrypt issues real certs against the computed
    hostname; its wildcard resolver handles A-record resolution server-side
    so this module creates no Route 53 resources at all when this flag is
    set.

    When true, var.route53_zone_name and var.app_subdomain are ignored.
    Default false preserves the existing Route 53 path.
  EOT
  type        = bool
  default     = false
}

variable "route53_zone_name" {
  description = "Existing Route 53 hosted zone name (e.g. example.com). This module ONLY looks the zone up; it does NOT create one. The zone must already exist in the account. Ignored when use_nip_io = true."
  type        = string
  default     = ""
}

variable "app_subdomain" {
  description = "Subdomain (without trailing dot, without zone) where the app is reachable, e.g. 'velocityai' resolves to velocityai.<route53_zone_name>. Set apex_record=true to ignore this and use the zone apex. Ignored when use_nip_io = true."
  type        = string
  default     = "velocityai"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$", var.app_subdomain))
    error_message = "app_subdomain must be one or more DNS labels (lowercase alnum + hyphens), e.g. 'velocityai' or 'app.velocityai'. Use apex_record=true for the zone apex."
  }
}

variable "apex_record" {
  description = "If true, create the A-record at the apex of the zone (ignores app_subdomain). Default false. Ignored when use_nip_io = true."
  type        = bool
  default     = false
}

variable "eip_address" {
  description = "Elastic IP address (string form). When use_nip_io=false, the A-record points at this address. When use_nip_io=true, this address is the source of the computed nip.io hostname (`<dashed-ip>.nip.io`)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.eip_address))
    error_message = "eip_address must look like 1.2.3.4."
  }
}

variable "ttl_seconds" {
  description = "TTL on the A-record. 60 during go-live, raise to 300 once stable. Ignored when use_nip_io = true (no record is created)."
  type        = number
  default     = 60

  validation {
    condition     = var.ttl_seconds >= 30 && var.ttl_seconds <= 86400
    error_message = "ttl_seconds must be between 30 and 86400."
  }
}
