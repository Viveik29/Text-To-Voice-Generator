# Components Reference

## `app.py` — Streamlit UI

Two tabs sharing `tts_engine.list_voices()`:

**News Analyst tab**
- Left column: input mode, exam focus, voice/speed/volume, text area or PDF uploader
- Right column: analysis preview with expandable sections, audio player, download buttons
- Primary action: `run_pipeline()` → stores result in `st.session_state["pipeline_result"]`
- Disabled when `ANTHROPIC_API_KEY` is missing

**Text-to-Voice tab**
- Standalone text → `synthesize()` → `st.session_state["last_audio"]`

---

## `agents/news_analyst/agent.py` — LLM Config

Defines three constants used by the analyzer:

| Constant | Purpose |
|----------|---------|
| `MODEL` | Claude model ID from `ANTHROPIC_MODEL` env (default: `claude-sonnet-5`) |
| `SYSTEM_INSTRUCTION` | Expert persona and analysis rules |
| `OUTPUT_SCHEMA` | Reference to `NewsAnalysis` Pydantic model |

No API calls happen here — this is configuration only.

---

## `pipeline/analyzer.py` — Claude Integration

```python
client.messages.parse(
    model=MODEL,
    max_tokens=8192,
    system=SYSTEM_INSTRUCTION,
    messages=[{"role": "user", "content": prompt}],
    output_format=NewsAnalysis,
)
```

- Validates `ANTHROPIC_API_KEY` before calling
- Maps exam focus labels (e.g. "UPSC Prelims" → full description)
- Returns validated `NewsAnalysis` with `exam_focus` set from UI selection
- Raises `RuntimeError` if `parsed_output` is empty

---

## `pipeline/schemas.py` — Data Contract

`NewsAnalysis` is the single schema shared between:
- Claude structured output (`output_format`)
- JSON artifact serialization (`model_dump_json`)
- PDF report rendering
- Streamlit UI preview

---

## `pipeline/runner.py` — Orchestrator

`run_pipeline()` is the only function the UI calls for news analysis.

```python
@dataclass
class PipelineResult:
    job_id: str
    analysis: NewsAnalysis
    pdf_path: Path
    audio_path: Path
    json_path: Path
    source_text_path: Path
```

Steps: generate job ID → extract text → analyze → save JSON → PDF → audio → return paths.

---

## `pipeline/extract.py` — Input Processing

| Function | Description |
|----------|-------------|
| `extract_text_from_pdf(path)` | PyMuPDF text extraction, 50-page limit |
| `normalize_text(text)` | Whitespace cleanup, 80k char cap |

---

## `pipeline/report.py` — PDF Generation

Uses ReportLab `SimpleDocTemplate` on A4 with styled sections:
- Title banner, exam focus + date metadata
- Brief summary, exam one-liner (highlighted callout)
- Comprehensive analysis, prelims facts, mains points, syllabus links
- Footer disclaimer

---

## `pipeline/audio.py` — Narration Wrapper

Thin adapter over `tts_engine.synthesize()`:
- Truncates long narration scripts at word boundary
- Passes through speed/volume/output filename

---

## `tts_engine.py` — TTS Core

| Function | Description |
|----------|-------------|
| `list_voices()` | Returns `AVAILABLE_VOICES` dict (display name → voice ID) |
| `ensure_voice(voice_id)` | Auto-downloads Piper ONNX model if missing |
| `synthesize(text, voice_id, ...)` | Main synthesis entry point |
| `validate_text(text)` | Empty check + 5,000 char limit |

**Piper path:** Load ONNX → split into ~800 char chunks → synthesize WAV → concatenate.

**gTTS path:** Hindi language code for both Hindi and Bhojpuri voice IDs → save MP3.

---

## `generator.py` — CLI

```bash
python generator.py "Your text" -v en_US-lessac-medium -s 1.2 --volume 1.0 -o out.wav
```

Argument parser over `tts_engine.synthesize()`. Useful for scripting without Streamlit.

---

## `anthropic_key_test.py` — API Smoke Test

Minimal script to verify `ANTHROPIC_API_KEY` works:

```bash
python anthropic_key_test.py
```

Prints a short Claude response or raises on auth/model errors.
