"""Select a proxy and reference, explicitly generate a finite CVM video, then play it."""

from __future__ import annotations

import asyncio
import io
from http.client import HTTPException
from pathlib import Path

import av
import numpy as np
from PIL import Image, UnidentifiedImageError
from reactor_runtime import (
    ApplicationError,
    ClientInfo,
    CommandError,
    InputField,
    ReactorApp,
    StepOutcome,
    UploadedFile,
    connected,
    event,
    get_weights_path,
    session_ended,
)
from reactor_runtime.distributed import DistributedRunner

from code_video_model_assets import prepare_assets, validate_proxy
from code_video_model_model import (
    ClipRequest,
    CodeVideoInput,
    CodeVideoModel,
    CodeVideoResult,
)
from code_video_model_types import CodeVideoOutput, CodeVideoState, StateUpdate


class CodeVideo(ReactorApp):
    """Generate a 124-frame clip from a Three.js proxy, reference image and prompt.

    Select inputs before start. Every clip uses twenty denoising updates and
    plays at its native 24 FPS with synchronized audio. New prompts are
    accepted by start for independent clips, with no live autoregressive editing.
    """

    state: CodeVideoState
    fps = 24
    buffer_size = 124

    def load(self, config_path: Path | None) -> None:
        settings = prepare_assets(config_path, get_weights_path())
        self._scratch = settings.pop("scratch")
        self._render_socket = settings.pop("render_socket")
        self._engine = DistributedRunner(
            CodeVideoModel,
            world_size=1,
            call_timeout=1200,
            start_timeout=1200,
            load_kwargs={**settings, "scratch": self._scratch},
        )
        self._engine.start()

    async def process_input(self) -> CodeVideoInput:
        if self.state._phase not in {"queued", "denoising", "decoding"}:
            raise ApplicationError("Waiting for start")
        return CodeVideoInput(
            job_id=self.state._job_id,
            request=self.state._request
            if self.state._acknowledged != self.state._job_id
            else None,
        )

    def generate(self, input: CodeVideoInput) -> CodeVideoResult:
        return self._engine.generate(input)

    async def process_output(self, outcome: StepOutcome) -> CodeVideoOutput | None:
        if outcome.error is not None:
            # Validated inputs reach the engine; unexpected model/GPU failures need operator attention.
            raise outcome.error
        result: CodeVideoResult = outcome.result
        self.state._acknowledged = result.job_id
        self.state._phase = result.phase
        self.state._step = result.denoising_step
        self.state._seconds += outcome.elapsed
        await self.send(StateUpdate.of(self.state))
        if result.complete:
            if result.sample_rate != 32000:
                raise ValueError("Unexpected native audio sample rate")
            self.state._request = None
            audio = _playback_audio(result.audio, result.sample_rate)
            return CodeVideoOutput(main_video=result.frames, main_audio=audio)
        return None

    def _require_idle(self) -> None:
        if self.state._phase in {"queued", "denoising", "decoding"}:
            raise CommandError(
                "busy", "Cancel the current generation before selecting new inputs."
            )

    @event(name="set_proxy")
    async def set_proxy(
        self,
        video: UploadedFile = InputField(
            moderate=True,
            description="H.264 proxy: 960x544, 124 frames, 24 FPS, no audio.",
        ),
    ) -> StateUpdate:
        self._require_idle()
        try:
            await asyncio.to_thread(validate_proxy, video.data, self._scratch)
        except ValueError as exc:
            raise CommandError("invalid_proxy", str(exc)) from exc
        self.state._proxy = video.data
        await self.send(StateUpdate.of(self.state))
        return StateUpdate.of(self.state)

    @event(name="set_scene")
    async def set_scene(
        self,
        scene: UploadedFile = InputField(
            moderate=True,
            description="ZIP containing case/index.html and local Three.js scene files; render on the isolated CPU renderer.",
        ),
    ) -> StateUpdate:
        self._require_idle()
        if not self._render_socket.is_socket():
            raise CommandError(
                "renderer_unavailable",
                "Configure the isolated scene renderer before uploading code.",
            )
        from code_video_model_render import render_remote

        try:
            video = await asyncio.to_thread(
                render_remote, self._render_socket, scene.data
            )
            await asyncio.to_thread(validate_proxy, video, self._scratch)
        except (ValueError, OSError, HTTPException) as exc:
            raise CommandError("render_failed", str(exc)) from exc
        self.state._proxy = video
        await self.send(StateUpdate.of(self.state))
        return StateUpdate.of(self.state)

    @event(name="set_reference")
    async def set_reference(
        self,
        image: UploadedFile = InputField(
            moderate=True,
            description="Reference style image, PNG or JPEG. Selection does not generate.",
        ),
    ) -> StateUpdate:
        self._require_idle()
        try:
            await asyncio.to_thread(_validate_image, image.data)
        except (
            ValueError,
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ) as exc:
            raise CommandError("invalid_reference", str(exc)) from exc
        self.state._reference = image.data
        await self.send(StateUpdate.of(self.state))
        return StateUpdate.of(self.state)

    @event(name="start")
    async def start(
        self,
        prompt: str = InputField(
            moderate=True,
            min_length=1,
            max_length=8000,
            description="Scene description for this independent clip.",
        ),
        seed: int = InputField(default=42, ge=0, le=2147483647),
        keep_steps: int = InputField(
            default=5,
            ge=0,
            le=20,
            description="Initial updates conditioned on the proxy; all clips use twenty updates.",
        ),
    ) -> StateUpdate:
        self._require_idle()
        if (
            not prompt.strip()
            or self.state._proxy is None
            or self.state._reference is None
        ):
            raise CommandError(
                "missing_input",
                "Select a proxy or scene, select a reference, and enter a prompt.",
            )
        self.output.flush()
        self.state._request = ClipRequest(
            proxy=self.state._proxy,
            reference=self.state._reference,
            prompt=prompt,
            seed=seed,
            keep_steps=keep_steps,
        )
        self.state._job_id += 1
        self.state._phase = "queued"
        self.state._step = 0
        self.state._seconds = 0.0
        await self.send(StateUpdate.of(self.state))
        return StateUpdate.of(self.state)

    @event(name="cancel")
    async def cancel(self) -> StateUpdate:
        """Cancel at the next denoising boundary and stop buffered playback."""
        self._engine.reset()
        self.output.flush()
        self.state._request = None
        self.state._acknowledged = None
        self.state._phase = "cancelled"
        await self.send(StateUpdate.of(self.state))
        return StateUpdate.of(self.state)

    @connected
    async def on_connect(self, client: ClientInfo) -> None:
        await client.send(StateUpdate.of(self.state))

    @session_ended
    def on_session_ended(self) -> None:
        self._engine.reset()
        self.output.flush()


def _playback_audio(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Convert native [C,S] float audio to the WebRTC sink's 48 kHz mono PCM.

    Runtime 3.8.1 feeds WebRTC at 48 kHz without resampling track payloads.
    Flush the resampler so the complete finite clip retains its duration.
    """
    mono = np.ascontiguousarray(
        np.clip(samples.mean(axis=0, keepdims=True), -1, 1), dtype=np.float32
    )
    frame = av.AudioFrame.from_ndarray(mono, format="flt", layout="mono")
    frame.sample_rate = sample_rate
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    converted = resampler.resample(frame) + resampler.resample(None)
    return np.concatenate([part.to_ndarray() for part in converted], axis=1)


def _validate_image(data: bytes) -> None:
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Reference exceeds 20 MiB")
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("Reference must be PNG or JPEG")
        w, h = image.size
        if w * h > 16_000_000 or w > 4 * h or h > 4 * w:
            raise ValueError(
                "Reference must be <=16 megapixels and within 1:4 to 4:1 aspect ratio"
            )
        image.load()
