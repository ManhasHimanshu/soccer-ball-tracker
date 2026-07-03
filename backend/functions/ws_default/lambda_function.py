import json

def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    body = event.get("body", "")

    print(json.dumps({
        "route": "$default",
        "connectionId": connection_id,
        "body": body,
    }))

    return {"statusCode": 200}