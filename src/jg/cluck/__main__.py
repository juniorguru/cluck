import os
import signal
import time
from datetime import datetime
import sounddevice as sd
import soundfile as sf
from threading import Thread
from rich.console import Console

console = Console()
running = True

def record_audio(filename: str, device: int, samplerate: int = 44100):
    console.log(f"Starting recording to {filename} from device {device}")
    with sf.SoundFile(
        filename,
        mode="w",
        samplerate=samplerate,
        channels=1,
        format="FLAC",
        subtype="PCM_16",
    ) as file:
        with sd.InputStream(samplerate=samplerate, device=device, channels=1) as stream:
            while running:
                data, _ = stream.read(1024)
                file.write(data)

def signal_handler(sig, frame):
    global running
    console.log("Stopping all recordings...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
devices = sd.query_devices()
for i, d in enumerate(devices):
    if isinstance(d, dict):
        name = d.get("name") or ""
    else:
        try:
            name = str(d)
        except Exception:
            name = ""
    if "Jabra" in name:
        mic_device = i
        break
else:
    mic_device = sd.default.device[0]


timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
target_flac = os.path.expanduser(f"~/recording_{timestamp}.flac")
thread = Thread(target=record_audio, args=(target_flac, mic_device))
thread.start()

console.log(f"Recording... Press Ctrl+C to stop. File: {target_flac}")
while running:
    time.sleep(0.5)

thread.join()
console.log(f"Recording stopped. File saved as {target_flac}")
