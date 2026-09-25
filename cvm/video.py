"""MiniMax-H3: persistent image conditioning, early-only proxy conditioning."""
from dataclasses import dataclass
import gc
import hashlib

import numpy as np
from PIL import Image
import torch

from . import WIDTH, HEIGHT, FPS, FRAMES, STEPS, KEEP_STEPS, SEED, check_video

STYLE_REFERENCE = (
    "The provided image condition is a visual style reference. "
    "Transfer its color palette, lighting, texture, material treatment, rendering medium, "
    "and overall aesthetic to the generated video. Do not copy the image's exact composition, "
    "object identity, pose, or spatial layout; follow the main prompt for content and action."
)


def stream_seed(seed, stream, step=-1):
    # Stream IDs determine the CPU float32 noise sequence.
    value = f"{int(seed)}:{step}:0:{stream}".encode("ascii")
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big") % (2**63 - 1)


def advance(sample, velocity, timestep, sigma, sigma_next):
    """Data-ward H3 integration without resetting scheduler state."""
    if sample.shape != velocity.shape:
        raise ValueError("State and velocity shapes differ.")
    s, sn = float(sigma.item()), float(sigma_next.item())
    if not 0 <= sn < s <= 1:
        raise ValueError("Invalid H3 sigma interval.")
    t = torch.as_tensor(timestep, device=sample.device, dtype=sample.dtype)
    denoised = sample + (1.0 - t) * velocity
    dtype = torch.float32 if sample.dtype in (torch.float16, torch.bfloat16) else sample.dtype
    ratio = torch.as_tensor(sn / s, device=sample.device, dtype=dtype)
    return (ratio * sample.to(dtype) + (1.0 - ratio) * denoised.to(dtype)).to(sample.dtype)


def unpatchify(rows, shape, patch):
    _, channels, frames, height, width = shape
    pt, ph, pw = patch
    expected = ((frames // pt) * (height // ph) * (width // pw), channels * pt * ph * pw)
    if tuple(rows.shape) != expected:
        raise ValueError(f"Invalid packed video shape: {tuple(rows.shape)} != {expected}")
    return rows.reshape(1, frames // pt, height // ph, width // pw, channels, pt, ph, pw
                        ).permute(0, 4, 1, 5, 2, 6, 3, 7).reshape(shape).contiguous()


@dataclass
class Condition:
    embeds: torch.Tensor
    layout: dict
    rows: torch.Tensor


class H3:
    def __init__(self, text_device, generation_device):
        def device(value):
            d = torch.device(value)
            return torch.device("cuda", 0) if d.type == "cuda" and d.index is None else d
        self.text_device, self.device = device(text_device), device(generation_device)
        self.managers = []

    def load(self, model_root):
        from diffusers import ComponentsManager, ModularPipeline
        encoder = ModularPipeline.from_pretrained(str(model_root)).blocks.get_workflow(
            "t2va").sub_blocks["text_encoder"]
        workflow = ModularPipeline.from_pretrained(str(model_root)).blocks.get_workflow("ref2va")
        workflow.sub_blocks.pop("before_encode")
        workflow.sub_blocks.pop("text_encoder")
        text_manager = ComponentsManager()
        self.managers.append(text_manager)
        text_manager.enable_auto_cpu_offload(device=str(self.text_device), memory_reserve_margin="4GB")
        self.conditioner = encoder.init_pipeline(str(model_root), components_manager=text_manager)
        self.conditioner.load_components(dtype=torch.bfloat16)
        generation_manager = ComponentsManager()
        self.managers.append(generation_manager)
        generation_manager.enable_auto_cpu_offload(device=str(self.device), memory_reserve_margin="16GB")
        self.generation = workflow.init_pipeline(str(model_root), components_manager=generation_manager)
        self.generation.load_components(dtype=torch.bfloat16)
        self.transformer = generation_manager.get_one(name="transformer_ref")

    def encode_pixels(self, pixels):
        from diffusers.modular_pipelines.minimax_h3.encoders import encode_vae_condition
        g = self.generation
        return encode_vae_condition(g.vae, pixels, g.pixel_mean, g.pixel_std,
                                    encode_seed=42).to(self.device, torch.float32)

    def proxy(self, path):
        from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3VideoReference
        from diffusers.modular_pipelines.minimax_h3.before_encoder import MiniMaxH3Ref2VASetupStep
        g = self.generation
        video = MiniMaxH3VideoReference.from_file(path)
        frames = MiniMaxH3Ref2VASetupStep._normalize_video_condition(
            video.frames, float(video.fps), 2**31 - 1, g.canvas_multiple,
            min(HEIGHT, WIDTH), HEIGHT * WIDTH, g.fps)
        if frames.shape != (FRAMES, HEIGHT, WIDTH, 3):
            raise ValueError("The normalized proxy does not match the H3 canvas and frame count.")
        pixels = torch.from_numpy(frames).to(self.device).permute(3, 0, 1, 2)[None]
        ref = MiniMaxH3VideoReference(frames=frames, fps=float(g.fps), audio=None, sample_rate=None)
        return ref, self.encode_pixels(pixels)

    def image(self, path):
        from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3ImageReference
        with Image.open(path) as source:
            image = source.convert("RGB")
        w, h = image.size
        if w > 4 * h or h > 4 * w:
            raise ValueError("Image aspect ratio must be within 1:4 and 4:1.")
        g = self.generation
        scale = int(g.config.get("reference_image_short_edge", 2048)) / min(w, h)
        m = g.canvas_multiple
        size = (max(m, round(w * scale / m) * m), max(m, round(h * scale / m) * m))
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        pixels = torch.from_numpy(np.array(image)).to(self.device).permute(2, 0, 1)[None, :, None]
        return MiniMaxH3ImageReference(image=image), self.encode_pixels(pixels)

    def reference_rows(self, latent, seed):
        from diffusers.modular_pipelines.minimax_h3.before_denoise import patchify_video_latents
        noise = torch.randn(latent.shape, generator=torch.Generator(device="cpu").manual_seed(seed),
                            dtype=torch.float32).to(self.device)
        g = self.generation
        noised = g.scheduler.scale_noise(latent, g.keyframe_noise_aug, noise)
        return patchify_video_latents(noised, g.patch_size)

    def condition(self, prompt, refs, latents, rows, geometry):
        from diffusers.modular_pipelines.minimax_h3.encoders import (
            MiniMaxH3Ref2VATextEncoderStep, get_qwen3vl_prompt_embeds)
        from diffusers.modular_pipelines.minimax_h3.before_denoise import MiniMaxH3Ref2VAPrepareLayoutStep
        c, g = self.conditioner, self.generation
        block = MiniMaxH3Ref2VATextEncoderStep(video_sample_fps=2.0)
        vision, images, videos, timestamps = block._gather_vision_features(c.processor, refs, c.fps)
        ids, tags = block._build_presentation(
            c.tokenizer, prompt, refs, images, videos, timestamps,
            text_tag=c.text_tag, video_tag=c.video_tag)
        embeds = get_qwen3vl_prompt_embeds(
            c.text_encoder, c.processor, ids, vision, text_encoder_layer=c.text_encoder_layer,
            device=c._execution_device, dtype=c.text_encoder.dtype)
        packed = MiniMaxH3Ref2VAPrepareLayoutStep.build_ref2va_packed_sequence(
            torch.tensor(tags, dtype=torch.long), refs, latents, [], *geometry,
            g.patch_size, g.audio_channels, g.audio_tag, g.video_tag)
        positions, token_tags, video_indices, audio_indices, text_indices, nv, na = packed
        if na or nv != rows.shape[0]:
            raise ValueError("Reference rows and packed layout disagree.")
        layout = dict(position_ids=positions, token_tags=token_tags, video_indices=video_indices,
                      audio_indices=audio_indices, text_indices=text_indices)
        return Condition(embeds.to(self.device), {k: v.to(self.device) for k, v in layout.items()}, rows)

    def predict(self, condition, video, audio, video_t, audio_t):
        from diffusers.modular_pipelines.minimax_h3.before_denoise import MiniMaxH3SetTimestepsStep
        layout, count = condition.layout, condition.rows.shape[0]
        timesteps, indices = MiniMaxH3SetTimestepsStep.build_row_timesteps(
            layout["video_indices"], layout["audio_indices"], count, 0,
            layout["text_indices"].numel(), video_t, audio_t,
            max(video_t, self.generation.keyframe_noise_aug), 1.0)
        packed = torch.cat([condition.rows, video])
        if packed.shape[0] != layout["video_indices"].numel() or audio.shape[0] != layout["audio_indices"].numel():
            raise ValueError("Model inputs and packed layout disagree.")
        vp, ap = self.transformer(
            hidden_states=packed[None], audio_hidden_states=audio[None],
            encoder_hidden_states=condition.embeds, timestep=timesteps.to(self.device),
            timestep_indices=indices.to(self.device), **layout, return_dict=False)
        return vp[0, count:].float(), ap[0].float()

    def decode(self, video, audio, audio_frames):
        g = self.generation
        mean = torch.tensor(g.vae.config.latents_mean, device=self.device).view(1, -1, 1, 1, 1)
        std = torch.tensor(g.vae.config.latents_std, device=self.device).view(1, -1, 1, 1, 1)
        with torch.autocast(device_type=self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"):
            frames = g.vae.decode(video * std + mean, return_dict=False)[0]
        pixel_mean = torch.tensor(g.pixel_mean, device=self.device).view(1, -1, 1, 1, 1)
        pixel_std = torch.tensor(g.pixel_std, device=self.device).view(1, -1, 1, 1, 1)
        frames = g.video_processor.postprocess_video(
            (frames.float() * pixel_std + pixel_mean).clamp(0, 1), output_type="pil")[0]
        audio = audio.reshape(g.audio_channels, audio_frames, -1).permute(0, 2, 1).contiguous()
        mean = torch.tensor(g.audio_vae.config.latents_mean, device=self.device).view(1, -1, 1)
        std = torch.tensor(g.audio_vae.config.latents_std, device=self.device).view(1, -1, 1)
        audio = g.audio_vae.decode(audio * std + mean, return_dict=False)[0]
        return frames, audio.float().permute(1, 0, 2)[0].contiguous()

    def close(self):
        for manager in self.managers:
            manager.disable_auto_cpu_offload()
        self.transformer = self.conditioner = self.generation = None
        for manager in self.managers:
            for identifier in list(manager.get_ids()):
                manager.remove(identifier)
        gc.collect()


def generate(proxy, image, prompt, model_root, output, *, seed=SEED, keep_steps=KEEP_STEPS,
             text_device="cuda:1", generation_device="cuda:0"):
    if output.exists():
        raise FileExistsError(output)
    if not 0 <= keep_steps <= STEPS:
        raise ValueError(f"keep_steps must lie in [0, {STEPS}].")
    if not model_root.is_dir():
        raise FileNotFoundError(model_root)
    if not image.is_file():
        raise FileNotFoundError(image)
    check_video(proxy)
    from diffusers.modular_pipelines.minimax_h3.before_denoise import patchify_video_latents
    from diffusers.modular_pipelines.minimax_h3.modular_pipeline import audio_latent_num_frames
    from diffusers.utils.export_utils import encode_video
    runner = H3(text_device, generation_device)
    temporary = output.with_suffix(".partial.mp4")
    try:
        with torch.inference_mode():
            runner.load(model_root)
            g = runner.generation
            ref_video, video_latent = runner.proxy(proxy)
            ref_image, image_latent = runner.image(image)
            shape = video_latent.shape
            audio_frames = audio_latent_num_frames(FRAMES)
            geometry = (*shape[2:], audio_frames)
            image_rows = runner.reference_rows(
                image_latent, stream_seed(seed, "target_first_frame_condition_noise", -20))
            video_rows = runner.reference_rows(video_latent, stream_seed(seed, "ref2va_condition_noise"))
            prompt = prompt.rstrip() + "\n\nstyle_reference_guidance: " + STYLE_REFERENCE
            base = runner.condition(prompt, [ref_image], [image_latent], image_rows, geometry)
            full = runner.condition(prompt, [ref_image, ref_video], [image_latent, video_latent],
                                    torch.cat([image_rows, video_rows]), geometry)
            for scheduler, shift in ((g.scheduler, 12), (g.audio_scheduler, 3)):
                scheduler.set_timesteps(STEPS + 1, device=runner.device)
                if len(scheduler.timesteps) != STEPS or scheduler.shift != shift:
                    raise ValueError("Expected the native H3 20-update schedule with shifts 12/3.")
            if runner.text_device == runner.device:
                runner.managers[0].disable_auto_cpu_offload()
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            rng = torch.Generator(device="cpu").manual_seed(stream_seed(seed, "sdedit_base_noise"))
            video = torch.randn(shape, generator=rng, dtype=torch.float32).to(runner.device)
            audio = torch.randn((audio_frames * g.audio_channels, g.audio_latent_channels),
                                generator=rng, dtype=torch.float32).to(runner.device)
            video = patchify_video_latents(video, g.patch_size)
            for i in range(STEPS):
                condition = full if i < keep_steps else base
                tv, ta = g.scheduler.timesteps[i], g.audio_scheduler.timesteps[i]
                vp, ap = runner.predict(condition, video, audio, float(tv), float(ta))
                video = advance(video, vp, tv, g.scheduler.sigmas[i], g.scheduler.sigmas[i + 1])
                audio = advance(audio, ap, ta, g.audio_scheduler.sigmas[i], g.audio_scheduler.sigmas[i + 1])
            frames, sound = runner.decode(unpatchify(video, shape, g.patch_size), audio, audio_frames)
            output.parent.mkdir(parents=True, exist_ok=True)
            encode_video(frames, fps=FPS, output_path=str(temporary), audio=sound,
                         audio_sample_rate=int(g.audio_sampling_rate))
            check_video(temporary, audio=True)
            temporary.replace(output)
    finally:
        runner.close()
        temporary.unlink(missing_ok=True)
