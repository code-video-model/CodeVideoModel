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
function fingerprint(array) { window.__bfTrace?.add(1);
  const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
  let hash = 2166136261;
  for (const byte of bytes) hash = Math.imul(hash ^ byte, 16777619) >>> 0;
  return { bytes: bytes.length, fnv1a: hash.toString(16).padStart(8, '0') };
}

export function preservationState(scene, renderer, chair) {
  const nodes = [], geometries = new Map(), materials = new Map(), textures = new Map(), images = new Map();
  const nodeIds = new Map();
  scene.traverse(node => nodeIds.set(node, nodeIds.size));
  function textureState(texture) {
    if (!textures.has(texture)) {
      const image = texture.image;
      if (image && !images.has(image)) {
        let pixels = image.data;
        if (image.getContext) {
          // Read through a CPU-backed copy so repeated audits never migrate the source canvas.
          const copy = document.createElement('canvas');
          copy.width = image.width; copy.height = image.height;
          const context = copy.getContext('2d', { willReadFrequently: true });
          context.drawImage(image, 0, 0);
          pixels = context.getImageData(0, 0, copy.width, copy.height).data;
        }
        if (!pixels) throw new Error(`Unsupported audit image for ${texture.name}`);
        images.set(image, { width: image.width, height: image.height, pixels: fingerprint(pixels) });
      }
      const state = { image: image ? [...images.keys()].indexOf(image) : null };
      for (const key of ['mapping', 'channel', 'wrapS', 'wrapT', 'magFilter', 'minFilter', 'anisotropy', 'format', 'type', 'rotation', 'matrixAutoUpdate', 'generateMipmaps', 'premultiplyAlpha', 'flipY', 'unpackAlignment', 'colorSpace']) state[key] = texture[key];
      for (const key of ['offset', 'repeat', 'center', 'matrix']) state[key] = texture[key].toArray();
      // Auto-updated UV matrices are lazy renderer caches; compare their authored transform.
      if (texture.matrixAutoUpdate) state.matrix = texture.matrix.clone().setUvTransform(
        texture.offset.x, texture.offset.y, texture.repeat.x, texture.repeat.y,
        texture.rotation, texture.center.x, texture.center.y
      ).toArray();
      textures.set(texture, state);
    }
    return [...textures.keys()].indexOf(texture);
  }
  function materialState(material) {
    if (!materials.has(material)) {
      const state = {};
      for (const [key, value] of Object.entries(material)) {
        if (['uuid', 'id', 'version', '_listeners'].includes(key)) continue;
        if (value?.isTexture) state[key] = { texture: textureState(value) };
        else if (value?.toArray) state[key] = value.toArray();
        else if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) state[key] = value;
        else if (Array.isArray(value) || key === 'userData') state[key] = value;
      }
      materials.set(material, state);
    }
    return [...materials.keys()].indexOf(material);
  }
  scene.traverse(node => {
    const state = {
      name: node.name, type: node.type, parent: nodeIds.get(node.parent) ?? null,
      position: node.position.toArray(), quaternion: node.quaternion.toArray(), scale: node.scale.toArray(),
      visible: node.visible, castShadow: node.castShadow, receiveShadow: node.receiveShadow,
      layers: node.layers.mask, renderOrder: node.renderOrder, frustumCulled: node.frustumCulled,
      matrixAutoUpdate: node.matrixAutoUpdate, userData: node.userData,
    };
    if (node.geometry) {
      const geometry = node.geometry;
      if (!geometries.has(geometry)) {
        const attributes = {};
        for (const [key, attribute] of Object.entries(geometry.attributes)) attributes[key] = {
          itemSize: attribute.itemSize, count: attribute.count, normalized: attribute.normalized,
          arrayType: attribute.array.constructor.name, buffer: fingerprint(attribute.array),
        };
        geometries.set(geometry, {
          type: geometry.type, parameters: geometry.parameters, attributes,
          index: geometry.index ? fingerprint(geometry.index.array) : null,
          groups: geometry.groups, drawRange: { start: geometry.drawRange.start, count: Number.isFinite(geometry.drawRange.count) ? geometry.drawRange.count : 'Infinity' },
        });
      }
      state.geometry = [...geometries.keys()].indexOf(node.geometry);
    }
    if (node.material) state.materials = (Array.isArray(node.material) ? node.material : [node.material]).map(materialState);
    if (node.isInstancedMesh) state.instances = {
      count: node.count, matrix: fingerprint(node.instanceMatrix.array),
      color: node.instanceColor ? fingerprint(node.instanceColor.array) : null,
    };
    if (node.isLight) {
      state.light = { color: node.color.toArray(), intensity: node.intensity };
      for (const key of ['distance', 'decay', 'angle', 'penumbra']) if (key in node) state.light[key] = node[key];
      if (node.groundColor) state.light.groundColor = node.groundColor.toArray();
      if (node.target) state.light.target = node.target.position.toArray();
      if (node.shadow) {
        state.light.shadow = {};
        for (const key of ['bias', 'normalBias', 'radius', 'blurSamples', 'intensity', 'autoUpdate']) state.light.shadow[key] = node.shadow[key];
        state.light.shadow.mapSize = node.shadow.mapSize.toArray();
        state.light.shadow.camera = {};
        for (const key of ['near', 'far', 'left', 'right', 'top', 'bottom', 'fov']) if (key in node.shadow.camera) state.light.shadow.camera[key] = node.shadow.camera[key];
      }
    }
    nodes.push(state);
  });
  return {
    nodes, chairNode: nodeIds.get(chair), geometries: [...geometries.values()],
    materials: [...materials.values()], textures: [...textures.values()], images: [...images.values()],
    background: scene.background.getHex(),
    renderer: { exposure: renderer.toneMappingExposure, toneMapping: renderer.toneMapping, colorSpace: renderer.outputColorSpace, shadows: renderer.shadowMap.enabled, shadowType: renderer.shadowMap.type, width: renderer.domElement.width, height: renderer.domElement.height },
  };
}
