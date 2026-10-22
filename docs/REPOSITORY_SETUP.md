# Repository setup and private model assets

## Python source layout

`ai-engine/` and `agents/` are the canonical source directories. Python imports
use `ai_engine` and `agents`, so after cloning run this from the repository root:

```sh
python scripts/link_ai_engine.py
```

This creates ignored `backend/ai_engine` and `backend/agents` junctions on
Windows or relative symlinks on Linux/macOS. It accepts an existing correct link and refuses to
replace any other existing directory or file. No source data is deleted.
Run it before starting native backend services or backend tests. CI runs it
after checkout. The existing Windows junctions remain intact locally.

Python Docker images use the repository root as their build context and copy
`ai-engine/` to `/ai_engine`, with `/` on `PYTHONPATH`. They do not copy or
depend on the local junction:

```sh
docker build -f backend/Dockerfile -t campus-sentinel-backend .
docker build -f backend/Dockerfile.worker -t campus-sentinel-worker .
```

Compose and CI use these root contexts. Frontend builds retain `frontend/`
as their context. Root, backend and frontend Docker ignore files exclude
credentials, student records, spreadsheets, databases and generated artifacts.
Docker ignore rules protect build contexts; bind mounts and runtime environment
injection are separate. Review runtime mounts before using private data.

## Local credentials

For Compose, copy the root `.env.example` to the ignored root `.env` if it does
not already exist. For native backend commands launched from `backend/`, create
`backend/.env` from the same template if it does not already exist: settings
load `.env` relative to the process working directory. Both locations are
ignored by Git. Do not overwrite an existing private configuration; update the
appropriate file privately and keep shared service credentials consistent.
Replace every `REPLACE_WITH_` value with your own local configuration.
Generate a signing key locally with
`openssl rand -hex 32`; do not paste it into documentation or Git. Set database,
Redis and Grafana passwords consistently for the corresponding services.
Set SMTP credentials only in the local environment when email is enabled.
The shipped placeholders are not suitable credentials for deployment.
The existing private `.env` is not modified by repository preparation.
For native provisioning with `scripts/deploy-local.sh`, export
`POSTGRES_PASSWORD` before running the script; it no longer ships a database
password fallback. Set `DEBUG` to a boolean such as `false` when running tests.

## Public detector weights

Weights are excluded from both Git and Docker build contexts. Install
`backend/requirements.txt` in your Python environment first. Obtain the public
`yolov8n.pt` model from the official
[Ultralytics YOLOv8 model repository](https://huggingface.co/Ultralytics/YOLOv8/blob/main/yolov8n.pt),
or load the named model using the
[Ultralytics Python API](https://docs.ultralytics.com/usage/python/):

```sh
cd backend
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

The named-model route can download the public weights and requires network
access on first use. Set `YOLO_MODEL_PATH=yolov8n.pt` in the local `.env` for
native execution from `backend/` (set this in `backend/.env`), or place the downloaded file at
`backend/models/weights/yolov8n.pt` and use the default relative path
`models/weights/yolov8n.pt`. Paths resolve relative to the backend process's
working directory; an absolute path is also supported.

For Compose, provision the file into the `model_weights` volume mounted at
`/app/models/weights`. For an initial public-model download into that volume:

```sh
docker compose run --rm --no-deps --workdir /app/models/weights backend python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

Use `YOLO_MODEL_PATH=/app/models/weights/yolov8n.pt` for that container setup.
Download only from a trusted publisher and review its licensing before use.

## Private or trained weights

Obtain private weights through an authorized private channel and configure their
local or container path. Do not commit weights, training datasets, face images,
student identity spreadsheets or QR records. Never load untrusted pickle or
PyTorch model files.

Prediction training is implemented in `ai-engine/prediction/model_trainer.py`;
its output directory is currently `/app/models/prediction`. From a configured
container, an optional synthetic-data example is:

```sh
docker compose run --rm --no-deps celery_worker python -m ai_engine.prediction.model_trainer --model rf --synthetic
```

Training produces local artifacts; this command does not retrieve private
models. Provision persistent storage separately for prediction artifacts you
need to retain. No models are downloaded or trained during repository auditing.

## CI publication controls

Tests run normally. Image publishing is disabled unless the repository variable
`ENABLE_IMAGE_PUBLISH` is explicitly set to `true`. Production deployment also
requires `ENABLE_PRODUCTION_DEPLOY=true`, the image job to succeed, and the
configured production environment and credentials. Keep these variables unset
until publication and deployment are approved.
