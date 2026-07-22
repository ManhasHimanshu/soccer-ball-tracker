# Soccer Ball Tracker

Upload a soccer video, get the ball's peak speed in km/h — computed by a
YOLOv8 detector running on a serverless AWS pipeline, with live progress
streamed to the browser over WebSockets.

> **Demo:** 

https://github.com/user-attachments/assets/c9f128f3-8591-4e10-a8bf-2cdadb8224d5





---

## What it does

You upload an MP4. A few minutes later the page shows how fast the ball was
moving at its quickest — **51.2 km/h** on the sample clip — along with frame
counts and detection stats. While it works, a progress indicator updates in
real time: extracting frames, running inference, storing results, computing
distance.

Everything behind that is event-driven and serverless. Nothing runs 24/7.

---

## Architecture

```
Browser (React + Vite)
  │  Cognito / Google OAuth
  │
  ├─ PUT video ──────────────► S3 ──► triggers Step Functions
  │                                        │
  │                                        ├─ extract_frames    (video → frames @ 60fps → S3)
  │                                        ├─ run_inference     (frames → SageMaker YOLOv8 → detections)
  │                                        ├─ store_results     (detections → DynamoDB)
  │                                        └─ compute_distance  (detections → peak km/h → DynamoDB)
  │
  ├─ GET /results ───────────► API Gateway REST ──► get_results Lambda ──► DynamoDB
  │
  └─ WSS ────────────────────► API Gateway WebSocket ◄── status broadcasts from each step
```

**Step Functions** is the conductor: it sequences the Lambdas, retries with
exponential backoff, and routes failures. The Lambdas don't know about each
other — `run_inference` could be swapped for a different detector without
touching any other step.

**DynamoDB** (`sbt-tracking-dev`, composite key `videoId` + `frameId`) holds
three kinds of row: per-frame detections (the work), a `SPEED` row (the
answer), and a `STATUS` row (the progress). Keeping status separate is what
lets live updates stream independently of whether the computation has
finished.

---

## Engineering decisions worth reading about

### Measuring speed without camera calibration

Converting pixel movement to real-world distance normally means homography —
calibrating against known field markings to build a perspective transform.
Broadcast and phone footage rarely gives you four reliable reference points.

Instead, the ball itself is the ruler. A regulation size-5 ball is 0.22m in
diameter, and the detector already returns its bounding box every frame. That
gives a meters-per-pixel scale *at the ball's depth*, refreshed continuously,
with no calibration step and no assumptions about the camera.

The tradeoff is honest: it's accurate near the ball's plane and degrades with
large depth changes. For peak speed over short bursts of play, that's the
right trade.

### Frame sampling and aliasing

Early speed numbers were unstable. The cause was sampling: frames were being
extracted at a rate that aliased against the ball's motion, so displacement
between consecutive samples varied with where in the ball's travel each
sample landed. Moving extraction to 60fps fixed it — the fix wasn't in the
speed maths at all, it was upstream in how the video was being sampled.

### Reverse-engineering orphaned resources into IaC

The SageMaker model and endpoint config were created by hand during
development, which left them as *orphans* — live AWS resources no template
owned, with the recipe existing only in terminal scrollback.

The fix was three moves: `describe-*` to read the live settings, write
`infrastructure/sagemaker.yaml` to reproduce them, then hand ownership to
CloudFormation.

CloudFormation *resource import* can adopt existing resources without
deleting them, which is the right tool for stateful or precious ones —
databases, data buckets. These were free, stateless, and rebuilt in seconds,
so import's safety bought nothing and cost complexity. Delete-and-recreate
was the simpler correct answer. The judgment call is matching the tool to the
stakes rather than reaching for the most sophisticated option.

The **endpoint** is deliberately *not* in the stack. It's the only meaningful
recurring cost, so it stays a manual toggle — a declarative base with an
imperative cost knob — meaning teardown doesn't leave the stack in drift.

### Catch, broadcast, re-raise

Original bug: if `run_inference` failed, Step Functions correctly recorded the
run as failed — but nothing told the browser. The UI sat on
`RUNNING_INFERENCE` forever. A frozen spinner is a worse failure than an
error message, because the user can't tell it apart from slow.

The fix wraps the work in `try/except`, and in the handler does two things:

1. **Broadcast** — write a `FAILED` status row and push it over the WebSocket,
   so the UI flips to an error state with the real cause attached.
2. **Re-raise** — let the exception keep propagating, so Step Functions still
   marks the execution failed.

The re-raise is the part that matters. Swallowing the exception after
handling it would make the function *look* successful, desyncing the
orchestrator's view of the run from reality. The catch exists only to perform
a side effect — informing the user — not to resolve the error. Both truths
survive: the user learns what happened, and the run is still correctly failed.

Verified end to end through the browser: `EXTRACTING_FRAMES` →
`RUNNING_INFERENCE` → `FAILED`, with the underlying SageMaker error surfaced
in the UI.

---

## Repo layout

```
backend/functions/     one directory per Lambda
  extract_frames/        video → frames
  run_inference/         frames → SageMaker → detections
  store_results/         detections → DynamoDB
  compute_distance/      detections → peak speed
  get_results/           REST read API
  get_status/            status read
  get_upload_url/        presigned S3 upload URL
  trigger_pipeline/      S3 event → Step Functions
  ws_connect/ ws_disconnect/ ws_default/   WebSocket lifecycle

infrastructure/        CloudFormation, one stack per concern
  storage.yaml           S3 + DynamoDB
  auth.yaml              Cognito + Google OAuth
  api.yaml               REST API Gateway
  websocket.yaml         WebSocket API Gateway
  pipeline.yaml          Step Functions + pipeline Lambdas
  sagemaker.yaml         model + endpoint config (endpoint excluded, see above)
  trigger.yaml           S3 event wiring

model/                 YOLOv8 inference container
  Dockerfile
  src/inference.py       SageMaker inference handler

frontend/              React + Vite + Tailwind
```

---

## Running it

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Requires `VITE_WS_URL` in `frontend/.env` (the WebSocket API Gateway URL).
It's a public endpoint address, not a credential — Vite inlines it into the
bundle at build time regardless.

**Infrastructure**

Each stack deploys independently:

```bash
aws cloudformation deploy \
  --template-file infrastructure/storage.yaml \
  --stack-name sbt-storage-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Deploy order: `storage` → `auth` → `sagemaker` → `pipeline` → `api` →
`websocket` → `trigger`.

**The SageMaker endpoint** is not deployed by any stack, by design. Bring it
up only when you need to process a video:

```bash
# up (~$0.10-0.15/hr)
aws sagemaker create-endpoint \
  --endpoint-name sbt-yolov8-endpoint \
  --endpoint-config-name sbt-yolov8-config \
  --region us-east-1

# down
aws sagemaker delete-endpoint \
  --endpoint-name sbt-yolov8-endpoint \
  --region us-east-1
```

It is currently **down**. Uploading a video with the endpoint down is a
legitimate way to exercise the failure path — the UI surfaces the error
rather than hanging.

---

## Cost

No EC2, no always-on compute. Lambda, Step Functions, DynamoDB, and S3 at
this volume sit inside or near free tier. The SageMaker endpoint is the only
real cost, which is exactly why it's a manual toggle and not a stack
resource. A budget alarm is configured as a backstop, though the actual
protection is remembering to run the teardown command.

---

## Known gaps

Kept here deliberately rather than quietly:

- **Failure broadcasting is per-step.** Only `run_inference` catches and
  broadcasts. The other three pipeline steps report progress but not failure,
  so a failure in one of them still leaves the UI spinning. The general fix
  belongs at the orchestration layer — a broadcast task in front of the
  terminal `Fail` state, which all four `Catch` blocks route through — rather
  than four copies of the same `try/except`.
- **Retries are visible to the user.** `run_inference` retries twice with
  exponential backoff, and each attempt broadcasts, so the UI flickers
  `FAILED` → `RUNNING_INFERENCE` → `FAILED` before settling. The terminal
  state is correct; the path to it is noisy. Same fix as above: a per-attempt
  status and a per-run status are different things, and only the orchestrator
  knows when the run is actually over.
- **`get_results` returns 404 mid-pipeline.** A video that exists but hasn't
  written rows yet is indistinguishable from one that doesn't exist. A 202 or
  an explicit `PENDING` would be more honest.
- **No automated tests.**

---

## Stack

Python 3.11 · React · Vite · Tailwind · YOLOv8 · OpenCV · AWS Lambda ·
Step Functions · SageMaker · DynamoDB · S3 · API Gateway (REST + WebSocket) ·
Cognito · CloudFormation
