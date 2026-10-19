"""
app.py - what composition could not finish, finished (UX02 20.2).

Composition catches its own failures: a generation or an Update that writes
nothing refunds its charge and records its run as failed, and a rewrite
writes its row as failed (20.1). That holds only while the code RUNS. What it
cannot catch is a timeout at 900 seconds, an out-of-memory kill, a crash at
start-up - a stale layer, a bad import - and anything raised before a path's
own try. Lambda does not retry those (maximum_retry_attempts = 0), so each
used to vanish: the money kept, the run left "running", the screen waiting.

Each now lands on the composition-failed queue as an on-failure INVOCATION
RECORD, which carries the original event as requestPayload and the error as
responsePayload. This function reads them and does what composition would
have done had it lived:

  generation  refund the charge and write the run failed - unless the run
              names a memo, which means the row was written before the
              function died. That memo opens, and the charge bought it
              (decided 19 October 2026).
  update      refund the charge and write the Update run failed.
  rewrite     write the memo_rewrite row failed. A rewrite is not charged.

A SEPARATE FUNCTION, NOT COMPOSITION READING ITS OWN QUEUE (decided 19
October 2026). A composition that dies at start-up would break the thing
meant to clean up after it.

ONLY WHAT IS STILL RUNNING. A run already finished, a row already settled,
is left exactly as it is - the queue can deliver a message twice, and a run
can finish in the moment between its failure and this. Refunds are keyed on
the charge (wallet.refund_generation), so a second one is refused by the
ledger whatever this function believes.

A MESSAGE THAT CANNOT BE HANDLED IS LEFT ON THE QUEUE, reported back as a
batch item failure, so it is tried again and stays visible rather than being
deleted unhandled. The queue keeps it fourteen days.
"""

import datetime
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

import wallet

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# What a person is told. Composition's own sentences, so a run that died
# reads the same as one that failed in the ordinary way - the person cannot
# tell the two apart and has no reason to.
GENERATE_FAULT = ("The memorandum could not be written because of a fault on "
                  "our side. Try it again.")
UPDATE_FAULT = ("The update stopped because of a fault on our side. "
                "Try it again.")
REWRITE_FAULT = ("The rewrite stopped because of a fault on our side. "
                 "Try it again.")


def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


# --- where runs are kept ---------------------------------------------------
#
# MIRRORED in lambda/api/app.py, which writes each run first, and in
# lambda/composition/app.py, which finishes it. The three must not drift;
# tests/test_composition_failed.py asserts they agree.

def _generate_key(tenant_id, engagement_id, run):
    return "tenants/%d/runs/generate/%d/%s.json" % (
        int(tenant_id), int(engagement_id), run)


def _update_key(tenant_id, memo_id, run):
    return "tenants/%d/updates/memos/%d/%s.json" % (
        int(tenant_id), int(memo_id), run)


def _get(key):
    try:
        body = _s3.get_object(Bucket=CURATED_BUCKET, Key=key)["Body"].read()
    except ClientError as exc:
        # As the API reads these: a missing key reads as AccessDenied to a
        # role without ListBucket.
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "AccessDenied", "403"):
            return None
        raise
    return json.loads(body.decode("utf-8"))


def _put(key, state):
    _s3.put_object(Bucket=CURATED_BUCKET, Key=key,
                   Body=json.dumps(state).encode("utf-8"),
                   ContentType="application/json")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _refund(tenant_id, entry_id, by):
    """wallet.refund_generation. RAISES on failure, unlike composition's
    wrapper: here a refund that could not be made is a message to try
    again, not a sentence to show."""
    return wallet.refund_generation(tenant_id, entry_id, by)


# --- the three kinds of run ------------------------------------------------

def _generation(payload, why):
    tenant_id = int(payload["tenant_id"])
    run = payload.get("run")
    engagement_id = payload.get("engagement_id")
    entry_id = payload.get("entry_id")
    by = payload.get("generated_by")

    if not run or engagement_id is None:
        # Invoked by hand, or queued before runs existed. Whether a memo was
        # written cannot be told, so nothing is refunded on a guess.
        return "generation without a run: nothing recorded, nothing refunded"

    key = _generate_key(tenant_id, engagement_id, run)
    state = _get(key) or {"run": run, "engagement_id": engagement_id,
                          "entry_id": entry_id}
    if state.get("status") not in (None, "running"):
        return "already " + str(state.get("status"))

    state["completed_at"] = _now()
    state["died"] = why

    # The row was written before the function died. The memo opens.
    if state.get("memo_id"):
        state.update(status="done", incomplete=True)
        _put(key, state)
        return "memo %s written before it died: not refunded" % state["memo_id"]

    given = _refund(tenant_id, entry_id, by)
    state.update(status="failed", error=GENERATE_FAULT,
                 refunded=bool(given.get("refunded")),
                 amount_cents=given.get("amount_cents") or 0)
    _put(key, state)
    return "refunded=%s repeated=%s" % (given.get("refunded"),
                                        given.get("repeated"))


def _update(payload, why):
    tenant_id = int(payload["tenant_id"])
    memo_id = int(payload["memo_id"])
    run = str(payload["run"])

    key = _update_key(tenant_id, memo_id, run)
    state = _get(key) or {"run": run, "memo_id": memo_id}
    if state.get("status") not in (None, "running"):
        return "already " + str(state.get("status"))

    # An Update that died offered nothing: its rows are written only at the
    # end, all together, with the run.
    given = _refund(tenant_id, payload.get("entry_id"),
                    payload.get("requested_by"))
    state.update(status="failed", error=UPDATE_FAULT, completed_at=_now(),
                 died=why, refunded=bool(given.get("refunded")),
                 amount_cents=given.get("amount_cents") or 0)
    _put(key, state)
    return "refunded=%s repeated=%s" % (given.get("refunded"),
                                        given.get("repeated"))


def _rewrite(payload, why):
    tenant_id = int(payload["tenant_id"])
    rewrite_id = int(payload["rewrite_id"])
    # Only a row still running. One that finished stays as it finished.
    done = _sql(
        """
        UPDATE memo_rewrite
        SET status = 'failed', error = :error, completed_at = UTC_TIMESTAMP()
        WHERE tenant_id = :t AND rewrite_id = :r AND status = 'running'
        """,
        [_p("error", REWRITE_FAULT), _p("t", tenant_id), _p("r", rewrite_id)])
    return "rows=%s" % done.get("numberOfRecordsUpdated", 0)


def _handle(record):
    """One invocation record. Returns what was done, for the log line."""
    payload = record.get("requestPayload") or {}
    response = record.get("responsePayload") or {}
    context = record.get("requestContext") or {}
    # Why it died, as Lambda put it: "Task timed out after 900.00 seconds",
    # an error type, or the condition alone.
    why = (response.get("errorMessage") or response.get("errorType")
           or context.get("condition") or "unknown")[:300]

    action = payload.get("action")
    if action == "rewrite":
        outcome = _rewrite(payload, why)
    elif action == "update":
        outcome = _update(payload, why)
    else:
        outcome = _generation(payload, why)

    print("[composition-died] tenant=%s action=%s run=%s rewrite=%s why=%s "
          "outcome=%s" % (payload.get("tenant_id"), action or "generate",
                          payload.get("run"), payload.get("rewrite_id"),
                          why, outcome))
    return outcome


def lambda_handler(event, context):
    """SQS, a batch at a time. A message that could not be handled is named
    back to SQS (ReportBatchItemFailures) and comes round again; the rest
    are deleted."""
    failures = []
    for message in event.get("Records", []):
        try:
            _handle(json.loads(message["body"]))
        except Exception as exc:  # noqa: BLE001 - left on the queue, named
            print("[composition-died-unhandled] message=%s %r" % (
                message.get("messageId"), exc))
            failures.append({"itemIdentifier": message.get("messageId")})
    return {"batchItemFailures": failures}
