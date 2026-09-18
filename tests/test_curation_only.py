"""
What the ARQEDIA workspace may not do. The API module is loaded with boto3
replaced, so nothing reaches AWS. Run from the repository root:

    python -m unittest discover -s tests
"""

import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "lambda" / "api"
SHARED = ROOT / "lambda" / "shared"

ENV = {
    "CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
    "DATABASE": "arqedia",
    "DOCS_BUCKET": "docs", "REVIEW_BUCKET": "review",
    "CURATED_BUCKET": "curated", "BRAND_BUCKET": "brand",
    "COMPOSITION_FUNCTION": "composition",
    "TEXTRACT_TOPIC_ARN": "arn:topic", "TEXTRACT_ROLE_ARN": "arn:role",
    "RENDER_FUNCTION": "render", "PROPOSER_FUNCTION": "proposer",
    "PADDLE_API_BASE": "https://sandbox-api.paddle.test",
    "PADDLE_API_KEY_SECRET_ARN": "arn:paddle-key",
    "PADDLE_PRICE_BASE": "pri_base", "PADDLE_PRICE_BUSINESS": "pri_business",
    "PADDLE_PRICE_TOPUP": "pri_topup",
}

# The five the curator may not use, and three it may.
REFUSED = [
    "POST /config/templates/fork",
    "POST /uploads",
    "POST /engagements/{id}/file",
    "POST /engagements/{id}/generate",
    "POST /billing/checkout",
]
ALLOWED = [
    "POST /config/publish",
    "PUT /config/active",
    "POST /config/draft/sections",
]

# The same guard the other way round: the catalogue is set in the ARQEDIA
# workspace and read there, and refused to everybody else.
CURATOR_ONLY = [
    "GET /config/offer",
    "PUT /config/offer",
]


def load_api():
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
        for name in ("app", "billing", "wallet", "seats", "paddle_api",
                     "config", "editor", "registry", "textract", "pack",
                     "extractors"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(API))
        sys.path.insert(1, str(SHARED))
        try:
            return importlib.import_module("app")
        finally:
            sys.path[:] = saved


class CurationOnlyTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_the_pack_tenant_is_the_one_registry_names(self):
        self.assertEqual(self.app.registry.PACK_TENANT, 0)

    def test_each_refused_route_refuses_tenant_zero(self):
        for route in REFUSED:
            with self.subTest(route=route):
                reply = self.app._curation_only(0, route)
                self.assertIsNotNone(reply)
                self.assertEqual(reply["statusCode"], 403)
                body = json.loads(reply["body"])
                self.assertIn("curates the catalogue", body["error"])
                self.assertIn("does not file documents", body["error"])

    def test_each_refused_route_allows_a_real_tenant(self):
        for route in REFUSED:
            with self.subTest(route=route):
                for tenant_id in (1, 5, 9101):
                    self.assertIsNone(
                        self.app._curation_only(tenant_id, route))

    def test_curation_routes_allow_tenant_zero(self):
        for route in ALLOWED:
            with self.subTest(route=route):
                self.assertIsNone(self.app._curation_only(0, route))

    def test_the_list_is_exactly_those_five(self):
        self.assertEqual(sorted(self.app.CURATOR_REFUSED_ROUTES),
                         sorted(REFUSED))

    def test_the_catalogue_routes_refuse_every_other_tenant(self):
        for route in CURATOR_ONLY:
            with self.subTest(route=route):
                for tenant_id in (1, 5, 9101):
                    reply = self.app._curation_only(tenant_id, route)
                    self.assertIsNotNone(reply)
                    self.assertEqual(reply["statusCode"], 403)
                    body = json.loads(reply["body"])
                    self.assertIn("ARQEDIA workspace", body["error"])

    def test_the_catalogue_routes_allow_the_curator(self):
        for route in CURATOR_ONLY:
            with self.subTest(route=route):
                self.assertIsNone(self.app._curation_only(0, route))

    def test_the_curator_only_list_is_exactly_those_two(self):
        self.assertEqual(sorted(self.app.CURATOR_ONLY_ROUTES),
                         sorted(CURATOR_ONLY))

    def test_no_route_is_on_both_lists(self):
        # One would be refused to everybody, which is a route that exists on
        # paper and nowhere else.
        self.assertEqual(
            self.app.CURATOR_REFUSED_ROUTES & self.app.CURATOR_ONLY_ROUTES,
            frozenset())

    def test_the_dispatcher_refuses_a_tenant_reaching_the_catalogue(self):
        event = {
            "routeKey": "PUT /config/offer",
            "body": json.dumps({"revision": 9, "templates": ["x"]}),
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": "5", "custom:role": "admin",
                "email": "someone@firm.com"}}}},
        }
        reply = self.app.lambda_handler(event, None)
        self.assertEqual(reply["statusCode"], 403)
        self.assertIn("ARQEDIA workspace", reply["body"])

    def test_the_dispatcher_refuses_before_anything_is_read(self):
        # A token for tenant 0 on a refused route, with a body that would
        # otherwise be parsed and acted on.
        event = {
            "routeKey": "POST /uploads",
            "body": json.dumps({"engagement": "acme", "filename": "a.pdf"}),
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": "0", "custom:role": "admin",
                "email": "admin@arqedia.com"}}}},
        }
        reply = self.app.lambda_handler(event, None)
        self.assertEqual(reply["statusCode"], 403)
        self.assertIn("curates the catalogue", reply["body"])
        self.app._s3.generate_presigned_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
