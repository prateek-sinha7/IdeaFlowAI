# Foundation layer outputs (network, KMS, IAM, secrets, backups) are read
# directly from its remote state keyed on the environment. The app layer
# never duplicates foundation inputs; it consumes them here.
data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "velocityai/${var.environment}/foundation.tfstate"
    region = var.aws_region
  }
}
