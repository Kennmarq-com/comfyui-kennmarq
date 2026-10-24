"""Kennmarq.com's ComfyUI nodes.

Kennmarq.com Mark & Save Image takes the place of Save Image: Save Image re-encodes the file, which
would drop a manifest, so the marks are made as the file is written. Each picture gets the invisible
watermark and signed, time-stamped Content Credentials, made on this machine (the SDK's local mode):
only the manifest goes to Kennmarq.com to be signed, never pixels. Without a key it still writes the
watermark and the IPTC AI label, and says how to add signed credentials.

- The source is guessed from the graph: a Load Image node means the picture was made from another
  one (composite); otherwise it was made from scratch (created). The widget can say otherwise.
- ComfyUI's prompt and workflow stay in a PNG by default, as Save Image keeps them. They reveal the
  prompt: turn keep_workflow off to leave them out.
- The key comes from the KENNMARQ_API_KEY environment variable, never from a widget: a widget's value
  is saved in the workflow, and the workflow goes into every PNG.

Kennmarq.com Safety Check reads pictures for the AI Act's Art. 5 bans on this machine (nothing is sent,
nothing counted): it stops the run on a block, or passes its answers on so that Mark & Save Image
leaves a blocked picture unwritten.

Release 9: Kennmarq.com Mark & Save Audio and Mark & Save Video mark songs and clips in the cloud (the
SDK's mark()): the node writes the sound or the frames as a file of the best quality the API takes,
Kennmarq.com puts the watermarks in (AudioSeal in the sound, Video Seal in the frames), encodes the
file you asked for and signs it, and the node saves what comes back. A clip is a job: the node waits
for it. They need a key: songs and clips have no local mode yet.
"""
from __future__ import annotations

import io
import json
import os
from fractions import Fraction

import numpy as np
from PIL import Image

CATEGORY = "Kennmarq.com"
FORMATS = ["png", "jpeg", "webp"]
EXTENSIONS = {"png": "png", "jpeg": "jpg", "webp": "webp"}
NO_KEY_NOTE = ("No KENNMARQ_API_KEY: saved with the watermark and the IPTC AI label only. A free key at kennmarq.com "
               "adds signed Content Credentials (1,000 files a month).")
MEDIA_KEY_NOTE = ("Songs and clips are marked in Kennmarq.com's cloud, with a key: start ComfyUI with KENNMARQ_API_KEY "
                  "(a free key at kennmarq.com gives 1,000 marks a month: five per started minute of a song, "
                  "five per started second of a clip).")
AUDIO_FORMATS = ["mp3", "m4a", "wav"]
#: What the API takes in one song (25 MB, with room): a 16-bit WAV while it fits, else an MP3 at the
#: highest of these bitrates that fits.
MAX_SONG_BYTES = 24 * 1024 * 1024
MP3_BITRATES = (320_000, 256_000, 192_000, 160_000, 128_000)


def pictures(images) -> list[bytes]:
    """ComfyUI's IMAGE batch ([B, H, W, C] floats in 0-1) as lossless PNGs."""
    out = []
    for image in images:
        array = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format="PNG", compress_level=1)
        out.append(buffer.getvalue())
    return out


def guess_source(choice: str, prompt: dict | None) -> str:
    """"auto": composite when the graph loads a picture (a Load Image node), else created."""
    if choice != "auto":
        return choice
    nodes = prompt.values() if isinstance(prompt, dict) else []
    loads = any(isinstance(n, dict) and str(n.get("class_type", "")).startswith("LoadImage") for n in nodes)
    return "composite" if loads else "created"


def _client():
    from kennmarq import Kennmarq

    return Kennmarq()


class MarkAndSaveImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "Kennmarq"}),
                "format": (FORMATS, {"default": "png"}),
                "source": (["auto", "created", "composite", "edited"], {"default": "auto"}),
                "safety_check": (["off", "ai-act", "safe-only"], {"default": "off"}),
                "keep_workflow": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "provider": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "app_name": ("STRING", {"default": ""}),
                "app_version": ("STRING", {"default": ""}),
                "safety": ("KENNMARQ_SAFETY",),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("paths", "notes")
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = CATEGORY
    DESCRIPTION = "Saves pictures with Kennmarq.com's invisible watermark and signed Content Credentials, for the EU AI Act."

    def save(self, images, filename_prefix="Kennmarq", format="png", source="auto", safety_check="off", keep_workflow=True,
             model="", app_name="", safety=None, prompt=None, extra_pnginfo=None, provider="", app_version=""):
        import folder_paths
        from kennmarq import ContentBlocked

        output_dir = folder_paths.get_output_directory()
        folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, output_dir, images[0].shape[1], images[0].shape[0])
        client = _client()
        chosen = guess_source(source, prompt)
        text: dict[str, str] = {}
        if keep_workflow and format == "png":
            if prompt is not None:
                text["prompt"] = json.dumps(prompt)
            for key, value in (extra_pnginfo or {}).items():
                text[key] = json.dumps(value)
        answers = (safety or {}).get("answers") or []
        saved, notes, ui = [], [], []
        if not client.api_key:
            notes.append(NO_KEY_NOTE)
        for i, data in enumerate(pictures(images)):
            if i < len(answers) and answers[i].get("verdict") == "block":
                notes.append(f"Picture {i + 1} not saved: the safety check blocked it ({answers[i].get('reason')}).")
                continue
            name = f"{filename}_{counter:05}_.{EXTENSIONS[format]}"
            path = os.path.join(folder, name)
            try:
                if client.api_key:
                    result = client.mark_file(data, path, source=chosen, provider=provider or None, model=model or None,
                                              app_name=app_name or None, app_version=app_version or None,
                                              output_format=format, check=safety_check, png_text=text)
                    if result.safety and result.safety.get("verdict") == "flag":
                        notes.append(f"Picture {i + 1} flagged: {result.safety.get('reason')}. Get the person's consent before you publish it.")
                else:
                    if safety_check != "off":
                        answer = client.check(data, safety_check, local=True)
                        if answer["verdict"] == "block":
                            raise ContentBlocked("blocked", {**answer, "picture": "file"})
                    client.watermark_file(data, path, source=chosen, output_format=format, png_text=text)
            except ContentBlocked as blocked:
                notes.append(f"Picture {i + 1} not saved: the safety check blocked it ({blocked.safety.get('reason')}).")
                continue
            saved.append(path)
            ui.append({"filename": name, "subfolder": subfolder, "type": "output"})
            counter += 1
        return {"ui": {"images": ui, "text": notes}, "result": ("\n".join(saved), "\n".join(notes))}


def sound_file(audio: dict) -> tuple[bytes, str]:
    """ComfyUI's AUDIO ({"waveform": [B, C, N] floats, "sample_rate"}, the first of the batch) as the
    best file the API takes (MAX_SONG_BYTES): a 16-bit WAV, or an MP3. Returns the bytes and their
    extension."""
    import av

    waveform = audio["waveform"][0].float().cpu().numpy()[:2]
    rate = int(audio["sample_rate"])
    channels = waveform.shape[0]
    seconds = waveform.shape[1] / rate
    wav = waveform.shape[1] * channels * 2 + 44 <= MAX_SONG_BYTES
    bit_rate = next((b for b in MP3_BITRATES if seconds * b / 8 <= MAX_SONG_BYTES), MP3_BITRATES[-1])
    out = io.BytesIO()
    with av.open(out, "w", format="wav" if wav else "mp3") as container:
        stream = container.add_stream("pcm_s16le" if wav else "libmp3lame", rate=rate, layout="mono" if channels == 1 else "stereo")
        if not wav:
            stream.bit_rate = bit_rate
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(np.clip(waveform, -1, 1), dtype=np.float32), format="fltp",
                                           layout="mono" if channels == 1 else "stereo")
        frame.sample_rate = rate
        frame.pts = 0
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return out.getvalue(), "wav" if wav else "mp3"


def clip_file(images, fps: float, audio: dict | None = None) -> bytes:
    """ComfyUI's IMAGE batch as frames of an MP4 (H.264 at CRF 12, near lossless: Kennmarq.com
    re-encodes it once marked), with `audio` as AAC at 256 kb/s."""
    import av

    out = io.BytesIO()
    height, width = int(images.shape[1]) // 2 * 2, int(images.shape[2]) // 2 * 2
    rate = Fraction(fps).limit_denominator(1001)
    with av.open(out, "w", format="mp4") as container:
        video = container.add_stream("libx264", rate=rate, options={"crf": "12", "preset": "medium"})
        video.width, video.height, video.pix_fmt = width, height, "yuv420p"
        sound = None
        if audio is not None:
            waveform = audio["waveform"][0].float().cpu().numpy()
            layout = "mono" if waveform.shape[0] == 1 else "stereo"
            sound = container.add_stream("aac", rate=int(audio["sample_rate"]), layout=layout)
            sound.bit_rate = 256_000
        for index, image in enumerate(images):
            array = np.clip(255.0 * image.cpu().numpy(), 0, 255).astype(np.uint8)[:height, :width]
            frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(array), format="rgb24")
            frame.pts, frame.time_base = index, 1 / rate
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
        if sound is not None:
            samples = np.ascontiguousarray(np.clip(waveform[:2], -1, 1), dtype=np.float32)
            frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout=layout)
            frame.sample_rate = int(audio["sample_rate"])
            frame.pts = 0
            for packet in sound.encode(frame):
                container.mux(packet)
            for packet in sound.encode(None):
                container.mux(packet)
    return out.getvalue()


def _media_client():
    client = _client()
    if not client.api_key:
        raise RuntimeError(MEDIA_KEY_NOTE)
    return client


def _output_path(filename_prefix: str, extension: str) -> tuple[str, str, str]:
    """(path, file name, subfolder) for the next file of `filename_prefix` in ComfyUI's output folder."""
    import folder_paths

    folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, folder_paths.get_output_directory())
    name = f"{filename}_{counter:05}_.{extension}"
    return os.path.join(folder, name), name, subfolder


class MarkAndSaveAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"default": "audio/Kennmarq"}),
                "format": (AUDIO_FORMATS, {"default": "mp3"}),
                "source": (["created", "composite", "edited"], {"default": "created"}),
            },
            "optional": {
                "provider": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "app_name": ("STRING", {"default": ""}),
                "app_version": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("path", "notes")
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = CATEGORY
    DESCRIPTION = ("Saves a song with Kennmarq.com's inaudible AudioSeal watermark and signed Content Credentials, for the "
                   "EU AI Act. Marked in Kennmarq.com's cloud: needs KENNMARQ_API_KEY. Five marks per started minute.")

    def save(self, audio, filename_prefix="audio/Kennmarq", format="mp3", source="created", model="", app_name="",
             provider="", app_version=""):
        client = _media_client()
        data, _ = sound_file(audio)
        result = client.mark(data, source=source, provider=provider or None, model=model or None, app_name=app_name or None,
                             app_version=app_version or None, output_format=format)
        path, name, subfolder = _output_path(filename_prefix, format)
        with open(path, "wb") as f:
            f.write(result.data)
        notes = [f"Marked: {result.marks_counted or 1} mark(s); the mark in the sound is {result.audio_watermark}."]
        if result.audio_watermark == "unclaimed":
            notes.append("The sound's mark didn't read back (too quiet or too short); the Content Credentials still say it's AI.")
        return {"ui": {"audio": [{"filename": name, "subfolder": subfolder, "type": "output"}], "text": notes},
                "result": (path, "\n".join(notes))}


class MarkAndSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 0.01}),
                "filename_prefix": ("STRING", {"default": "video/Kennmarq"}),
                "source": (["auto", "created", "composite", "edited"], {"default": "auto"}),
                "safety_check": (["off", "ai-act", "safe-only"], {"default": "off"}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "provider": ("STRING", {"default": ""}),
                "model": ("STRING", {"default": ""}),
                "app_name": ("STRING", {"default": ""}),
                "app_version": ("STRING", {"default": ""}),
                # Release C3: the EU's visible label on every frame; a deep fake gets it whatever visible_label says.
                "visible_label": ("BOOLEAN", {"default": False}),
                "deepfake": ("BOOLEAN", {"default": False}),
                "label_language": (["en", "ko", "zh"], {"default": "en"}),
                "label_position": (["top-right", "top-left", "bottom-right", "bottom-left"], {"default": "top-right"}),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("path", "notes")
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = CATEGORY
    DESCRIPTION = ("Saves frames as an MP4 with Kennmarq.com's Video Seal watermark (and AudioSeal in its sound) and signed "
                   "Content Credentials, for the EU AI Act. Marked in Kennmarq.com's cloud: needs KENNMARQ_API_KEY. A mark "
                   "per started second (five marks); the safety check reads 12 frames, two marks each. visible_label (or "
                   "deepfake) draws the EU's \"AI GENERATED\" label on every frame.")

    def save(self, images, fps=24.0, filename_prefix="video/Kennmarq", source="auto", safety_check="off", audio=None,
             model="", app_name="", prompt=None, provider="", app_version="", visible_label=False, deepfake=False,
             label_language="en", label_position="top-right"):
        from kennmarq import ContentBlocked

        client = _media_client()
        data = clip_file(images, fps, audio)
        labelled = visible_label or deepfake
        try:
            result = client.mark(data, source=guess_source(source, prompt), provider=provider or None, model=model or None,
                                 app_name=app_name or None, app_version=app_version or None, check=safety_check,
                                 deepfake=deepfake, label=True if visible_label else None,
                                 label_language=label_language if labelled else None,
                                 label_position=label_position if labelled else None)
        except ContentBlocked as blocked:
            frame = (blocked.safety or {}).get("frame") or {}
            note = f"Not saved: the safety check blocked frame {frame.get('index', '?')} ({(blocked.safety or {}).get('reason')})."
            return {"ui": {"text": [note]}, "result": ("", note)}
        path, name, subfolder = _output_path(filename_prefix, "mp4")
        with open(path, "wb") as f:
            f.write(result.data)
        notes = [f"Marked: {result.marks_counted} mark(s); watermark {result.watermark_id}; the sound's mark is {result.audio_watermark}."]
        if result.safety and result.safety.get("verdict") == "flag":
            notes.append(f"Flagged: {result.safety.get('reason')}. Get the person's consent before you publish it.")
        return {"ui": {"images": [{"filename": name, "subfolder": subfolder, "type": "output"}], "animated": (True,), "text": notes},
                "result": (path, "\n".join(notes))}


class SafetyCheck:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "policy": (["ai-act", "safe-only"], {"default": "ai-act"}),
                "on_block": (["stop the run", "pass the answers on"], {"default": "stop the run"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "KENNMARQ_SAFETY", "STRING")
    RETURN_NAMES = ("images", "safety", "verdicts")
    FUNCTION = "check"
    CATEGORY = CATEGORY
    DESCRIPTION = ("Screens pictures for sexual content with an apparent minor or a realistic face (the AI Act's Art. 5 "
                   "bans), on this machine. A risk signal with published error rates, not a guarantee.")

    def check(self, images, policy="ai-act", on_block="stop the run"):
        client = _client()
        answers = [client.check(data, policy, local=True) for data in pictures(images)]
        lines = [f"Picture {i + 1}: {a['verdict']}" + (f" ({a['reason']})" if a.get("reason") else "") for i, a in enumerate(answers)]
        blocked = [line for line, a in zip(lines, answers) if a["verdict"] == "block"]
        if blocked and on_block == "stop the run":
            raise RuntimeError("Kennmarq.com Safety Check blocked " + "; ".join(blocked) + ". The run stopped here; nothing after it ran.")
        return (images, {"policy": policy, "answers": answers}, "\n".join(lines))


NODE_CLASS_MAPPINGS = {
    "KennmarqMarkAndSaveImage": MarkAndSaveImage,
    "KennmarqMarkAndSaveAudio": MarkAndSaveAudio,
    "KennmarqMarkAndSaveVideo": MarkAndSaveVideo,
    "KennmarqSafetyCheck": SafetyCheck,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "KennmarqMarkAndSaveImage": "Kennmarq.com Mark & Save Image",
    "KennmarqMarkAndSaveAudio": "Kennmarq.com Mark & Save Audio",
    "KennmarqMarkAndSaveVideo": "Kennmarq.com Mark & Save Video",
    "KennmarqSafetyCheck": "Kennmarq.com Safety Check",
}
