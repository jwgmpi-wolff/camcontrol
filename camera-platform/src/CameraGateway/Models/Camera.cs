namespace CameraGateway.Models;

public class Camera
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string IpAddress { get; set; } = string.Empty;
    public string? Hostname { get; set; }
    public string? MacAddress { get; set; }
    public string? RtspUrl { get; set; }        // stored encrypted or via Key Vault reference
    public string? OnvifServiceUrl { get; set; }
    public string Model { get; set; } = "YI Outdoor Camera 1080p YHS.3017";
    public string FccId { get; set; } = "2AFIB-YHS3017";
    public bool RtspConfirmed { get; set; }
    public bool OnvifConfirmed { get; set; }
    public string Status { get; set; } = "unknown";  // online|offline|unknown
    public DateTime LastSeenUtc { get; set; }
    public DateTime CreatedUtc { get; set; } = DateTime.UtcNow;
    public List<Recording> Recordings { get; set; } = [];
}

public record CameraCreateRequest(
    string Name,
    string IpAddress,
    string? Hostname,
    string? MacAddress,
    string? RtspUrl,
    string? OnvifServiceUrl
);
