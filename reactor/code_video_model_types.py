"""Finite clip controls, status and synchronized media tracks."""

from reactor_runtime import Audio, InputState, MessageField, ModelMessage, Output, Video

from code_video_model_model import ClipRequest


class CodeVideoOutput(Output):
    main_video: Video
    main_audio: Audio


class CodeVideoState(InputState):
    _proxy: bytes | None = None
    _reference: bytes | None = None
    _request: ClipRequest | None = None
    _job_id: int = 0
    _acknowledged: int | None = None
    _phase: str = "idle"
    _step: int = 0
    _seconds: float = 0.0


class StateUpdate(ModelMessage):
    has_proxy: bool = MessageField(description="A validated proxy video is selected.")
    has_reference: bool = MessageField(description="A reference image is selected.")
    job_id: int = MessageField(description="Current finite generation job.")
    phase: str = MessageField(
        description="idle, queued, denoising, decoding, complete or cancelled."
    )
    denoising_step: int = MessageField(
        description="Completed H3 updates, from zero to twenty."
    )
    compute_seconds: float = MessageField(
        description="Measured model time for this job, excluding playback."
    )

    @classmethod
    def of(cls, state: CodeVideoState):
        return cls(
            has_proxy=state._proxy is not None,
            has_reference=state._reference is not None,
            job_id=state._job_id,
            phase=state._phase,
            denoising_step=state._step,
            compute_seconds=state._seconds,
        )
