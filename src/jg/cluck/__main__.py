import signal
from pathlib import Path
import time
from datetime import datetime
from threading import Thread, Event

import sounddevice
import soundfile
from rich.console import Console

console = Console()


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


def _record_thread(
    path: Path, device_index: int, stop_event: Event, label: str
) -> None:
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
                while not stop_event.is_set():
                    try:
                        data, _ = stream.read(1024)
                    except Exception as exc:
                        if isinstance(exc, sounddevice.PortAudioError):
                            console.log(
                                f"Device for '{label}' disappeared; stopping this track."
                            )
                            break
                        if isinstance(exc, OSError):
                            console.log(
                                f"Device for '{label}' reported OS error and disappeared; stopping this track."
                            )
                            break
                        console.log(
                            f"Recording {label} encountered unexpected error; stopping this track and showing traceback:"
                        )
                        console.print_exception()
                        break
                    file.write(data)
    except Exception:
        console.log(f"Recording {label} failed!")
        console.print_exception()


def start_recording(device_index, label, stop_event: Event) -> tuple[Thread, Path]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = Path.home() / "Downloads"
    outdir.mkdir(parents=True, exist_ok=True)
    filename = f"record-discord-{label}-{ts}.flac"
    path = outdir / filename
    thread = Thread(
        target=_record_thread, args=(path, device_index, stop_event, label), daemon=True
    )
    thread.start()
    return thread, path


def stop_all(procs: list[Thread]) -> None:
    for t in procs:
        try:
            t.join(timeout=5)
        except Exception:
            pass

def signal_handler(sig, frame):
    global running
    running = False
    console.log("Stopping all recordings...")

def main() -> None:
    stop_event = Event()

    def _signal_handler(sig, frame):
        stop_event.set()
        console.log("Stopping all recordings...")

    signal.signal(signal.SIGINT, _signal_handler)

    procs: list[Thread] = []
    files: list[Path] = []

    for name, label in DEVICES_MAPPING:
        index = get_device_index(name)
        if index is not None:
            proc, path = start_recording(index, label, stop_event)
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
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    stop_all(procs)
    console.log("All recordings finished.")
    for file in files:
        console.log(file)


if __name__ == "__main__":
    main()
