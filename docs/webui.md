# ChemFlow WebUI 3.1.0

ChemFlow menyediakan CLI, library Python dan ruang kerja web dengan pipeline
ilmiah yang sama. WebUI menggunakan React/TypeScript, FastAPI dan NGL yang
dibundel lokal. Satu workspace dipakai satu operator dengan beberapa perangkat.

## Instalasi dan menjalankan

Python 3.10+ diperlukan. Untuk membangun frontend source gunakan Node.js 22 LTS.
Wheel release dengan aset frontend bawaan tidak memerlukan Node.

```sh
python -m pip install -e ".[web]"
cd frontend
npm ci
npm run build
cd ..
python -m chemflow web
```

Buka `http://127.0.0.1:8000`. Kata sandi acak tercetak pada terminal, atau
tetapkan `CHEMFLOW_WEB_PASSWORD` minimal 12 karakter sebelum menjalankan server.
Gunakan workspace tetap agar antrean, input, checkpoint dan hasil tersimpan:

```sh
python -m chemflow web --workspace ./chemflow-workspace --port 8000
```

Semua path input dari browser diunggah ke workspace server. Path lokal pada
perangkat yang membuka browser berbeda dengan path mesin komputasi. Executable
Vina/Open Babel harus tersedia pada server; pilihan executable terdaftar
ditampilkan dalam formulir, tanpa menerima perintah shell bebas dari browser.
BIOVIA otomatis tetap memerlukan Windows desktop; fitur lainnya mengikuti
dukungan library ilmiah pada OS server.

## Akses LAN dan tunnel

Secara bawaan server hanya mendengarkan loopback. Untuk perangkat lain pada LAN:

```sh
python -m chemflow web --host 0.0.0.0 --allowed-host 192.168.1.20 --workspace ./chemflow-workspace
```

`0.0.0.0` adalah alamat listen, bukan URL browser. Buka IP LAN server dan
pastikan firewall mengizinkan port tersebut. Gunakan hostname eksplisit untuk
setiap alamat akses; jangan memakai wildcard. Untuk tunnel HTTPS:

```sh
python -m chemflow web --host 127.0.0.1 --allowed-host chemflow.example.org --trusted-proxy 127.0.0.1 --secure-cookie --workspace ./chemflow-workspace
```

Sesuaikan domain dan IP proxy dengan deployment. `--secure-cookie` memerlukan
HTTPS pada browser. Gunakan Cloudflare Access/Zero Trust untuk kebijakan akses,
serta autentikasi ChemFlow. Tidak ada domain/tunnel yang dibuat otomatis.
Lihat [contoh Cloudflare](../deploy/cloudflared.example.yml) dan
[contoh Nginx/SSE](../deploy/nginx-location.example.conf). Proxy harus meneruskan
stream SSE tanpa buffering. Server memakai satu worker per workspace.

## Alur eksperimen

1. **Tujuan**: pilih screening, validasi native, template input, GC-MS,
   similaritas, interaksi, atau melanjutkan hasil.
2. **Bahan**: unggah file atau buat workbook ligan/reseptor langsung di browser.
   Untuk reseptor, cari kode PDB dan pilih native, koordinat manual atau beberapa
   situs. Klik **Gunakan** agar workbook tersimpan sebagai bahan eksperimen.
3. **Parameter**: atur opsi ilmiah, executable terdaftar dan parameter lanjutan.
   Pencarian membantu menemukan argumen CLI; hanya parameter yang relevan dengan
   tujuan ditampilkan. Draft dipertahankan saat pindah langkah.
4. **Tinjau**: periksa bahan, parameter dan ringkasan perintah sebelum menjalankan.

Desktop menggunakan sidebar; mobile memakai floating bottom navbar Beranda,
Eksperimen, Buat, Mesin dan Lainnya. Panduan, Materi & sitasi, pengaturan dan
keluar tersedia melalui Lainnya. Dropdown/checkbox memakai komponen custom,
mendukung keyboard dan focus terlihat. Transisi menghormati reduced motion.
Hero memakai ilustrasi molekul 3D yang bergerak terus. Geser mouse/sentuhan untuk
memutar dan cubit untuk zoom. Keyboard panah memutar, +/- mengatur zoom dan R
mengembalikan kamera. Ilustrasi mempertahankan rangka heksagonal dan warna awal, bukan hasil docking.

## Input interaktif dan pemantauan

Jika pipeline memerlukan SMILES, pemilihan native atau gridbox, pertanyaan
ditampilkan sebagai form pada ruang eksperimen. Isi jawaban lalu kirim melalui
API; tidak perlu terminal pada perangkat browser. Proses menunggu jawaban dan
lanjut dengan pilihan yang sama seperti CLI. Pembatalan juga menghentikan proses
yang sedang menunggu. Jawaban disimpan sebagai bagian jejak input eksperimen.

Log/stage/status dan pemantauan CPU, RAM serta disk berasal dari mesin server,
bukan perangkat browser. SSE memperbarui status dengan reconnect/poll fallback.
Job berjalan pada subprocess tersendiri; antrean dan checkpoint disimpan pada
workspace. UI menampilkan job menunggu, berjalan, berhasil, gagal, dibatalkan
atau terinterupsi. Hasil dapat diunduh setelah job selesai; checkpoint dipakai
untuk melanjutkan job yang mendukung resume.

## Preview molekul dan hasil

Pada **Buat workbook reseptor di browser**, viewer NGL menampilkan protein,
ligan native emas dan kotak docking sian dalam sistem koordinat Å. Memilih
native atau mengubah center/size XYZ langsung memperbarui geometri kotak.
**Fokus situs** mendekatkan kamera ke kotak; **Seluruh reseptor** menampilkan
konteks protein. Klik atom untuk membaca XYZ atau menjadikannya pusat kotak.
Drag/zoom/pinch memakai kontrol NGL. Workbook menyimpan koordinat yang dipilih.

Browser hasil mendukung struktur PDB/PDBQT/pose, representasi molekul, model,
koordinat, kontak dan gridbox; gambar plot; workbook, CSV/TSV, teks dan unduhan
file lengkap. NGL memerlukan WebGL; metadata/tabel tetap tersedia tanpa WebGL.
Preview dibatasi ukuran/jumlah baris untuk menjaga responsivitas. Formula Excel
menampilkan nilai cache, bukan menghitung ulang formula dalam browser.

Pada tabel dengan kolom numerik, pilih **Grafik interaktif**, kolom seri dan
label, lalu batang/garis. Nilai diperiksa dengan pointer atau keyboard; grafik
dapat diunduh sebagai SVG. Grafik memakai nilai preview dari file, maksimal 30
titik per halaman. Nilai kosong/nonfinite tidak diubah menjadi nol. Gunakan
hasil analitik penuh pipeline untuk interpretasi ilmiah yang lengkap.

## Materi, sitasi, dan grafik

Buka **Materi & sitasi**. PDF workshop 56 halaman dibaca langsung dengan
navigasi halaman, zoom dan keyboard; PDF dan PPTX dapat diunduh melalui sesi
yang sama. Berkas dan PDF.js dibundel dalam paket tanpa layanan dokumen/CDN.
Sitasi software/metode tersedia dengan tombol salin dan ekspor BibTeX.

```sh
chemflow citations
chemflow citations --format bibtex > chemflow.bib
```

Pilih referensi sesuai metode yang benar-benar digunakan. CLI dan WebUI memakai
registri referensi yang sama. Referensi ilmiah tidak menggantikan pelaporan
parameter, input, versi dan batasan metode dalam penelitian.

## Keamanan dan penyimpanan

Autentikasi memakai sesi HttpOnly/SameSite, token CSRF untuk mutasi, pemeriksaan
origin/host, pembatasan percobaan kata sandi salah dan header CSP. Sesi berakhir
setelah delapan jam. Ini workspace satu operator, bukan isolasi akun multi-tenant.
PPT/PDF, struktur, hasil dan endpoint API memerlukan autentikasi.

Upload dibatasi 100 MB dengan ekstensi yang diizinkan. Akses file dikurung ke
workspace dan symlink berbahaya ditolak. Preview file dibatasi 20 MB; workbook
juga memiliki batas isi ZIP, kolom dan baris. Tidak ada endpoint eksekusi shell
bebas. Backup workspace secara rutin, terutama sebelum migrasi versi besar.

## Impor hasil CLI

```sh
python -m chemflow web --workspace ./chemflow-workspace --import-run ./hasil-lama
```

Impor menyalin berkas/checkpoint tanpa mengubah folder asal; symlink dilewati.
Hapus `--import-run` setelah impor pertama agar tidak menduplikasi run saat
restart manual. Restart updater otomatis tidak mengulang impor. Run tanpa
checkpoint tetap dapat dipreview/diunduh; resume memerlukan `_state/config.json`.
Output web dapat dipakai dari CLI pada `WORKSPACE/runs/OUTPUT_ID/`.

## Pembaruan otomatis GitHub

CLI memeriksa release stabil resmi saat startup, dengan cache enam jam. WebUI
memeriksa di latar belakang dan memasang pembaruan ketika tidak ada job antre
atau berjalan. Aktivasi memerlukan verifikasi versi, import dan aset UI. Server
restart dengan workspace/host/port yang sama; browser memuat ulang ketika versi
berubah dan pengguna perlu login kembali.

Updater menyiapkan virtual environment terpisah di
`~/.cache/chemflow/updates/versions/`, lalu menerbitkan `active.json` secara atomik.
Checkout dan environment awal dipertahankan. CLI lama meneruskan otomatis ke
runtime terbaru yang telah diverifikasi. Sumber hanya release resmi
`Arifmaulanaazis/chemflow`; commit `main` merupakan informasi, bukan dipasang
langsung. Tidak ada downgrade atau prerelease otomatis.

Wheel release resmi dengan frontend bawaan diutamakan. Jika tidak tersedia,
source ZIP tag resmi dibangun dengan Node/npm sebelum instalasi; dependensi
Python diambil oleh pip. Jaringan, ruang disk dan tool build harus tersedia.
Kegagalan mempertahankan runtime lama dan menunggu enam jam sebelum mencoba
kembali. Lihat `install.log` dan **Akses & pembaruan**. Checkout yang memiliki
perubahan lokal menunda update. `CHEMFLOW_AUTO_UPDATE=0` menonaktifkan pemasangan;
`CHEMFLOW_UPDATE_HOME` menentukan cache khusus.

Referensi implementasi: [arsitektur](webui-architecture.md).
Referensi primer: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[NGL](https://nglviewer.org/ngl/api/manual/),
[Motion reduced motion](https://motion.dev/docs/react-use-reduced-motion),
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/).
