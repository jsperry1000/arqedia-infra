"""
Every message goes out named "ARQEDIA <no-reply@...>" (5 November 2026).

    python -m unittest discover -s tests

Cognito's messages always carried the name; the three functions that send
through SES themselves sent the bare address. Each is checked at the call it
makes, with boto3 replaced so nothing reaches AWS.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NAMED = "ARQEDIA <no-reply@arqedia.test>"


def load(path, name, env):
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    boto3.resource = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions}
    with mock.patch.dict(sys.modules, modules), \
            mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class SenderNameTest(unittest.TestCase):
    def test_the_api_names_the_sender(self):
        mail = load(ROOT / "lambda" / "api" / "mail.py", "mail_named", {})
        mail._ses = mock.MagicMock()
        with mock.patch.dict(os.environ, {"SENDER": "no-reply@arqedia.test"}):
            self.assertTrue(mail.send("a@b.test", "Subject", "Body"))
        self.assertEqual(mail._ses.send_email.call_args.kwargs["Source"],
                         NAMED)

    def test_signup_names_the_sender(self):
        text = (ROOT / "lambda" / "signup" / "app.py").read_text(
            encoding="utf-8")
        self.assertIn('Source=formataddr(("ARQEDIA", SENDER))', text)

    def test_the_viewer_names_the_sender(self):
        text = (ROOT / "lambda" / "share_viewer" / "app.py").read_text(
            encoding="utf-8")
        self.assertIn('Source=formataddr(("ARQEDIA", sender))', text)

    def test_no_sender_sends_a_bare_source(self):
        for path in ("lambda/api/mail.py", "lambda/signup/app.py",
                     "lambda/share_viewer/app.py"):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertNotRegex(text, r"Source=(SENDER|sender|address),")


if __name__ == "__main__":
    unittest.main()
