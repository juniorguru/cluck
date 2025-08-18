# cluck 🎧

Backup record of audio during Junior Guru talks

## Audio MIDI Setup

Have Black Hole 2ch installed. Create:

- **Jabra Recording**, Aggregate device, Clock source: Black Hole, Sample rate: 16 KHz, Use: Jabra + BlackHole, Drift correction: Jabra. This allows to reliably record BT headphones.
- **Discord Recording**, Multi-output device, Primary device: Jabra, Sample rate: 44.1 KHz, Use: Jabra + BlackHole, Drift correction: BlackHole. This allows to record Discord and listen to it in BT headphones.

## If BT headphones die

- Aggregate device should prevent ffmpeg to crash or create empty file.
- Must go to **Discord Recording** (Multi-output device) and check MacBook Air Speakers, otherwise I won't hear Discord.

## BT headphones and BT profile changes

If you start speaking too soon after the start of recording, ffmpeg starts recording before the BT profile settles, and the whole recording of BT speakers is unusable crap, just scratching sounds.

If you start recording before you connect the headphones, all is good. That's why this program forces you to first start recording, and only then connect the BT headphones.
