import boto3
import os
import subprocess
import json
from datetime import datetime, timezone

s3 = boto3.client('s3')
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
FRAMES_PREFIX = 'frames'

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
    video_id = event['videoId']
    bucket   = event['bucket']
    key      = event['key']

    table = dynamodb.Table(TABLE_NAME)

    # Mark pipeline as started
    set_status(table, video_id, 'EXTRACTING_FRAMES')

    # Download video to /tmp
    local_video = f'/tmp/{video_id}.mp4'
    s3.download_file(bucket, key, local_video)

    # Extract frames with ffmpeg (1 frame per second)
    frames_dir = f'/tmp/{video_id}_frames'
    os.makedirs(frames_dir, exist_ok=True)
    subprocess.run([
        'ffmpeg', '-i', local_video,
        '-vf', 'fps=1',
        f'{frames_dir}/frame_%04d.jpg',
        '-y'
    ], check=True)

    # Upload frames to S3
    frame_keys = []
    for filename in sorted(os.listdir(frames_dir)):
        local_path = os.path.join(frames_dir, filename)
        s3_key = f'{FRAMES_PREFIX}/{video_id}/{filename}'
        s3.upload_file(local_path, bucket, s3_key)
        frame_keys.append(s3_key)

    return {
        'videoId': video_id,
        'bucket': bucket,
        'frameKeys': frame_keys
    }