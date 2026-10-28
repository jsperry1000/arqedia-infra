"""
tenant_inventory.py - everything one tenant holds, counted. READ-ONLY.

Step 2 and step 9 of docs/runbooks/account_deletion_manual.md. Run before a
deletion to record what is there, and after it to prove what is left:

    python docs/runbooks/tenant_inventory.py <tenant_id> > before.json

Counts Aurora rows by tenant_id, S3 object VERSIONS (every bucket is
versioned, so a current-object count would read zero while every byte is
still held), DynamoDB items, and lists the tenant's seat addresses, which
step 7 needs after the seat rows are gone. Writes nothing anywhere.
"""

import json
import sys

import boto3

PROFILE = "arqedia"
REGION = "us-east-2"
ACCOUNT = "667523685221"
CLUSTER_ARN = "arn:aws:rds:us-east-2:%s:cluster:arqedia-dev-aurora" % ACCOUNT
DATABASE = "arqedia"

# Every table carrying tenant_id, read from information_schema on 20 October
# 2026, and again on 27 October 2026 for the workspace tables (migrations 040,
# 045, 047) and terms_acceptance (049). A table added since is missed here:
# step 2 re-reads the list and stops if it differs.
TENANT_TABLES = [
    "claim_evidence", "claim", "memo_source", "memo_rewrite", "memo",
    "extracted_value", "document", "engagement",
    "seat_workspace", "workspace_deletion", "workspace",
    "config_section_field", "config_section", "config_template",
    "config_type_schema", "config_field", "config_schema",
    "config_document_type", "config_category", "config_revision",
    "pack_offer", "meter_price",
    "seat_invitation", "seat", "topup_request",
    "wallet_allocation", "wallet_bucket", "wallet_ledger",
    "paddle_event", "terms_acceptance", "subscription", "tenant_domain",
    "tenant",
]

# Carries no tenant_id: an invitation's workspaces, found through the
# invitation, which does.
INVITATION_WORKSPACES = (
    "SELECT COUNT(*) FROM seat_invitation_workspace WHERE invitation_id IN "
    "(SELECT invitation_id FROM seat_invitation WHERE tenant_id = :t)")

BUCKETS = {
    "docs": ["tenants/{t}/"],
    "review": ["tenants/{t}/"],
    "curated": ["tenants/{t}/", "shares/{t}/"],
    "brand": ["tenants/{t}/"],
}


def main(tenant_id):
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    rds = session.client("rds-data")
    secret = _cluster_secret(session)

    def sql(statement, params=()):
        return rds.execute_statement(
            resourceArn=CLUSTER_ARN, secretArn=secret, database=DATABASE,
            sql=statement, parameters=list(params))["records"]

    t = [{"name": "t", "value": {"longValue": tenant_id}}]
    out = {"tenant_id": tenant_id, "aurora": {}, "s3_versions": {},
           "dynamodb": {}}

    live = sorted(r[0]["stringValue"] for r in sql(
        "SELECT DISTINCT table_name FROM information_schema.columns "
        "WHERE table_schema = 'arqedia' AND column_name = 'tenant_id'"))
    out["tables_unlisted"] = sorted(set(live) - set(TENANT_TABLES))

    for table in TENANT_TABLES:
        if table not in live:   # terms_acceptance, until 049 is applied
            out["aurora"][table] = None
            continue
        out["aurora"][table] = sql(
            "SELECT COUNT(*) FROM `%s` WHERE tenant_id = :t" % table,
            t)[0][0]["longValue"]
    out["aurora"]["seat_invitation_workspace"] = sql(
        INVITATION_WORKSPACES, t)[0][0]["longValue"]

    tenant = sql("SELECT name, plan FROM tenant WHERE tenant_id = :t", t)
    out["tenant_name"] = tenant[0][0].get("stringValue") if tenant else None
    out["seat_emails"] = [r[0]["stringValue"] for r in sql(
        "SELECT email FROM seat WHERE tenant_id = :t ORDER BY email", t)]
    out["domains"] = [r[0]["stringValue"] for r in sql(
        "SELECT domain FROM tenant_domain WHERE tenant_id = :t", t)]
    out["subscription"] = [
        {"paddle_subscription_id": r[0].get("stringValue"),
         "paddle_status": r[1].get("stringValue")}
        for r in sql("SELECT paddle_subscription_id, paddle_status "
                     "FROM subscription WHERE tenant_id = :t", t)]

    s3 = session.client("s3")
    for bucket, prefixes in BUCKETS.items():
        name = "arqedia-dev-%s-%s" % (bucket, ACCOUNT)
        for prefix in prefixes:
            prefix = prefix.format(t=tenant_id)
            versions = markers = 0
            for page in s3.get_paginator("list_object_versions").paginate(
                    Bucket=name, Prefix=prefix):
                versions += len(page.get("Versions", []))
                markers += len(page.get("DeleteMarkers", []))
            out["s3_versions"]["%s/%s" % (name, prefix)] = {
                "versions": versions, "delete_markers": markers}

    dynamo = session.resource("dynamodb")
    grants = []
    for page in session.client("dynamodb").get_paginator("query").paginate(
            TableName="arqedia-dev-share-grant", IndexName="tenant-index",
            KeyConditionExpression="tenant_id = :t",
            ExpressionAttributeValues={":t": {"N": str(tenant_id)}}):
        grants += [i["grant_id"]["S"] for i in page["Items"]]
    log = 0
    for g in grants:
        for page in session.client("dynamodb").get_paginator("query").paginate(
                TableName="arqedia-dev-share-access-log",
                KeyConditionExpression="grant_id = :g",
                ExpressionAttributeValues={":g": {"S": g}}, Select="COUNT"):
            log += page["Count"]
    usage = dynamo.Table("arqedia-dev-share-usage").query(
        KeyConditionExpression="tenant_id = :t",
        ExpressionAttributeValues={":t": tenant_id}, Select="COUNT")["Count"]
    out["dynamodb"] = {"share-grant": len(grants),
                       "share-access-log": log, "share-usage": usage}

    print(json.dumps(out, indent=2))


def _cluster_secret(session):
    cluster = session.client("rds").describe_db_clusters(
        DBClusterIdentifier="arqedia-dev-aurora")["DBClusters"][0]
    return cluster["MasterUserSecret"]["SecretArn"]


if __name__ == "__main__":
    main(int(sys.argv[1]))
