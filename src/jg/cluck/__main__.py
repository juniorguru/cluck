import signal
from pathlib import Path
import time
from datetime import datetime
from threading import Thread, Event

import shutil
import subprocess
from rich.console import Console
import re
import sys

console = Console()


DEVICES_MAPPING = [
    ("Jabra", "mic-jabra"),
    ("BlackHole", "blackhole"),
    ("MacBook", "mic-macbook"),
]


def _record_thread(
    ffmpeg_path: str, path: Path, device_index: int, stop_event: Event, label: str
) -> None:
    out_path = str(path.with_suffix(".m4a"))
    ffmpeg_cmd = [
        ffmpeg_path,
        "-y",
        "-f",
        "avfoundation",
        "-i",
        f":{device_index}",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        out_path,
    ]
    console.log(f"[ffmpeg {label}] Starting: {' '.join(ffmpeg_cmd)}")

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )

    try:
        assert proc.stderr is not None
        while True:
            if stop_event.is_set():
                break
            line = proc.stderr.readline()
            if line == "":
                break
            console.log(f"[ffmpeg {label}] {line.strip()}")

        if stop_event.is_set() and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
    except Exception:
        console.log(f"[ffmpeg {label}] Failed or exited unexpectedly")
        console.print_exception()
    finally:
        # Ensure the process is terminated and its stderr is closed.
        try:
            return_code = proc.poll()
            if return_code is None:
                try:
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        proc.kill()
            else:
                console.log(f"[ffmpeg {label}] Process exited with code: {return_code}")
        finally:
            try:
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass


def run_ffmpeg_list_devices(ffmpeg_path: str) -> str:
    """Run ffmpeg to list avfoundation devices and return stderr text (ffmpeg prints devices to stderr)."""
    completed = subprocess.run(
        [ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    if output := (completed.stderr or ""):
        return output
    raise RuntimeError(
        "ffmpeg did not produce any output when listing avfoundation devices"
    )


def parse_avfoundation_device_list(output: str) -> list[tuple[str, int]]:
    """Parse ffmpeg avfoundation device list stderr output into a list of
    (device_name, index) tuples in the order they appear.
    """
    devices: list[tuple[str, int]] = []
    if not output:
        return devices
    out_lines = output.splitlines()
    audio_section = False
    for line in out_lines:
        if "AVFoundation audio devices:" in line or "Audio devices" in line:
            audio_section = True
            continue
        if audio_section:
            match = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if match:
                index = int(match.group(1))
                name = match.group(2).strip()
                devices.append((name, index))
            # stop heuristics intentionally omitted; return whatever we found
    return devices


def find_device_index_by_name(
    device_name_to_find: str, devices: list[tuple[str, int]]
) -> int | None:
    """Return the ffmpeg device index for the first device whose name contains
    the provided search string (case-insensitive), or None if not found.
    """
    needle = device_name_to_find.lower()
    for device_name, index in devices:
        if needle in device_name.lower():
            return index
    return None


def start_recording(
    ffmpeg_path: str, output_dir: Path, device_index: int, label: str, stop_event: Event
) -> tuple[Thread, Path]:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"record-discord-{label}-{timestamp}.m4a"
    path = output_dir / filename
    thread = Thread(
        target=_record_thread,
        args=(ffmpeg_path, path, device_index, stop_event, label),
        daemon=True,
    )
    thread.start()
    return thread, path


def stop_all(threads: list[Thread]) -> None:
    for thread in threads:
        try:
            thread.join(timeout=5)
        except Exception:
            console.log(
                f"Failed to join thread {getattr(thread, 'name', repr(thread))}"
            )
            console.print_exception()


def main() -> None:
    stop_event = Event()

    def _signal_handler(sig: int, frame) -> None:
        stop_event.set()
        console.log("Stopping all recordings...")

    signal.signal(signal.SIGINT, _signal_handler)

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        console.print(
            "[red]ffmpeg not found in PATH. Install ffmpeg (e.g. brew install ffmpeg) and try again.[/red]"
        )
        sys.exit(1)

    raw_output = run_ffmpeg_list_devices(ffmpeg_path)
    ffmpeg_devices = parse_avfoundation_device_list(raw_output)
    if ffmpeg_devices:
        console.log(f"ffmpeg avfoundation audio devices: {ffmpeg_devices}")
    else:
        console.log(
            "No avfoundation audio devices found by ffmpeg (this may be fine on some systems)."
        )

    threads: list[Thread] = []
    paths: list[Path] = []

    output_dir = Path.home() / "Downloads"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, label in DEVICES_MAPPING:
        device_index = find_device_index_by_name(name, ffmpeg_devices)
        if device_index is not None:
            thread, path = start_recording(
                ffmpeg_path, output_dir, device_index, label, stop_event
            )
            if thread:
                threads.append(thread)
                paths.append(path)
        else:
            console.print(
                f"[red]{name} not found among ffmpeg devices, skipping...[/red]"
            )

    if not threads:
        console.print(
            "[red]No recording processes started.[/red] Ensure devices are available."
        )
        return

    console.log("Recording... Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    stop_all(threads)
    console.log("All recordings finished.")
    for path in paths:
        console.log(path)


if __name__ == "__main__":
    main()
