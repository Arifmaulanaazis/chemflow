/** Muat distribusi NGL mandiri yang dipatok versinya hanya saat struktur dibuka. */
let pending: Promise<any> | null = null;
export function fitStructure(stage: any, component: any) {
  if (!stage || !component) return;
  stage.handleResize();
  const bounds = component.getBox();
  // A bounding sphere fits the structure at every camera rotation.
  const radius = bounds.min.distanceTo(bounds.max) / 2 + 2;
  const viewer = stage.viewer;
  if (viewer.width <= 0 || viewer.height <= 0) return;
  const halfFov = viewer.perspectiveCamera.fov * Math.PI / 360;
  const angle = Math.atan(Math.tan(halfFov) * Math.min(1, viewer.width / viewer.height));
  stage.animationControls.zoomMove(component.getCenter(), -radius * 1.1 / Math.sin(angle), 0);
}
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
