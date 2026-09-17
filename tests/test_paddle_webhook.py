"""
The Paddle receiver. Run from the repository root:

    python -m unittest discover -s tests

boto3 is replaced before the module is loaded, so nothing reaches AWS.
"""

import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SECRET = "pdl_ntfset_test_secret"
NOW = 1_700_000_000
EMAIL = "buyer@example.com"


def load_webhook():
    fake = types.ModuleType("boto3")
    fake.client = mock.MagicMock()
    env = {"WEBHOOK_SECRET_ARN": "arn:secret", "PROCESSOR_FUNCTION": "processor"}
    with mock.patch.dict(sys.modules, {"boto3": fake}), \
            mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "paddle_webhook_app", ROOT / "lambda/paddle_webhook/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module._secret = SECRET
    module._lambda = mock.MagicMock()
    return module


def sign(ts, body, secret=SECRET):
    return hmac.new(secret.encode(), str(ts).encode() + b":" + body,
                    hashlib.sha256).hexdigest()


def payload_bytes():
    return json.dumps({
        "event_id": "evt_1", "event_type": "customer.created",
        "occurred_at": "2026-09-16T10:00:00.000000Z",
        "data": {"id": "ctm_1", "email": EMAIL, "name": "Zoë"},
    }, ensure_ascii=False).encode("utf-8")


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.app = load_webhook()

    def call(self, event, now=NOW):
        out = io.StringIO()
        with mock.patch.object(self.app.time, "time", return_value=now), \
                redirect_stdout(out):
            reply = self.app.lambda_handler(event, None)
        return reply, out.getvalue()

    def test_valid_signature_invokes_processor(self):
        body = payload_bytes()
        event = {"headers": {"Paddle-Signature": "ts=%d;h1=%s" % (NOW, sign(NOW, body))},
                 "body": body.decode("utf-8"), "isBase64Encoded": False}
        reply, log = self.call(event)
        self.assertEqual(reply["statusCode"], 200)
        kwargs = self.app._lambda.invoke.call_args.kwargs
        self.assertEqual(kwargs["InvocationType"], "Event")
        self.assertEqual(json.loads(kwargs["Payload"])["event_id"], "evt_1")
        self.assertNotIn(EMAIL, log)

    def test_bad_signature_is_refused_and_nothing_invoked(self):
        body = payload_bytes()
        event = {"headers": {"paddle-signature": "ts=%d;h1=%s" % (NOW, "0" * 64)},
                 "body": body.decode("utf-8")}
        reply, log = self.call(event)
        self.assertEqual(reply["statusCode"], 401)
        self.app._lambda.invoke.assert_not_called()
        self.assertNotIn(EMAIL, log)

    def test_stale_timestamp_is_refused(self):
        body = payload_bytes()
        old = NOW - 6
        event = {"headers": {"paddle-signature": "ts=%d;h1=%s" % (old, sign(old, body))},
                 "body": body.decode("utf-8")}
        reply, _ = self.call(event)
        self.assertEqual(reply["statusCode"], 401)
        self.app._lambda.invoke.assert_not_called()

    def test_base64_body_is_verified_on_the_decoded_bytes(self):
        body = payload_bytes()
        event = {"headers": {"paddle-signature": "ts=%d;h1=%s" % (NOW, sign(NOW, body))},
                 "body": base64.b64encode(body).decode("ascii"),
                 "isBase64Encoded": True}
        reply, _ = self.call(event)
        self.assertEqual(reply["statusCode"], 200)

    def test_rotated_secret_with_two_h1_values(self):
        body = payload_bytes()
        header = "ts=%d;h1=%s;h1=%s" % (NOW, sign(NOW, body, "pdl_ntfset_old"),
                                        sign(NOW, body))
        event = {"headers": {"paddle-signature": header},
                 "body": body.decode("utf-8")}
        reply, _ = self.call(event)
        self.assertEqual(reply["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
