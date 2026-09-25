WIDTH, HEIGHT, FPS, FRAMES = 960, 544, 24, 124
STEPS, KEEP_STEPS, SEED = 20, 5, 42
PROGRAM_MODEL = "gpt-6-astra"
IMAGE_MODEL = "openai/gpt-image-2"


def check_video(path, *, audio=False):
    import json
    import subprocess
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams",
        "-of", "json", str(path)]))
    videos = [s for s in info["streams"] if s["codec_type"] == "video"]
    sounds = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if len(videos) != 1 or len(sounds) != int(audio):
        raise ValueError(f"Unexpected video/audio streams in {path}")
    stream = videos[0]
    from fractions import Fraction
    if (stream["width"], stream["height"], int(stream["nb_read_frames"]),
            Fraction(stream["avg_frame_rate"])) != (WIDTH, HEIGHT, FRAMES, FPS):
        raise ValueError(f"Expected {WIDTH}x{HEIGHT}, {FRAMES} frames at {FPS} FPS: {path}")
    if stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p":
        raise ValueError(f"Expected H.264/yuv420p: {path}")
