"""
cancel_subscription.py - step 3 of docs/runbooks/account_deletion_manual.md.

    python docs/runbooks/cancel_subscription.py <tenant_id>

Cancels the tenant's Paddle subscription immediately, through
lambda/api/paddle_api.cancel_subscription: the one implementation, with the
Paddle settings the deployed API function runs with (sandbox or live is
whatever that function points at). The key is read from Secrets Manager and
never printed.

Does nothing when the tenant has no subscription, or when it already reads
canceled. Cannot be undone: Paddle does not reinstate a cancelled
subscription.
"""

import os
import sys

# Before anything imports boto3: the default profile is another account.
os.environ["AWS_PROFILE"] = "arqedia"
os.environ["AWS_DEFAULT_REGION"] = "us-east-2"

import boto3  # noqa: E402

API_FUNCTION = "arqedia-dev-api"
CLUSTER_ARN = ("arn:aws:rds:us-east-2:667523685221:cluster:"
               "arqedia-dev-aurora")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def main(tenant_id):
    rds = boto3.client("rds-data")
    secret = boto3.client("rds").describe_db_clusters(
        DBClusterIdentifier="arqedia-dev-aurora"
    )["DBClusters"][0]["MasterUserSecret"]["SecretArn"]
    found = rds.execute_statement(
        resourceArn=CLUSTER_ARN, secretArn=secret, database="arqedia",
        sql="SELECT paddle_subscription_id, paddle_status FROM subscription "
            "WHERE tenant_id = :t",
        parameters=[{"name": "t", "value": {"longValue": tenant_id}}],
    )["records"]
    if not found:
        print("tenant %d has no subscription; nothing to cancel" % tenant_id)
        return
    subscription_id = found[0][0]["stringValue"]
    status = found[0][1].get("stringValue")
    if status == "canceled":
        print("%s already canceled; nothing to do" % subscription_id)
        return

    # paddle_api reads its settings from the environment at import.
    env = boto3.client("lambda").get_function_configuration(
        FunctionName=API_FUNCTION)["Environment"]["Variables"]
    for name, value in env.items():
        if name.startswith("PADDLE_"):
            os.environ[name] = value
    sys.path.insert(0, os.path.join(REPO, "lambda", "api"))
    import paddle_api

    print("cancelling %s (was %s) at %s"
          % (subscription_id, status, env["PADDLE_API_BASE"]))
    print("Paddle answers: %s" % paddle_api.cancel_subscription(
        subscription_id))


if __name__ == "__main__":
    main(int(sys.argv[1]))
