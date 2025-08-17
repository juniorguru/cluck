import os
import re
import signal
import subprocess
import time
from datetime import datetime
from rich.console import Console

console = Console()
procs = []
files = []
running = True

def get_device_index(name):
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stderr or result.stdout or ""
        for line in out.splitlines():
            if name in line:
                m = re.search(r"\[(\d+)\]", line)
                if m:
                    return m.group(1)
    except FileNotFoundError:
        console.log("ffmpeg not found on PATH")
    return None


def start_record(index, label):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = os.path.expanduser("~/Downloads")
    os.makedirs(outdir, exist_ok=True)
    filename = f"record-discord-{label}-{ts}.m4a"
    path = os.path.join(outdir, filename)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "avfoundation",
        "-i",
        f":{index}",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        path,
    ]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.log(f"Recording {label} -> {path}")
        return p, path
    except FileNotFoundError:
        console.log("ffmpeg not found, cannot record")
        return None, None


def stop_all():
    for p in procs:
        try:
            if p.poll() is None:
                p.terminate()
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass

def signal_handler(sig, frame):
    global running
    running = False
    console.log("Stopping all recordings...")

signal.signal(signal.SIGINT, signal_handler)

mapping = [
    ("Jabra", "mic-jabra"),
    ("BlackHole", "blackhole"),
    ("MacBook", "mic-macbook"),
]

for name, label in mapping:
    idx = get_device_index(name)
    if idx is not None:
        p, path = start_record(idx, label)
        if p:
            procs.append(p)
            files.append(path)
    else:
        console.log(f"{name} not found, skipping...")

if not procs:
    console.log(
        "No recording processes started. Ensure ffmpeg is installed and devices are available."
    )
else:
    console.log("Recording... Press Ctrl+C to stop.")
    try:
        while running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        running = False
    stop_all()
    console.log("All recordings finished.")
    for f in files:
        console.log(f)
