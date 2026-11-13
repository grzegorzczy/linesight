#!/usr/bin/env python3
"""E2-03: detekcje z potoku DeepStream (nvinfer + nasz parser) na folderze zdjęć -> JSON.

Jetson, Python 3.6, DeepStream 6.0.1, pyds 1.1.1. Te same zdjęcia co w E1-08 (data/eval/<split>),
więc na laptopie training/eval_ds.py porównuje wynik 1:1 z TensorRT uruchamianym z Pythona.

Użycie (z ~/linesight):
    python3 jetson/ds_dump.py deepstream/configs/nvinfer_yolo26_eval.txt data/eval/test models/ds_test.json

Potok: multifilesrc -> jpegdec (CPU) -> nvvideoconvert (NVMM) -> nvstreammux 640x360 -> nvinfer -> fakesink.
Sonda (probe) na wyjściu nvinfer czyta metadane obiektów: ramki są już po NMS i w pikselach klatki.
"""
import json
import os
import sys
import tempfile

import gi
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402
import pyds  # noqa: E402


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    cfg, folder, out = sys.argv[1:4]
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith(".jpg"))
    if not names:
        sys.exit("brak zdjęć .jpg w " + folder)

    # multifilesrc czyta pliki po numerze -> dowiązania 00000.jpg, 00001.jpg... w kolejności names
    tmp = tempfile.mkdtemp(prefix="ds_eval_")
    for i, n in enumerate(names):
        os.symlink(os.path.abspath(os.path.join(folder, n)), os.path.join(tmp, "%05d.jpg" % i))

    Gst.init(None)
    pipeline = Gst.parse_launch(
        "multifilesrc location={tmp}/%05d.jpg index=0 stop-index={last} caps=image/jpeg,framerate=30/1 "
        "! jpegdec ! nvvideoconvert ! video/x-raw(memory:NVMM),format=NV12 "
        "! m.sink_0 nvstreammux name=m batch-size=1 width=640 height=360 live-source=0 "
        "! nvinfer name=infer config-file-path={cfg} ! fakesink sync=false".format(
            tmp=tmp, last=len(names) - 1, cfg=os.path.abspath(cfg)))

    dets = {n: [] for n in names}
    seen = set()

    def probe(pad, info, _):
        batch = pyds.gst_buffer_get_nvds_batch_meta(hash(info.get_buffer()))
        l_frame = batch.frame_meta_list
        while l_frame is not None:
            fm = pyds.NvDsFrameMeta.cast(l_frame.data)
            name = names[fm.frame_num]  # nvstreammux numeruje klatki źródła od 0
            seen.add(name)
            l_obj = fm.obj_meta_list
            while l_obj is not None:
                o = pyds.NvDsObjectMeta.cast(l_obj.data)
                r = o.rect_params
                dets[name].append([r.left, r.top, r.left + r.width, r.top + r.height,
                                   o.confidence, o.class_id])
                l_obj = l_obj.next
            l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

    pipeline.get_by_name("infer").get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, probe, None)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus, msg):
        if msg.type == Gst.MessageType.EOS:
            loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("BŁĄD:", err, dbg)
            loop.quit()

    bus.connect("message", on_message)
    pipeline.set_state(Gst.State.PLAYING)
    loop.run()
    pipeline.set_state(Gst.State.NULL)

    with open(out, "w") as f:
        json.dump({"config": cfg, "dets": dets}, f)
    n_obj = sum(len(v) for v in dets.values())
    print("zdjęcia: {}/{} przetworzone, detekcje: {} -> {}".format(len(seen), len(names), n_obj, out))
    if len(seen) != len(names):
        sys.exit("UWAGA: nie wszystkie zdjęcia przeszły przez potok")


if __name__ == "__main__":
    main()
