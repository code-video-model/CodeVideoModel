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

export function cameraClearance(scene, chair, camera) {
  let distance = Infinity, nearest = null;
  const box = new THREE.Box3();
  scene.traverse(node => {
    if (!node.isMesh || node.name.includes('ambient-contact')) return;
    for (let parent = node; parent; parent = parent.parent) {
      if (parent.name === 'outdoor-neighbor-and-trees') return;
    }
    if (!node.geometry.boundingBox) node.geometry.computeBoundingBox();
    box.copy(node.geometry.boundingBox).applyMatrix4(node.matrixWorld);
    const next = box.distanceToPoint(camera.position);
    if (next < distance) { distance = next; nearest = node.name; }
  });
  const chairBox = new THREE.Box3().setFromObject(chair.getObjectByName('shared-chair-model'));
  const points = [];
  for (const x of [chairBox.min.x, chairBox.max.x]) for (const y of [chairBox.min.y, chairBox.max.y]) for (const z of [chairBox.min.z, chairBox.max.z]) {
    points.push(new THREE.Vector3(x, y, z).project(camera));
  }
  return {
    distance, nearest, cameraSafetyRadius: .08,
    leftWallInteriorClearance: camera.position.x - (-1.16),
    chairProjectedAABB: {
      left: Math.min(...points.map(p => (p.x + 1) / 2)),
      right: Math.max(...points.map(p => (p.x + 1) / 2)),
      top: Math.min(...points.map(p => (1 - p.y) / 2)),
      bottom: Math.max(...points.map(p => (1 - p.y) / 2)),
    },
  };
}

export function frameWorldState(scene, chair) {
  const objects = [];
  scene.traverse(node => {
    const state = {
      type: node.type, name: node.name, position: node.position.toArray(),
      quaternion: node.quaternion.toArray(), scale: node.scale.toArray(),
      visible: node.visible, castShadow: node.castShadow, receiveShadow: node.receiveShadow,
      geometryVersion: node.geometry ? Object.fromEntries(Object.entries(node.geometry.attributes).map(([key, attribute]) => [key, attribute.version])) : null,
    };
    if (node === chair) { delete state.position; delete state.quaternion; }
    if (node.material) state.materials = (Array.isArray(node.material) ? node.material : [node.material]).map(material => ({
      version: material.version, color: material.color?.getHex(), opacity: material.opacity,
      mapVersion: material.map?.version, roughness: material.roughness, metalness: material.metalness,
      emissive: material.emissive?.getHex(), emissiveIntensity: material.emissiveIntensity,
    }));
    if (node.isLight) state.light = { color: node.color.getHex(), intensity: node.intensity, position: node.position.toArray() };
    objects.push(state);
  });
  return objects;
}
