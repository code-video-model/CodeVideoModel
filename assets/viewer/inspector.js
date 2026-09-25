export function createInspector(initial, trajectory, stage, fail) {
  const {THREE, scene, camera, renderer} = initial;
  const view = new THREE.WebGLRenderer({antialias: true});
  view.setPixelRatio(Math.min(devicePixelRatio, 2));
  view.outputColorSpace = renderer.outputColorSpace;
  view.toneMapping = renderer.toneMapping;
  view.toneMappingExposure = renderer.toneMappingExposure;
  view.shadowMap.enabled = renderer.shadowMap.enabled;
  view.shadowMap.type = renderer.shadowMap.type;
  stage.append(view.domElement);
  const points = trajectory.map(entry => new THREE.Vector3(...entry));
  const bounds = new THREE.Box3().setFromObject(scene);
  points.forEach(point => bounds.expandByPoint(point));
  const size = Math.max(bounds.getSize(new THREE.Vector3()).length(), 1);
  const target = bounds.getCenter(new THREE.Vector3());
  const initialTarget = target.clone();
  const initialDistance = size * 1.1;
  let distance = initialDistance, azimuth = .6, elevation = .45;
  let runtime = initial;
  const observer = new THREE.PerspectiveCamera(45, 1, size / 10000, size * 30);
  const overlay = new THREE.Scene();
  const displayCamera = camera.clone(false);
  const frustum = new THREE.CameraHelper(displayCamera);
  const path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({color: 0x25bddd, depthTest: false}));
  const grid = new THREE.GridHelper(size * 1.5, 20, 0x4b99aa, 0x667d86);
  grid.position.set(target.x, bounds.min.y, target.z);
  overlay.add(frustum, path, grid);
  let disposed = false;

  function draw() {
    if (disposed) return;
    observer.position.set(
      Math.sin(azimuth) * Math.cos(elevation) * distance,
      Math.sin(elevation) * distance,
      Math.cos(azimuth) * Math.cos(elevation) * distance
    ).add(target);
    observer.lookAt(target);
    observer.updateMatrixWorld();
    displayCamera.copy(runtime.camera, false);
    runtime.camera.getWorldPosition(displayCamera.position);
    runtime.camera.getWorldQuaternion(displayCamera.quaternion);
    displayCamera.far = Math.min(runtime.camera.far, Math.max(runtime.camera.near * 2, size * .2));
    displayCamera.updateProjectionMatrix();
    displayCamera.updateMatrixWorld();
    frustum.update();
    view.toneMappingExposure = runtime.renderer.toneMappingExposure;
    observer.layers.mask = runtime.camera.layers.mask;
    view.autoClear = true;
    // Camera-relative fog must not hide the scene from the outside observer.
    const fog = runtime.scene.fog;
    try {
      runtime.scene.fog = null;
      view.render(runtime.scene, observer);
    } finally {
      runtime.scene.fog = fog;
    }
    view.autoClear = false;
    view.clearDepth();
    view.render(overlay, observer);
  }

  function redraw() {
    try {draw();}
    catch (error) {fail(error);}
  }
  function resize() {
    if (!stage.clientWidth || !stage.clientHeight || disposed) return;
    observer.aspect = stage.clientWidth / stage.clientHeight;
    observer.updateProjectionMatrix();
    view.setSize(stage.clientWidth, stage.clientHeight, false);
    redraw();
  }
  const events = new AbortController();
  const listen = (element, name, fn, options = {}) =>
    element.addEventListener(name, fn, {...options, signal: events.signal});
  let pointer = null;
  listen(stage, 'pointerdown', event => {
    pointer = {x: event.clientX, y: event.clientY};
    stage.setPointerCapture(event.pointerId);
    stage.focus();
  });
  listen(stage, 'pointermove', event => {
    if (!pointer) return;
    const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
    if (event.shiftKey || event.buttons === 2) {
      const scale = 2 * distance * Math.tan(THREE.MathUtils.degToRad(observer.fov / 2)) / stage.clientHeight;
      target.addScaledVector(new THREE.Vector3(1, 0, 0).applyQuaternion(observer.quaternion), -dx * scale);
      target.addScaledVector(new THREE.Vector3(0, 1, 0).applyQuaternion(observer.quaternion), dy * scale);
    } else {
      azimuth -= dx * .006;
      elevation = Math.max(-1.45, Math.min(1.45, elevation + dy * .006));
    }
    pointer = {x: event.clientX, y: event.clientY};
    redraw();
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    listen(stage, name, () => {pointer = null;});
  }
  listen(stage, 'contextmenu', event => event.preventDefault());
  listen(stage, 'wheel', event => {
    event.preventDefault();
    distance = Math.max(size * .01, Math.min(size * 10, distance * Math.exp(event.deltaY * .001)));
    redraw();
  }, {passive: false});
  listen(stage, 'keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'ArrowLeft') azimuth -= .1;
    if (event.key === 'ArrowRight') azimuth += .1;
    if (event.key === 'ArrowUp') elevation = Math.min(1.45, elevation + .1);
    if (event.key === 'ArrowDown') elevation = Math.max(-1.45, elevation - .1);
    redraw();
  });
  listen(document.getElementById('reset'), 'click', () => {
    target.copy(initialTarget);
    distance = initialDistance; azimuth = .6; elevation = .45;
    redraw();
  });
  for (const [id, object] of [['frustum', frustum], ['path', path], ['grid', grid]]) {
    listen(document.getElementById(id), 'change', event => {
      object.visible = event.target.checked;
      redraw();
    });
  }
  listen(view.domElement, 'webglcontextlost', event => {
    event.preventDefault();
    if (!disposed) fail(new Error('World Inspector lost its WebGL context. Reload the page.'));
  });
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  resize();
  return {
    draw(next) {runtime = next; draw();},
    dispose() {
      disposed = true;
      resizeObserver.disconnect();
      events.abort();
      frustum.dispose();
      path.geometry.dispose(); path.material.dispose();
      grid.geometry.dispose();
      for (const material of [grid.material].flat()) material.dispose();
      view.dispose();
      view.forceContextLoss();
    },
  };
}
