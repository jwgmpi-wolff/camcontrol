FROM python:3.12-slim

# ffmpeg: required by the RTSP and Hi3518e H.264 snapshot capture backends.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# /home is persisted by App Service when app storage is enabled.
ENV HOST=0.0.0.0
ENV PORT=8000
ENV CAMCONTROL_CONFIG_DIR=/home/data
EXPOSE 8000

CMD ["python", "-m", "camera_bridge.main"]
