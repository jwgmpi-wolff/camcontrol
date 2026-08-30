using CameraGateway.Models;
using CameraGateway.Services;
using Microsoft.AspNetCore.Mvc;

namespace CameraGateway.Controllers;

[ApiController]
[Route("api/[controller]")]
public class CameraController(CameraService cameras, ILogger<CameraController> logger) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> List() =>
        Ok(await cameras.GetAllAsync());

    [HttpGet("{id:int}")]
    public async Task<IActionResult> Get(int id)
    {
        var cam = await cameras.GetByIdAsync(id);
        return cam is null ? NotFound() : Ok(cam);
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CameraCreateRequest req)
    {
        var cam = await cameras.AddAsync(req);
        return CreatedAtAction(nameof(Get), new { id = cam.Id }, cam);
    }

    [HttpDelete("{id:int}")]
    public async Task<IActionResult> Delete(int id)
    {
        await cameras.DeleteAsync(id);
        return NoContent();
    }

    // Discovery endpoint – triggers Python discovery script
    [HttpPost("discover")]
    public IActionResult Discover([FromQuery] string? subnetPrefix)
    {
        logger.LogInformation("Discovery triggered for subnet {Prefix}", subnetPrefix ?? "auto");
        // TODO: invoke camera_discovery.py or detect-yhs3017.ps1 via Process and return JSON
        return Accepted(new { message = "Discovery started; poll /api/camera for results." });
    }

    // Device direct methods routed to the underlying bridge
    [HttpPost("{id:int}/command/{method}")]
    public async Task<IActionResult> Command(int id, string method, [FromBody] object? payload)
    {
        var result = await cameras.InvokeCommandAsync(id, method, payload);
        return result is null ? NotFound() : Ok(result);
    }

    // Health / status
    [HttpGet("{id:int}/status")]
    public async Task<IActionResult> Status(int id)
    {
        var status = await cameras.GetStatusAsync(id);
        return status is null ? NotFound() : Ok(status);
    }
}
