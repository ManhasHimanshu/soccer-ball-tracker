import boto3
import os
import json

dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ['TRACKING_TABLE']

def lambda_handler(event, context):
    video_id = event['pathParameters']['videoId']
    table    = dynamodb.Table(TABLE_NAME)

    response = table.get_item(Key={
        'videoId': video_id,
        'frameId': 'STATUS'
    })

    item = response.get('Item')
    if not item:
        return {
            'statusCode': 404,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Video not found'})
        }

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type':                'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'videoId':   item['videoId'],
            'state':     item['state'],
            'updatedAt': item['updatedAt'],
            'error':     item.get('error')
        })
    }