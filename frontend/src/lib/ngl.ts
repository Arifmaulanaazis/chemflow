/** Muat distribusi NGL mandiri yang dipatok versinya hanya saat struktur dibuka. */
let pending: Promise<any> | null = null;
export function loadNgl(): Promise<any> {
  if (window.NGL) return Promise.resolve(window.NGL);
  if (!pending)
    pending = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/vendor/ngl-2.5.0.js";
      script.async = true;
      script.onload = () =>
        window.NGL
          ? resolve(window.NGL)
          : reject(new Error("NGL gagal diinisialisasi."));
      script.onerror = () => {
        pending = null;
        script.remove();
        reject(new Error("Bundle viewer NGL tidak dapat dimuat."));
      };
      document.head.appendChild(script);
    });
  return pending;
}
