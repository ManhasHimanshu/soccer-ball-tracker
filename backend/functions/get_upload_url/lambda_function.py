import boto3
import os
import json
import uuid

s3 = boto3.client('s3')

BUCKET_NAME = os.environ['VIDEO_BUCKET']

def lambda_handler(event, context):
    video_id = str(uuid.uuid4())
    s3_key   = f'videos/{video_id}.mp4'

    presigned_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket':      BUCKET_NAME,
            'Key':         s3_key,
            'ContentType': 'video/mp4'
        },
        ExpiresIn=3600
    )

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type':                'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'uploadUrl': presigned_url,
            'videoId':   video_id
        })
    }