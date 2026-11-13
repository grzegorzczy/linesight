// E2-03: parser wyjścia YOLO26n dla Gst-nvinfer (DeepStream 6.0.1, JetPack 4.6.1).
//
// Wyjście silnika: [1, 7, N] (N = 5040 dla wejścia 384x640), układ kanałowy:
//   out[c * N + i], c = 0..3 -> cx, cy, w, h w pikselach wejścia sieci,
//                   c = 4..6 -> pewności klas (bottle, missing_cap, fallen), już po sigmoidzie.
// Parser wybiera klasę o najwyższej pewności (jak NMS w ultralytics, multi_label=False),
// odrzuca kandydatów poniżej pre-cluster-threshold i oddaje ramki w pikselach wejścia sieci.
// NMS (per klasa) i przeskalowanie do rozdzielczości klatki robi nvinfer (cluster-mode=2).
#include <algorithm>
#include <iostream>
#include "nvdsinfer_custom_impl.h"

static const int NUM_CLASSES = 3;

extern "C" bool NvDsInferParseYolo26(
    std::vector<NvDsInferLayerInfo> const &outputLayersInfo,
    NvDsInferNetworkInfo const &networkInfo,
    NvDsInferParseDetectionParams const &detectionParams,
    std::vector<NvDsInferObjectDetectionInfo> &objectList)
{
    if (outputLayersInfo.size() != 1) {
        std::cerr << "yolo26: oczekiwano 1 warstwy wyjściowej, jest "
                  << outputLayersInfo.size() << std::endl;
        return false;
    }
    const NvDsInferLayerInfo &layer = outputLayersInfo[0];
    // inferDims nie zawiera wymiaru batcha: oczekujemy [7, N]
    if (layer.dataType != FLOAT || layer.inferDims.numDims != 2 ||
        layer.inferDims.d[0] != 4 + NUM_CLASSES) {
        std::cerr << "yolo26: nieoczekiwany kształt/typ wyjścia (numDims="
                  << layer.inferDims.numDims << ", d0=" << layer.inferDims.d[0]
                  << ", dataType=" << layer.dataType << ")" << std::endl;
        return false;
    }

    const int n = layer.inferDims.d[1];
    const float *out = static_cast<const float *>(layer.buffer);
    const float netW = static_cast<float>(networkInfo.width);
    const float netH = static_cast<float>(networkInfo.height);

    for (int i = 0; i < n; ++i) {
        int cls = 0;
        float conf = out[4 * n + i];
        for (int c = 1; c < NUM_CLASSES; ++c) {
            const float s = out[(4 + c) * n + i];
            if (s > conf) { conf = s; cls = c; }
        }
        if (conf < detectionParams.perClassPreclusterThreshold[cls]) continue;

        const float cx = out[i], cy = out[n + i], w = out[2 * n + i], h = out[3 * n + i];
        const float left = std::max(0.0f, cx - w / 2), top = std::max(0.0f, cy - h / 2);
        const float right = std::min(netW, cx + w / 2), bottom = std::min(netH, cy + h / 2);
        if (right <= left || bottom <= top) continue;

        NvDsInferObjectDetectionInfo obj;
        obj.classId = cls;
        obj.left = left;
        obj.top = top;
        obj.width = right - left;
        obj.height = bottom - top;
        obj.detectionConfidence = conf;
        objectList.push_back(obj);
    }
    return true;
}

// Kompilator sprawdza, czy sygnatura zgadza się z NvDsInferParseCustomFunc z SDK.
CHECK_CUSTOM_PARSE_FUNC_PROTOTYPE(NvDsInferParseYolo26);
