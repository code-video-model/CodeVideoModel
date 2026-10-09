<div align="center">

<h1>Code Video Model</h1>

<p>
<b>Code Video Model Team</b>
</p>

<p>
<img src="assets/badges/tech-report.svg" alt="Tech Report" height="20">
<a href="https://code-video-model.github.io/"><img src="assets/badges/project-page.svg" alt="Project Page" height="20"></a>
<a href="https://huggingface.co/datasets/code-video-model/CodeVideoBench"><img src="assets/badges/hugging-face.svg" alt="Hugging Face" height="20"></a>
<a href="https://github.com/code-video-model/CodeVideoModel"><img src="assets/badges/code.svg" alt="GitHub Code" height="20"></a>
<a href="LICENSE"><img src="assets/badges/code-license.svg" alt="Code License: Apache 2.0" height="20"></a>
<a href="examples/LICENSES/CC-BY-4.0.txt"><img src="assets/badges/examples-license.svg" alt="Examples License: CC BY 4.0" height="20"></a>
</p>

</div>

## Demo Video

<div align="center">

<a href="https://code-video-model.github.io/static/demo/Demo_CodeVideoModel_New.mp4">
  <img src="https://code-video-model.github.io/static/images/first-frames-native/f3259741b723aa48ea56dfe6dee81a9673e6bcab06b64b840e48a396d2ff528f-frame000030.webp" alt="Code Video Model demo video" width="100%">
</a>

<p>
  <a href="https://code-video-model.github.io/static/demo/Demo_CodeVideoModel_New.mp4"><b>▶ Watch the demo video</b></a>
  &nbsp;·&nbsp;
  <a href="https://code-video-model.github.io/">Project Page</a>
</p>

</div>

## Installation

Use Ubuntu 22.04 and a CUDA 12.6-compatible NVIDIA driver for MiniMax-H3.

```bash
git clone https://github.com/code-video-model/CodeVideoModel.git
cd CodeVideoModel

conda create -n cvm python=3.10 -y
conda activate cvm
conda install -c conda-forge "ffmpeg[version='>=6',build='gpl_*']" -y
python -m pip install --upgrade pip
python -m pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The Three.js stage uses GPT-6. For GPT-Image-2, set `OPENROUTER_API_KEY` securely in
your environment.

### Checkpoint

Download the [MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) checkpoint:

```bash
python download_h3.py --output models/MiniMax-H3-ref2va
```

## Quick Start

Each demo bundles a prompt, a reference image, and a Three.js video,
ready for direct generation with MiniMax-H3.

| Example | Directory under `examples/` |
|---|---|
| Sports Car | [`sports_car`](examples/sports_car) |
| Tank Boarding | [`tank_boarding`](examples/tank_boarding) |
| Loft Tour | [`loft_tour`](examples/loft_tour) |
| Robot Navigation | [`robot_navigation`](examples/robot_navigation) |

Set `example` to any directory name above:

```bash
example=tank_boarding
python -m inference.generate_video \
  --code-video "examples/${example}/code_video.mp4" \
  --reference-image "examples/${example}/reference.png" \
  --prompt-file "examples/${example}/prompt.txt" \
  --model-root models/MiniMax-H3-ref2va \
  --keep-steps 5 \
  --output "outputs/${example}.mp4"
```

## Inference

### 1. Text → Three.js Codebase

Generate an editable scene from a text prompt. GPT-6 builds the codebase and
refines it through direct visual review:

```bash
python -m inference.generate_threejs \
  --prompt "A red car follows a curved road through a sunlit town, with a smooth tracking camera." \
  --output outputs/threejs
```

The generated scene files are saved in the output workspace's case directory.
Prompts can be entered directly or read from a text file.

**Export the video:**

```bash
python -m inference.render video --scene outputs/threejs
```

**View the scene** in your browser:

```bash
python -m inference.viewer --scene outputs/threejs --port 8000
```

Open the local URL printed in the terminal. Play or scrub the timeline, step
through frames, and select a source file to read its code. In the World Inspector,
drag to orbit, Shift-drag to pan, and scroll to zoom; toggle the camera frustum,
trajectory, and grid.

### 2. Three.js Video → Reference Image

**Strict alignment**

Extract the video's first frame and use GPT-Image-2 to create a
1536×864 reference, with instructions to preserve the scene's composition and content:

```bash
python -m inference.generate_reference \
  --video outputs/threejs/case/reconstruction.mp4 \
  --output outputs/threejs/reference.png
```

You can also provide an already extracted frame instead of a video.

**Text-guided reference**

Use the first frame as loose visual context and a text prompt to guide the
result, without requiring the same camera, composition, or object placement:

```bash
python -m inference.generate_reference_guided \
  --video examples/loft_tour/code_video.mp4 \
  --prompt "A sunlit modern loft with a leather sofa and floating stairs, photographed at eye level." \
  --output outputs/loft_reference_guided.png
```

This mode also accepts an extracted frame and a scene description loaded from
a text file. It produces a 1536×864 reference image.

### 3. Three.js Video + Reference Image → MiniMax-H3 Video

Generate a video using the proxy, reference image, and original scene prompt:

```bash
python -m inference.generate_video \
  --code-video outputs/threejs/case/reconstruction.mp4 \
  --reference-image outputs/threejs/reference.png \
  --prompt-file outputs/threejs/prompt.txt \
  --model-root models/MiniMax-H3-ref2va \
  --keep-steps 5 \
  --output outputs/threejs/video.mp4
```

### Create a pair

Both
[original](examples/chair_placement/original) and
[edited](examples/chair_placement/edited) workspaces include scene code, a proxy
video, a reference image, and a prompt. Generate a new edited result from the
provided original:

```bash
python -m inference.generate_pair \
  --prompt-file examples/chair_placement/edited/prompt.txt \
  --anchor examples/chair_placement/original \
  --edit-file examples/chair_placement/edit.txt \
  --pair-type scene \
  --model-root models/MiniMax-H3-ref2va \
  --output outputs/chair_placement
```

## Benchmark

[**Download on Hugging Face**](https://huggingface.co/datasets/code-video-model/CodeVideoBench).
CodeVideoBench provides 22 cases across eight applications, with editable Three.js
programs, proxy videos, reference images, prompts, and a browser-based viewer.

```bash
python -m pip install huggingface_hub
hf download code-video-model/CodeVideoBench \
  --repo-type dataset \
  --local-dir data/CodeVideoBench
```

To browse the gallery and inspect the prepared scenes:

```bash
python -m http.server 8001 --bind 127.0.0.1 --directory data/CodeVideoBench
```

To run a prepared case with H3, use
`Cases/<case_id>/code_video.mp4`, `reference.png`, and `prompt.txt` as the three
inputs in Inference 3.

### Evaluation

Evaluate **Structure**, **Style**, and **Quality** with Qwen3.8-27B through
OpenRouter. Set `OPENROUTER_API_KEY` in your environment, then run:

```bash
python evaluate_video.py \
  --video outputs/sports_car.mp4 \
  --code-video examples/sports_car/code_video.mp4 \
  --reference-image examples/sports_car/reference.png \
  --prompt-file examples/sports_car/prompt.txt \
  --output outputs/sports_car_evaluation
```

The script makes one request per dimension and saves scores.

## Citation

If you find this repository useful, please cite:

```bibtex
% Citation coming soon.
```
