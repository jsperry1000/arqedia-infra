# ---------------------------------------------------------------------------
# Ops alerts (go-live stage 9, decided 4 November 2026).
#
# Until this file, no alarm in the stack told anybody anything: each went into
# ALARM in the console and waited for someone to look. These email
# info@arqedia.com (the last two added 5 November 2026, EXT-02):
#
#   paddle-processor-failed   a Paddle event failed and waits in its queue -
#                             a customer may have paid and received nothing.
#                             Replay procedure: paddle.tf header. It emails
#                             again when the queue is empty (ok_actions).
#   paddle-needs-review       the processor flagged an event (below).
#   composition-failed        composition died; composition-failed has already
#                             refunded the run. Visibility only.
#   extraction-failed         extraction died; extraction-failed marked and
#                             refunded the document (extraction_failed.tf).
#   document-stuck            a document was charged and extraction never
#                             marked it (below). Refund by hand.
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

# --- a document charged and never extracted (EXT-02 case 4) ----------------
#
# The reconcile job prints one [stuck] line per document charged more than an
# hour ago that extraction never marked and that has not been refunded, while
# it is under two hours old - so each is named on about four runs and the
# alarm fires for a new one rather than sitting in ALARM over an old one.
# Alert only, decided 5 November 2026: reconcile writes nothing.
#
# PATTERN PROVED with test-metric-filter: it matched the [stuck] line and
# refused the summary line, which carries "stuck=" too, an [orphan] line and
# the bare word mid-sentence.
#
# WHEN IT FIRES, the line names tenant and document. Refund by hand with
# wallet.refund(tenant_id, document_id, charge_entry_id) - keyed, so it
# cannot pay twice - and mark the row so the screen stops waiting:
#
#   UPDATE document SET extracted_at = UTC_TIMESTAMP(),
#     extraction_error = 'extraction_never_ran'
#   WHERE tenant_id = :t AND document_id = :d AND extracted_at IS NULL
resource "aws_cloudwatch_log_metric_filter" "document_stuck" {
  name           = "${local.name_prefix}-document-stuck"
  log_group_name = "/aws/lambda/${aws_lambda_function.reconcile.function_name}"
  pattern        = "%\\[stuck\\]%"

  metric_transformation {
    name          = "DocumentStuck"
    namespace     = "ARQEDIA/${local.name_prefix}"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "document_stuck" {
  alarm_name          = "${local.name_prefix}-document-stuck"
  alarm_description   = "A document was charged and extraction never marked it. Refund and mark by hand: ops_alerts.tf."
  namespace           = "ARQEDIA/${local.name_prefix}"
  metric_name         = "DocumentStuck"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  tags                = { Name = "${local.name_prefix}-document-stuck" }
}
