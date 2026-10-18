# Desain workbench ChemFlow, revisi 3

Produk ini adalah workbench riset untuk skrining molekul, bukan landing page.
Prioritas pengguna: aplikasi yang terpandu dan menarik, baik di desktop maupun
ponsel jarak jauh.

Revisi 3 menambahkan logo gambar resmi, sketsa molekul berputar yang terkandung
dalam kartu hero, transisi Motion, kontrol pilihan dan kotak centang khusus yang
aksesibel, pembaca workshop terautentikasi, serta penjelajah grafik numerik.
Pembuat reseptor berbagi geometri kotak nyata dengan penampil hasil: konteks
protein hijau kebiruan, ligan native keemasan, dan tepi target sian dalam
koordinat Angstrom. Pola dasbor data dipakai demi keterbacaan hasil; pola
pemasaran dan gaya neumorfisme tidak cocok untuk alur eksperimen.

## Token dan hierarki

- Tinta `#183344`, redup `#526775`, permukaan putih yang dapat diedit, kertas `#f2f6f8`.
- Cobalt `#2057bb` menandai aksi utama dan kontrol terpilih.
- Teal `#136b62` dan hero akuatik pucat mencerminkan subjek molekuler.
- Aptos / Avenir Next / Segoe UI / sans sistem; basis 16px, tinggi baris 1,5.
  Monospace teknis hanya untuk koordinat, flag, dan log.
- Ilustrasi jejaring molekul menjadi titik fokus beranda. Ini ilustrasi, bukan
  struktur eksperimen; NGL menampilkan berkas yang sebenarnya.
- Radius mengikuti fungsi: 26px hero workbench, 18–23px permukaan, 11–14px kontrol,
  indikator langkah berbentuk lingkaran. Permukaan memakai border dan bayangan yang tertahan.

## Desktop dan ponsel

Desktop memakai rail navigasi terang dan permukaan kerja berbatas. Beranda
menyediakan satu aksi buat, pembacaan sumber daya langsung, dan daftar eksperimen
yang dapat difilter. Baris daftar berubah menjadi item yang mudah dibaca di
ponsel, bukan tabel lebar yang dipaksakan.

Pada lebar <=900px rail diganti navbar bawah mengambang berisi lima item dengan
ruang aman. Dialog native memuat navigasi sekunder dan keluar; penjebakan fokus
dan tombol Escape bawaan tetap berfungsi. Konten utama menyisakan ruang untuk
bar. Pada <=650px langkah wizard menjadi urutan horizontal dan tombol aksi berada
di atas navigasi aplikasi. Pada layar lanskap pendek, baris aksi kembali ke alur
konten. Kontrol mempertahankan target sentuh 44–48px dan fokus keyboard yang terlihat.

## Komposisi terpandu

Empat langkah: pilih alur kerja, siapkan bahan, atur parameter, tinjau.
Kesalahan input ditampilkan dengan panduan fokus/gulir. Pembuat dan unggahan
memblokir aksi berikutnya sampai permintaannya selesai. Input ADMET/GC-MS opsional
berada di balik disclosure eksplisit. Semua flag ilmiah tetap dapat dicari lewat
nama CLI dan punya label yang mudah dibaca. Format pilihan ganda memakai kotak
centang; vektor numerik tetap dapat diedit sebelum dinormalisasi. Langkah yang
sudah selesai dapat dikunjungi lagi.

Pertanyaan native/gridbox dan SMILES saat runtime memakai formulir terstruktur
khusus. Job yang membutuhkan input ditandai pada daftar eksperimen. Halaman hasil
memisahkan artefak dan aktivitas dalam tab yang dapat dioperasikan keyboard.
Kondisi kosong/filter menjelaskan langkah berikutnya; tidak ada persentase
kemajuan atau hasil ilmiah rekaan yang ditampilkan.

## Modul dan verifikasi

Atom: Button, Badge, Notice, Empty, dan keluarga ikon SVG lokal. Molekul:
BottomNav, WizardSteps, ResourceStrip. Modul fitur: JobComposer, ParameterPanel,
OptionField, ExperimentReview, pembuat ligan/reseptor, InputRequests, penjelajah
hasil, dan penampil NGL yang dimuat saat dibutuhkan. State API berada di luar atom visual.

Build dan pemeriksaan browser mencakup desktop, ponsel 390px, 375px, tablet 768px,
dan lanskap 844x390. Axe memeriksa beranda, tinjauan wizard, dan hasil; tab
keyboard, status error/validasi, job template CLI nyata, NGL, dan unduhan diuji.
Bukti per revisi ada di [pengujian](../testing-webui-refactor.md).

## Hero 3D

Dua belas simpul berwarna asli, kerangka heksagonal, dan dua kurva orbital
dipertahankan. Ini ilustrasi molekul grafis, bukan konformer bola-dan-batang.
Simpul mempertahankan gaya cakram datar berwarna dengan sorotan; posisi dan garis
penghubungnya menempati ruang 3D sesungguhnya. Kamera perspektif, kemiringan
multi-sumbu yang lembut, paralaks kedalaman, dan kurva orbital yang bergerak
mandiri menambah gerak tanpa mengganti karya asli dengan senyawa lain.

`heroMoleculeData.ts` berisi posisi grafis asli beserta offset kedalaman
ilustratif. `heroMoleculeScene.ts` mengelola adegan Three.js yang dimuat saat
dibutuhkan, kontrol, dan pembersihan sumber daya. Tidak ada senyawa ilmiah atau
hasil eksperimen yang tersirat. Seluruh aset dan renderer dibundel lokal.

OrbitControls mendukung rotasi mouse/sentuh, zoom cubit, serta tombol panah,
+/- dan R pada keyboard. Tidak ada tombol jeda, sesuai permintaan eksplisit
pengguna. Animasi berlanjut setelah interaksi, tetapi ditangguhkan saat di luar
layar atau tab tersembunyi agar tidak membuang GPU. Navigasi membuang listener,
observer, geometri, material, kontrol, dan konteks WebGL. Kanvas pas di dalam hero
ponsel dengan fokus keyboard yang terlihat; petunjuk interaksi hanya untuk pembaca layar.

Referensi: [Three.js](https://threejs.org/docs/) dan
[OrbitControls](https://threejs.org/docs/#OrbitControls).

Empat partikel kecil mengikuti dua kurva orbital pada ruang koordinat lokalnya,
mewarisi rotasi 3D tiap kurva. Petunjuk interaksi yang terlihat dihapus; instruksi
keyboard yang aksesibel tetap ada. Geometri/material partikel berbagi sumber daya
dan dibuang bersama adegan.
