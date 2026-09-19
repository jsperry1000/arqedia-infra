# ---------------------------------------------------------------------------
# Observability.
#
# Written after an afternoon spent unable to answer a simple question. A tenant
# uploaded seventeen files, the browser said "Failed to fetch", and there was
# no record anywhere of whether the requests had arrived: the $default stage
# had no access logging, and the API Lambda logged START, END and REPORT and
# nothing else. Sixteen of those seventeen left no trace at all, and still
# have not been explained.
#
# Three things, and none of them changes behaviour:
#   the gateway records every request
#   the API records the route and what it answered
#   [normalizer-error] becomes a number somebody can alarm on
# ---------------------------------------------------------------------------

# HTTP APIs need no IAM role for this. That is a REST API requirement - an
# account-wide CloudWatch role set by aws_api_gateway_account - and it does not
# apply here: the log group and the stage setting are the whole of it.
# Confirmed against the API Gateway developer guide, September 2026.
resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${local.name_prefix}-api-access"
  retention_in_days = 30

  tags = { Name = "${local.name_prefix}-api-access" }
}

# --- counting what went wrong in the normalizer ----------------------------
#
# [normalizer-error] is printed at exactly one place - the catch-all below the
# fetch in lambda/normalizer/app.py - and nowhere else, so this counts that and
# nothing besides. It fires where a refusal row was written for a reason nobody
# anticipated, which is the case worth watching: the anticipated ones are
# refusals a person can read and act on.
#
# A REGEX, AND THE ONLY FORM THAT WORKS. Three others were tried against
# test-metric-filter with a real line, and none of them counts this:
#
#   "[normalizer-error]"    REJECTED by the API - "Invalid character(s) in
#                           term 'normalizer-error'". The brackets are read as
#                           a space-delimited field expression despite the
#                           quotes, and the hyphen is not legal in a field
#                           name. PutMetricFilter ACCEPTS it, so the filter
#                           deploys and matches nothing.
#   "normalizer-error"      accepted, matched 0 of 3
#   normalizer-error        accepted, matched 0 of 3
#   %normalizer-error%      matches, but also matches the phrase anywhere in
#                           any line
#
# %\[normalizer-error\]% matches the prefix and nothing else - proved against
# the real line, two other prefixes, and a decoy carrying the bare phrase
# mid-sentence. Check it with test-metric-filter, not by reading it: a pattern
# that deploys and silently counts nothing is worse than no filter, and two of
# the four above do exactly that.
#
# The log group is NOT declared here. Lambda creates it on first invocation,
# and declaring it would need an import against an environment where it already
# exists - OBS-01 in the backlog. On a brand new environment this filter cannot
# be created until the normalizer has run once.
resource "aws_cloudwatch_log_metric_filter" "normalizer_error" {
  name           = "${local.name_prefix}-normalizer-error"
  log_group_name = "/aws/lambda/${aws_lambda_function.normalizer.function_name}"
  pattern        = "%\\[normalizer-error\\]%"

  metric_transformation {
    name      = "NormalizerError"
    namespace = "ARQEDIA/${local.name_prefix}"
    value     = "1"
    # Absent means none, not unknown. Without this the metric has gaps rather
    # than zeros, and a gap is what an alarm treats as missing data.
    default_value = "0"
    unit          = "Count"
  }
}
