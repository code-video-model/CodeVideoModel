## Required camera trajectory

Expose `window.reconstruction.getCameraState()` returning the active camera's
`position`, `quaternion`, and finite numeric `fov` after every `seek(t)`.
Write `@WORK@/case/camera_trajectory.json` as a JSON object with exact top-level
`width`, `height`, `fps`, and `frames` metadata plus a `trajectory` array.
The array must contain exactly @FRAMES@ entries, in frame order,
each shaped as `{"frame": i, "time": i / @FPS@,
"position": [x,y,z], "quaternion": [x,y,z,w], "fov": number}`. Sample each
entry only after seeking and reading `getCameraState()`. All values must be
finite and metadata must exactly match the target.
