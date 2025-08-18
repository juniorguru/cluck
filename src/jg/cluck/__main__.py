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


BT_HEADPHONES_NAMES = ["Jabra Elite Active"]

DEVICES_MAPPING = [
    (
        "Jabra Recording",
        "mic-jabra",
        [],
    ),
    (
        "BlackHole",
        "blackhole",
        [],
    ),
    (
        "MacBook",
        "mic-macbook",
        ["-use_wallclock_as_timestamps", "1"],
    ),
]


def _record_thread(
    ffmpeg_path: str,
    ffmpeg_args: list[str],
    path: Path,
    device_index: int,
    stop_event: Event,
    label: str,
) -> None:
    """Record audio from an avfoundation input into an ADTS AAC file.

    The function launches an ffmpeg subprocess that records from the
    specified device index and writes an ADTS (.aac) file at ``path``.
    It watches ``stop_event`` to perform a graceful shutdown sequence
    (send "q" to ffmpeg stdin, then SIGINT/terminate/kill fallbacks).

    Parameters
    - ffmpeg_path: path to the ffmpeg binary.
    - path: target Path (without suffix) used to build filenames.
    - device_index: avfoundation device index to record from.
    - stop_event: Event used to request recorder shutdown.
    - label: short label used for logging.
    """
    out_aac = str(path.with_suffix(".aac"))
    log_path = str(path.with_suffix(".ffmpeg.log"))

    ffmpeg_cmd = [
        ffmpeg_path,
        "-y",
        "-flush_packets",
        "1",
        "-f",
        "avfoundation",
        "-i",
        f":{device_index}",
        *ffmpeg_args,
        "-map",
        "0:a",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "adts",
        out_aac,
    ]
    console.log(" ".join(ffmpeg_cmd))

    # Keep stdin open so we can send the "q" command to let ffmpeg finish
    # cleanly (preferred over forcing SIGINT/terminate which may truncate frames).
    stderr_f = None
    try:
        stderr_f = open(log_path, "ab")
    except Exception:
        stderr_f = subprocess.DEVNULL

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stderr=stderr_f,
        stdout=subprocess.DEVNULL,
        stdin=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        while True:
            if stop_event.is_set():
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        console.log(f"ffmpeg for {label} exited")

        if stop_event.is_set() and proc.poll() is None:
            # Try the graceful "q" quit first. If stdin is unavailable or this
            # doesn't finish ffmpeg in time, fall back to SIGINT/terminate/kill.
            try:
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
                proc.wait(timeout=5)
            except Exception:
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
        console.log(f"ffmpeg for {label} exited unexpectedly")
        console.print_exception()

    try:
        stderr_f.close()  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        log_path = Path(log_path)
        final_path = Path(out_aac)
        console.log(f"Recording finished: {final_path} (log: {log_path})")
    except Exception:
        console.print_exception()


def run_ffmpeg_list_devices(ffmpeg_path: str) -> str:
    """Run ffmpeg to list avfoundation devices and return stderr text (ffmpeg prints devices to stderr)."""
    completed = subprocess.run(
        [ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
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
            if match := re.search(r"\[(\d+)\]\s+(.+)$", line):
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
    ffmpeg_path: str,
    ffmpeg_args: list[str],
    output_dir: Path,
    device_index: int,
    label: str,
    stop_event: Event,
) -> tuple[Thread, Path]:
    """Start a background thread that records a device to disk.

    Returns a tuple of the started Thread and the Path to the recording
    file (the .aac file). The thread is started as a daemon.
    """

    path = output_dir / f"{label}.aac"
    thread = Thread(
        target=_record_thread,
        args=(ffmpeg_path, ffmpeg_args, path, device_index, stop_event, label),
        daemon=True,
    )
    thread.start()
    return thread, path


def stop_all(threads: list[Thread]) -> None:
    """Attempt to join all recording threads, logging any failures.

    Each thread is joined with a short timeout to avoid hanging the
    shutdown sequence.
    """

    for thread in threads:
        try:
            thread.join(timeout=5)
        except Exception:
            console.log(
                f"Failed to join thread {getattr(thread, 'name', repr(thread))}"
            )
            console.print_exception()


def main() -> None:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        console.print(
            "[red]ffmpeg not found in PATH. Install ffmpeg (e.g. brew install ffmpeg) and try again.[/red]"
        )
        sys.exit(1)

    stop_event = Event()

    def _signal_handler(sig: int, frame) -> None:
        stop_event.set()
        console.log("Stopping all recordings...")

    signal.signal(signal.SIGINT, _signal_handler)

    raw_output = run_ffmpeg_list_devices(ffmpeg_path)
    ffmpeg_devices = parse_avfoundation_device_list(raw_output)
    console.log(
        "Devices: " + ", ".join([f"{index} - {name}" for name, index in ffmpeg_devices])
    )

    for name in BT_HEADPHONES_NAMES:
        if find_device_index_by_name(name, ffmpeg_devices) is not None:
            raise RuntimeError(f"Start recording BEFORE connecting {name!r}")

    threads: list[Thread] = []
    paths: list[Path] = []

    base_output = Path.home() / "Downloads"
    timestamp_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = base_output / timestamp_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    console.log(f"Writing output to: {output_dir}")

    for name, label, ffmpeg_args in DEVICES_MAPPING:
        device_index = find_device_index_by_name(name, ffmpeg_devices)
        if device_index is not None:
            thread, path = start_recording(
                ffmpeg_path, ffmpeg_args, output_dir, device_index, label, stop_event
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


if __name__ == "__main__":
    main()
