namespace CameraGateway.Models;

public class Recording
{
    public int Id { get; set; }
    public int CameraId { get; set; }
    public Camera Camera { get; set; } = null!;
    public string SessionId { get; set; } = string.Empty;
    public string Destination { get; set; } = "local";   // local|nas|azure
    public string OutputPath { get; set; } = string.Empty;
    public string? BlobUrl { get; set; }
    public string Status { get; set; } = "recording";    // recording|stopped|uploaded|error
    public DateTime StartedUtc { get; set; } = DateTime.UtcNow;
    public DateTime? StoppedUtc { get; set; }
    public long? FileSizeBytes { get; set; }
    public string? ErrorMessage { get; set; }
}
