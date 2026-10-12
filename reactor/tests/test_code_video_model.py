import asyncio
import io
import zipfile
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
from reactor_runtime import ApplicationError, CommandError, StepOutcome

from code_video_model import CodeVideo
from code_video_model_model import (
    ClipRequest,
    CodeVideoInput,
    CodeVideoModel,
    CodeVideoResult,
)
from code_video_model_render import extract_scene
from code_video_model_types import CodeVideoState


def app():
    application = CodeVideo()
    application.state = CodeVideoState()
    application.output = Mock()
    application._engine = Mock()
    messages = []

    async def send(message):
        messages.append(message)

    application.send = send
    return application, messages


def start(application):
    application.state._proxy = b"proxy"
    application.state._reference = b"reference"
    asyncio.run(application.start("A robot moves", 42, 5))


def test_refusal_never_reaches_model():
    application, _ = app()
    with pytest.raises(ApplicationError):
        asyncio.run(application.process_input())
    with pytest.raises(CommandError):
        asyncio.run(application.start("robot", 42, 5))
    application._engine.generate.assert_not_called()


def test_generate_uses_input_only():
    application, _ = app()
    application.state = None
    input = CodeVideoInput(job_id=1, request=None)
    application.generate(input)
    application._engine.generate.assert_called_once_with(input)


def test_request_until_acknowledged_and_busy_rejection():
    application, messages = app()
    start(application)
    first = asyncio.run(application.process_input())
    assert asyncio.run(application.process_input()).request is first.request
    asyncio.run(
        application.process_output(
            StepOutcome(
                result=CodeVideoResult(job_id=1, phase="denoising", denoising_step=0),
                elapsed=2,
            )
        )
    )
    assert asyncio.run(application.process_input()).request is None
    assert messages[-1].compute_seconds == 2
    with pytest.raises(CommandError):
        asyncio.run(application.start("different", 42, 5))


def test_failure_not_completion():
    application, _ = app()
    start(application)
    with pytest.raises(RuntimeError):
        asyncio.run(
            application.process_output(
                StepOutcome(error=RuntimeError("gpu"), elapsed=3)
            )
        )
    assert application.state._acknowledged is None
    assert application.state._seconds == 0
    assert application.state._phase == "queued"


def test_cancel_and_new_session():
    application, _ = app()
    start(application)
    asyncio.run(application.cancel())
    with pytest.raises(ApplicationError):
        asyncio.run(application.process_input())
    application.on_session_ended()
    assert application._engine.reset.call_count == 2
    application.state = CodeVideoState()
    assert application.state._proxy is None


def test_native_audio_track_and_quantization():
    application, _ = app()
    start(application)
    result = CodeVideoResult(
        job_id=1,
        phase="complete",
        denoising_step=20,
        complete=True,
        frames=np.zeros((124, 2, 2, 3), np.uint8),
        audio=np.ones((2, 32000), np.float32) * 0.5,
        sample_rate=32000,
    )
    output = asyncio.run(
        application.process_output(StepOutcome(result=result, elapsed=1))
    )
    assert output.main_audio.dtype == np.int16
    assert output.main_audio.shape == (1, 48000)
    assert abs(int(output.main_audio[0, 0]) - 16384) <= 1
    with pytest.raises(ApplicationError):
        asyncio.run(application.process_input())


def test_model_twenty_boundaries_and_independent_clips(tmp_path):
    model = CodeVideoModel()
    model.scratch = tmp_path
    model.backend = Mock()
    frames, audio = np.zeros((124, 2, 2, 3), np.uint8), np.zeros((2, 32000), np.float32)
    model.backend.decode.return_value = frames, audio, 32000
    request = ClipRequest(
        proxy=b"proxy", reference=b"ref", prompt="robot", seed=42, keep_steps=5
    )
    first = model.generate(CodeVideoInput(job_id=1, request=request))
    assert first.denoising_step == 0
    for index in range(1, 21):
        result = model.generate(CodeVideoInput(job_id=1, request=None))
        assert result.denoising_step == index and result.frames is None
    result = model.generate(CodeVideoInput(job_id=1, request=None))
    assert result.complete and result.frames is frames
    assert model.backend.step.call_count == 20
    assert model.backend.prepare.call_count == 1
    with pytest.raises(ValueError, match="complete"):
        model.generate(CodeVideoInput(job_id=1, request=None))
    model.generate(CodeVideoInput(job_id=2, request=request))
    assert model.backend.prepare.call_count == 2


def test_backend_failure_does_not_advance(tmp_path):
    model = CodeVideoModel()
    model.backend = Mock()
    model.job_id = 1
    model.backend.step.side_effect = RuntimeError("denoiser failed")
    with pytest.raises(RuntimeError):
        model.generate(CodeVideoInput(job_id=1, request=None))
    assert model.index == 0


@pytest.mark.parametrize(
    "name",
    [
        "../escape.js",
        "/case/abs.js",
        "case/../../a.js",
        "case/x.py",
        "vendor/three.module.js",
        "case\\a.js",
    ],
)
def test_scene_paths_refused(tmp_path, name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "test")
    with pytest.raises(ValueError):
        extract_scene(buffer.getvalue(), tmp_path, tmp_path)


def test_scene_uses_server_owned_vendor(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    (source / "vendor").mkdir(parents=True)
    (source / "vendor/three.module.js").write_text("trusted")
    target.mkdir()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("case/index.html", "<canvas></canvas>")
    extract_scene(buffer.getvalue(), target, source)
    assert (target / "vendor/three.module.js").read_text() == "trusted"


def test_model_import_does_not_import_runtime():
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import code_video_model_model; assert 'reactor_runtime' not in sys.modules",
        ],
        check=True,
    )


def test_joining_viewer_does_not_reset_shared_job():
    application, _ = app()
    start(application)
    viewer = Mock(send=AsyncMock())
    asyncio.run(application.on_connect(viewer))
    application._engine.reset.assert_not_called()
    assert application.state._phase == "queued"
    viewer.send.assert_awaited_once()


def test_new_prompt_starts_independent_job():
    application, _ = app()
    start(application)
    first = asyncio.run(application.process_input())
    asyncio.run(application.cancel())
    asyncio.run(application.start("A second scene", 99, 10))
    second = asyncio.run(application.process_input())
    assert second.job_id == first.job_id + 1
    assert second.request.prompt == "A second scene"
    assert second.request.seed == 99
    assert application.state._step == 0
    assert application.state._seconds == 0


def test_invalid_reference_is_rejected_before_model():
    application, _ = app()
    with pytest.raises(CommandError):
        asyncio.run(application.set_reference(Mock(data=b"not an image")))
    assert application.state._reference is None
    application._engine.generate.assert_not_called()


def test_oversized_reference_and_empty_proxy(tmp_path):
    from code_video_model import _validate_image
    from code_video_model_assets import validate_proxy

    with pytest.raises(ValueError, match="20 MiB"):
        _validate_image(b"x" * (20 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="nonempty"):
        validate_proxy(b"", tmp_path)


def test_scene_renderer_failure_does_not_replace_selected_proxy(tmp_path):
    application, _ = app()
    application._render_socket = tmp_path / "absent.sock"
    application.state._proxy = b"old proxy"
    with pytest.raises(CommandError):
        asyncio.run(application.set_scene(Mock(data=b"invalid zip")))
    assert application.state._proxy == b"old proxy"
    application._engine.generate.assert_not_called()


def test_audio_resampling_preserves_duration_and_frequency():
    from code_video_model import _playback_audio
    from code_video_model_types import CodeVideoOutput

    samples = 0.25 * np.sin(2 * np.pi * 440 * np.arange(32000) / 32000)
    pcm = _playback_audio(samples.astype(np.float32)[None, :], 32000)
    assert pcm.shape == (1, 48000)
    assert CodeVideoOutput.__tracks__["main_audio"].rate == 48000
    peak = np.argmax(np.abs(np.fft.rfft(pcm[0])))
    assert peak == 440
    assert 8000 < int(pcm.max()) < 8300
