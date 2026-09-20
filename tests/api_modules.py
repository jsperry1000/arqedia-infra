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

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "lambda" / "api"
# wallet.py moved to lambda/shared so the collector can import it from
# the layer. billing still does `import wallet` and resolves it here.
SHARED = ROOT / "lambda" / "shared"

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
        sys.path.insert(1, str(SHARED))
        try:
            return importlib.import_module("billing")
        finally:
            sys.path[:] = saved


def load_api():
    """app, with the modules it imports as it imported them.

    Every environment variable app.py and its imports read at import time is
    set here; a missing one is a KeyError at import rather than a test
    failure that names something else."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions}
    env = dict(ENV, **{
        "DOCS_BUCKET": "docs", "REVIEW_BUCKET": "review",
        "CURATED_BUCKET": "curated", "BRAND_BUCKET": "brand",
        "COMPOSITION_FUNCTION": "composition",
        "TEXTRACT_TOPIC_ARN": "arn:topic", "TEXTRACT_ROLE_ARN": "arn:role",
        "RENDER_FUNCTION": "render", "PROPOSER_FUNCTION": "proposer",
    })
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, env):
        for name in ("app", "billing", "config", "editor", "mail",
                     "paddle_api", "registry", "seats", "textract", "wallet"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(API))
        sys.path.insert(1, str(SHARED))
        try:
            return importlib.import_module("app")
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
