"""
paddle_webhook - receives Paddle notifications.

The only thing Paddle calls. It checks the signature on the exact bytes that
arrived, hands the verified event to the processor, and answers. It never
touches the database: the cluster pauses at zero capacity and can take longer
to wake than Paddle waits.

NEVER LOG THE BODY OR THE PAYLOAD. A Paddle event carries the customer's email
address. What is logged is the event id, its type and what became of it.

The signature, from Paddle's "Verify webhook signatures":

  Paddle-Signature: ts=1671552777;h1=eb4d...
  h1 = hex HMAC-SHA256(secret, ts + ":" + raw body)

There may be more than one h1 while Paddle rotates a secret. Any one matching
is enough. The timestamp is held against the clock so a captured request
cannot be replayed later.
"""

import base64
import hashlib
import hmac
import json
import os
import time

import boto3

_secrets = boto3.client("secretsmanager")
_lambda = boto3.client("lambda")

WEBHOOK_SECRET_ARN = os.environ["WEBHOOK_SECRET_ARN"]
PROCESSOR_FUNCTION = os.environ["PROCESSOR_FUNCTION"]

# PROPOSED value: the tolerance Paddle's SDKs use by default.
TOLERANCE_SECONDS = 5

_secret = None


def _webhook_secret():
    """Read once per container. A replaced secret reaches a warm container
    only when that container is recycled."""
    global _secret
    if _secret is None:
        _secret = _secrets.get_secret_value(
            SecretId=WEBHOOK_SECRET_ARN)["SecretString"]
    return _secret


def raw_body(event):
    """The bytes Paddle signed. API Gateway base64-encodes a body it does not
    treat as text; hashing the encoded form would never match."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def parse_signature(header):
    ts, signatures = None, []
    for part in (header or "").split(";"):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "ts":
            ts = value
        elif key == "h1":
            signatures.append(value)
    return ts, signatures


def verify(header, body, secret, now):
    """'ok', or the reason it is not. The reason is logged; nothing else is."""
    ts, signatures = parse_signature(header)
    if not ts or not signatures:
        return "missing"
    if not (ts.isascii() and ts.isdigit()):
        return "malformed"
    if abs(now - int(ts)) > TOLERANCE_SECONDS:
        return "stale"
    expected = hmac.new(secret.encode("utf-8"),
                        ts.encode("ascii") + b":" + body,
                        hashlib.sha256).hexdigest()
    if any(hmac.compare_digest(expected, s) for s in signatures):
        return "ok"
    return "mismatch"


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    # The clock is read before the secret is fetched, so a cold start does not
    # count against the request.
    now = int(time.time())
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = raw_body(event)

    outcome = verify(headers.get("paddle-signature"), body,
                     _webhook_secret(), now)
    if outcome != "ok":
        print("[paddle-webhook] refused outcome=%s" % outcome)
        return _reply(401, {"error": "signature"})

    payload = json.loads(body)
    event_id = payload.get("event_id")
    event_type = payload.get("event_type")

    # Asynchronous: the processor may wait on the cluster to wake, and Paddle
    # waits five seconds. An invoke that fails raises, Paddle sees a 500 and
    # delivers again.
    _lambda.invoke(FunctionName=PROCESSOR_FUNCTION, InvocationType="Event",
                   Payload=json.dumps(payload).encode("utf-8"))

    print("[paddle-webhook] event=%s type=%s outcome=queued"
          % (event_id, event_type))
    return _reply(200, {"received": True})
