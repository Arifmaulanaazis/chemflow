/** Kotak Vina sejajar sumbu: pusat +/- setengah ukuran, dalam Angstrom. Dipakai bersama oleh kedua penampil. */
export function boxVertices(coordinates: number[]) {
  const [x, y, z, sx, sy, sz] = coordinates;
  if (
    coordinates.length !== 6 ||
    !coordinates.every(Number.isFinite) ||
    [sx, sy, sz].some((v) => v <= 0)
  )
    return [];
  return Array.from({ length: 8 }, (_, i) => [
    x + (i & 1 ? sx : -sx) / 2,
    y + (i & 2 ? sy : -sy) / 2,
    z + (i & 4 ? sz : -sz) / 2,
  ]);
}
export function gridShape(NGL: any, coordinates: number[], name = "Gridbox") {
  const vertices = boxVertices(coordinates);
  if (!vertices.length) return null;
  const shape = new NGL.Shape(name);
  for (let i = 0; i < 8; i++)
    for (const bit of [1, 2, 4])
      if (!(i & bit))
        shape.addCylinder(
          vertices[i],
          vertices[i | bit],
          [0.18, 0.84, 0.76],
          0.12,
        );
  shape.addSphere(coordinates.slice(0, 3), [1, 0.72, 0.23], 0.35);
  return shape;
}
