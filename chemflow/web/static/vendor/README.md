# Distribusi penampil NGL

NGL 2.5.0 `dist/ngl.js` yang dipatok versinya, distribusi browser mandiri dari paket
npm `ngl@2.5.0` (MIT; lisensi disertakan di samping aset).
SHA-256: ceab08a04b246cd4ba799749fce0a822c370e34b7366a3c090530ea5e8d48507

Dimuat saat dibutuhkan lewat src/lib/ngl.ts dari origin yang sama, sehingga
penampil tetap berjalan offline dan tidak membawa dependensi build Mol*
native/headless yang khusus Node. Untuk memperbarui: tinjau rilis resmi NGL,
ganti distribusi browser dan lisensinya, perbarui versi/hash pada loader, lalu
jalankan uji Playwright WebGL nyata. Jangan menggantinya dengan skrip CDN tanpa
versi tetap.
