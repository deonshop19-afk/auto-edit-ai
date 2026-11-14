# Auto Edit AI — Versi 2 (Beta)

Aplikasi Flask + FFmpeg untuk menggabungkan 1–8 video, mode vlog 16:9, jualan/Reels 9:16, efek fade opsional, sisipan maksimal 5 gambar pendukung yang diunggah sendiri dengan efek zoom, musik opsional, dan preview/download hasil MP4.

**Belum ada** AI yang memahami isi video, pencarian gambar otomatis, generasi gambar AI, subtitle otomatis, atau motion graphic kompleks. Jangan menganggap fitur tersebut sudah tersedia.

## Deploy
Unggah isi folder ini ke **root** repository GitHub `auto-edit-ai` (jangan unggah folder pembungkus sebagai satu folder). Pastikan `templates/index.html` tetap berada dalam folder `templates` (nama harus tepat). Dockerfile sudah memasang FFmpeg. Atur port 10000 jika diminta hosting.

Untuk uji lokal: pasang FFmpeg dan `pip install -r requirements.txt`, lalu `python app.py`. Buka http://localhost:10000.

Batas unggahan 180 MB; proses sinkron dapat memerlukan waktu lama dan membutuhkan CPU/RAM. Untuk penggunaan publik perlu sistem antrean, batas durasi, otentikasi, dan penyimpanan hasil yang lebih aman.
