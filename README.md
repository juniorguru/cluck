# cluck 🎧

Backup record of audio during Junior Guru talks

## Audio MIDI Setup

Have Black Hole 2ch installed. Create:

- **Jabra Recording**, Aggregate device, Clock source: Black Hole, Sample rate: 16 KHz, Use: Jabra + BlackHole, Drift correction: Jabra. This allows to reliably record BT headphones.
- **Discord Recording**, Multi-output device, Primary device: Jabra, Sample rate: 44.1 KHz, Use: Jabra + BlackHole, Drift correction: BlackHole. This allows to record Discord and listen to it in BT headphones.

## If BT changes profile mid recording

- Aggregate device should prevent ffmpeg to save scratching sounds.

## If BT headphones die

- Aggregate device should prevent ffmpeg to crash or create empty file.
- Must go to **Discord Recording** (Multi-output device) and check MacBook Air Speakers, otherwise I won't hear Discord.
