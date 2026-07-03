import os
import time
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])

def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]

    table.put_item(
        Item={
            "connectionId": connection_id,
            "ttl": int(time.time()) + 7200,  # auto-expire in 2 hours
        }
    )

    return {"statusCode": 200}