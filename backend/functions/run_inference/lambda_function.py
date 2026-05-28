import boto3
import os
import json
from datetime import datetime, timezone

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
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