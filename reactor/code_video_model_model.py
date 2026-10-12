"""Runtime-independent finite-clip model and CPU-only step contracts."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ClipRequest:
    """Immutable selection for one complete clip, sent until its job is acknowledged.

    proxy is the validated original MP4; reference is the original PNG/JPEG.
    Their encoded bytes preserve native preprocessing without re-encoding an image.
    prompt, seed and keep_steps remain fixed throughout the twenty updates.
    """

    proxy: bytes
    reference: bytes
    prompt: str
    seed: int
    keep_steps: int


@dataclass(frozen=True)
class CodeVideoInput:
    """One compute boundary; request is omitted after job_id acknowledgment."""

    job_id: int
    request: ClipRequest | None


@dataclass(frozen=True)
class CodeVideoResult:
    """CPU RGB uint8 [T,H,W,3] and native float32 audio [C,S]."""

    job_id: int
    phase: str
    denoising_step: int
    frames: np.ndarray | None = None
    audio: np.ndarray | None = None
    sample_rate: int = 0
    complete: bool = False


class CodeVideoModel:
    """Own resident weights and one finite job; expose only CPU result facts.

    index counts successful denoising updates. decoded guards repeated decoding.
    The backend owns native conditioning, schedules and evolving video/audio latents.
    """

    def __init__(self) -> None:
        self.backend = None
        self.scratch = None
        self.job_id = None
        self.index = 0
        self.keep_steps = 5
        self.decoded = False

    def load(
        self,
        source: Path,
        weights: Path,
        scratch: Path,
        text_device: str = "cuda:1",
        device: str = "cuda:0",
    ) -> None:
        from code_video_model_backend import NativeBackend

        self.scratch = scratch
        self.backend = NativeBackend()
        self.backend.load(source, weights, text_device, device)

    def reset(self) -> None:
        if self.backend is not None:
            self.backend.reset()
        self.job_id = None
        self.index = 0
        self.decoded = False

    def generate(self, input: CodeVideoInput) -> CodeVideoResult:
        if self.backend is None:
            raise RuntimeError("Model has not loaded")
        if input.job_id != self.job_id:
            request = input.request
            if request is None:
                raise ValueError("A new job requires proxy, reference and prompt")
            if not request.prompt.strip() or not 0 <= request.keep_steps <= 20:
                raise ValueError("Invalid clip request")
            self.reset()
            # Native CVM loaders require paths. Copy the original bounded bytes,
            # without a decode/re-encode or a changed reference crop, and remove
            # the temporary files immediately after native conditioning.
            with tempfile.TemporaryDirectory(dir=self.scratch) as directory:
                proxy, reference = (
                    Path(directory) / "proxy.mp4",
                    Path(directory) / "reference.png",
                )
                proxy.write_bytes(request.proxy)
                reference.write_bytes(request.reference)
                self.backend.prepare(proxy, reference, request.prompt, request.seed)
            self.job_id = input.job_id
            self.keep_steps = request.keep_steps
            return CodeVideoResult(
                job_id=input.job_id, phase="denoising", denoising_step=0
            )
        if self.decoded:
            raise ValueError("Clip is complete; start a new job")
        if self.index < 20:
            self.backend.step(self.keep_steps)
            self.index += 1
            return CodeVideoResult(
                job_id=input.job_id,
                phase="decoding" if self.index == 20 else "denoising",
                denoising_step=self.index,
            )
        frames, audio, rate = self.backend.decode()
        self.backend.reset()
        self.decoded = True
        return CodeVideoResult(
            job_id=input.job_id,
            phase="complete",
            denoising_step=20,
            frames=frames,
            audio=audio,
            sample_rate=rate,
            complete=True,
        )
