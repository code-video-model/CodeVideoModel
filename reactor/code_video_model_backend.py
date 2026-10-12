"""Native CVM sampling, split only at the twenty denoising boundaries.

The equations, reference layouts and RNG streams come from upstream cvm.video.
The text encoder and H3 components stay resident across independent clips.
"""

from pathlib import Path


class NativeBackend:
    def load(self, source: Path, weights: Path, text_device: str, device: str) -> None:
        import sys

        sys.path.insert(0, str(source))
        from cvm.video import H3

        self.runner = H3(text_device, device)
        self.runner.load(weights)
        self.reset()

    def reset(self) -> None:
        self.base = self.full = self.video = self.audio = None
        self.shape = None
        self.audio_frames = 0
        self.index = 0

    def prepare(self, proxy: Path, reference: Path, prompt: str, seed: int) -> None:
        import torch
        from cvm import FRAMES, STEPS, check_video
        from cvm.video import STYLE_REFERENCE, stream_seed
        from diffusers.modular_pipelines.minimax_h3.before_denoise import (
            patchify_video_latents,
        )
        from diffusers.modular_pipelines.minimax_h3.modular_pipeline import (
            audio_latent_num_frames,
        )

        check_video(proxy)
        r, g = self.runner, self.runner.generation
        with torch.inference_mode():
            ref_video, video_latent = r.proxy(proxy)
            ref_image, image_latent = r.image(reference)
            self.shape = video_latent.shape
            self.audio_frames = audio_latent_num_frames(FRAMES)
            geometry = (*self.shape[2:], self.audio_frames)
            image_rows = r.reference_rows(
                image_latent,
                stream_seed(seed, "target_first_frame_condition_noise", -20),
            )
            video_rows = r.reference_rows(
                video_latent, stream_seed(seed, "ref2va_condition_noise")
            )
            prompt = (
                prompt.rstrip() + "\n\nstyle_reference_guidance: " + STYLE_REFERENCE
            )
            self.base = r.condition(
                prompt, [ref_image], [image_latent], image_rows, geometry
            )
            self.full = r.condition(
                prompt,
                [ref_image, ref_video],
                [image_latent, video_latent],
                torch.cat([image_rows, video_rows]),
                geometry,
            )
            for scheduler, shift in ((g.scheduler, 12), (g.audio_scheduler, 3)):
                scheduler.set_timesteps(STEPS + 1, device=r.device)
                if len(scheduler.timesteps) != STEPS or scheduler.shift != shift:
                    raise ValueError(
                        "Expected native H3 20-update schedule with shifts 12/3"
                    )
            rng = torch.Generator(device="cpu").manual_seed(
                stream_seed(seed, "sdedit_base_noise")
            )
            video = torch.randn(self.shape, generator=rng, dtype=torch.float32).to(
                r.device
            )
            self.audio = torch.randn(
                (self.audio_frames * g.audio_channels, g.audio_latent_channels),
                generator=rng,
                dtype=torch.float32,
            ).to(r.device)
            self.video = patchify_video_latents(video, g.patch_size)
            self.index = 0

    def step(self, keep_steps: int) -> None:
        import torch
        from cvm.video import advance

        r, g, i = self.runner, self.runner.generation, self.index
        with torch.inference_mode():
            condition = self.full if i < keep_steps else self.base
            tv, ta = g.scheduler.timesteps[i], g.audio_scheduler.timesteps[i]
            vp, ap = r.predict(condition, self.video, self.audio, float(tv), float(ta))
            self.video = advance(
                self.video, vp, tv, g.scheduler.sigmas[i], g.scheduler.sigmas[i + 1]
            )
            self.audio = advance(
                self.audio,
                ap,
                ta,
                g.audio_scheduler.sigmas[i],
                g.audio_scheduler.sigmas[i + 1],
            )
            self.index += 1

    def decode(self):
        import numpy as np
        import torch
        from cvm.video import unpatchify

        with torch.inference_mode():
            frames, audio = self.runner.decode(
                unpatchify(self.video, self.shape, self.runner.generation.patch_size),
                self.audio,
                self.audio_frames,
            )
        return (
            np.stack([np.asarray(f) for f in frames]),
            audio.cpu().numpy(),
            int(self.runner.generation.audio_sampling_rate),
        )
