# Licensing and third-party components

Project-authored code and documentation are licensed under
[Apache License 2.0](../../LICENSE). The bundled CodeVideoBench assets listed below
and third-party components are excluded from this grant and retain their
respective licenses. File paths below are relative to the repository root.

`vendor/three.module.js` is Three.js r160. Its original copyright header and MIT
license in `vendor/LICENSE.threejs` are retained.

Copilot CLI, Playwright/Chromium, PyTorch, Diffusers, and other dependencies are
obtained separately under their respective terms. MiniMax-H3 weights are not
bundled. The H3-compatible backend is pinned to the public Hugging Face Diffusers
commit specified in `requirements.txt`; its Apache-2.0 terms remain applicable.
GPT-Image-2 is accessed through OpenRouter with the OpenAI provider;
users supply their own credentials and are responsible for API charges.

The prompt, reference image, and proxy video in `examples/chair_placement/original/`,
`examples/chair_placement/edited/`, `examples/tank_boarding/`,
`examples/robot_navigation/`, `examples/sports_car/`, and
`examples/loft_tour/` are unmodified copies from
[CodeVideoBench](https://huggingface.co/datasets/code-video-model/CodeVideoBench),
by the **CodeVideoBench contributors**. These assets are licensed under
[CC BY 4.0](CC-BY-4.0.txt). The license covers only rights the
contributors can grant, not third-party characters, trademarks, or separately
owned material.

The scene source in `examples/chair_placement/*/case/` is adapted from
CodeVideoBench under [MIT](CodeVideoBench-MIT.txt). Local runtime
imports and variant names were adapted for standalone workspaces; the scene
geometry, camera, and chair layouts are unchanged. Source license notices are
retained in the JavaScript files. Each workspace's Three.js copy retains its
upstream MIT license in `vendor/LICENSE.threejs`.

The project license does not replace these component-specific licenses or
grant rights to separately licensed model weights and services.
