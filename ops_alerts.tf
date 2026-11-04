# ---------------------------------------------------------------------------
# Ops alerts (go-live stage 9, decided 4 November 2026).
#
# Until this file, no alarm in the stack told anybody anything: each went into
# ALARM in the console and waited for someone to look. Three now email
# info@arqedia.com:
#
#   paddle-processor-failed   a Paddle event failed and waits in its queue -
#                             a customer may have paid and received nothing.
#                             Replay procedure: paddle.tf header. It emails
#                             again when the queue is empty (ok_actions).
#   paddle-needs-review       the processor flagged an event (below).
#   composition-failed        composition died; composition-failed has already
#                             refunded the run. Visibility only.
#
# THE SUBSCRIPTION MUST BE CONFIRMED. AWS emails info@arqedia.com a link
# after the first apply, and nothing is delivered until it is clicked.
#
# Nothing sent here carries a customer's data: an alarm email names the alarm,
# never an event's payload.
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "ops_alerts" {
  name = "${local.name_prefix}-ops-alerts"
  tags = { Name = "${local.name_prefix}-ops-alerts" }
}

resource "aws_sns_topic_subscription" "ops_alerts_email" {
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = "info@arqedia.com"
}

# --- an event flagged for review ---------------------------------------------
#
# needs_review is set on paddle_event and read by nothing (stage 9). The
# processor prints exactly two outcomes when it sets it - "review" for an
# event recorded and not applied, and "topup-granted-unmatched" for a top-up
# granted with no request of ours behind it - so the alarm counts those log
# lines rather than reading the table.
#
# THE PATTERN WAS PROVED, as observability.tf asks. test-metric-filter: it
# matched both outcomes and refused "reviewed-elsewhere" and
# "topup-granted-unmatched-later". filter-log-events over the processor's
# whole history (15 September - 3 November 2026) found exactly the four
# events paddle_event flags, and nothing else. Alternation inside a group,
# (review|...), is refused by the API; anchoring each branch with $ is what
# stops a longer outcome matching.
#
# WHEN IT FIRES, look at what was flagged:
#
#   q "SELECT event_id, event_type, occurred_at, tenant_id, paddle_entity_id
#      FROM paddle_event WHERE needs_review = 1 ORDER BY occurred_at DESC"
#
# and the processor's log line for the event_id says which outcome it was.
# review: nothing was applied - an unknown tenant, a refund or chargeback, a
# plan change that cannot be placed. topup-granted-unmatched: the credit was
# granted, because it was paid for; no top-up request of ours matched it.
#
# The log group is Lambda's own and not declared here (OBS-01), as the
# normalizer's filter is.
resource "aws_cloudwatch_log_metric_filter" "paddle_needs_review" {
  name           = "${local.name_prefix}-paddle-needs-review"
  log_group_name = "/aws/lambda/${aws_lambda_function.paddle_processor.function_name}"
  pattern        = "%outcome=review$|outcome=topup-granted-unmatched$%"

  metric_transformation {
    name          = "PaddleNeedsReview"
    namespace     = "ARQEDIA/${local.name_prefix}"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

# No ok_actions: the count is back to zero five minutes later whatever was
# done, so an OK email would say nothing.
resource "aws_cloudwatch_metric_alarm" "paddle_needs_review" {
  alarm_name          = "${local.name_prefix}-paddle-needs-review"
  alarm_description   = "A Paddle event was flagged needs_review. Query and meanings: ops_alerts.tf."
  namespace           = "ARQEDIA/${local.name_prefix}"
  metric_name         = "PaddleNeedsReview"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  tags                = { Name = "${local.name_prefix}-paddle-needs-review" }
}
