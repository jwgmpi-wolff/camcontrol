FROM python:3.12-slim AS base

# GStreamer RTSP server packages – only installed when the image targets Linux edge
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-libav \
        gstreamer1.0-rtsp \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        python3-gi \
        python3-gst-1.0 \
        gir1.2-gst-rtsp-server-1.0 \
        libgl1 \
        libglib2.0-0 \
        v4l-utils \
        usbutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Snapshots are written here; mount a volume or Azure Blob Fuse at runtime
RUN mkdir -p /data/snapshots

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    SNAPSHOT_DIRECTORY=/data/snapshots \
    STREAM_ENABLED=false \
    LOG_LEVEL=INFO

# The camera device must be passed at runtime: --device /dev/video0
# Never embed IOTHUB_DEVICE_CONNECTION_STRING in the image
ENTRYPOINT ["python", "-m", "camera_bridge.main"]
