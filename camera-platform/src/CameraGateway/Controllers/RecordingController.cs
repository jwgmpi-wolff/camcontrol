using CameraGateway.Services;
using Microsoft.AspNetCore.Mvc;

namespace CameraGateway.Controllers;

[ApiController]
[Route("api/[controller]")]
public class RecordingController(RecordingService recordings, AzureStorageService storage) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> List([FromQuery] int? cameraId, [FromQuery] int page = 1, [FromQuery] int pageSize = 20) =>
        Ok(await recordings.ListAsync(cameraId, page, pageSize));

    [HttpPost("start")]
    public async Task<IActionResult> Start([FromBody] RecordingStartRequest req)
    {
        var session = await recordings.StartAsync(req);
        return session is null
            ? BadRequest(new { error = "Stream URL not confirmed; verify RTSP connectivity first." })
            : Accepted(session);
    }

    [HttpPost("{sessionId}/stop")]
    public async Task<IActionResult> Stop(string sessionId)
    {
        var result = await recordings.StopAsync(sessionId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpGet("{sessionId}/status")]
    public async Task<IActionResult> Status(string sessionId)
    {
        var status = await recordings.GetStatusAsync(sessionId);
        return status is null ? NotFound() : Ok(status);
    }

    // Upload a local clip to Azure Blob Storage
    [HttpPost("{sessionId}/upload-azure")]
    public async Task<IActionResult> UploadAzure(string sessionId)
    {
        var url = await storage.UploadClipAsync(sessionId);
        return url is null
            ? StatusCode(503, new { error = "Azure Storage not configured or upload failed." })
            : Ok(new { blobUrl = url });
    }
}

public record RecordingStartRequest(
    int CameraId,
    string RtspUrl,
    string Destination,  // "local" | "nas" | "azure"
    string? OutputPath,
    string? AzureContainer
);
