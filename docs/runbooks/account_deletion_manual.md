# ARQEDIA — Deleting a tenant by hand

Written 20 October 2026, for item #9 in `docs/ARQEDIA_decisions_2026-10-20.md`.
**A stopgap.** No automated account deletion exists. This is what a person
runs, in this order, when a tenant must be deleted. Nothing here has been
run end to end; the inventory script (steps 2 and 9) has been run read-only
against tenant 10.

Run from `c:\terraform\arqedia` in Git Bash, `--profile arqedia`, us-east-2.
Every command that deletes is irreversible except by restoring a backup
(see Gaps).

---

## What was read to write this (20 October 2026, live)

- **Aurora.** 29 tables carry `tenant_id`. There is **one** foreign key in
  the schema, `subscription.plan_id → plan`, and no triggers, so the
  database enforces no order; the order below is children before parents so
  a run stopped half way leaves the tenant row to find it by. Five tables
  hold no `tenant_id`: `plan`, `schema_migration` (not personal),
  `signup_attempt` (email domain, SHA-256 of the email, IP),
  `pending_signup` (email, organisation, IP), `signup_allow` (invited
  addresses).
- **`tenant_domain`** maps `domain → tenant_id`. Sign-up refuses a new
  workspace for a domain with a row and `multi_allowed` false
  (`lambda/signup/app.py:545`). Deleting the row frees the domain: anyone at
  it can then sign up and take a new trial. Not deleting it refuses that
  domain at sign-up for ever (the defect in CLAUDE.md, What is open).
- **S3**, all four buckets versioned, so deleting a key only adds a delete
  marker and every byte stays. Tenant data lives under `tenants/<id>/` in
  `docs`, `review`, `curated` and `brand`, and `shares/<id>/` in `curated`.
  `admin`, `frontend`, `site` hold no tenant data.
- **Image files** (added 26 October 2026, graphics-insert decision N3). A
  person's own images in memos are in `curated`, in two places, both under
  `tenants/<id>/`: `tenants/<id>/images/memos/<memo>/` (a saved revision's
  own copies, kept as long as the revision) and
  `tenants/<id>/working/images/memos/<memo>/` (uploads while editing, which
  the daily image sweep removes 24 hours after nothing names them). Step 5's
  `tenants/<id>/` prefix in `curated` takes both, every version; step 9's
  inventory counts them in that prefix. Nothing about them is in Aurora: a
  memo's text names an image, and the file is only in S3.
- **DynamoDB.** `share-grant` (tenant on `tenant-index`), `share-access-log`
  (by grant), `share-usage` (by tenant). `viewer-account` is the
  recipient's, not the tenant's, and is not touched: other tenants may
  share with the same person. Point-in-time recovery is on, 35 days.
- **`share.purge_tenant`** (`lambda/api/share.py:821`) deletes the tenant's
  grants, each grant's access log, its usage counters and `shares/<id>/` in
  `curated`. Nothing else: no Aurora, no `tenants/` prefixes, no Cognito. It
  is called from nowhere, and it is **not used here**, for three reasons:
  it needs the API Lambda's whole import chain and environment to run; its
  access-log and usage queries read only the first page (1 MB) and would
  leave the rest; and on a versioned bucket its `delete_object` leaves every
  PDF in place behind a delete marker. Step 5 does what it does, paginated
  and versions included. Whoever wires it into real deletion fixes those.
- **Cognito.** Customer users are in `arqedia-dev-users`
  (`us-east-2_AcsEyzDLL`) with the email as username and
  `custom:tenant_id`. They are not removed by anything in Aurora; a user left
  behind can still sign in and carries a tenant id that no longer exists.
  Cognito cannot filter on a custom attribute, so the addresses come from
  the `seat` table, captured in step 2 before step 6 deletes it.
  `arqedia-dev-viewers` holds recipients and is not touched;
  `arqedia-dev-staff` is ours.
- **Paddle.** A subscription left active keeps billing a tenant that no
  longer exists.

---

## Steps

Set these once:

```bash
export MSYS_NO_PATHCONV=1 AWS_PROFILE=arqedia AWS_REGION=us-east-2
T=<tenant_id>
C=arn:aws:rds:us-east-2:667523685221:cluster:arqedia-dev-aurora
S=$(aws rds describe-db-clusters --db-cluster-identifier arqedia-dev-aurora \
      --query 'DBClusters[0].MasterUserSecret.SecretArn' --output text)
q() { aws rds-data execute-statement --resource-arn $C --secret-arn "$S" \
        --database arqedia --format-records-as JSON \
        --query formattedRecords --output text --sql "$1"; }
```

### 1. Confirm the request

- The request comes from an Administrator of that tenant, in writing, to
  info@ebl-finance.com. Check the address is an `admin` seat:
  `q "SELECT email, role FROM seat WHERE tenant_id = $T"`
- Record the request, the date and who is running this. **Gap:** there is no
  deletion log or ticket system; keep the record outside the product.

**Verify:** the requester's address appears with role `admin`.

### 2. Take the inventory

```bash
python docs/runbooks/tenant_inventory.py $T > deletion-$T-before.json
```

Keep the file. It holds the seat addresses step 7 needs, the Paddle
subscription id step 3 needs, and the counts step 9 compares against.

**Verify:** `"tables_unlisted": []`. If any table is listed, a table carrying
`tenant_id` has been added since this was written — **stop** and add it to
step 6 and to `TENANT_TABLES` in the script before going on.

### 3. Cancel the Paddle subscription

```bash
python docs/runbooks/cancel_subscription.py $T
```

It cancels the tenant's subscription **immediately** (not at period end)
through `paddle_api.cancel_subscription`, with the Paddle settings of the
deployed `arqedia-dev-api` function, and does nothing when there is no
subscription or it already reads `canceled`. **Decided 20 October 2026:**
cancelling is part of every deletion; the deletion request is the
confirmation and no separate one is sought. Paddle cannot reinstate it.

Do not go on to step 6 before this verifies: the `subscription.updated`
webhook rewrites the subscription row for this tenant, and one landing after
step 6 would put a row back.

**Verify:** after the webhook lands,
`q "SELECT paddle_status FROM subscription WHERE tenant_id = $T"` reads
`canceled`. **Gap:** Paddle keeps its own customer record and invoices; this
procedure does not and cannot remove them (Paddle is merchant of record).

### 4. Stop the tenant's users signing in

For every address in `seat_emails`:

```bash
aws cognito-idp admin-disable-user --user-pool-id us-east-2_AcsEyzDLL \
  --username <email>
aws cognito-idp admin-user-global-sign-out --user-pool-id us-east-2_AcsEyzDLL \
  --username <email>
```

**Verify:** `aws cognito-idp admin-get-user --user-pool-id us-east-2_AcsEyzDLL
--username <email> --query Enabled` reads `false` for each. An access token
already issued lives up to 60 minutes; wait that long before step 5 if the
tenant was active today.

### 5. Delete sharing and S3

Revokes every share (a deleted grant is a refused link) and removes every
version of every object - the memos' image files among them, under
`curated/tenants/<id>/images/` and `curated/tenants/<id>/working/images/`.

```bash
python - "$T" <<'EOF'
import sys, boto3
t = int(sys.argv[1])
s = boto3.Session(profile_name="arqedia", region_name="us-east-2")
ddb = s.client("dynamodb")
grants = []
for p in ddb.get_paginator("query").paginate(
        TableName="arqedia-dev-share-grant", IndexName="tenant-index",
        KeyConditionExpression="tenant_id = :t",
        ExpressionAttributeValues={":t": {"N": str(t)}}):
    grants += [i["grant_id"]["S"] for i in p["Items"]]
for g in grants:
    for p in ddb.get_paginator("query").paginate(
            TableName="arqedia-dev-share-access-log",
            KeyConditionExpression="grant_id = :g",
            ExpressionAttributeValues={":g": {"S": g}}):
        for i in p["Items"]:
            ddb.delete_item(TableName="arqedia-dev-share-access-log",
                            Key={"grant_id": i["grant_id"],
                                 "occurred_at": i["occurred_at"]})
    ddb.delete_item(TableName="arqedia-dev-share-grant",
                    Key={"grant_id": {"S": g}})
for p in ddb.get_paginator("query").paginate(
        TableName="arqedia-dev-share-usage",
        KeyConditionExpression="tenant_id = :t",
        ExpressionAttributeValues={":t": {"N": str(t)}}):
    for i in p["Items"]:
        ddb.delete_item(TableName="arqedia-dev-share-usage",
                        Key={"tenant_id": i["tenant_id"],
                             "period": i["period"]})
s3 = s.client("s3")
for bucket, prefixes in {"docs": ["tenants"], "review": ["tenants"],
                         "curated": ["tenants", "shares"],
                         "brand": ["tenants"]}.items():
    name = "arqedia-dev-%s-667523685221" % bucket
    for prefix in prefixes:
        prefix = "%s/%d/" % (prefix, t)   # the trailing slash matters:
        # without it tenant 1 would take tenants 10 to 19 with it
        for p in s3.get_paginator("list_object_versions").paginate(
                Bucket=name, Prefix=prefix):
            objs = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                    for v in p.get("Versions", []) + p.get("DeleteMarkers", [])]
            for i in range(0, len(objs), 1000):
                s3.delete_objects(Bucket=name,
                                  Delete={"Objects": objs[i:i + 1000],
                                          "Quiet": True})
print("grants", len(grants))
EOF
```

**Verify:** in step 9. For the images on their own:

```bash
for p in images working/images; do
  aws s3api list-object-versions --bucket arqedia-dev-curated-667523685221 \
    --prefix "tenants/$T/$p/" --query 'length(Versions || `[]`)'
done
```

reads `0` and `0`.

### 6. Delete the Aurora rows

One transaction: all of it or none.

```bash
X=$(aws rds-data begin-transaction --resource-arn $C --secret-arn "$S" \
      --database arqedia --query transactionId --output text)
# No tenant_id of its own: through the invitation, before seat_invitation goes.
aws rds-data execute-statement --resource-arn $C --secret-arn "$S" \
  --database arqedia --transaction-id "$X" \
  --sql "DELETE FROM seat_invitation_workspace WHERE invitation_id IN
         (SELECT invitation_id FROM seat_invitation WHERE tenant_id = $T)" \
  --query numberOfRecordsUpdated --output text | sed "s/^/seat_invitation_workspace /"
for table in claim_evidence claim memo_source memo_rewrite memo \
    extracted_value document engagement \
    seat_workspace workspace_deletion workspace \
    config_section_field config_section config_template config_type_schema \
    config_field config_schema config_document_type config_category \
    config_revision pack_offer meter_price \
    seat_invitation seat topup_request wallet_allocation wallet_bucket \
    subscription tenant_domain tenant; do
  aws rds-data execute-statement --resource-arn $C --secret-arn "$S" \
    --database arqedia --transaction-id "$X" \
    --sql "DELETE FROM \`$table\` WHERE tenant_id = $T" \
    --query numberOfRecordsUpdated --output text | sed "s/^/$table /"
done
```

Read the counts against the inventory. They match: commit.
They do not: roll back, and find out why before anything else.

```bash
aws rds-data commit-transaction   --resource-arn $C --secret-arn "$S" --transaction-id "$X"
# or
aws rds-data rollback-transaction --resource-arn $C --secret-arn "$S" --transaction-id "$X"
```

**Unverified for a large tenant.** A Data API statement times out after 45
seconds. Tenant 1 holds 66,690 `claim_evidence` rows; whether one DELETE of
that size finishes in time has not been tried. If one times out, the
transaction rolls back and nothing is lost — split that table's delete by
`memo_id` and run it again.

`meter_price` and `pack_offer` delete only the tenant's own rows; the
standard rows have `tenant_id IS NULL` and `= $T` never matches them.

**Kept, deliberately: `wallet_ledger` and `paddle_event`.** The ledger is
append-only (CLAUDE.md, Money) and the Terms draft of 20 October says it is
kept as an accounting record. Both hold personal data —
`wallet_ledger.created_by` is the address that clicked, and `paddle_event`
holds Paddle's payloads. **Decided 20 October 2026:** both are kept as they
are, and the addresses are not blanked.

**Not touched, and personal data:** `signup_attempt`, `pending_signup` and
`signup_allow`, which hold no `tenant_id`.

**Kept, deliberately: `terms_acceptance`** (migration 049). Decided 27
October 2026: kept as the ledger is kept, as the evidence that the
customer agreed (`docs/ARQEDIA_decisions_2026-10-27.md` §5). Remove the tenant's rows by
address and domain if the request covers them:

```bash
q "SELECT COUNT(*) FROM pending_signup WHERE email IN ('<a>','<b>')"
q "SELECT COUNT(*) FROM signup_allow   WHERE email IN ('<a>','<b>')"
q "SELECT COUNT(*) FROM signup_attempt WHERE email_domain = '<domain>'"
```

**Gap:** `signup_attempt` stores a hash of the email, not the address, and
rows from other people at the same domain share it; there is no clean way to
take one person's rows out of it. It has no retention limit (#10).

### 7. Delete the Cognito users

For every address in `seat_emails` from step 2:

```bash
aws cognito-idp admin-delete-user --user-pool-id us-east-2_AcsEyzDLL \
  --username <email>
```

**Verify:** `admin-get-user` for each returns `UserNotFoundException`.

### 8. Tell the requester

What was deleted, and what remains and for how long (the Gaps below):
backups up to 35 days, logs, the ledger, Paddle's records.

### 9. Prove it

```bash
python docs/runbooks/tenant_inventory.py $T > deletion-$T-after.json
```

**Verify:** every `aurora` count is 0 except `wallet_ledger` and
`paddle_event`, which equal the before file; every `s3_versions` entry is
`0` and `0`; `terms_acceptance` equals the before file; every `dynamodb` count is 0; `seat_emails`, `domains` and
`subscription` are empty.

---

## Gaps — what this procedure cannot do or cannot prove

- **No dry run.** Step 2's inventory and step 6's transaction counts are the
  nearest thing. S3 and DynamoDB deletes in step 5 have no rollback.
- **No undo, and the data outlives the deletion in backups.** Aurora keeps
  automated backups 7 days; DynamoDB point-in-time recovery keeps 35. The
  deleted tenant is restorable, and so not gone, for that long. Nothing takes
  a deliberate backup first, on purpose: one would keep the data the request
  asked to remove.
- **CloudWatch Logs.** Lambda log groups have no retention set and keep
  everything for ever; lines carry tenant ids, document ids, file names and
  some email addresses. There is no way to delete one tenant's lines.
- **AWS services we call.** Whether Textract or Bedrock hold anything after
  a call returns is not verified here.
- **Paddle** keeps its customer, transactions and invoices.
- **Viewer accounts** of people the tenant shared with stay, by design.
- **The domain is free again** after step 6. Deleting `tenant_domain` lets
  the same firm sign up for a new trial.
- **Not run end to end.** No step after 2 has been exercised. The first run
  should be a throwaway tenant on dev, compared before and after.
  `cancel_subscription.py` has a unit test for the request it sends and has
  never been run against Paddle; its first run should cancel a sandbox
  subscription made for that throwaway tenant.
