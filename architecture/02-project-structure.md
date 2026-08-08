# Project Structure

```
TEXT_TO_VOICE_GENERATOR/
│
├── app.py                      # Streamlit entry point (2 tabs)
├── tts_engine.py               # Shared TTS engine (Piper + gTTS)
├── generator.py                # CLI wrapper for TTS
├── anthropic_key_test.py       # Smoke test for ANTHROPIC_API_KEY
│
├── requirements.txt
├── .env.example                # Environment variable template
├── .gitignore
│
├── agents/                     # LLM agent configuration
│   └── news_analyst/
│       ├── __init__.py
│       └── agent.py            # System prompt, model name, output schema
│
├── pipeline/                   # News analysis pipeline
│   ├── __init__.py
│   ├── runner.py               # Orchestrates extract → analyze → report → audio
│   ├── extract.py              # PDF text extraction + text normalization
│   ├── analyzer.py             # Calls Claude API with structured output
│   ├── report.py               # PDF report generation (ReportLab)
│   ├── audio.py                # Narration audio via tts_engine
│   └── schemas.py              # Pydantic NewsAnalysis model
│
├── voices/                     # Piper ONNX voice model configs
│   ├── en_US-lessac-medium.onnx.json
│   ├── en_US-ryan-medium.onnx.json
│   └── en_GB-cori-medium.onnx.json
│
├── assets/                     # Static assets (diagrams, etc.)
│   └── news-analyst-pipeline-flow.png
│
├── architecture/               # This documentation folder
│
├── output/                     # TTS audio files (gitignored, auto-created)
├── uploads/                    # Temporary PDF uploads (gitignored)
└── artifacts/                  # Pipeline job outputs (gitignored)
    └── <job_id>/
        ├── source.txt
        ├── analysis.json
        ├── <job_id>_report.pdf
        └── <job_id>_narration.wav|mp3
```

## Module Responsibilities

| Path | Role |
|------|------|
| `app.py` | UI layout, form inputs, session state, download buttons |
| `agents/news_analyst/agent.py` | Claude model ID, system instruction, schema reference |
| `pipeline/runner.py` | Single entry `run_pipeline()` — wires all stages |
| `pipeline/extract.py` | PDF → text; raw text cleaning and length cap |
| `pipeline/analyzer.py` | Builds prompt, calls `client.messages.parse()` |
| `pipeline/schemas.py` | `NewsAnalysis` Pydantic model (shared contract) |
| `pipeline/report.py` | Renders analysis into branded A4 PDF |
| `pipeline/audio.py` | Truncates narration script, delegates to `tts_engine` |
| `tts_engine.py` | Voice listing, model download, WAV/MP3 synthesis |
| `generator.py` | argparse CLI over `tts_engine.synthesize()` |

## Runtime Directories (auto-created)

| Directory | Created by | Contents |
|-----------|------------|----------|
| `output/` | `tts_engine.py` | Standalone TTS and temp audio files |
| `uploads/` | `app.py` | Uploaded PDFs before pipeline run |
| `artifacts/<job_id>/` | `pipeline/runner.py` | Full job bundle per analysis run |
| `voices/` | `tts_engine.py` | Downloaded Piper `.onnx` models |

## Dependency Graph (imports)

```
app.py
 ├── pipeline.runner
 ├── pipeline.analyzer (EXAM_FOCUS_LABELS)
 └── tts_engine

pipeline/runner.py
 ├── pipeline.extract
 ├── pipeline.analyzer
 ├── pipeline.report
 └── pipeline.audio

pipeline/analyzer.py
 ├── agents.news_analyst.agent
 └── pipeline.schemas

pipeline/audio.py
 └── tts_engine

agents/news_analyst/agent.py
 └── pipeline.schemas (NewsAnalysis)
```
