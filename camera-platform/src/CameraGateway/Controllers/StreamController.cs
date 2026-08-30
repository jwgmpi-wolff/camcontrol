using CameraGateway.Services;
using Microsoft.AspNetCore.Mvc;

namespace CameraGateway.Controllers;

[ApiController]
[Route("api/[controller]")]
public class StreamController(StreamService stream, ILogger<StreamController> logger) : ControllerBase
{
    /// <summary>MJPEG frame for Windows dashboard and Android relay — pulled per-request.</summary>
    [HttpGet("{cameraId:int}/frame")]
    public IActionResult Frame(int cameraId)
    {
        var jpeg = stream.GetLatestFrame(cameraId);
        if (jpeg is null)
            return StatusCode(503, new { error = "No active stream for this camera." });
        return File(jpeg, "image/jpeg");
    }

    [HttpPost("{cameraId:int}/start")]
    public async Task<IActionResult> Start(int cameraId, [FromBody] StreamStartRequest req)
    {
        var ok = await stream.StartAsync(cameraId, req.RtspUrl, req.Destinations);
        return ok ? Ok(new { streaming = true }) : BadRequest(new { error = "Stream start failed." });
    }

    [HttpPost("{cameraId:int}/stop")]
    public async Task<IActionResult> Stop(int cameraId)
    {
        stream.Stop(cameraId);
        return Ok(new { streaming = false });
    }

    [HttpGet("{cameraId:int}/destinations")]
    public IActionResult Destinations(int cameraId) =>
        Ok(stream.GetDestinations(cameraId));

    [HttpPut("{cameraId:int}/destinations")]
    public async Task<IActionResult> SetDestinations(
        int cameraId, [FromBody] StreamDestinationUpdateRequest req)
    {
        await stream.SetDestinationsAsync(cameraId, req.Destinations);
        return Ok();
    }
}

public record StreamStartRequest(string RtspUrl, List<string> Destinations);
public record StreamDestinationUpdateRequest(List<string> Destinations);
