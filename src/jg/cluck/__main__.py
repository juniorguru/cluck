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
    with sf.SoundFile(filename, mode='w', samplerate=samplerate, channels=1) as file:
        with sd.InputStream(samplerate=samplerate, device=device, channels=1) as stream:
            while running:
                data, _ = stream.read(1024)
                file.write(data)

def signal_handler(sig, frame):
    global running
    console.log("Stopping all recordings...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

# Výběr zařízení (např. první Jabra mic, nebo default)
devices = sd.query_devices()
for i, d in enumerate(devices):
    if "Jabra" in d['name']:
        mic_device = i
        break
else:
    mic_device = sd.default.device[0]

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = os.path.expanduser(f"~/recording_{timestamp}.wav")

# Spuštění nahrávání ve vlákně
thread = Thread(target=record_audio, args=(filename, mic_device))
thread.start()

console.log(f"Recording... Press Ctrl+C to stop. File: {filename}")
while running:
    time.sleep(0.5)

thread.join()
console.log(f"Recording stopped. File saved as {filename}")
