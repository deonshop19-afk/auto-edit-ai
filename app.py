import os
import re
import uuid
import shutil
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 180 * 1024 * 1024  # Total request size
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
AUDIO_EXT = {'.mp3', '.wav', '.m4a', '.aac'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def run(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or 'Proses FFmpeg gagal')[-1400:])


def duration(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                       capture_output=True, text=True, timeout=20)
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise ValueError('Ada file video yang tidak bisa dibaca.')


def save_upload(file, directory, allowed, index):
    ext = Path(secure_filename(file.filename or '')).suffix.lower()
    if ext not in allowed:
        raise ValueError('Format file tidak didukung: ' + ext)
    target = directory / f'input_{index}{ext}'
    file.save(target)
    return target


def title_filter(title):
    # Escape characters interpreted by ffmpeg drawtext filter.
    safe = re.sub(r'[^\w\s.,!?\-]', '', title, flags=re.UNICODE)[:55].strip()
    if not safe:
        return None
    safe = safe.replace('\\', '').replace(':', '').replace("'", '')
    return f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:fontsize=42:box=1:boxcolor=black@0.6:boxborderw=16:x=(w-text_w)/2:y=h*0.10"


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/health')
def health():
    return jsonify(status='ok')


@app.post('/edit')
def edit():
    workspace = Path(tempfile.mkdtemp(prefix='autoedit_'))
    try:
        mode = request.form.get('mode', 'vlog')
        if mode not in ('vlog', 'jualan', 'short'):
            raise ValueError('Mode tidak valid.')
        files = [f for f in request.files.getlist('videos') if f.filename]
        if not 1 <= len(files) <= 8:
            raise ValueError('Pilih 1 sampai 8 video.')
        clips = [save_upload(f, workspace, VIDEO_EXT, i) for i, f in enumerate(files)]
        music = request.files.get('music')
        music_path = save_upload(music, workspace, AUDIO_EXT, 'music') if music and music.filename else None
        motion = request.form.get('motion') == 'on'
        images_enabled = request.form.get('images_enabled') == 'on'
        image_files = [f for f in request.files.getlist('images') if f.filename] if images_enabled else []
        if len(image_files) > 5:
            raise ValueError('Maksimal 5 gambar pendukung.')
        images = [save_upload(f, workspace, IMAGE_EXT, 'image'+str(i)) for i, f in enumerate(image_files)]
        # One CPU / 2 GB RAM: limit clip length, size and resolution.
        cap = {'vlog': 25, 'jualan': 12, 'short': 12}[mode]
        width, height = (1280, 720) if mode == 'vlog' else (720, 1280)
        title = (request.form.get('title') or '').strip()
        segments = []
        for i, clip in enumerate(clips):
            length = duration(clip)
            if length < 0.3:
                raise ValueError('Salah satu video terlalu pendek.')
            segment = workspace / f'segment_{i}.mp4'
            scale = (f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                     f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24')
            filters = [scale]
            if motion:
                fade_out = max(0, min(cap, length) - 0.4)
                filters.append(f'fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.2f}:d=0.35')
            if mode == 'jualan' and title:
                tf = title_filter(title)
                if tf:
                    filters.append(tf)
            cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(clip),
                   '-t', str(min(cap, length)), '-vf', ','.join(filters), '-an',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '29',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(segment)]
            run(cmd)
            segments.append(segment)
        for i, picture in enumerate(images):
            segment = workspace / f'picture_{i}.mp4'
            vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                  f'crop={width}:{height},setsar=1,'
                  f'zoompan=z=min(zoom+0.0008\\,1.12):d=72:s={width}x{height}:fps=24,'
                  'format=yuv420p')
            if motion:
                vf += ',fade=t=in:st=0:d=0.35,fade=t=out:st=2.6:d=0.35'
            run(['ffmpeg','-y','-hide_banner','-loglevel','error','-loop','1','-i',str(picture),
                 '-t','3','-vf',vf,'-an','-c:v','libx264','-preset','ultrafast',
                 '-crf','29','-pix_fmt','yuv420p',str(segment)])
            position = min(len(segments), (i+1)*len(clips)//(len(images)+1)+i)
            segments.insert(position, segment)
        listfile = workspace / 'clips.txt'
        listfile.write_text(''.join(f"file '{p.as_posix()}'\n" for p in segments), encoding='utf-8')
        combined = workspace / 'combined.mp4'
        run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
             '-i', str(listfile), '-c', 'copy', str(combined)])
        output = workspace / 'hasil-auto-edit.mp4'
        if music_path:
            run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(combined),
                 '-stream_loop', '-1', '-i', str(music_path), '-map', '0:v:0', '-map', '1:a:0',
                 '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest',
                 '-movflags', '+faststart', str(output)])
        else:
            shutil.copyfile(combined, output)
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: shutil.rmtree(workspace, ignore_errors=True))
            return response
        return send_file(output, as_attachment=True, download_name='hasil-auto-edit.mp4', mimetype='video/mp4')
    except (ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        shutil.rmtree(workspace, ignore_errors=True)
        return jsonify(error=str(exc)), 400
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        app.logger.exception('Video processing failed')
        return jsonify(error='Gagal memproses video. Coba file yang lebih kecil.'), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify(error='Total unggahan terlalu besar (maksimal 180 MB).'), 413


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
