import * as THREE from '../_viewer/three.js';
export * from '../_viewer/three.js';

// This facade is served in memory; the workspace's Three.js file stays untouched.
export class WebGLRenderer extends THREE.WebGLRenderer {
  constructor(...args) {
    super(...args);
    const render = this.render.bind(this);
    this.render = (scene, camera) => {
      if (scene.isScene && camera.isCamera && this.getRenderTarget() === null) {
        window.__cvmRuntime = {THREE, scene, camera, renderer: this};
      }
      return render(scene, camera);
    };
  }
}
