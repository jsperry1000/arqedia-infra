"""
paddle_webhook - receives Paddle notifications.

A placeholder until step 3. It answers 503 so that a delivery arriving before
the handler exists is retried by Paddle rather than acknowledged and lost.

STEP 3: never log the request body or the payload. It carries the customer's
email address.
"""

import json


def lambda_handler(event, context):
    return {
        "statusCode": 503,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": "not built yet"}),
    }
