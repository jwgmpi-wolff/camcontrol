using CameraGateway.Data;
using CameraGateway.Models;
using Microsoft.EntityFrameworkCore;

namespace CameraGateway.Services;

public class CameraService(CameraDbContext db, ILogger<CameraService> logger)
{
    public Task<List<Camera>> GetAllAsync() => db.Cameras.AsNoTracking().ToListAsync();

    public Task<Camera?> GetByIdAsync(int id) =>
        db.Cameras.AsNoTracking().FirstOrDefaultAsync(c => c.Id == id);

    public async Task<Camera> AddAsync(CameraCreateRequest req)
    {
        var cam = new Camera
        {
            Name = req.Name,
            IpAddress = req.IpAddress,
            Hostname = req.Hostname,
            MacAddress = req.MacAddress,
            RtspUrl = req.RtspUrl,
            OnvifServiceUrl = req.OnvifServiceUrl,
        };
        db.Cameras.Add(cam);
        await db.SaveChangesAsync();
        return cam;
    }

    public async Task DeleteAsync(int id)
    {
        var cam = await db.Cameras.FindAsync(id);
        if (cam is not null) { db.Cameras.Remove(cam); await db.SaveChangesAsync(); }
    }

    public async Task<object?> InvokeCommandAsync(int id, string method, object? payload)
    {
        var cam = await db.Cameras.FindAsync(id);
        if (cam is null) return null;

        // TODO: forward command to Python bridge HTTP API or Azure IoT Hub direct method
        logger.LogInformation("Camera {Id} command {Method} payload {Payload}", id, method, payload);
        return new { cameraId = id, method, status = "queued" };
    }

    public async Task<object?> GetStatusAsync(int id)
    {
        var cam = await db.Cameras.AsNoTracking().FirstOrDefaultAsync(c => c.Id == id);
        if (cam is null) return null;
        return new
        {
            cam.Id,
            cam.IpAddress,
            cam.Status,
            cam.RtspConfirmed,
            cam.OnvifConfirmed,
            cam.LastSeenUtc,
        };
    }
}
