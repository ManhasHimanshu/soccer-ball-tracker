import boto3
import os
import json
import math
import re
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['TRACKING_TABLE']

# --- ball-reference speed/distance parameters (proven locally) ---
BALL_DIAMETER_M      = 0.22          # regulation size-5 soccer ball, ~22 cm across
BALL_CLASS_ID        = 32            # COCO "sports ball"
CONF_MIN             = 0.50          # drop low-confidence detections
ASPECT_MIN           = 0.7           # a ball's box is ~square; reject elongated boxes
ASPECT_MAX           = 1.43
MOVE_FRACTION        = 0.03          # a step must move > 3% of ball diameter to count (rejects jitter)
TTL_DAYS             = 7


def _frame_index(frame_id):
    """Extract the integer frame number from a frame filename for NUMERIC ordering.
    e.g. 'frame_10.jpg' -> 10.  Falls back to 0 if no digits found."""
    m = re.search(r'(\d+)', frame_id)
    return int(m.group(1)) if m else 0


def _best_ball(detections):
    """From one frame's detection list, return the highest-confidence valid ball
    as (cx, cy, diameter_px), or None if there's no trustworthy ball this frame."""
    best = None
    for d in detections:
        if d.get('class_id') != BALL_CLASS_ID:
            continue
        conf = d.get('confidence', 0.0)
        if conf < CONF_MIN:
            continue
        b = d['bbox']
        w = b['x2'] - b['x1']
        h = b['y2'] - b['y1']
        if h <= 0 or w <= 0:
            continue
        aspect = w / h
        if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
            continue
        if best is None or conf > best[0]:
            cx = (b['x1'] + b['x2']) / 2.0
            cy = (b['y1'] + b['y2']) / 2.0
            diam = (w + h) / 2.0
            best = (conf, cx, cy, diam)
    if best is None:
        return None
    _, cx, cy, diam = best
    return (cx, cy, diam)


def lambda_handler(event, context):
    video_id = event['videoId']
    table = dynamodb.Table(TABLE_NAME)

    # 1. read all items for this video, drop non-frame rows (STATUS, SPEED)
    resp = table.query(KeyConditionExpression=Key('videoId').eq(video_id))
    items = [i for i in resp.get('Items', []) if i['frameId'] not in ('STATUS', 'SPEED')]

    # 2. sort frames NUMERICALLY (string sort would scramble 1,10,2,...)
    items.sort(key=lambda x: _frame_index(x['frameId']))

    # 3. reduce each frame to its best ball; keep only frames that have one
    track = []  # list of (frame_index, cx, cy, diam)
    for item in items:
        payload = json.loads(item['detections'])
        dets = payload.get('detections', payload) if isinstance(payload, dict) else payload
        ball = _best_ball(dets)
        if ball is not None:
            track.append((_frame_index(item['frameId']), ball[0], ball[1], ball[2]))

    fps = float(event.get('fps', 60.0))  # frames/sec of the source video

    # 4. walk consecutive ball frames: gate jitter, sum moving distance, find peak speed
    moving_m = 0.0
    raw_m = 0.0
    peak_mps = 0.0
    for (fa, xa, ya, da), (fb, xb, yb, db) in zip(track, track[1:]):
        dpx = math.hypot(xb - xa, yb - ya)
        scale = (BALL_DIAMETER_M / da + BALL_DIAMETER_M / db) / 2.0  # avg local m/px
        meters = dpx * scale
        raw_m += meters
        threshold_px = MOVE_FRACTION * ((da + db) / 2.0)
        if dpx > threshold_px:
            moving_m += meters
            dt = (fb - fa) / fps
            if dt > 0:
                v = meters / dt
                if v > peak_mps:
                    peak_mps = v

    peak_kmh = 3.6 * peak_mps

    # 5. write the SPEED item back (separate lifecycle from STATUS/frames)
    expires = int((datetime.now(timezone.utc) + timedelta(days=TTL_DAYS)).timestamp())
    result = {
        'ballFramesUsed': len(track),
        'movingDistanceM': round(moving_m, 3),
        'peakSpeedMps':    round(peak_mps, 3),
        'peakSpeedKmh':    round(peak_kmh, 2),
        'computedAt':      datetime.now(timezone.utc).isoformat(),
    }
    table.put_item(Item={
        'videoId':   video_id,
        'frameId':   'SPEED',
        'result':    json.dumps(result),
        'expiresAt': expires,
    })

    return {'videoId': video_id, **result}
