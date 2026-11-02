# ---------------------------------------------------------------------------
# Single table (see backend/app/db.py for the key design).
#
#   product  PK = PRODUCT#<pid>  SK = META            GSI1PK = PRODUCT
#   link     PK = PRODUCT#<pid>  SK = LINK#<lid>      GSI1PK = LINK
#   price    PK = LINK#<lid>     SK = PRICE#<iso-ts>
#
# On-demand billing: nothing is charged while idle. Encryption uses the
# AWS-owned key (default), which is free.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "main" {
  name                        = local.table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = true

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1"
    projection_type = "ALL"

    key_schema {
      attribute_name = "GSI1PK"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "GSI1SK"
      key_type       = "RANGE"
    }
  }

  # Price history is small and re-scrapable; PITR (~0.20 USD/GB-month) is
  # deliberately off.
  point_in_time_recovery {
    enabled = false
  }
}
