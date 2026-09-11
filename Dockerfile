FROM python:3.12-slim

# ffmpeg: required by the RTSP and Hi3518e H.264 snapshot capture backends.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# config/ is expected to be an Azure Files mount in App Service (persists
# cameras.json/users.json across restarts and redeploys); captures/ is
# unused on this target since storage is configured to the azure_blob
# provider instead of local disk.
ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

CMD ["python", "-m", "camera_bridge.main"]
