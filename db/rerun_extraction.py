#!/usr/bin/env python3
"""
rerun_extraction.py - re-extract documents left half-done.

A document whose extraction failed part-way has values written and no
extracted_at, so the screen reports it as still extracting for ever. This
clears the partial values and re-fires extraction.

Extraction skips an envelope marked extraction_complete - that guard stops our
own write re-triggering the function - so the flag has to be cleared before the
envelope is written back.

Uses the AWS CLI rather than boto3, so it depends on nothing beyond what is
already installed to run terraform.

    python db/rerun_extraction.py 199 200 201
    python db/rerun_extraction.py --stuck        every stuck document

Deleting the partial values is deliberate rather than additive: they are half
of one document's extraction, and leaving them would mix a failed pass with a
successful one under the same document. Everything else about the document -
its row, its file, its filing - is untouched.
"""

import json
import subprocess
import sys

PROFILE = "arqedia"
REGION = "us-east-2"
CLUSTER = ("arn:aws:rds:us-east-2:667523685221:cluster:arqedia-dev-aurora")
SECRET = ("arn:aws:secretsmanager:us-east-2:667523685221:secret:"
          "rds!cluster-8f9fa8a3-b863-480a-b1cf-d00308c8b9f1-0e65rq")
DATABASE = "arqedia"
REVIEW_BUCKET = "arqedia-dev-review-667523685221"
TENANT = 1


def run(args, stdin=None):
    """Binary in, UTF-8 out, explicitly.

    Python on Windows decodes a subprocess using the locale encoding, which is
    cp1252 - and an envelope full of names from eight jurisdictions is not
    cp1252. Relying on the locale was the fault."""
    result = subprocess.run(
        args, capture_output=True,
        input=stdin.encode("utf-8") if stdin is not None else None)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode("utf-8", "replace").strip() or "command failed")
    return result.stdout.decode("utf-8")


def sql(statement):
    out = run([
        "aws", "rds-data", "execute-statement",
        "--profile", PROFILE, "--region", REGION,
        "--resource-arn", CLUSTER, "--secret-arn", SECRET,
        "--database", DATABASE, "--sql", statement, "--output", "json",
    ])
    return json.loads(out)


def cell(record, i):
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in record[i]:
            return record[i][kind]
    return None


def stuck():
    """Filed, values written, no extracted_at: extraction began and did not
    finish. A document with no values may simply have yielded nothing, so it
    is left alone."""
    result = sql(
        "SELECT document_id, s3_key, filename FROM document d "
        "WHERE tenant_id = %d AND state = 'filed' AND extracted_at IS NULL "
        "AND (SELECT COUNT(*) FROM extracted_value v "
        "     WHERE v.document_id = d.document_id) > 0 "
        "ORDER BY document_id" % TENANT)
    return [(cell(r, 0), cell(r, 1), cell(r, 2))
            for r in result.get("records", [])]


def rerun(document_id, s3_key, filename):
    print("  %s  (%s)" % (filename, document_id))

    result = sql("SELECT COUNT(*) FROM extracted_value "
                 "WHERE tenant_id = %d AND document_id = %d"
                 % (TENANT, document_id))
    before = cell(result.get("records", [[{}]])[0], 0) or 0

    sql("DELETE FROM extracted_value WHERE tenant_id = %d AND document_id = %d"
        % (TENANT, document_id))
    print("     cleared %s partial value%s"
          % (before, "" if before == 1 else "s"))

    envelope_key = s3_key + ".normalized.json"
    body = run(["aws", "s3", "cp", "--profile", PROFILE,
                "s3://%s/%s" % (REVIEW_BUCKET, envelope_key), "-"])
    envelope = json.loads(body)

    # The guard that stops our own write re-triggering extraction. Clearing it
    # is what makes the next write fire the function.
    envelope["extraction_complete"] = False
    envelope.pop("extraction_results", None)

    run(["aws", "s3", "cp", "--profile", PROFILE,
         "--content-type", "application/json", "-",
         "s3://%s/%s" % (REVIEW_BUCKET, envelope_key)],
        stdin=json.dumps(envelope, ensure_ascii=False))
    print("     envelope rewritten; extraction will re-fire")


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        return

    if args[0] == "--stuck":
        targets = stuck()
        if not targets:
            print("nothing is stuck")
            return
        print("re-running %d document%s\n"
              % (len(targets), "" if len(targets) == 1 else "s"))
    else:
        # Named explicitly, so the stuck test is not applied. A document
        # part-way through a previous run has had its values cleared already
        # and would no longer match "has values" - it must still be runnable.
        wanted = ",".join(str(int(a)) for a in args)
        result = sql(
            "SELECT document_id, s3_key, filename FROM document "
            "WHERE tenant_id = %d AND document_id IN (%s) ORDER BY document_id"
            % (TENANT, wanted))
        targets = [(cell(r, 0), cell(r, 1), cell(r, 2))
                   for r in result.get("records", [])]
        if not targets:
            print("no such document")
            return

    for document_id, s3_key, filename in targets:
        rerun(document_id, s3_key, filename)

    print("\nDone. Extraction runs asynchronously; watch the values column.")


if __name__ == "__main__":
    main()
