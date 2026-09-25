/*
MIT License

Copyright (c) 2026 CodeVideoBench contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Adapted for local workspace imports and descriptive variant names.
*/
import * as THREE from '../vendor/three.module.js';

export function box(parent, name, w, h, d, material, x = 0, y = 0, z = 0, bevel = 0) {
  let geometry;
  if (bevel) {
    const r = Math.min(bevel, w / 3, h / 3, d / 3);
    const shape = new THREE.Shape();
    shape.moveTo(-w / 2 + r, -h / 2);
    shape.lineTo(w / 2 - r, -h / 2);
    shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
    shape.lineTo(w / 2, h / 2 - r);
    shape.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
    shape.lineTo(-w / 2 + r, h / 2);
    shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
    shape.lineTo(-w / 2, -h / 2 + r);
    shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
    geometry = new THREE.ExtrudeGeometry(shape, { depth: d - 2 * r, bevelEnabled: true, bevelSize: r, bevelThickness: r, bevelSegments: 2, steps: 1, curveSegments: 3 });
    geometry.translate(0, 0, -d / 2 + r);
  } else geometry = new THREE.BoxGeometry(w, h, d);
  if (material.userData.wood && h > w * 2 && h > d * 1.5) {
    const uv = geometry.attributes.uv;
    for (let i = 0; i < uv.count; i++) {
      const u = uv.getX(i), v = uv.getY(i);
      uv.setXY(i, v, u);
    }
  }
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = name; mesh.position.set(x, y, z);
  mesh.castShadow = mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

export function cylinder(parent, name, top, bottom, height, material, x, y, z, segments = 24) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(top, bottom, height, segments), material);
  mesh.name = name; mesh.position.set(x, y, z);
  mesh.castShadow = mesh.receiveShadow = true; parent.add(mesh); return mesh;
}

export function rod(parent, name, a, b, radius, material, segments = 12) {
  const start = new THREE.Vector3(...a), end = new THREE.Vector3(...b);
  const mesh = cylinder(parent, name, radius, radius, start.distanceTo(end), material, 0, 0, 0, segments);
  mesh.position.copy(start).add(end).multiplyScalar(.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.sub(start).normalize());
  return mesh;
}

export function curve(parent, name, points, radius, material) {
  const spline = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)));
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(spline, 32, radius, 6, false), material);
  mesh.name = name; mesh.castShadow = true; parent.add(mesh); return mesh;
}

export function group(parent, name, x = 0, y = 0, z = 0) {
  const result = new THREE.Group(); result.name = name;
  result.position.set(x, y, z); parent.add(result); return result;
}

let contactMaterial;
export function contactShadow(parent, name, x, z, width, depth) {
  if (!contactMaterial) {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 128;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(64, 64, 8, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(24,14,7,.48)');
    gradient.addColorStop(.55, 'rgba(24,14,7,.25)');
    gradient.addColorStop(1, 'rgba(24,14,7,0)');
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, 128, 128);
    contactMaterial = new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false });
  }
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), contactMaterial);
  plane.name = name; plane.rotation.x = -Math.PI / 2;
  plane.position.set(x, .009, z); parent.add(plane);
}
