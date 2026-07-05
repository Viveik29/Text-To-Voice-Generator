"""Piper TTS engine - CPU-only, offline, MIT license."""

import io, re, subprocess, sys, uuid, wave
from functools import lru_cache
from pathlib import Path
from piper import PiperVoice, SynthesisConfig
from gtts import gTTS

ROOT = Path(__file__).resolve().parent
VOICES_DIR = ROOT / "voices"
OUTPUT_DIR = ROOT / "output"

# Curated voices
AVAILABLE_VOICES: dict[str, str] = {
    "Lessac (US, neutral)": "en_US-lessac-medium",
    "Amy (US, female)": "en_US-amy-medium",
    "Ryan (US, male)": "en_US-ryan-medium",
    "Alan (British)": "en_GB-alan-medium",
    "Cori (British, female)": "en_GB-cori-medium",
    # Hindi handled via gTTS fallback
    "Hindi (Female)": "hi_IN-female",
    "Hindi (Male)": "hi_IN-male",
    # Bhojpuri handled via gTTS fallback
    "Bhojpuri (Male)": "bh_IN-male",
    "Bhojpuri (Female)": "bh_IN-female",
}

MAX_CHARS = 5000
CHUNK_CHARS = 800

def _model_path(voice_id: str) -> Path:
    return VOICES_DIR / f"{voice_id}.onnx"

def ensure_voice(voice_id: str) -> Path:
    """Download voice model if missing. Returns path to .onnx file."""
    path = _model_path(voice_id)
    if path.exists():
        return path
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "piper.download_voices", voice_id, "--download-dir", str(VOICES_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to download voice '{voice_id}'.\n{result.stderr or result.stdout}")
    if not path.exists():
        raise FileNotFoundError(f"Voice model not found after download: {path}")
    return path

@lru_cache(maxsize=8)
def _load_voice(voice_id: str) -> PiperVoice:
    model = ensure_voice(voice_id)
    return PiperVoice.load(str(model))

def _split_text(text: str) -> list[str]:
    """Split long text into sentence-sized chunks Piper can handle reliably."""
    text = text.strip()
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""
    for part in parts:
        if len(current) + len(part) + 1 < CHUNK_CHARS:
            current = f"{current} {part}".strip()
        else:
            if current: chunks.append(current)
            if len(part) <= CHUNK_CHARS:
                current = part
            else:
                for i in range(0, len(part), CHUNK_CHARS):
                    chunks.append(part[i:i+CHUNK_CHARS])
                current = ""
    if current: chunks.append(current)
    return chunks or [text]

def _wav_bytes(chunks: list[str], voice: PiperVoice, config: SynthesisConfig) -> bytes:
    """Synthesize one or more text chunks into a single WAV byte stream."""
    frames, params = [], None
    for chunk in chunks:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(chunk, wf, syn_config=config)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            if params is None:
                params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(params[0]); wf.setsampwidth(params[1]); wf.setframerate(params[2])
        wf.writeframes(b"".join(frames))
    return out.getvalue()

def validate_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Please enter some text to convert.")
    if len(cleaned) > MAX_CHARS:
        raise ValueError(f"Text is too long ({len(cleaned)} chars). Max is {MAX_CHARS}.")
    return cleaned

def synthesize(text: str, voice_id: str, *, speed: float = 1.0, volume: float = 1.0, output_name: str | None = None) -> Path:
    """Convert text to speech and save a WAV/MP3 file."""
    cleaned = validate_text(text)

    # Hindi & Bhojpuri fallback via gTTS
    if voice_id.startswith("hi_IN") or voice_id.startswith("bh_IN"):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        name = output_name or f"{voice_id}_{uuid.uuid4().hex[:8]}.mp3"
        out_path = OUTPUT_DIR / name
        # Use Hindi TTS engine for Bhojpuri slang too
        tts = gTTS(cleaned, lang="hi")
        tts.save(str(out_path))
        return out_path

    # Piper voices
    voice = _load_voice(voice_id)
    length_scale = max(0.5, min(2.0, 1.0 / speed))
    config = SynthesisConfig(volume=max(0.1, min(2.0, volume)), length_scale=length_scale)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    name = output_name or f"speech_{uuid.uuid4().hex[:8]}.wav"
    if not name.endswith(".wav"): name += ".wav"
    out_path = OUTPUT_DIR / name
    wav_data = _wav_bytes(_split_text(cleaned), voice, config)
    out_path.write_bytes(wav_data)
    return out_path

def list_voices() -> dict[str, str]:
    """Return available voices dictionary."""
    return dict(AVAILABLE_VOICES)
