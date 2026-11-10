# LineSight

Edge AI for packaging-line downtime diagnostics. A camera watches a mini
bottle line, a YOLO model runs on an NVIDIA Jetson Nano with TensorRT, and
every stop of the line is linked to a video clip, PLC signals from the
30 seconds before it, and an assistant that answers *why the line stopped
and how to fix it*.

> Status: **Stage 0 – setup** (in progress)

## Architecture (target)

| Device | Role |
|---|---|
| Jetson Nano 4 GB (JetPack 4.6.1) | camera, TensorRT engine, DeepStream pipeline, RTSP H.264, event clips, event publishing |
| Laptop (RTX 3050 4 GB, Docker) | training (PyTorch), ONNX export, CODESYS soft-PLC, MQTT, TimescaleDB, Grafana, RAG assistant |
| Ultralytics Platform | image labeling only |
| GCP | model version registry, frames for retraining, optional assistant API |

Detection classes: `bottle`, `missing_cap`, `bottle_fallen` (jam).

## Stages

| # | Stage | Status |
|---|---|---|
| 0 | Jetson setup, camera, repository, backlog | in progress |
| 1 | Dataset, training, ONNX → TensorRT, FP32/FP16/INT8 benchmark | – |
| 2 | GStreamer/DeepStream pipeline, tracking, counting, RTSP, event clips | – |
| 3 | CODESYS PackML state machine, OPC UA → MQTT → TimescaleDB, Grafana | – |
| 4 | Stop diagnostics: rules + cycle-time anomaly detection (PyTorch) | – |
| 5 | RAG assistant (pgvector) with evaluation set | – |
| 6 | GCP: model registry, retraining loop | – |
| 7 | Demo video, results, final documentation | – |

MVP = stages 1–3.

## Repository layout

```
linesight/
├── docs/       stage-by-stage notes: commands, results, decisions (Polish)
├── training/   laptop: dataset, training, ONNX export          (stage 1)
├── jetson/     Jetson: TensorRT engine, DeepStream pipeline    (stages 1–2)
├── plc/        CODESYS project export                          (stage 3)
└── infra/      docker-compose: MQTT, TimescaleDB, Grafana      (stage 3)
```

Folders are added when their first file appears.

## Documentation

- [Stage 0 – Jetson setup, camera, memory](docs/etap-0-jetson.md)
- [MVP backlog](docs/backlog.md)

## Not in the repository

Model weights and engines (`.pt`, `.onnx`, `.engine`), datasets, training
runs and video clips are ignored by Git (see `.gitignore`). Models will be
versioned in a GCP bucket (stage 6).
