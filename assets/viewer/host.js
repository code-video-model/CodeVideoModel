(() => {
  const pending = new Set();
  const request = window.requestAnimationFrame.bind(window);
  const cancel = window.cancelAnimationFrame.bind(window);
  window.__cvmErrors = [];
  window.addEventListener('error', event => window.__cvmErrors.push(event.message));
  window.addEventListener('unhandledrejection', event => window.__cvmErrors.push(String(event.reason)));
  window.requestAnimationFrame = callback => {
    const id = request(time => {
      pending.delete(id);
      callback(time);
    });
    pending.add(id);
    return id;
  };
  window.__cvmFreeze = () => {
    window.reconstruction.pause();
    // Cancel existing loops, but allow seek() to await a new animation frame.
    pending.forEach(cancel);
    pending.clear();
    window.__cvmRuntime?.renderer.setAnimationLoop(null);
  };
})();
