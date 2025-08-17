import signal
from pathlib import Path
import time
from datetime import datetime
from threading import Thread

import sounddevice
import soundfile
from rich.console import Console

console = Console()
procs = []
files = []
running = True


DEVICES_MAPPING = [
    ("Jabra", "mic-jabra"),
    ("BlackHole", "blackhole"),
    ("MacBook", "mic-macbook"),
]


def get_device_index(name) -> int | None:
    devices = sounddevice.query_devices()
    needle = name.lower()
    for i, device in enumerate(devices):
        device_name = (device.get("name") or "").lower()
        if needle in device_name:
            return i
    return None


def start_recording(device_index, label) -> tuple[Thread, Path]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = Path.home() / "Downloads"
    outdir.mkdir(parents=True, exist_ok=True)
    filename = f"record-discord-{label}-{ts}.flac"
    path = outdir / filename

    def _rec_thread(path: str, device_index: int):
        samplerate = 44100
        try:
            with soundfile.SoundFile(
                path,
                mode="w",
                samplerate=samplerate,
                channels=1,
                format="FLAC",
                subtype="PCM_16",
            ) as file:
                with sounddevice.InputStream(
                    samplerate=samplerate, device=device_index, channels=1
                ) as stream:
                    console.log(f"Recording {label}: {path}")
                    while running:
                        data, _ = stream.read(1024)
                        file.write(data)
        except Exception:
            console.log(f"Recording {label} failed!")
            console.print_exception()

    thread = Thread(target=_rec_thread, args=(path, device_index), daemon=True)
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
def main() -> None:
    for name, label in DEVICES_MAPPING:
        index = get_device_index(name)
        if index is not None:
            proc, path = start_recording(index, label)
            if proc:
                procs.append(proc)
                files.append(path)
        else:
            console.log(f"{name} not found, skipping...")

    if not procs:
        console.log("No recording processes started. Ensure devices are available.")
        return

    console.log("Recording... Press Ctrl+C to stop.")
    try:
        while running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        # already handled by signal handler, but ensure flag is cleared
        pass
    stop_all()
    console.log("All recordings finished.")
    for file in files:
        console.log(file)


if __name__ == "__main__":
    main()
