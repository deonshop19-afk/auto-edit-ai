from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
import subprocess, uuid

app = Flask(__name__)
BASE = Path('/tmp/auto_edit_ai')
BASE.mkdir(exist_ok=True)

@app.get('/')
def home():
    return render_template('index.html')

@app.post('/edit')
def edit():
    video = request.files.get('video')
    if not video or not video.filename:
        return 'Pilih video terlebih dahulu.', 400
    if Path(video.filename).suffix.lower() not in {'.mp4', '.mov', '.mkv', '.webm'}:
        return 'Format video tidak didukung.', 400
    job = BASE / str(uuid.uuid4())
    job.mkdir()
    source = job / ('input' + Path(secure_filename(video.filename)).suffix.lower())
    target = job / 'hasil.mp4'
    video.save(source)
    cmd = ['ffmpeg', '-y', '-i', str(source), '-vf', 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '25', '-c:a', 'aac', '-movflags', '+faststart', str(target)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=240)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 'Video gagal diproses. Coba video yang lebih pendek.', 500
    return send_file(target, as_attachment=True, download_name='auto-edit-ai-hasil.mp4')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
