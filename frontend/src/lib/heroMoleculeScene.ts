import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { heroNodes, heroLinks } from "./heroMoleculeData";

/** Ilustrasi molekul asli dalam ruang 3D berlapis, bukan konformer kimia. */
export function createHeroMolecule(host: HTMLElement, onContextLost: () => void, variant: "hero" | "login" = "hero") {
  const isLogin = variant === "login";
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 150);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.domElement.setAttribute("aria-hidden", "true");
  host.appendChild(renderer.domElement);
  const model = new THREE.Group();
  scene.add(model);
  const materials = (isLogin ? [0x8ac4d1, 0x65ccbb, 0x7ca9ff] : [0x285c70, 0x216a64, 0x2866c0]).map(color => new THREE.MeshBasicMaterial({color}));
  const highlight = new THREE.MeshBasicMaterial({color:0xffffff, transparent:true, opacity:0.45});
  const bondMaterial = new THREE.MeshBasicMaterial({color:isLogin ? 0x8fbac4 : 0x326073});
  const disc = new THREE.CircleGeometry(1, 36);
  const cylinder = new THREE.CylinderGeometry(1, 1, 1, 10);
  const points = heroNodes.map(node => new THREE.Vector3((node.x-230)/70, (150-node.y)/70, node.z));
  const discs: THREE.Group[] = [];
  heroNodes.forEach((node,i)=>{
    const group = new THREE.Group();
    group.position.copy(points[i]);
    const dot = new THREE.Mesh(disc,materials[node.color]);
    dot.scale.setScalar(node.radius/70);
    group.add(dot);
    const shine = new THREE.Mesh(disc,highlight);
    shine.scale.setScalar(0.04);
    shine.position.set(-0.045,0.055,0.008);
    group.add(shine);
    model.add(group);
    discs.push(group);
  });
  const up = new THREE.Vector3(0,1,0);
  for(const [from,to] of heroLinks){
    const start=points[from],end=points[to],direction=end.clone().sub(start);
    const link=new THREE.Mesh(cylinder,bondMaterial);
    link.position.copy(start).add(end).multiplyScalar(0.5);
    link.quaternion.setFromUnitVectors(up,direction.clone().normalize());
    link.scale.set(0.029,direction.length(),0.029);
    model.add(link);
  }
  // Tanda cincin dalam tetap berupa garis grafis dengan kedalaman yang sama seperti simpulnya.
  const lineMaterial=new THREE.LineBasicMaterial({color:isLogin ? 0x8fbac4 : 0x326073});
  const lineGeometries:THREE.BufferGeometry[]=[];
  for(const [from,to] of [[1,2],[3,4],[5,0]]){
    const start=points[from].clone().multiplyScalar(.73);
    const end=points[to].clone().multiplyScalar(.73);
    const geometry=new THREE.BufferGeometry().setFromPoints([start,end]);
    lineGeometries.push(geometry);
    model.add(new THREE.Line(geometry,lineMaterial));
  }
  const orbitalMaterial=new THREE.LineBasicMaterial({color:isLogin ? 0x83aeb8 : 0xa3c6cf,transparent:true,opacity:.65});
  const orbitals:THREE.LineLoop[]=[];
  const particleGeometry = new THREE.SphereGeometry(1, 12, 8);
  const particleMaterial = new THREE.MeshBasicMaterial({color:isLogin ? 0xb0e6f4 : 0x267ab6});
  const haloMaterial = new THREE.MeshBasicMaterial({color:0x6cbfc7,transparent:true,opacity:.18,depthWrite:false});
  const particles: {group:THREE.Group; rx:number; ry:number; phase:number; speed:number}[] = [];
  for(const [rx,ry,tilt,turn] of [[2.32,.89,.55,-.45],[1.57,1.93,-.6,.62]]){
    const points=Array.from({length:128},(_,i)=>{
      const angle=i/128*Math.PI*2;
      return new THREE.Vector3(Math.cos(angle)*rx,Math.sin(angle)*ry,0);
    });
    const geometry=new THREE.BufferGeometry().setFromPoints(points);
    lineGeometries.push(geometry);
    const loop=new THREE.LineLoop(geometry,orbitalMaterial);
    loop.rotation.set(tilt,0,turn);
    model.add(loop);
    orbitals.push(loop);
    // Anak mewarisi kemiringan/gerak orbital yang sama, sehingga titik tetap berada di garisnya.
    for (let index = 0; index < 6; index++) {
      const phase = index / 6 * Math.PI * 2;
      const group = new THREE.Group();
      const core = new THREE.Mesh(particleGeometry, particleMaterial);
      core.scale.setScalar(.06);
      const halo = new THREE.Mesh(particleGeometry, haloMaterial);
      halo.scale.setScalar(.115);
      group.add(core, halo);
      loop.add(group);
      particles.push({group,rx,ry,phase:phase+orbitals.length*.8,speed:orbitals.length===1?.55:-.42});
    }
  }
  // Satu draw call bersama untuk partikel latar bulat yang melayang pada halaman login.
  let dust: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial> | undefined;
  let dustTexture: THREE.CanvasTexture | undefined;
  if (isLogin) {
    const textureCanvas = document.createElement("canvas");
    textureCanvas.width = textureCanvas.height = 32;
    const context = textureCanvas.getContext("2d")!;
    const glow = context.createRadialGradient(16,16,0,16,16,16);
    glow.addColorStop(0,"rgba(255,255,255,1)");
    glow.addColorStop(.3,"rgba(255,255,255,.85)");
    glow.addColorStop(1,"rgba(255,255,255,0)");
    context.fillStyle = glow;
    context.fillRect(0,0,32,32);
    dustTexture = new THREE.CanvasTexture(textureCanvas);
    const positions = Float32Array.from(Array.from({length:54},(_,index)=>{
      const angle = index * 2.399963;
      const radius = 1.7 + (index%9)*.23;
      return [Math.cos(angle)*radius,Math.sin(angle)*radius*.72,-.8-(index%7)*.22];
    }).flat());
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",new THREE.BufferAttribute(positions,3));
    dust = new THREE.Points(geometry,new THREE.PointsMaterial({color:0x9ddfdc,map:dustTexture,size:.075,transparent:true,opacity:.7,depthWrite:false}));
    scene.add(dust);
  }
  model.rotation.set(.1,-.12,0);
  const radius=2.65;
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.065;
  controls.rotateSpeed = 0.65;
  controls.zoomSpeed = 0.65;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 1.25;
  controls.minPolarAngle = 0.12;
  controls.maxPolarAngle = Math.PI - 0.12;
  // Roda mouse tetap untuk halaman. Cubit dan keyboard memperbesar model.
  controls.enableZoom = false;
  const touch = (event: PointerEvent) => { if (event.pointerType === "touch") controls.enableZoom = true; };
  renderer.domElement.addEventListener("pointerdown", touch);
  let fit = 20;
  const reset = () => { camera.position.set(0, fit * 0.12, fit); controls.target.set(0, 0, 0); controls.update(); };
  const resize = () => {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * Math.max(1, 1 / camera.aspect) * 1.08;
    controls.minDistance = fit * 0.65;
    controls.maxDistance = fit * 1.7;
    reset();
    renderer.setSize(width, height);
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();
  const keyboard = (event: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "r", "R"].includes(event.key)) return;
    event.preventDefault();
    const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
    if (event.key === "ArrowLeft") spherical.theta += 0.18;
    if (event.key === "ArrowRight") spherical.theta -= 0.18;
    if (event.key === "ArrowUp") spherical.phi -= 0.18;
    if (event.key === "ArrowDown") spherical.phi += 0.18;
    if (["+", "="].includes(event.key)) spherical.radius *= 0.9;
    if (event.key === "-") spherical.radius *= 1.1;
    spherical.phi = THREE.MathUtils.clamp(spherical.phi, controls.minPolarAngle, controls.maxPolarAngle);
    spherical.radius = THREE.MathUtils.clamp(spherical.radius, controls.minDistance, controls.maxDistance);
    camera.position.setFromSpherical(spherical).add(controls.target);
    if (event.key.toLowerCase() === "r") reset();
    controls.update();
  };
  host.addEventListener("keydown", keyboard);
  let visible = true;
  const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
  intersection.observe(host);
  let previous = 0, elapsed = 0;
  renderer.setAnimationLoop(time => {
    const delta = previous ? Math.min((time - previous) / 1000, 0.05) : 0;
    previous = time;
    if (!visible || document.hidden) return;
    elapsed += delta;
    if (dust) {
      dust.rotation.z = elapsed*.018;
      dust.rotation.y = Math.sin(elapsed*.12)*.12;
      dust.material.opacity = .58 + Math.sin(elapsed*.65)*.12;
    }
    model.position.y = Math.sin(elapsed * 0.7) * 0.065;
    model.rotation.x = .12 + Math.sin(elapsed*.32)*.17;
    model.rotation.y = -.12 + Math.sin(elapsed*.25)*.38;
    orbitals[0].rotation.y = Math.sin(elapsed*.2)*.22;
    orbitals[1].rotation.y = Math.sin(elapsed*.17+1)*.25;
    particles.forEach(({group,rx,ry,phase,speed}) => {
      const angle = elapsed * speed + phase;
      group.position.set(Math.cos(angle)*rx, Math.sin(angle)*ry, 0);
    });
    // Lingkaran grafis selalu menghadap pengamat, sementara posisi 3D-nya menghasilkan paralaks.
    model.updateMatrixWorld(true);
    const inverse = model.getWorldQuaternion(new THREE.Quaternion()).invert();
    discs.forEach(dot=>dot.quaternion.copy(inverse).multiply(camera.quaternion));
    controls.update(delta);
    renderer.render(scene, camera);
  });
  const lost = (event: Event) => { event.preventDefault(); renderer.setAnimationLoop(null); onContextLost(); };
  renderer.domElement.addEventListener("webglcontextlost", lost);
  return () => {
    renderer.setAnimationLoop(null);
    observer.disconnect(); intersection.disconnect();
    host.removeEventListener("keydown", keyboard);
    renderer.domElement.removeEventListener("pointerdown", touch);
    renderer.domElement.removeEventListener("webglcontextlost", lost);
    controls.dispose();
    disc.dispose(); cylinder.dispose(); bondMaterial.dispose();
    lineGeometries.forEach(geometry=>geometry.dispose());
    lineMaterial.dispose(); orbitalMaterial.dispose(); highlight.dispose();
    particleGeometry.dispose(); particleMaterial.dispose(); haloMaterial.dispose();
    dust?.geometry.dispose(); dust?.material.dispose(); dustTexture?.dispose();
    materials.forEach(material => material.dispose());
    renderer.dispose(); renderer.forceContextLoss();
    renderer.domElement.remove();
  };
}
