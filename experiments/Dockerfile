# Dockerfile VTrace
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 安装基础依赖
RUN apt-get update && apt-get install -y \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstrtspserver-1.0-0 \
    libopencv-dev \
    python3-opencv \
    python3-pip \
    libzbar0 \
    libzbar-dev \
    && rm -rf /var/lib/apt/lists/*

# Python依赖
RUN pip3 install --no-cache-dir \
    ultralytics \
    boxmot \
    pyzbar \
    mediapipe \
    redis \
    paho-mqtt

WORKDIR /app
COPY . /app

CMD ["python3", "main.py"]