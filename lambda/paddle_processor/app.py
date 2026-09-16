"""
paddle_processor - applies a verified Paddle event.

A placeholder until step 3. Nothing invokes it until the receiver is built.

STEP 3: never log the event or its payload. It carries the customer's email
address.
"""

import json


def lambda_handler(event, context):
    return {
        "statusCode": 503,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": "not built yet"}),
    }
