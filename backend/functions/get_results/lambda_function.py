import boto3
import os
import json
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ['TRACKING_TABLE']

def lambda_handler(event, context):
    video_id = event['pathParameters']['videoId']
    table    = dynamodb.Table(TABLE_NAME)

    response = table.query(
        KeyConditionExpression=Key('videoId').eq(video_id)
    )

    items = response.get('Items', [])
    # Pull out the SPEED item (written by the compute-distance step) before filtering
    speed_item = next((i for i in items if i['frameId'] == 'SPEED'), None)
    speed = json.loads(speed_item['result']) if speed_item else None
    # Keep only real frame rows (drop STATUS and SPEED)
    frame_items = [item for item in items if item['frameId'] not in ('STATUS', 'SPEED')]

    if not frame_items:
        return {
            'statusCode': 404,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'No results found for this video'})
        }

    frames = []
    for item in sorted(frame_items, key=lambda x: x['frameId']):
        frames.append({
            'frameId':    item['frameId'],
            'detections': json.loads(item['detections'])
        })

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type':                'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'videoId':    video_id,
            'frameCount': len(frames),
            'frames':     frames,
            'speed':      speed
        })
    }