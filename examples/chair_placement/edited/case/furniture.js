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
import { mats, solid, random, bookMaterial } from './materials.js';
import { box, cylinder, rod, curve, group, contactShadow } from './geometry.js';

const colors = ['#1b3534', '#d7c7a0', '#46342b', '#343c34', '#ad9c6a', '#714036', '#232e39', '#c8c5ad', '#6c7766'];
const titles = ['THE NATURAL WORLD', 'ESSAYS', 'A HISTORY OF ART', 'GARDENS', 'THE COLLECTED POEMS', 'ARCHITECTURE', 'FIELD NOTES', 'MODERN DESIGN', 'LITERATURE', 'PLANTS & PEOPLE', 'ATLAS', 'LANDSCAPES'];
const bookMats = titles.map((title, i) => bookMaterial(title, colors[i % colors.length], i + 323));

function book(parent, name, x, y, z, w, h, d, index, tilt = 0) { window.__bfTrace?.add(9);
  const b = group(parent, name, x, y, z); b.rotation.z = tilt;
  box(b, 'page-block', w - .007, h - .012, d - .01, mats.pages, 0, h / 2, -.003);
  for (const xx of [-w / 2, w / 2]) box(b, 'book-cover', .005, h, d, bookMats[index % bookMats.length], xx, h / 2, 0);
  box(b, 'lettered-spine', w, h, .009, bookMats[index % bookMats.length], 0, h / 2, d / 2);
  return b;
}

function stack(parent, x, y, z, count, seed, w = .34) { window.__bfTrace?.add(17);
  const rng = random(seed);
  let height = y;
  for (let i = 0; i < count; i++) {
    const h = .022 + rng() * .026;
    const b = group(parent, 'horizontal-book', x + (rng() - .5) * .025, height, z + (rng() - .5) * .025);
    b.rotation.y = (rng() - .5) * .12;
    box(b, 'pages', w, h, .235, mats.pages, 0, h / 2, 0);
    for (const yy of [0, h]) box(b, 'cover', w + .008, .004, .245, bookMats[(seed + i) % bookMats.length], 0, yy, 0);
    box(b, 'book-spine', w, h, .008, bookMats[(seed + i) % bookMats.length], 0, h / 2, .12);
    for (let j = 0; j < 3; j++) box(b, 'page-edge', w - .01, .0009, .001, mats.paper, 0, .005 + j * h / 3, .12);
    height += h + .005;
  }
}

function paperStack(parent, x, y, z, count, seed, w = .34) { window.__bfTrace?.add(32);
  const rng = random(seed);
  for (let i = 0; i < count; i++) {
    const p = box(parent, 'loose-paper', w, .0014, .23, mats.paper, x + (rng() - .5) * .025, y + i * .0015, z + (rng() - .5) * .02);
    p.rotation.y = (rng() - .5) * .16;
  }
  for (let i = 0; i < 7; i++) box(parent, 'paper-printed-line', w * .65, .0003, .002, solid('#a49f90'), x - .018, y + count * .0015 + .0001, z - .07 + i * .013);
}

function deskLamp(parent) { window.__bfTrace?.add(41);
  const lamp = group(parent, 'silver-articulated-desk-lamp', -.4, .86, .08);
  lamp.scale.set(.9, .75, .9);
  cylinder(lamp, 'weighted-base', .105, .118, .025, mats.silver, 0, .014, 0);
  cylinder(lamp, 'base-inset', .088, .102, .012, mats.black, 0, .004, 0);
  const a = [0, .04, 0], b = [-.06, .5, 0], c = [.17, .79, -.01];
  for (const offset of [-.014, .014]) {
    rod(lamp, 'lower-arm', [a[0] + offset, a[1], a[2]], [b[0] + offset, b[1], b[2]], .007, mats.silver);
    rod(lamp, 'upper-arm', [b[0] + offset, b[1], b[2]], [c[0] + offset, c[1], c[2]], .007, mats.silver);
  }
  for (const p of [a, b, c]) {
    const joint = cylinder(lamp, 'pivot', .017, .017, .04, mats.black, ...p);
    joint.rotation.x = Math.PI / 2;
  }
  rod(lamp, 'shade-neck', c, [.23, .745, -.01], .012, mats.silver);
  const shade = group(lamp, 'bell-shade', .24, .707, -.01); shade.rotation.z = -.13;
  cylinder(shade, 'metal-shade', .034, .105, .12, mats.silver, 0, 0, 0, 40);
  cylinder(shade, 'white-reflector', .094, .094, .003, mats.paper, 0, -.061, 0);
  cylinder(shade, 'upper-socket', .025, .025, .06, mats.silver, 0, .083, 0);
  curve(lamp, 'lamp-wire', [[.21, .8, -.02], [.19, .85, -.01], [.15, .81, 0], [-.075, .49, .015], [.015, .075, .02], [.12, .015, -.13]], .003, mats.black);
}

export function makeDesk(world) {
  const desk = group(world, 'old-oak-double-pedestal-desk', .48, 0, .4);
  desk.scale.set(.8, 1.065, 1);
  contactShadow(world, 'desk-ambient-contact', .48, .49, 2.25, 1.15);
  box(desk, 'thick-overhung-desktop', 2.36, .052, .82, mats.oak, 0, .826, 0, .012);
  box(desk, 'desktop-front-lip', 2.34, .021, .03, mats.oakEdge, 0, .794, .411, .005);
  box(desk, 'rear-modesty-panel', 2.12, .64, .035, mats.dark, 0, .39, -.345);
  for (const x of [-.82, .82]) {
    const pedestal = group(desk, 'three-drawer-pedestal', x, 0, 0);
    for (const dx of [-.285, .285]) {
      box(pedestal, 'paneled-side', .04, .59, .68, mats.oakEdge, dx, .485, .005);
      box(pedestal, 'side-inset', .009, .47, .49, mats.oak, dx + Math.sign(dx) * .023, .49, .005);
      for (const z of [-.305, .34]) box(pedestal, 'square-upright-leg', .049, .783, .049, mats.oakEdge, dx, .395, z, .003);
    }
    box(pedestal, 'bottom-crossrail', .58, .043, .058, mats.oakEdge, 0, .201, .346);
    for (let i = 0; i < 3; i++) {
      const yy = .302 + i * .188;
      const drawerMaterial = mats.oak.clone();
      drawerMaterial.map = mats.oak.map.clone();
      drawerMaterial.map.offset.set(i * .173 + (x + .82) * .12, i * .27);
      drawerMaterial.map.needsUpdate = true;
      box(pedestal, 'drawer-dark-reveal', .535, .181, .026, mats.dark, 0, yy, .344);
      box(pedestal, `drawer-front-${i}`, .52, .172, .038, drawerMaterial, 0, yy, .365, .005);
      box(pedestal, 'drawer-recessed-center', .46, .124, .006, drawerMaterial, 0, yy, .387, .003);
      for (const dx of [-.06, .06]) box(pedestal, 'handle-peg', .021, .021, .023, mats.oakEdge, dx, yy, .402, .003);
      box(pedestal, 'plain-wood-pull', .195, .043, .042, mats.pull, 0, yy + .004, .424, .008);
      if (i === 2) {
        const lock = cylinder(pedestal, 'drawer-keyhole', .009, .009, .001, mats.dark, 0, yy + .061, .391, 12);
        lock.rotation.x = Math.PI / 2;
      }
    }
  }
  box(desk, 'center-pencil-drawer', .96, .095, .071, mats.oak, 0, .747, .338, .003);
  const keyhole = cylinder(desk, 'center-keyhole', .009, .009, .003, mats.silver, 0, .762, .376, 12); keyhole.rotation.x = Math.PI / 2;

  stack(desk, -.94, .855, .1, 4, 81, .35);
  paperStack(desk, -.98, 1.015, .1, 4, 73, .31);
  let bx = -.9;
  for (let i = 0; i < 15; i++) {
    const w = .033 + ((i * 11) % 5) * .009;
    book(desk, 'desktop-upright-book', bx, .856, -.24, w, .25 + ((i * 7) % 5) * .028, .17, i, i < 3 ? .012 : 0);
    bx += w + .005;
  }
  stack(desk, .37, .855, -.18, 4, 92, .33);
  deskLamp(desk);
  const monitor = group(desk, 'dark-desktop-monitor', .86, .852, -.15);
  monitor.rotation.y = -.1;
  box(monitor, 'monitor-foot', .27, .016, .17, mats.black, 0, .01, .015, .006);
  rod(monitor, 'monitor-stand', [0, .018, -.025], [0, .14, -.052], .017, mats.black);
  const panel = group(monitor, 'tilted-monitor-panel', 0, .349, -.055); panel.rotation.x = -.075;
  box(panel, 'monitor-black-bezel', .51, .365, .032, mats.black, 0, 0, 0, .009);
  box(panel, 'dark-screen', .472, .321, .001, mats.screen, 0, .006, .019, .002);
  box(panel, 'monitor-status-led', .004, .002, .002, solid('#789e89'), .201, -.173, .019);
  box(panel, 'monitor-logo', .014, .005, .002, mats.silver, 0, -.172, .019);
  const keyboard = group(desk, 'black-keyboard', .24, .859, .209); keyboard.rotation.y = -.035;
  box(keyboard, 'keyboard-case', .51, .019, .158, mats.black, 0, .01, 0, .008);
  const keymat = solid('#343c39');
  for (let row = 0; row < 5; row++) for (let col = 0; col < 17; col++) {
    box(keyboard, 'keyboard-key', .0215, .009, .02, keymat, -.235 + col * .0285, .025 - row * .0012, -.059 + row * .026, .002);
  }
  box(keyboard, 'spacebar', .13, .01, .019, keymat, -.02, .02, .065, .002);
  const mouse = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 12), mats.black);
  mouse.name = 'mouse'; mouse.scale.set(.052, .02, .075); mouse.position.set(.63, .874, .233); desk.add(mouse);
  curve(desk, 'mouse-cable', [[.63, .867, .18], [.65, .863, .12], [.52, .86, .035], [.58, .86, -.03]], .002, mats.black);
  paperStack(desk, .92, .855, .244, 12, 39, .37);
  paperStack(desk, -.21, .855, .31, 4, 62, .32);
  const sticky = box(desk, 'sticky-note', .09, .001, .076, solid('#dbd5a3'), .78, .879, .101);
  sticky.rotation.y = .2;
  curve(desk, 'monitor-cable', [[.86, .88, -.28], [.98, .71, -.35], [.68, .18, -.32], [.2, .07, -.24]], .004, mats.black);
  box(desk, 'power-strip-under-desk', .3, .034, .064, mats.trim, .35, .044, -.24, .005);
  for (let i = 0; i < 4; i++) box(desk, 'power-strip-socket', .027, .002, .028, mats.black, .24 + i * .072, .063, -.24);
}

function picture(parent, x, y, z, w, h, seed) { window.__bfTrace?.add(136);
  const p = group(parent, 'small-framed-family-picture', x, y + h / 2, z);
  box(p, 'picture-frame', w, h, .025, mats.oakEdge);
  box(p, 'picture-mat', w - .018, h - .018, .002, mats.paper, 0, 0, .014);
  box(p, 'picture-background', w - .035, h - .036, .002, solid('#5f7668'), 0, 0, .016);
  for (let i = 0; i < 3; i++) {
    const xx = (i - 1) * w * .2;
    const body = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), solid(colors[(seed + i) % colors.length]));
    body.scale.set(w * .14, h * .23, .005); body.position.set(xx, -h * .12, .021); p.add(body);
    const head = new THREE.Mesh(new THREE.SphereGeometry(h * .095, 12, 8), solid('#c09c76'));
    head.scale.z = .2; head.position.set(xx, h * .09, .021); p.add(head);
  }
}

export function makeBookshelf(world) {
  const shelf = group(world, 'tall-dark-densely-filled-bookshelf', 2.04, 0, .12);
  shelf.scale.set(1, .86, 1);
  contactShadow(world, 'bookshelf-ambient-contact', 2.04, .17, 1.5, .73);
  const width = 1.16, depth = .34;
  box(shelf, 'bookcase-back', width, 2.58, .025, mats.dark, 0, 1.3, -.155);
  for (const x of [-width / 2, width / 2]) box(shelf, 'bookcase-side', .044, 2.63, depth, mats.dark, x, 1.325, 0, .004);
  const rng = random(424);
  for (let level = 0; level < 7; level++) {
    const y = .067 + level * .414;
    box(shelf, 'shelf-board', width, .037, depth + .018, mats.dark, 0, y, .005, .003);
    if (level === 6) continue;
    let x = -.515;
    const count = level % 3 === 0 ? 12 : 10;
    for (let i = 0; i < count; i++) {
      const w = .025 + rng() * .025;
      const h = .26 + rng() * .105;
      const tilt = i > count - 3 ? -.075 - rng() * .14 : (rng() - .5) * .035;
      book(shelf, 'shelf-upright-book', x, y + .022, .01 + rng() * .025, w, h, .225 + rng() * .04, level * 7 + i, tilt);
      x += w + .009;
    }
    if (level === 2 || level === 4) {
      picture(shelf, .09, y + .022, .13, .285, .19, level);
      if (level === 2) {
        cylinder(shelf, 'small-vase', .027, .037, .105, solid('#8d8971'), .095, y + .075, .06);
        cylinder(shelf, 'vase-neck', .02, .029, .055, solid('#8d8971'), .095, y + .148, .06);
      }
    } else {
      stack(shelf, .29, y + .026, .017, level === 0 ? 6 : 4, 46 + level, .38);
      if (level !== 5) paperStack(shelf, .3, y + .214, .045, 10, 880 + level, .35);
    }
  }
}

export function makeChair(world) {
  const chair = group(world, 'chair-root');
  contactShadow(chair, 'chair-ambient-contact', 0, .01, .84, .8);
  const model = group(chair, 'shared-chair-model');
  model.scale.set(1.1, 1.14, 1.1);
  // The same local +Z-facing chair is transformed as a single rigid object.
  const wood = mats.chair;
  box(model, 'solid-wood-seat', .53, .043, .5, wood, 0, .459, 0, .013);
  for (const x of [-.222, .222]) {
    box(model, 'front-square-leg', .044, .45, .047, wood, x, .231, .205, .005);
    const rear = box(model, 'continuous-rear-post', .045, 1.018, .047, wood, x, .529, -.211, .006);
    rear.rotation.x = -.08;
    box(model, 'side-seat-apron', .031, .072, .429, wood, x, .407, 0, .003);
    box(model, 'side-low-stretcher', .025, .033, .425, wood, x, .132, 0, .003);
  }
  box(model, 'front-seat-apron', .467, .076, .035, wood, 0, .407, .207, .004);
  box(model, 'back-seat-apron', .466, .066, .032, wood, 0, .407, -.21, .003);
  box(model, 'front-cross-stretcher', .442, .031, .025, wood, 0, .149, .205, .003);
  box(model, 'rear-cross-stretcher', .442, .03, .025, wood, 0, .149, -.208, .003);
  box(model, 'back-lower-rail', .455, .063, .037, wood, 0, .542, -.219, .006);
  const top = box(model, 'solid-top-rail', .465, .1, .043, wood, 0, .959, -.25, .008); top.rotation.x = -.08;
  for (const x of [-.125, 0, .125]) {
    const slat = box(model, 'narrow-vertical-back-slat', .042, .351, .025, wood, x, .747, -.236, .005);
    slat.rotation.x = -.08;
  }
  const cushion = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), mats.fabric);
  cushion.name = 'thin-grey-striped-cushion';
  const positions = cushion.geometry.attributes.position;
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i), y = positions.getY(i), z = positions.getZ(i);
    positions.setXYZ(i, Math.sign(x) * Math.pow(Math.abs(x), .48) * .246, y * .028, Math.sign(z) * Math.pow(Math.abs(z), .48) * .226);
    cushion.geometry.attributes.uv.setXY(i, positions.getX(i) / .492 + .5, positions.getZ(i) / .452 + .5);
  }
  cushion.geometry.computeVertexNormals(); cushion.position.set(0, .5, .006);
  cushion.castShadow = cushion.receiveShadow = true; model.add(cushion);
  const seam = [];
  for (let i = 0; i <= 64; i++) {
    const a = i / 64 * Math.PI * 2, x = Math.cos(a), z = Math.sin(a);
    seam.push([Math.sign(x) * Math.pow(Math.abs(x), .45) * .246, .497, Math.sign(z) * Math.pow(Math.abs(z), .45) * .226 + .006]);
  }
  curve(model, 'cushion-piped-seam', seam, .002, solid('#777367'));
  for (const x of [-.22, .22]) {
    curve(model, 'cushion-tie', [[x * .85, .49, -.18], [x, .481, -.232], [x + .016, .481, -.245], [x + .02, .46, -.23], [x, .472, -.228], [x - .019, .455, -.211]], .0019, mats.fabric);
  }
  return chair;
}
