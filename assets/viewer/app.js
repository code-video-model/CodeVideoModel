import {createInspector} from './inspector.js';

const $ = id => document.getElementById(id);
const host = $('scene-host');
let config, child, api, inspector, observer;
let current = 0, playing = false, animation = 0, stopped = false;
let requested = null, seeking = false, sourceRequest;

function pause() {
  playing = false;
  cancelAnimationFrame(animation);
  $('play').textContent = 'Play';
}
function dispose() {
  if (stopped) return;
  pause();
  stopped = true;
  sourceRequest?.abort();
  observer?.disconnect();
  inspector?.dispose();
  host.remove();
}
function fail(error) {
  if (stopped) return;
  $('status').hidden = false;
  $('status').className = 'error';
  $('status').textContent = `Unable to display scene: ${error.message}`;
  document.querySelectorAll('button, input, select').forEach(element => {element.disabled = true;});
  dispose();
}
function runtime() {
  if (child.__cvmErrors?.length) throw new Error(child.__cvmErrors.join('; '));
  if (!child.__cvmRuntime) {
    throw new Error('No Three.js renderer found. Import the workspace vendor/three.module.js.');
  }
  return child.__cvmRuntime;
}
async function draw(frame) {
  await api.seek(frame / config.fps);
  if (stopped) return;
  inspector.draw(runtime());
  current = frame;
  $('timeline').value = String(frame);
  $('frame-label').textContent = `Frame ${frame} / ${config.frames - 1}`;
  $('time-label').textContent = `${(frame / config.fps).toFixed(3)} / ${((config.frames - 1) / config.fps).toFixed(3)} s`;
}
async function seek(frame) {
  requested = Math.max(0, Math.min(config.frames - 1, Math.round(frame)));
  if (seeking || stopped) return;
  seeking = true;
  try {
    // Coalesce slider events; asynchronous seek implementations must never overlap.
    while (requested !== null && !stopped) {
      const next = requested;
      requested = null;
      await draw(next);
    }
  } catch (error) {fail(error);}
  finally {seeking = false;}
}
function play() {
  if (playing) {pause(); return;}
  if (stopped) return;
  playing = true;
  $('play').textContent = 'Pause';
  const first = current === config.frames - 1 ? 0 : current;
  const start = performance.now() - first / config.fps * 1000;
  function tick(now) {
    if (!playing || stopped) return;
    const frame = Math.min(config.frames - 1, Math.floor((now - start) / 1000 * config.fps));
    seek(frame);
    if (frame === config.frames - 1) {pause(); return;}
    animation = requestAnimationFrame(tick);
  }
  animation = requestAnimationFrame(tick);
}
async function loadSource() {
  sourceRequest?.abort();
  const request = new AbortController();
  sourceRequest = request;
  $('source-code').textContent = 'Loading source...';
  try {
    const name = $('source-file').value.split('/').map(encodeURIComponent).join('/');
    const response = await fetch(`_viewer/source/${name}`, {signal: request.signal});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const text = await response.text();
    request.signal.throwIfAborted();
    const lines = text.split('\n').map((value, index) => {
      const line = document.createElement('span');
      line.className = 'code-line';
      const number = document.createElement('span');
      number.className = 'line-number';
      number.textContent = index + 1;
      line.append(number, document.createTextNode(value));
      return line;
    });
    $('source-code').replaceChildren(...lines);
    $('source-code').scrollTop = 0;
  } catch (error) {
    if (request.signal.aborted) return;
    $('source-code').textContent = `Unable to load source: ${error.message}`;
  }
}
async function init() {
  const response = await fetch('_viewer/config.json');
  if (!response.ok) throw new Error(`Workspace settings: HTTP ${response.status}`);
  config = await response.json();
  $('scene-name').textContent = config.title;
  document.title = `${config.title} / Scene Viewer`;
  $('timeline').max = config.frames - 1;
  $('camera-stage').style.aspectRatio = `${config.width} / ${config.height}`;
  host.width = config.width;
  host.height = config.height;
  observer = new ResizeObserver(() => {
    host.style.transform = `scale(${$('camera-stage').clientWidth / config.width})`;
  });
  observer.observe($('camera-stage'));
  $('source-file').replaceChildren(...config.sources.map(name => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name.replace(/^case\//, '');
    return option;
  }));
  $('source-file').value = config.sources.find(name => /\/(main|scene|app)\.js$/.test(name)) || config.sources[0];
  loadSource();
  host.src = 'case/index.html';
  const start = performance.now();
  while (!stopped) {
    child = host.contentWindow;
    if (child.__cvmErrors?.length) throw new Error(child.__cvmErrors.join('; '));
    if (child.reconstruction?.seek && child.reconstruction?.pause && child.__cvmFreeze) break;
    if (performance.now() - start > 30000) {
      throw new Error('Scene timed out. It must expose reconstruction.pause() and seek(seconds).');
    }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  if (stopped) return;
  api = child.reconstruction;
  child.__cvmFreeze();
  $('status').textContent = 'Preparing camera path...';
  const trajectory = [];
  for (let frame = 0; frame < config.frames; frame++) {
    await api.seek(frame / config.fps);
    if (stopped) return;
    const {THREE, camera} = runtime();
    trajectory.push(camera.getWorldPosition(new THREE.Vector3()).toArray());
    if (frame % 16 === 0) await new Promise(resolve => setTimeout(resolve, 0));
  }
  await api.seek(0);
  if (stopped) return;
  inspector = createInspector(runtime(), trajectory, $('world-stage'), fail);
  await draw(0);
  if (stopped) return;
  document.querySelectorAll('button, input, select').forEach(element => {element.disabled = false;});
  $('status').hidden = true;
}
$('play').addEventListener('click', play);
$('timeline').addEventListener('input', event => {pause(); seek(event.target.valueAsNumber);});
$('previous').addEventListener('click', () => {pause(); seek(current - 1);});
$('next').addEventListener('click', () => {pause(); seek(current + 1);});
$('source-file').addEventListener('change', loadSource);
document.addEventListener('visibilitychange', () => {if (document.hidden) pause();});
window.addEventListener('pagehide', dispose);
window.addEventListener('pageshow', event => {if (event.persisted) location.reload();});
init().catch(fail);
