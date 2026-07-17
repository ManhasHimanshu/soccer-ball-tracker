import boto3
import os
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

sagemaker_runtime = boto3.client('sagemaker-runtime')

TABLE_NAME    = os.environ['TRACKING_TABLE']
ENDPOINT_NAME = os.environ['SAGEMAKER_ENDPOINT']

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
    bucket     = event['bucket']
    frame_keys = event['frameKeys']

    table = dynamodb.Table(TABLE_NAME)
    set_status(table, video_id, 'RUNNING_INFERENCE')

    detections = []
    for key in frame_keys:
        # Download frame
        response = s3.get_object(Bucket=bucket, Key=key)
        frame_bytes = response['Body'].read()

        # Send to SageMaker
        sm_response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='application/octet-stream',
            Body=frame_bytes
        )
        result = json.loads(sm_response['Body'].read())

        detections.append({
            'frameKey': key,
            'detections': result
        })

    return {
        'videoId': video_id,
        'bucket': bucket,
        'detections': detections
    }