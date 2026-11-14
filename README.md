# Auto Edit AI V3 Beta
## Upload
Replace `app.py`, `templates/index.html`, `requirements.txt`, and `Dockerfile` in the existing GitHub repo. Do not upload the ZIP directly to GitHub expecting auto-extraction.

## Features
- Audio choices: extract original clip audio, upload VO, or mute.
- Images appear over the video rather than being appended as separate clips.
- Alternating full-frame and picture-in-picture.
- Image keyword labels and optional speech timing.

## Important limitation
Speech matching requires a speech-to-text model. It is OFF by default to avoid exhausting a small hosting instance. To enable, add `faster-whisper` to `requirements.txt` and set `ENABLE_TRANSCRIPTION=1` in hosting environment. The model downloads on first use. Set `WHISPER_MODEL=tiny` (default). With no transcription, images are distributed across the video and NOT speech-synchronized.
This beta does not generate AI voices, auto-subtitles, or automatically select best scenes. VO is uploaded audio.

## Test before deployment
Try one short video and one image. Back up V2 first. Container memory/CPU limits may require lowering resolution or disabling transcription.
