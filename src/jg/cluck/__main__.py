import os
import signal
import time
from datetime import datetime
from threading import Thread

import sounddevice as sd
import soundfile as sf
from rich.console import Console

console = Console()
procs = []
files = []
running = True

def get_device_index(name):
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if isinstance(d, dict):
                dev_name = d.get("name") or ""
            else:
                try:
                    dev_name = str(d)
                except Exception:
                    dev_name = ""
            if name in dev_name:
                return i
    except Exception:
        console.log("sounddevice not available or failed to list devices")
    return None


def start_record(index, label):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = os.path.expanduser("~/Downloads")
    os.makedirs(outdir, exist_ok=True)
    filename = f"record-discord-{label}-{ts}.flac"
    path = os.path.join(outdir, filename)

    def _rec_thread(path: str, device_index: int):
        samplerate = 44100
        try:
            with sf.SoundFile(
                path,
                mode="w",
                samplerate=samplerate,
                channels=1,
                format="FLAC",
                subtype="PCM_16",
            ) as file:
                with sd.InputStream(
                    samplerate=samplerate, device=device_index, channels=1
                ) as stream:
                    console.log(f"Recording {label} -> {path}")
                    while running:
                        data, _ = stream.read(1024)
                        file.write(data)
        except Exception as exc:
            console.log(f"Recording {label} failed: {exc}")

    thread = Thread(target=_rec_thread, args=(path, index), daemon=True)
    thread.start()
    return thread, path


def stop_all():
    for t in procs:
        try:
            t.join(timeout=5)
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
