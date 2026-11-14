import os, re, shutil, subprocess, tempfile
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
from werkzeug.utils import secure_filename

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=180*1024*1024
VIDEO_EXT={'.mp4','.mov','.mkv','.webm','.m4v'}
AUDIO_EXT={'.mp3','.wav','.m4a','.aac','.mp4','.mov','.mkv','.webm'}
IMAGE_EXT={'.jpg','.jpeg','.png','.webp'}
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
MODEL=None

def run(cmd,timeout=420):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError((p.stderr or 'FFmpeg gagal')[-1000:])

def probe(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],capture_output=True,text=True,timeout=20)
    try: return float(p.stdout.strip())
    except (ValueError,TypeError): raise ValueError('File media tidak dapat dibaca.')

def has_audio(path):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=index','-of','csv=p=0',str(path)],capture_output=True,text=True,timeout=20)
    return bool(p.stdout.strip())

def save(f,folder,allowed,label):
    ext=Path(secure_filename(f.filename or '')).suffix.lower()
    if ext not in allowed: raise ValueError('Format tidak didukung: '+ext)
    target=folder/(label+ext);f.save(target);return target

def transcribe(path):
    """Optional: enable via ENABLE_TRANSCRIPTION=1. Download model on first use."""
    if os.getenv('ENABLE_TRANSCRIPTION','0')!='1': return []
    try:
        from faster_whisper import WhisperModel
        global MODEL
        if MODEL is None: MODEL=WhisperModel(os.getenv('WHISPER_MODEL','tiny'),device='cpu',compute_type='int8')
        segments,_=MODEL.transcribe(str(path),language='id',vad_filter=True)
        return [(float(s.start),float(s.end),s.text.lower()) for s in segments]
    except Exception as exc:
        app.logger.warning('Transkripsi tidak tersedia: %s',exc)
        return []

def image_times(images,labels,transcript,total):
    times=[]
    for i,_ in enumerate(images):
        words=[w for w in re.findall(r'\w+',labels[i].lower()) if len(w)>=3]
        hits=[(start,end) for start,end,spoken in transcript if words and any(w in spoken for w in words)]
        if hits:
            start=max(0,hits[0][0]); end=min(total,max(start+2.2,hits[0][1]))
        else:
            # Fallback: distribute images after the intro, never all at the start.
            start=min(max(0,total-1.6),total*(i+1)/(len(images)+1))
            end=min(total,start+2.8)
        if end-start>=0.5: times.append((start,end))
    return times

@app.get('/')
def home(): return render_template('index.html')

@app.get('/health')
def health(): return jsonify(status='ok',version='3')

@app.post('/edit')
def edit():
    work=Path(tempfile.mkdtemp(prefix='autoedit_v3_'))
    try:
        mode=request.form.get('mode','vlog')
        if mode not in ('vlog','jualan','short'): raise ValueError('Mode tidak valid.')
        audio_mode=request.form.get('audio_mode','extract')
        if audio_mode not in ('extract','vo','none'): raise ValueError('Pilihan audio tidak valid.')
        videos=[f for f in request.files.getlist('videos') if f.filename]
        if not 1<=len(videos)<=8: raise ValueError('Pilih 1 sampai 8 video.')
        clips=[save(f,work,VIDEO_EXT,f'clip_{i}') for i,f in enumerate(videos)]
        image_enabled=request.form.get('images_enabled')=='on'
        pics=[f for f in request.files.getlist('images') if f.filename] if image_enabled else []
        if len(pics)>5: raise ValueError('Maksimal 5 gambar.')
        images=[save(f,work,IMAGE_EXT,f'image_{i}') for i,f in enumerate(pics)]
        labels=[x.strip() for x in request.form.get('image_labels','').splitlines()]
        labels=(labels+['']*len(images))[:len(images)]
        voice=request.files.get('voice')
        voice_path=save(voice,work,AUDIO_EXT,'voice') if voice and voice.filename else None
        if audio_mode=='vo' and not voice_path: raise ValueError('Pilih file rekaman VO dahulu.')
        width,height=(1280,720) if mode=='vlog' else (720,1280)
        cap={'vlog':25,'jualan':12,'short':12}[mode]
        motion=request.form.get('motion')=='on'
        title=re.sub(r'[^\w\s.,!?\-]','',(request.form.get('title') or ''))[:55].strip()
        pieces=[]
        for i,clip in enumerate(clips):
            length=min(cap,probe(clip))
            if length<0.5: raise ValueError('Video terlalu pendek.')
            seg=work/f'seg_{i}.mp4'
            vf=(f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24')
            if motion and length>=1: vf+=f',fade=t=in:st=0:d=0.25,fade=t=out:st={max(0,length-.25):.3f}:d=0.25'
            if mode=='jualan' and title:
                vf+=f",drawtext=fontfile={FONT}:text='{title}':fontcolor=white:fontsize=38:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-text_w)/2:y=h*0.10"
            # Normalize each clip to a video + audio stream so concat keeps sound.
            cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(clip)]
            if not has_audio(clip):
                cmd+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=44100']
            cmd+=['-t',str(length),'-map','0:v:0','-map','0:a:0' if has_audio(clip) else '1:a:0',
                  '-vf',vf,'-c:v','libx264','-preset','ultrafast','-crf','29','-pix_fmt','yuv420p',
                  '-c:a','aac','-ar','44100','-ac','2','-b:a','96k','-shortest',str(seg)]
            run(cmd);pieces.append(seg)
        listing=work/'concat.txt'
        listing.write_text(''.join(f"file '{p.as_posix()}'\n" for p in pieces))
        base=work/'base.mp4'
        run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(base)])
        total=probe(base)
        timeline=[]
        if images:
            source=voice_path if audio_mode=='vo' else base if audio_mode=='extract' else None
            transcript=transcribe(source) if source else []
            timeline=image_times(images,labels,transcript,total)
        visual=base
        if timeline:
            # Composite full-screen / picture-in-picture alternating; no video time added.
            cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(base)]
            for pic in images: cmd+=['-loop','1','-i',str(pic)]
            fc=[];prev='[0:v]'
            for i,(start,end) in enumerate(timeline):
                out=f'[v{i}]'
                if i%2==0:
                    fc.append(f'[{i+1}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuva420p[p{i}]')
                else:
                    fc.append(f'[{i+1}:v]scale={int(width*.42)}:{int(height*.42)}:force_original_aspect_ratio=decrease,format=yuva420p[p{i}]')
                fc.append(f"{prev}[p{i}]overlay=x=(W-w)/2:y=(H-h)/2:enable='between(t,{start:.2f},{end:.2f})':eof_action=pass{out}")
                prev=out
            visual=work/'visual.mp4'
            cmd+=['-filter_complex',';'.join(fc),'-map',prev,'-an','-t',str(total),'-c:v','libx264','-preset','ultrafast','-crf','29','-pix_fmt','yuv420p',str(visual)]
            run(cmd,timeout=600)
        output=work/'hasil-auto-edit-v3.mp4'
        if audio_mode=='none':
            run(['ffmpeg','-y','-loglevel','error','-i',str(visual),'-map','0:v:0','-c:v','copy','-an','-movflags','+faststart',str(output)])
        elif audio_mode=='vo':
            run(['ffmpeg','-y','-loglevel','error','-i',str(visual),'-i',str(voice_path),
                 '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k',
                 '-af',f'apad=whole_dur={total:.2f}','-t',str(total),'-movflags','+faststart',str(output)])
        else:
            run(['ffmpeg','-y','-loglevel','error','-i',str(visual),'-i',str(base),
                 '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k',
                 '-t',str(total),'-movflags','+faststart',str(output)])
        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda:shutil.rmtree(work,ignore_errors=True))
            return response
        return send_file(output,as_attachment=True,download_name='hasil-auto-edit-v3.mp4',mimetype='video/mp4')
    except (ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        shutil.rmtree(work,ignore_errors=True)
        return jsonify(error=str(exc)),400
    except Exception:
        shutil.rmtree(work,ignore_errors=True)
        app.logger.exception('V3 error')
        return jsonify(error='Gagal memproses video. Coba unggahan lebih kecil.'),500

@app.errorhandler(413)
def large(_):return jsonify(error='Total unggahan maksimal 180 MB.'),413

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',10000)))
