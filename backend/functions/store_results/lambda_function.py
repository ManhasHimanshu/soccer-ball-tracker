import boto3
import os
import json
from datetime import datetime, timezone, timedelta

dynamodb = boto3.resource('dynamodb')

WS_CONNECTIONS_TABLE = os.environ['WS_CONNECTIONS_TABLE']
WS_CALLBACK_URL = os.environ['WS_CALLBACK_URL']
apigw = boto3.client('apigatewaymanagementapi', endpoint_url=WS_CALLBACK_URL)
ws_table = dynamodb.Table(WS_CONNECTIONS_TABLE)

def broadcast(payload):
    """Best-effort push of payload to every open WebSocket connection."""
    try:
        connections = ws_table.scan(ProjectionExpression='connectionId')['Items']
    except Exception as e:
        print(f'broadcast: scan failed: {e}')
        return
    data = json.dumps(payload).encode('utf-8')
    for conn in connections:
        cid = conn['connectionId']
        try:
            apigw.post_to_connection(ConnectionId=cid, Data=data)
        except Exception as e:
            print(f'broadcast: post to {cid} failed: {e}')

TABLE_NAME = os.environ['TRACKING_TABLE']
TTL_DAYS   = 7

def set_status(table, video_id, state, error=None):
    item = {
        'videoId': video_id,
        'frameId': 'STATUS',
        'state': state,
        'updatedAt': datetime.now(timezone.utc).isoformat()
    }
    if error:
        item['error'] = error
    table.put_item(Item=item)
    broadcast({'videoId': video_id, 'state': state, 'error': error})

def lambda_handler(event, context):
    video_id   = event['videoId']
    detections = event['detections']

    table   = dynamodb.Table(TABLE_NAME)
    expires = int((datetime.now(timezone.utc) + timedelta(days=TTL_DAYS)).timestamp())

    with table.batch_writer() as batch:
        for item in detections:
            frame_id = item['frameKey'].split('/')[-1]
            batch.put_item(Item={
                'videoId':    video_id,
                'frameId':    frame_id,
                'detections': json.dumps(item['detections']),
                'expiresAt':  expires
            })

    # Mark pipeline complete
    set_status(table, video_id, 'COMPLETE')

    return {
        'videoId': video_id,
        'frameCount': len(detections)
    }