using CameraGateway.Data;
using CameraGateway.Models;
using Microsoft.EntityFrameworkCore;

namespace CameraGateway.Services;

public class RecordingService(
    CameraDbContext db,
    IConfiguration config,
    ILogger<RecordingService> logger)
{
    // Active FFmpeg PIDs – in production replace with a durable store
    private readonly Dictionary<string, System.Diagnostics.Process> _active = [];

    public Task<List<Recording>> ListAsync(int? cameraId, int page, int pageSize)
    {
        var q = db.Recordings.AsNoTracking().AsQueryable();
        if (cameraId.HasValue) q = q.Where(r => r.CameraId == cameraId.Value);
        return q.OrderByDescending(r => r.StartedUtc)
                .Skip((page - 1) * pageSize)
                .Take(pageSize)
                .ToListAsync();
    }

    public async Task<Recording?> StartAsync(Controllers.RecordingStartRequest req)
    {
        // Require the caller to have confirmed RTSP is reachable before calling this method.
        // The gateway trusts the RtspUrl field because only an authenticated client can post here.
        var cam = await db.Cameras.FindAsync(req.CameraId);
        if (cam is null) return null;

        var sessionId = DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ");
        var outputPath = req.OutputPath
            ?? config["Recording:DefaultPath"]
            ?? Path.Combine(Path.GetTempPath(), "camera-platform", sessionId);

        Directory.CreateDirectory(outputPath);

        var ffmpeg = config["Recording:FfmpegPath"] ?? "ffmpeg";
        var pattern = Path.Combine(outputPath, $"{sessionId}-%Y%m%dT%H%M%SZ.mp4");

        var args = $"-loglevel warning -rtsp_transport tcp -i \"{req.RtspUrl}\" " +
                   $"-c copy -f segment -segment_time 300 -segment_format mp4 " +
                   $"-reset_timestamps 1 -strftime 1 \"{pattern}\"";

        var proc = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(ffmpeg, args)
        {
            RedirectStandardError = true,
            UseShellExecute = false,
        });

        if (proc is null)
        {
            logger.LogError("Failed to start FFmpeg for session {SessionId}", sessionId);
            return null;
        }

        _active[sessionId] = proc;
        logger.LogInformation("Recording started session={S} path={P}", sessionId, outputPath);

        var rec = new Recording
        {
            CameraId = req.CameraId,
            SessionId = sessionId,
            Destination = req.Destination,
            OutputPath = outputPath,
            Status = "recording",
        };
        db.Recordings.Add(rec);
        await db.SaveChangesAsync();
        return rec;
    }

    public async Task<Recording?> StopAsync(string sessionId)
    {
        var rec = await db.Recordings.FirstOrDefaultAsync(r => r.SessionId == sessionId);
        if (rec is null) return null;

        if (_active.TryGetValue(sessionId, out var proc))
        {
            proc.Kill();
            _active.Remove(sessionId);
        }

        rec.Status = "stopped";
        rec.StoppedUtc = DateTime.UtcNow;
        await db.SaveChangesAsync();
        return rec;
    }

    public async Task<Recording?> GetStatusAsync(string sessionId) =>
        await db.Recordings.AsNoTracking().FirstOrDefaultAsync(r => r.SessionId == sessionId);
}
