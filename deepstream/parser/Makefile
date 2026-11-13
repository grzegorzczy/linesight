# E2-03: buduje libnvdsparse_yolo26.so na Jetsonie (g++ 7, CUDA 10.2, DeepStream 6.0.1).
DS ?= /opt/nvidia/deepstream/deepstream-6.0
CUDA_VER ?= 10.2
CXXFLAGS = -Wall -O2 -fPIC -std=c++11 -I$(DS)/sources/includes -I/usr/local/cuda-$(CUDA_VER)/include
TARGET = libnvdsparse_yolo26.so

$(TARGET): nvdsparse_yolo26.cpp
	g++ $(CXXFLAGS) -shared -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: clean
