import boto3
import os
import json
from datetime import datetime, timezone, timedelta

dynamodb = boto3.resource('dynamodb')

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