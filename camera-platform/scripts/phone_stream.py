"""
Stream phone screen (YI app camera live view) via ADB → ffmpeg → HLS.
Usage: python phone_stream.py [device_id]
The phone must have the YI app open and showing camera live view.
"""
from __future__ import annotations
import shutil, subprocess, sys, time, os
from pathlib import Path

ADB_PT = Path(os.environ.get("LOCALAPPDATA","")) / "Microsoft/WinGet/Packages"
def _find_adb() -> str:
    # winget install location
    for p in ADB_PT.glob("Google.PlatformTools*/platform-tools/adb.exe"):
        return str(p)
    return shutil.which("adb") or "adb"

ADB = _find_adb()
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
HLS_ROOT = Path(__file__).parent.parent.parent / "streams" / "hls"

def open_yi_app(device: str = "") -> None:
    """Launch YI app to home screen via ADB intent."""
    dev = ["-s", device] if device else []
    # Try common YI app package names
    for pkg in ["com.xiaoyi.yihome", "com.yi.ipc", "com.kami.yihome"]:
        r = subprocess.run([ADB] + dev + ["shell", "monkey", "-p", pkg, "-c",
                           "android.intent.category.LAUNCHER", "1"],
                          capture_output=True, text=True)
        if "Events injected: 1" in r.stdout:
            print(f"Opened {pkg}")
            return
    print("Could not auto-open YI app — open it manually on the phone")

def stream_screen_to_hls(stream_name: str, device: str = "", rotate: int = 0) -> subprocess.Popen:
    """
    Pipe phone screen (H.264) via ADB to ffmpeg → HLS segments.
    stream_name: used as the HLS output folder name
    """
    out_dir = HLS_ROOT / stream_name
    out_dir.mkdir(parents=True, exist_ok=True)
    m3u8 = str(out_dir / "live.m3u8")

    dev = ["-s", device] if device else []
    # adb exec-out screenrecord --output-format=h264 - streams raw H.264
    adb_cmd = [ADB] + dev + ["exec-out", "screenrecord",
                              "--output-format=h264", "--size=1280x720", "-"]
    ffmpeg_cmd = [FFMPEG, "-loglevel", "warning",
                  "-f", "h264", "-i", "pipe:0",
                  "-c:v", "copy",
                  "-vf", f"rotate={rotate}*PI/180" if rotate else "null",
                  "-f", "hls",
                  "-hls_time", "2",
                  "-hls_list_size", "8",
                  "-hls_flags", "delete_segments+append_list",
                  "-hls_segment_filename", str(out_dir / "seg%05d.ts"),
                  m3u8]
    if rotate:
        ffmpeg_cmd[ffmpeg_cmd.index("-c:v")] = "-c:v"
        ffmpeg_cmd[ffmpeg_cmd.index("copy")] = "libx264"

    print(f"Starting ADB screen capture → {m3u8}")
    adb_proc = subprocess.Popen(adb_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=adb_proc.stdout,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    adb_proc.stdout.close()
    return ffmpeg_proc

if __name__ == "__main__":
    device = sys.argv[1] if len(sys.argv) > 1 else ""
    stream_name = sys.argv[2] if len(sys.argv) > 2 else "phone_screen"
    print(f"ADB: {ADB}")
    print(f"Opening YI app...")
    open_yi_app(device)
    time.sleep(3)
    print(f"Navigate to a camera live view on the phone, then press Enter...")
    input()
    proc = stream_screen_to_hls(stream_name, device)
    hls = HLS_ROOT / stream_name / "live.m3u8"
    print(f"Streaming... HLS at http://localhost:8080/streams/hls/{stream_name}/live.m3u8")
    print("Press Ctrl+C to stop")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
