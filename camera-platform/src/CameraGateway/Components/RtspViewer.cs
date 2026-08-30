using LibVLCSharp.Shared;

namespace CameraGateway.Components;

/// <summary>
/// LibVLCSharp RTSP viewer helper — embed in WPF, WinForms, or ASP.NET pages.
/// NuGet: LibVLCSharp (3.x) + VideoLAN.LibVLC.Windows
/// The RTSP URL must be pre-validated before calling Play().
/// </summary>
public sealed class RtspViewer : IDisposable
{
    private readonly LibVLC _libVlc;
    private readonly MediaPlayer _player;
    private bool _disposed;

    public MediaPlayer Player => _player;

    public RtspViewer()
    {
        Core.Initialize();
        _libVlc = new LibVLC();
        _player = new MediaPlayer(_libVlc);
    }

    /// <summary>Start playback from a confirmed RTSP URL (user-supplied credentials).</summary>
    public void Play(string rtspUrl)
    {
        if (string.IsNullOrWhiteSpace(rtspUrl))
            throw new ArgumentException("RTSP URL is required", nameof(rtspUrl));

        var media = new Media(_libVlc, new Uri(rtspUrl), FromType.FromLocation);
        // Low-latency options; adjust network-caching for your network conditions
        media.AddOption(":network-caching=150");
        media.AddOption(":rtsp-tcp");
        media.AddOption(":live-caching=150");
        _player.Play(media);
    }

    public void Stop() => _player.Stop();

    public void Dispose()
    {
        if (_disposed) return;
        _player.Dispose();
        _libVlc.Dispose();
        _disposed = true;
    }
}
