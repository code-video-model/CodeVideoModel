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
import { mats, solid, random, oakMap } from './materials.js';
import { box, cylinder, rod, group } from './geometry.js';

function tree(parent, x, z, seed, size = 1) { window.__bfTrace?.add(5);
  const rng = random(seed);
  const wood = solid('#625e40');
  const base = group(parent, `tree-${seed}`, x, -.1, z);
  rod(base, 'trunk', [0, 0, 0], [.12, 3.2 * size, 0], .065 * size, wood);
  const centers = [];
  for (let i = 0; i < 22; i++) {
    const a = rng() * Math.PI * 2;
    const h = (seed === 99 ? 1.65 + rng() * 2.6 : .45 + rng() * 3.8) * size;
    const r = (.5 + rng() * .9) * size;
    const p = [Math.cos(a) * r, h, Math.sin(a) * r];
    rod(base, 'branch', [.08, h * .6, 0], p, .012 * size, wood, 6);
    centers.push(p);
  }
  const leafGeo = new THREE.SphereGeometry(1, 5, 3);
  const leafMat = new THREE.MeshStandardMaterial({ color: '#9cab85', emissive: '#6a7953', emissiveIntensity: .13, roughness: 1 });
  const leaves = new THREE.InstancedMesh(leafGeo, leafMat, 8500);
  leaves.name = 'procedural-canopy'; leaves.castShadow = true;
  const dummy = new THREE.Object3D();
  for (let i = 0; i < 8500; i++) {
    const c = centers[i % centers.length];
    dummy.position.set(c[0] + (rng() - .5) * 1.35 * size, c[1] + (rng() - .5) * .95 * size, c[2] + (rng() - .5) * 1.25 * size);
    dummy.scale.set(.019 + rng() * .025, .007 + rng() * .011, .012 + rng() * .018);
    dummy.rotation.set(rng() * 3, rng() * 6, rng() * 3); dummy.updateMatrix();
    leaves.setMatrixAt(i, dummy.matrix);
    leaves.setColorAt(i, new THREE.Color().setHSL(.21 + rng() * .055, .18 + rng() * .21, .41 + rng() * .28));
  }
  base.add(leaves);
}

export function makeRoom(world) {
  box(world, 'back-plaster-wall', 7, 4, .16, mats.plaster, 1.55, 2, -.16);
  box(world, 'left-wall-below-window', .18, .69, 6.8, mats.plaster, -1.32, .345, 2.8);
  box(world, 'left-wall-above-window', .18, 1, 6.8, mats.plaster, -1.32, 3.49, 2.8);
  box(world, 'left-wall-corner-pier', .18, 2.32, .64, mats.plaster, -1.32, 1.98, .22);
  box(world, 'left-wall-front-pier', .18, 2.45, 2.4, mats.plaster, -1.32, 1.915, 4.48);
  box(world, 'floor-foundation', 9, .09, 10, mats.oakEdge, 1, -.08, 3);
  const rng = random(724);
  const floor = group(world, 'diagonal-oak-floor', 1, -.02, 2);
  floor.rotation.y = -.24;
  for (let row = -30; row <= 30; row++) {
    for (let col = -4; col < 5; col++) {
      const map = oakMap.clone();
      map.repeat.set(1.5, .22); map.offset.set(rng(), rng()); map.needsUpdate = true;
      const color = new THREE.Color().setHSL(.085 + rng() * .008, .29 + rng() * .1, .50 + rng() * .12);
      const material = new THREE.MeshStandardMaterial({ map, color, roughness: .6 + rng() * .12 });
      box(floor, 'oak-plank', 1.24, .022, .125, material, col * 1.243 + ((row % 3) * .37), 0, row * .128);
    }
  }
  box(world, 'back-baseboard', 5.7, .18, .045, mats.oakEdge, 1.55, .09, -.035);
  box(world, 'left-baseboard', .045, .18, 6.8, mats.oakEdge, -1.205, .09, 2.8);
  box(world, 'left-baseboard-top-moulding', .066, .022, 6.8, mats.oak, -1.195, .19, 2.8, .006);
  box(world, 'left-baseboard-shoe', .077, .036, 6.8, mats.oakEdge, -1.18, .023, 2.8, .009);

  const window = group(world, 'double-sash-window', -1.22, -.13, 0);
  const start = .55, end = 3.28, mid = (start + end) / 2;
  box(window, 'window-wood-reveal', .2, .075, end - start + .25, mats.oak, -.04, .86, mid);
  box(window, 'deep-wood-sill', .36, .05, end - start + .38, mats.oak, .07, .842, mid, .009);
  box(window, 'wood-apron', .08, .11, end - start + .26, mats.oakEdge, .045, .763, mid);
  for (const z of [start - .05, end + .05]) {
    box(window, 'oak-side-casing', .075, 2.43, .09, mats.oak, .025, 2.01, z, .008);
    box(window, 'sash-outer-jamb', .15, 2.36, .065, mats.trim, -.04, 2.03, z > mid ? end : start);
  }
  box(window, 'window-head', .13, .09, end - start, mats.trim, -.03, 3.18, mid);
  box(window, 'central-mullion', .17, 2.3, .095, mats.trim, .02, 2.02, mid);
  for (const [a, b] of [[start + .045, mid - .055], [mid + .055, end - .045]]) {
    for (const y of [.91, 1.7, 3.14]) box(window, 'sash-horizontal-rail', .095, .055, b - a, mats.trim, -.005, y, (a + b) / 2);
    for (const z of [a, b]) box(window, 'sash-vertical-stile', .095, 2.24, .04, mats.trim, -.012, 2.015, z);
    box(window, 'sash-latch', .017, .022, .063, mats.silver, .062, .95, (a + b) / 2, .004);
  }
  const blind = solid('#c0b59b');
  box(window, 'rolled-linen-blind', .055, .21, end - start + .04, blind, .06, 3.055, mid);
  for (let i = 0; i < 12; i++) box(window, 'blind-weave-fold', .058, .004, end - start + .04, mats.trim, .062, 2.96 + i * .015, mid);

  const outdoors = group(world, 'outdoor-neighbor-and-trees');
  const house = group(outdoors, 'pale-clapboard-neighbor', .8, 0, .6);
  const siding = solid('#cbd0bc');
  siding.emissive.set('#b7c0b1'); siding.emissiveIntensity = .32;
  box(house, 'neighbor-house', .25, 3.4, 7.5, siding, -6.2, 1.3, 1.7);
  for (let i = 0; i < 36; i++) box(house, 'clapboard-course', .034, .07, 7.5, siding, -6.055, -.28 + i * .095, 1.7);
  for (const z of [-.8, 1.3, 3.5]) for (const y of [.35, 1.85]) {
    box(house, 'neighbor-window-frame', .05, 1.04, .8, mats.trim, -6.005, y, z);
    box(house, 'neighbor-window-blueglass', .056, .91, .67, solid('#809b9c'), -5.975, y, z);
    box(house, 'neighbor-window-crossbar', .065, .025, .68, mats.trim, -5.942, y, z);
    box(house, 'neighbor-window-center', .065, .91, .023, mats.trim, -5.942, y, z);
  }
  box(house, 'neighbor-eaves', .55, .13, 7.7, mats.trim, -6.05, 3.0, 1.7);
  tree(outdoors, -3.7, -1.2, 10, 1.1);
  tree(outdoors, -3.4, 3.5, 99, 1.08);
  tree(outdoors, -5.1, 5.2, 31, 1.3);

  const pot = group(world, 'sill-terracotta-plant', -.99, .74, 2.43);
  cylinder(pot, 'saucer', .133, .11, .025, mats.terracotta, 0, .016, 0);
  cylinder(pot, 'pot', .112, .079, .145, mats.terracotta, 0, .096, 0);
  cylinder(pot, 'pot-rim', .122, .12, .027, mats.terracotta, 0, .168, 0);
  cylinder(pot, 'soil', .103, .103, .006, mats.soil, 0, .183, 0);
  const leafMat = solid('#658444');
  for (let i = 0; i < 12; i++) {
    const a = i * 2.4, r = .045 + rng() * .08;
    const p = [Math.cos(a) * r, .22 + rng() * .055, Math.sin(a) * r];
    rod(pot, 'plant-stem', [0, .17, 0], p, .003, leafMat);
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 6), leafMat);
    leaf.position.set(...p); leaf.scale.set(.055, .008, .027); leaf.rotation.set(.15 + rng(), -a, .3);
    leaf.castShadow = true; pot.add(leaf);
  }
}
