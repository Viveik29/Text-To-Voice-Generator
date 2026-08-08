# Architecture Documentation

This folder documents the **News Analyst MVP + Text-to-Voice** project end-to-end.

## Documents

| Document | Description |
|----------|-------------|
| **[project-flow.html](project-flow.html)** | **Colorful full project flow** — open in browser; Download PDF / PNG |
| [01-system-overview.md](01-system-overview.md) | What the app does, tech stack, and high-level diagram |
| [02-project-structure.md](02-project-structure.md) | Folder layout and file responsibilities |
| [03-data-flow.md](03-data-flow.md) | Pipeline stages, inputs/outputs, and artifact paths |
| [04-components.md](04-components.md) | Deep dive into each module |
| [05-api-configuration.md](05-api-configuration.md) | Environment variables, Claude setup, and TTS engines |

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY
python anthropic_key_test.py  # verify API key
streamlit run app.py          # launch UI
```

## System at a Glance

```
User (Streamlit UI)
       │
       ├── News Analyst tab ──► pipeline/ ──► Claude API
       │                              │
       │                              ├── PDF report (ReportLab)
       │                              └── Audio narration (Piper/gTTS)
       │
       └── Text-to-Voice tab ──► tts_engine.py (Piper/gTTS)
```

## Key Design Decisions

- **Claude (Anthropic)** powers news analysis via structured output (`messages.parse` + Pydantic schema).
- **Piper TTS** handles English voices offline on CPU; **gTTS** handles Hindi/Bhojpuri online.
- **Pipeline artifacts** are stored per job under `artifacts/<job_id>/`.
- **Streamlit** provides the single-page UI with two tabs sharing the same TTS engine.
