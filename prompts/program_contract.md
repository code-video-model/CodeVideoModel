## Prompt-synthesis contract

This is prompt synthesis, not reference reconstruction. No reference video exists.
Any top-level instructions about matching, extracting, comparing
against, or reconstructing a Reference video do not apply to this task.

Build a deterministic, fully procedural, editable Three.js scene from the
prompt. Prioritize semantic objects, camera, composition, trajectories, timing,
cuts, occlusion, and readable materials suitable as a structural Video Condition.
Use direct VLM inspection against the prompt; do not perform metric optimization.
Do not chase photorealism. Do not use external images or videos as textures,
backgrounds, billboards, overlays, masks, or any other visual input. The output
must be silent.

## Exact target

- Width: `@WIDTH@`
- Height: `@HEIGHT@`
- FPS: `@FPS@`
- Frame count: `@FRAMES@`
- Requested duration: `5.0`
- Encoded duration: `@DURATION@` (`frames / fps`)
- Frame alignment: `minimax-h3`
- Codec and pixel format: H.264 `yuv420p`

Render frame `i` at time `i / FPS`. Do not add or drop frames.

## Determinism and direct inspection

Expose:

```js
window.reconstruction = {
  pause(),
  seek(seconds)
};
```

`seek(t)` must update and render every camera, object, pose, material, light,
particle, effect, cut, and visibility state deterministically, including when
timestamps are visited out of order.

After the first complete scene, directly inspect generated keyframes and a
contact sheet against the prompt with VLM vision. Perform and record at least
these meaningful refinement passes:

1. camera and composition;
2. geometry, depth ordering, and occlusion;
3. motion, trajectories, cuts, and timing;
4. material contrast, lighting, and semantic legibility.

Re-render after each pass and inspect the result. Before completion, inspect a
contact sheet sampled across the complete encoded MP4 and fix remaining
semantic, camera, continuity, motion, occlusion, or legibility problems.

@CAMERA@

## Delivery

Pipeline-managed publication: true. This attempt must freshly render
`case/reconstruction.mp4`; do not merely reuse an old MP4. Validate JavaScript,
page loading, deterministic out-of-order seeks, silent audio, final visual
quality, and exact metadata. Stop local servers and remove temporary frame
sequences. Write `@WORK@/result.json` with `"status": "candidate"`, prompt and
target metadata, validation results, inspected timestamps, and all refinement
passes. Do not publish or copy the MP4 to the final output yourself.
