using System.Collections.Concurrent;

namespace CameraGateway.Services;

/// <summary>Holds latest JPEG frames per camera for MJPEG relay to browser and Android.</summary>
public class StreamService(ILogger<StreamService> logger)
{
    private readonly ConcurrentDictionary<int, byte[]> _frames = new();
    private readonly ConcurrentDictionary<int, List<string>> _destinations = new();

    public byte[]? GetLatestFrame(int cameraId) =>
        _frames.TryGetValue(cameraId, out var f) ? f : null;

    public void SetFrame(int cameraId, byte[] jpeg) => _frames[cameraId] = jpeg;

    public Task<bool> StartAsync(int cameraId, string rtspUrl, List<string> destinations)
    {
        // TODO: launch OpenCV capture thread feeding SetFrame()
        // For now, register the session so the controller knows it's active
        _destinations[cameraId] = destinations;
        logger.LogInformation("Stream registered camera={Id} rtsp={Url} → {Dests}",
            cameraId, rtspUrl, string.Join(",", destinations));
        return Task.FromResult(true);
    }

    public void Stop(int cameraId)
    {
        _frames.TryRemove(cameraId, out _);
        _destinations.TryRemove(cameraId, out _);
    }

    public List<string> GetDestinations(int cameraId) =>
        _destinations.TryGetValue(cameraId, out var d) ? d : [];

    public Task SetDestinationsAsync(int cameraId, List<string> destinations)
    {
        _destinations[cameraId] = destinations;
        return Task.CompletedTask;
    }
}
