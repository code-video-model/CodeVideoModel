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
import { makeRoom } from './room.js';
import { makeDesk, makeBookshelf, makeChair } from './furniture.js';
import { preservationState } from './state-audit.js';
import { cameraClearance, frameWorldState } from './camera-audit.js';

const WIDTH = 960, HEIGHT = 544, DURATION = 124 / 24;
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setSize(WIDTH, HEIGHT);
renderer.setPixelRatio(1);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.VSMShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = .98;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#e2e8df');
const world = new THREE.Group(); world.name = 'invariant-office'; scene.add(world);
makeRoom(world); makeDesk(world); makeBookshelf(world);
const chair = makeChair(scene);
const hemisphere = new THREE.HemisphereLight('#eef4ed', '#876844', .9);
hemisphere.name = 'sky-and-warm-floor-fill'; scene.add(hemisphere);
const sun = new THREE.DirectionalLight('#fff0ce', 2.0);
sun.name = 'sunlight-through-window'; sun.position.set(-4.5, 6.4, 2.7);
sun.target.position.set(.6, .2, .4);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -4; sun.shadow.camera.right = 4;
sun.shadow.camera.top = 4; sun.shadow.camera.bottom = -4;
sun.shadow.camera.near = .1; sun.shadow.camera.far = 18;
sun.shadow.bias = -.00025; sun.shadow.normalBias = .012;
sun.shadow.radius = 5; sun.shadow.blurSamples = 8; scene.add(sun, sun.target);
const windowFill = new THREE.PointLight('#ffefd3', 20, 8, 2);
windowFill.name = 'large-window-bounce'; windowFill.position.set(-.8, 2, 2.6); scene.add(windowFill);
const roomFill = new THREE.DirectionalLight('#f4e4c6', .4);
roomFill.name = 'diffuse-window-and-room-bounce'; roomFill.position.set(-1.4, 2.8, 5);
roomFill.target.position.set(.8, .8, 0); scene.add(roomFill, roomFill.target);
const camera = new THREE.PerspectiveCamera(44, WIDTH / HEIGHT, .05, 60);
camera.name = 'shared-curved-office-dolly-camera';
let time = 0, variant = 'original';

const chairStates = {
  'original': { position: [-.10, 0, 1.54], yaw: 1.05 },
  'edited': { position: [.30, 0, 1.12], yaw: Math.PI + .07 },
};

// Fixed midpoint of the two permitted chair roots, in the horizontal orbit plane.
const orbitPivot = new THREE.Vector3(.10, .72, 1.33);

function updateCamera(t) { window.__bfTrace?.add(51);
  const end = DURATION - 1 / 24, ramp = .65;
  const seconds = THREE.MathUtils.clamp(t, 0, end);
  const rampIntegral = s => (s - ramp / Math.PI * Math.sin(Math.PI * s / ramp)) / 2;
  const ease = seconds < ramp ? rampIntegral(seconds) / (end - ramp)
    : seconds > end - ramp ? 1 - rampIntegral(end - seconds) / (end - ramp)
      : (seconds - ramp / 2) / (end - ramp);
  const angle = THREE.MathUtils.degToRad(THREE.MathUtils.lerp(85, -70, ease));
  const radius = 1.14 + 2.16 * (1 - ease) ** 2 + .32 * Math.sin(Math.PI * ease) ** 2;
  camera.position.set(orbitPivot.x + Math.sin(angle) * radius, 2.45 - 1.05 * ease * ease * (3 - 2 * ease), orbitPivot.z + Math.cos(angle) * radius);
  camera.fov = 48 - 6 * ease + 4 * Math.sin(Math.PI * ease) ** 2;
  camera.updateProjectionMatrix();
  camera.lookAt(orbitPivot.x, THREE.MathUtils.lerp(.92, .62, ease), orbitPivot.z - .40 * ease * ease);
  camera.updateMatrixWorld(true);
}

function render(t) { window.__bfTrace?.add(67);
  if (!Number.isFinite(t)) throw new TypeError('seek requires finite seconds');
  time = THREE.MathUtils.clamp(t, 0, DURATION);
  updateCamera(time);
  scene.updateMatrixWorld(true);
  renderer.render(scene, camera);
}

function setVariant(next) { window.__bfTrace?.add(75);
  if (!Object.hasOwn(chairStates, next)) throw new RangeError('variant must be original or edited');
  variant = next;
  chair.position.set(...chairStates[next].position);
  chair.rotation.set(0, chairStates[next].yaw, 0);
  render(time);
}

function getCameraState() { window.__bfTrace?.add(83);
  return { position: camera.position.toArray(), quaternion: camera.quaternion.toArray(), fov: camera.fov };
}

function bufferFingerprint(array) { window.__bfTrace?.add(87);
  const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
  let hash = 2166136261;
  for (const byte of bytes) hash = Math.imul(hash ^ byte, 16777619) >>> 0;
  return hash.toString(16).padStart(8, '0');
}

function getInvariantState() { window.__bfTrace?.add(94);
  const objects = [];
  const geometries = new Map(), materials = new Map(), textures = new Map();
  scene.traverse(object => {
    const isChairRoot = object === chair;
    const state = { name: object.name, parent: object.parent?.uuid ?? null, type: object.type, scale: object.scale.toArray(), visible: object.visible, castShadow: object.castShadow, receiveShadow: object.receiveShadow };
    // Local descendant transforms retain chair geometry while omitting only its rigid pose.
    if (!isChairRoot) {
      state.position = object.position.toArray();
      state.quaternion = object.quaternion.toArray();
    }
    if (object.geometry) {
      const geometry = object.geometry;
      if (!geometries.has(geometry.uuid)) geometries.set(geometry.uuid, {
        type: geometry.type, parameters: geometry.parameters,
        attributes: Object.fromEntries(Object.entries(geometry.attributes).map(([name, attribute]) => [name, {
          count: attribute.count, itemSize: attribute.itemSize, fingerprint: bufferFingerprint(attribute.array),
        }])),
        index: geometry.index ? bufferFingerprint(geometry.index.array) : null,
      });
      state.geometry = geometry.uuid;
    }
    if (object.isInstancedMesh) {
      state.instances = { count: object.count, matrix: bufferFingerprint(object.instanceMatrix.array), color: object.instanceColor ? bufferFingerprint(object.instanceColor.array) : null };
    }
    if (object.material) {
      const list = Array.isArray(object.material) ? object.material : [object.material];
      state.materials = list.map(material => {
        if (!materials.has(material.uuid)) materials.set(material.uuid, {
          type: material.type, color: material.color?.getHex(), roughness: material.roughness,
          metalness: material.metalness, opacity: material.opacity, transparent: material.transparent,
          emissive: material.emissive?.getHex(), emissiveIntensity: material.emissiveIntensity,
          bumpScale: material.bumpScale, side: material.side, depthWrite: material.depthWrite,
          map: material.map?.uuid ?? null, bumpMap: material.bumpMap?.uuid ?? null,
        });
        for (const texture of [material.map, material.bumpMap]) if (texture && !textures.has(texture.uuid)) {
          textures.set(texture.uuid, {
            source: texture.source.uuid, width: texture.image.width, height: texture.image.height,
            wrapS: texture.wrapS, wrapT: texture.wrapT, repeat: texture.repeat.toArray(),
            offset: texture.offset.toArray(), rotation: texture.rotation, colorSpace: texture.colorSpace,
          });
        }
        return material.uuid;
      });
    }
    if (object.isLight) {
      state.color = object.color.getHex(); state.intensity = object.intensity;
      state.castShadow = object.castShadow;
      if (object.groundColor) state.groundColor = object.groundColor.getHex();
      if (object.distance !== undefined) state.distance = object.distance;
      if (object.decay !== undefined) state.decay = object.decay;
      if (object.shadow) state.shadow = {
        mapSize: object.shadow.mapSize.toArray(), radius: object.shadow.radius,
        bias: object.shadow.bias, normalBias: object.shadow.normalBias,
        near: object.shadow.camera.near, far: object.shadow.camera.far,
      };
    }
    objects.push(state);
  });
  return { objects, geometries: [...geometries], materials: [...materials], textures: [...textures], camera: getCameraState(), background: scene.background.getHex(), renderer: { exposure: renderer.toneMappingExposure, toneMapping: renderer.toneMapping, shadowType: renderer.shadowMap.type, width: WIDTH, height: HEIGHT } };
}

window.reconstruction = {
  pause() {},
  seek: render,
  setVariant,
  getCameraState,
  getInvariantState,
  getPreservationState() { return preservationState(scene, renderer, chair); },
  getCameraDiagnostics() { return cameraClearance(scene, chair, camera); },
  getFrameWorldState() { return frameWorldState(scene, chair); },
  getEditedObjectState() { return this.getChairState(); },
  getChairState() { return { position: chair.position.toArray(), quaternion: chair.quaternion.toArray() }; },
  getState() { return { time, variant }; },
};
setVariant('original');
