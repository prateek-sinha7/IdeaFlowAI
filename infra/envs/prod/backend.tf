terraform {
  backend "s3" {
    # Set the following keys via `terraform init -backend-config=...` flags
    # OR by editing the values below to match the bootstrap output.
    #
    # bucket         = "flowin-tfstate-<account-id>-<region>"
    # key            = "envs/prod/terraform.tfstate"
    # region         = "eu-west-2"
    # dynamodb_table = "flowin-tfstate-locks"
    # encrypt        = true
  }
}
