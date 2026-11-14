# LineSight

Edge AI for packaging-line downtime diagnostics. A camera watches a mini
bottle line, a YOLO model runs on an NVIDIA Jetson Nano with TensorRT, and
every stop of the line is linked to a video clip, PLC signals from the
30 seconds before it, and an assistant that answers *why the line stopped
and how to fix it*.

> Status: **MVP (stages 1–3) done** · next: Stage 4 – stop diagnostics

## Architecture (target)

| Device | Role |
|---|---|
| Jetson Nano 4 GB (JetPack 4.6.1) | camera, TensorRT engine, DeepStream pipeline, RTSP H.264, event clips, event publishing |
| Laptop (RTX 3050 Ti Laptop 4 GB, Docker) | training (PyTorch), ONNX export, MQTT broker, OPC UA → MQTT bridge, TimescaleDB, Grafana, RAG assistant |
| PLC (JUMO variTRON 300, CODESYS V3.5) | PackML state machine, simulated production, fault injection, OPC UA server |
| Ultralytics Platform | image labeling only |
| GCP | model version registry, frames for retraining, optional assistant API |

Detection classes: `bottle`, `missing_cap`, `fallen` (jam).

## Stages

| # | Stage | Status |
|---|---|---|
| 0 | Jetson setup, camera, repository, backlog | done |
| 1 | Dataset, training, ONNX → TensorRT, FP32/FP16/INT8 benchmark | done |
| 2 | GStreamer/DeepStream pipeline, tracking, counting, RTSP, event clips | done |
| 3 | CODESYS PackML state machine, OPC UA → MQTT → TimescaleDB, Grafana | done |
| 4 | Stop diagnostics: rules + cycle-time anomaly detection (PyTorch) | – |
| 5 | RAG assistant (pgvector) with evaluation set | – |
| 6 | GCP: model registry, retraining loop | – |
| 7 | Demo video, results, final documentation | – |

MVP = stages 1–3.

## Results so far

Detector: YOLO26n, own dataset (214 images, 536 boxes, split 150/43/21),
trained locally (PyTorch, ultralytics), deployed as a TensorRT FP16 engine
with a 384x640 input (camera is 640x360) on the Jetson Nano.

| Model | Device | val mAP50-95 | test mAP50-95 | Speed | Memory |
|---|---|---|---|---|---|
| PyTorch, 640, end-to-end head | laptop | 0.788 | 0.778 | 11.8 ms | – |
| **TensorRT FP16, 384x640, NMS head** | **Jetson Nano** | **0.771** | **0.764** | **34.4 FPS (28.8 ms GPU)** | **20 MiB** |

- TensorRT is lossless vs ONNX (FP32: 0.002 px; FP16: same decisions).
- 384x640 instead of 640x640: −41% compute, same accuracy.
- FP16 gives 1.23x, not 2x: convolutions are 71% of FP32 time (Amdahl),
  FP16 adds 25 reformat layers and slower activations (per-layer profile).
- INT8 brings nothing on the Nano (Maxwell GPU has no INT8 hardware).
- The ~0.012 mAP gap comes from the exported head: the NMS-free head needs
  the ONNX `Mod` op, which TensorRT 8.2 cannot parse.

Details: [docs/etap-1-model.md](docs/etap-1-model.md).

### Video pipeline on the Jetson (stage 2)

```
USB camera (YUY2 640x360@30) ─► nvvideoconvert (VIC) ─► nvstreammux ─► nvinfer (YOLO26n FP16, C++ parser)
  ─► nvtracker (IOU) ─► [pyds probe: line counting, class vote] ─► nvdsosd ─► nvv4l2h264enc (NVENC) ─► tee
       ├─► RTSP server  rtsp://<jetson>:8554/linesight
       ├─► ring buffer  splitmuxsink, 15 x 2 s in /dev/shm
       └─► MP4 (optional)
event (missing_cap / fallen) ─► clip 10 s before / 5 s after the line crossing (ffmpeg concat, no re-encode)
```

| Measurement | Result |
|---|---|
| Live pipeline (detection + tracking + OSD + RTSP + ring buffer) | **30 FPS**, 1.9 GB RAM, GPU 61–99 % |
| DeepStream vs TensorRT + Python, mAP50-95 val / test | 0.754 / 0.760 (vs 0.771 / 0.764; preprocessing differences) |
| Counting, manual test (truth 3/2/2 bottle/missing_cap/fallen) | 3/2/1 |
| Glass-to-glass latency to VLC on the laptop | ~620 ms, of which **73 ms** is the Jetson pipeline (GStreamer latency tracer) – the rest is mostly the VLC client |
| Event clip | 17 s, line crossing at 10 s, plays from the first frame |

- Counting: tracker IDs, direction-aware line crossing with ±20 px hysteresis, class decided by a
  majority vote over the track 5 s after the crossing (a hand on the bottle neck flips single frames).
- NVENC is a separate hardware block: RTSP and clips cost no FPS and no GPU time for the model.
- Ring buffer in RAM (tmpfs) – continuous writes do not wear the SD card.

Details: [docs/etap-2-wideo.md](docs/etap-2-wideo.md).

### PLC and data pipeline (stage 3)

```
Jetson: line-crossing event ──MQTT──┐
                                    ├─► Mosquitto ─► ingest ─► TimescaleDB ─► Grafana
PLC (PackML) ─OPC UA─► bridge ─MQTT─┘
```

All laptop services run from one `infra/docker-compose.yml`: `mosquitto`, `bridge`, `db`, `ingest`, `grafana`.

| Part | What it does |
|---|---|
| PLC (CODESYS, variTRON 300) | PackML subset (11 states, standard numbering), stop reasons (jam → Held, no product → Suspended, fault → Aborted), counter, measured cycle time, manual fault injection |
| `bridge/` | OPC UA subscription (200 ms) → MQTT `linesight/plc/<signal>`, QoS 1, retained; reconnects after PLC loss in ~5 s |
| `ingest/` | MQTT → TimescaleDB; persistent session, write before ack, duplicates dropped by a unique key |
| TimescaleDB | hypertables `plc_signal` (narrow: one row per change), `vision_event` (time = line crossing), `link_status`; `signals_before(t, '30 s')` returns the window plus each signal's value at its start |
| Grafana | provisioned datasource (read-only DB user) and dashboard: PackML state timeline with stop reason, link status, pieces/min PLC vs camera, cycle time, camera events as annotations |

| Measurement | Result |
|---|---|
| Clock offset vs NTP (laptop / Docker container / Jetson) | +1.8 / +6.5 / −1.1 ms (laptop was −1042 ms before fixing Windows time) |
| PLC loss (cable pulled) | status offline, back online ~5 s after reconnect |
| Production rate after cycle-time fix | 40 / 40 / 39 pieces/min (was exactly 30: timer quantised to the 200 ms task) |
| MQTT publishing on the Jetson | no FPS cost (30.0 FPS) |

- A bug found by cross-checking: the PLC reported the *set* cycle time, the dashboard's per-minute counter
  increments showed the real rate was 25 % lower. Cycle time is now measured with `TIME()`.
- Camera and PLC are not linked automatically: the cause of a stop must not be known by construction.

Details: [docs/etap-3-plc-dane.md](docs/etap-3-plc-dane.md).

## Repository layout

```
linesight/
├── docs/       stage-by-stage notes: commands, results, decisions (Polish)
├── training/   laptop: dataset, training, ONNX export          (stage 1)
├── jetson/     Jetson: image capture, TensorRT engines, benchmarks    (stages 1–2)
├── deepstream/ Jetson: DeepStream app, C++ parser, configs, tests (stage 2)
├── laptop/     laptop helpers (latency stopwatch)                (stage 2)
├── plc/        CODESYS sources (PackML state machine)           (stage 3)
├── bridge/     laptop, Docker: OPC UA → MQTT bridge             (stage 3)
├── ingest/     laptop, Docker: MQTT → TimescaleDB               (stage 3)
├── tools/      clock offset (SNTP), OPC UA browser              (stage 3)
└── infra/      docker-compose, Mosquitto, DB schema, Grafana    (stage 3)
```

Folders are added when their first file appears.

## Documentation

- [Stage 0 – Jetson setup, camera, memory](docs/etap-0-jetson.md)
- [Stage 1 – dataset, training, TensorRT engines, benchmark](docs/etap-1-model.md)
- [Stage 2 – DeepStream, tracking, counting, RTSP, event clips](docs/etap-2-wideo.md)
- [Stage 3 – PackML, OPC UA, MQTT, TimescaleDB, Grafana](docs/etap-3-plc-dane.md)
- [MVP backlog](docs/backlog.md)

## Not in the repository

Model weights and engines (`.pt`, `.onnx`, `.engine`), datasets, training
runs and video clips are ignored by Git (see `.gitignore`). Models will be
versioned in a GCP bucket (stage 6).
