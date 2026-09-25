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

export function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function canvasTexture(size, draw) { window.__bfTrace?.add(11);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  draw(canvas.getContext('2d'), size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

function woodTexture(seed, dark = false) { window.__bfTrace?.add(22);
  const rng = random(seed);
  return canvasTexture(768, (ctx, n) => {
    ctx.fillStyle = dark ? '#40372a' : '#a77c4f';
    ctx.fillRect(0, 0, n, n);
    for (let i = 0; i < 2100; i++) {
      const y = rng() * n;
      const light = rng() > .55;
      ctx.strokeStyle = light ? `rgba(220,176,108,${.02 + rng() * .10})` : `rgba(49,29,14,${.025 + rng() * .14})`;
      ctx.lineWidth = .3 + rng() * 2;
      const wave = 1 + rng() * 7;
      const phase = rng() * 7;
      ctx.beginPath();
      for (let x = 0; x <= n; x += 8) {
        const yy = y + Math.sin(x * .009 + phase) * wave + Math.sin(x * .03 + phase) * 1.3;
        if (x === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    }
    for (let i = 0; i < 6000; i++) {
      ctx.fillStyle = `rgba(26,14,5,${rng() * .14})`;
      ctx.fillRect(rng() * n, rng() * n, rng() * 5 + .5, .6);
    }
    for (let i = 0; i < 3; i++) {
      const x = rng() * n, y = rng() * n;
      for (let j = 1; j < 14; j++) {
        ctx.strokeStyle = `rgba(35,18,9,${.16 - j * .008})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(x, y, j * 9, j * 1.1, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  });
}

export const oakMap = woodTexture(71);
export const darkMap = woodTexture(25, true);
const plasterMap = canvasTexture(512, (ctx, n) => {
  const rng = random(839);
  ctx.fillStyle = '#d8c4a0';
  ctx.fillRect(0, 0, n, n);
  for (let i = 0; i < 48000; i++) {
    ctx.fillStyle = rng() > .5 ? 'rgba(255,249,224,.08)' : 'rgba(72,52,33,.035)';
    ctx.fillRect(rng() * n, rng() * n, 1 + rng() * 2, .5 + rng());
  }
});
plasterMap.repeat.set(4, 3);

const cushionMap = canvasTexture(512, (ctx, n) => {
  const rng = random(189);
  ctx.fillStyle = '#c0b8a8';
  ctx.fillRect(0, 0, n, n);
  for (let x = 0; x < n; x += 38) {
    ctx.fillStyle = '#777a76'; ctx.fillRect(x, 0, 4, n);
    ctx.fillStyle = '#e1d9c5'; ctx.fillRect(x + 6, 0, 9, n);
    ctx.fillStyle = '#90918b'; ctx.fillRect(x + 18, 0, 2, n);
    ctx.fillRect(x + 24, 0, 2, n);
  }
  for (let i = 0; i < 43000; i++) {
    ctx.fillStyle = rng() > .5 ? 'rgba(255,255,241,.16)' : 'rgba(32,32,31,.10)';
    ctx.fillRect(rng() * n, rng() * n, 1.5, .5);
  }
});

export const mats = {
  oak: new THREE.MeshStandardMaterial({ map: oakMap, color: '#d3c0a1', roughness: .64 }),
  oakEdge: new THREE.MeshStandardMaterial({ map: oakMap, color: '#cbbb9b', roughness: .68 }),
  pull: new THREE.MeshStandardMaterial({ map: oakMap, color: '#ead7b3', roughness: .63 }),
  chair: new THREE.MeshStandardMaterial({ map: oakMap, color: '#a99572', roughness: .66 }),
  dark: new THREE.MeshStandardMaterial({ map: darkMap, color: '#958068', roughness: .67 }),
  plaster: new THREE.MeshStandardMaterial({ map: plasterMap, bumpMap: plasterMap, bumpScale: .015, roughness: .97 }),
  trim: new THREE.MeshStandardMaterial({ color: '#e0d9c4', roughness: .62 }),
  black: new THREE.MeshStandardMaterial({ color: '#161c1b', roughness: .58 }),
  screen: new THREE.MeshBasicMaterial({ color: '#122124' }),
  silver: new THREE.MeshStandardMaterial({ color: '#a9aaa2', roughness: .3, metalness: .78 }),
  paper: new THREE.MeshStandardMaterial({ color: '#e8e1ce', roughness: .9 }),
  pages: new THREE.MeshStandardMaterial({ color: '#c5bda6', roughness: .96 }),
  terracotta: new THREE.MeshStandardMaterial({ color: '#a55f38', roughness: .9 }),
  soil: new THREE.MeshStandardMaterial({ color: '#2b2017', roughness: 1 }),
  fabric: new THREE.MeshStandardMaterial({ map: cushionMap, roughness: 1, bumpMap: cushionMap, bumpScale: .006 }),
};
for (const material of [mats.oak, mats.oakEdge, mats.pull, mats.chair, mats.dark]) material.userData.wood = true;

export function solid(color, roughness = .8) {
  return new THREE.MeshStandardMaterial({ color, roughness });
}

export function bookMaterial(title, color, seed) {
  const map = canvasTexture(256, (ctx, n) => {
    const rng = random(seed);
    ctx.fillStyle = color; ctx.fillRect(0, 0, n, n);
    for (let i = 0; i < 4500; i++) {
      ctx.fillStyle = `rgba(200,193,168,${rng() * .15})`;
      ctx.fillRect(rng() * n, rng() * n, 1, 1);
    }
    ctx.fillStyle = '#d6cba5';
    ctx.fillRect(14, 20, 228, 2); ctx.fillRect(14, 232, 228, 2);
    ctx.save(); ctx.translate(n / 2, n / 2); ctx.rotate(-Math.PI / 2);
    ctx.font = '17px Georgia'; ctx.textAlign = 'center';
    ctx.fillText(title, 0, -5, 182);
    ctx.font = '10px Georgia'; ctx.fillText('SELECTED WORKS', 0, 21, 160);
    ctx.restore();
  });
  return new THREE.MeshStandardMaterial({ map, roughness: .88 });
}
