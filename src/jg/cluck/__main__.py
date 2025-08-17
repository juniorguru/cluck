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
    path: Path, device_index: int, stop_event: Event, label: str, ffmpeg_path: str
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
        try:
            rc = proc.poll()
            if rc is None:
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
                console.log(f"[ffmpeg {label}] Process exited with code: {rc}")
        finally:
            try:
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass


def run_ffmpeg_list_devices(ffmpeg_path: str) -> str:
    """Run ffmpeg to list avfoundation devices and return stderr text (ffmpeg prints devices to stderr)."""
    proc = subprocess.run(
        [ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    if output := (proc.stderr or ""):
        return output
    raise RuntimeError(
        "ffmpeg did not produce any output when listing avfoundation devices"
    )


def parse_avfoundation_device_list(output: str) -> dict[int, str]:
    """Parse ffmpeg avfoundation device list stderr output into a mapping index->device name."""
    result: dict[int, str] = {}
    if not output:
        return result
    out_lines = output.splitlines()
    audio_section = False
    for line in out_lines:
        if "AVFoundation audio devices:" in line or "Audio devices" in line:
            audio_section = True
            continue
        if audio_section:
            m = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if m:
                idx = int(m.group(1))
                name = m.group(2).strip()
                result[idx] = name
            # stop heuristics intentionally omitted; return whatever we found
    return result


def start_recording(
    device_index: int, label: str, stop_event: Event, ffmpeg_path: str
) -> tuple[Thread, Path]:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outdir = Path.home() / "Downloads"
    outdir.mkdir(parents=True, exist_ok=True)
    filename = f"record-discord-{label}-{ts}.m4a"
    path = outdir / filename
    thread = Thread(
        target=_record_thread,
        args=(path, device_index, stop_event, label, ffmpeg_path),
        daemon=True,
    )
    thread.start()
    return thread, path


def stop_all(procs: list[Thread]) -> None:
    for t in procs:
        try:
            t.join(timeout=5)
        except Exception:
            pass

def signal_handler(sig: int, frame) -> None:
    global running
    running = False
    console.log("Stopping all recordings...")

def main() -> None:
    stop_event = Event()

    def _signal_handler(sig: int, frame) -> None:
        stop_event.set()
        console.log("Stopping all recordings...")

    signal.signal(signal.SIGINT, _signal_handler)

    # ensure ffmpeg exists (fail fast)
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        console.print(
            "[red]ffmpeg not found in PATH. Install ffmpeg (e.g. brew install ffmpeg) and try again.[/red]"
        )
        sys.exit(1)

    # list ffmpeg's avfoundation audio devices for diagnostics
    raw = run_ffmpeg_list_devices(ffmpeg_path)
    ff_dev = parse_avfoundation_device_list(raw)
    if ff_dev:
        console.log(f"ffmpeg avfoundation audio devices: {ff_dev}")
    else:
        console.log(
            "No avfoundation audio devices found by ffmpeg (this may be fine on some systems)."
        )

    procs: list[Thread] = []
    files: list[Path] = []

    for name, label in DEVICES_MAPPING:
        needle = name.lower()
        matched_index = None
        for idx, dev_name in ff_dev.items():
            if needle in dev_name.lower():
                matched_index = idx
                break
        if matched_index is not None:
            proc, path = start_recording(matched_index, label, stop_event, ffmpeg_path)
            if proc:
                procs.append(proc)
                files.append(path)
        else:
            console.print(
                f"[red]{name} not found among ffmpeg devices, skipping...[/red]"
            )

    if not procs:
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

    stop_all(procs)
    console.log("All recordings finished.")
    for file in files:
        console.log(file)


if __name__ == "__main__":
    main()
