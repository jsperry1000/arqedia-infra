"""
Loads the API's billing modules with boto3 and botocore replaced, so nothing
reaches AWS. Not a test file: discover skips it by name.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from unittest import mock

API = Path(__file__).resolve().parents[1] / "lambda" / "api"

ENV = {
    "CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
    "DATABASE": "arqedia",
    "PADDLE_API_BASE": "https://sandbox-api.paddle.test",
    "PADDLE_API_KEY_SECRET_ARN": "arn:paddle-key",
    "PADDLE_PRICE_BASE": "pri_base", "PADDLE_PRICE_BUSINESS": "pri_business",
    "PADDLE_PRICE_TOPUP": "pri_topup",
}


def load_billing():
    """billing, with .wallet, .seats and .paddle_api as it imported them."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, ENV):
        for name in ("billing", "wallet", "seats", "paddle_api"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(API))
        try:
            return importlib.import_module("billing")
        finally:
            sys.path[:] = saved


def rows(*values):
    """Data API records from plain Python values."""
    def cell(v):
        if v is None:
            return {"isNull": True}
        if isinstance(v, bool):
            return {"booleanValue": v}
        if isinstance(v, int):
            return {"longValue": v}
        return {"stringValue": v}
    return {"records": [[cell(v) for v in row] for row in values]}
