# API Configuration

## Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```env
# Required for News Analyst tab
ANTHROPIC_API_KEY="sk-ant-..."

# Optional: override Claude model
ANTHROPIC_MODEL="claude-sonnet-5"
```

| Variable | Required | Default | Used by |
|----------|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Yes (News Analyst) | — | `pipeline/analyzer.py`, `anthropic_key_test.py` |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-5` | `agents/news_analyst/agent.py` |

`python-dotenv` loads `.env` automatically in `app.py` and `anthropic_key_test.py`.

## Getting an Anthropic API Key

1. Sign up at [console.anthropic.com](https://console.anthropic.com/)
2. Go to **Settings → API Keys**
3. Create a key and paste it into `.env`

## Verify Setup

```bash
python anthropic_key_test.py
```

Expected: a short text response printed to stdout.

## Claude Structured Output

The analyzer uses Anthropic's `messages.parse()` with the `NewsAnalysis` Pydantic model as `output_format`. This means:

- Claude returns JSON matching the schema
- The SDK validates and deserializes into a Python object
- No manual JSON parsing or markdown fence stripping needed

Requirements:
- `anthropic>=0.120.0`
- `pydantic>=2.0.0`
- A model that supports structured outputs (Sonnet 4+ recommended)

## TTS Configuration

TTS does **not** require API keys for English voices (Piper runs locally).

| Engine | Voices | Network | Output |
|--------|--------|---------|--------|
| Piper | `en_US-*`, `en_GB-*` | Only for first-time model download | `.wav` |
| gTTS | `hi_IN-*`, `bh_IN-*` | Required at synthesis time | `.mp3` |

Piper models are stored in `voices/` and auto-downloaded via `piper.download_voices`.

### Voice IDs

| Display Name | Voice ID | Engine |
|--------------|----------|--------|
| Lessac (US, neutral) | `en_US-lessac-medium` | Piper |
| Amy (US, female) | `en_US-amy-medium` | Piper |
| Ryan (US, male) | `en_US-ryan-medium` | Piper |
| Alan (British) | `en_GB-alan-medium` | Piper |
| Cori (British, female) | `en_GB-cori-medium` | Piper |
| Hindi (Female) | `hi_IN-female` | gTTS |
| Hindi (Male) | `hi_IN-male` | gTTS |
| Bhojpuri (Male) | `bh_IN-male` | gTTS |
| Bhojpuri (Female) | `bh_IN-female` | gTTS |

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Launch UI
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Error Troubleshooting

| Error | Likely cause | Fix |
|-------|--------------|-----|
| `ANTHROPIC_API_KEY is not set` | Missing `.env` | Copy `.env.example` → `.env`, add key |
| `authentication_error` | Invalid/expired key | Regenerate key in Anthropic console |
| `not_found_error` (model) | Wrong model name | Set `ANTHROPIC_MODEL` to a valid model |
| `Failed to download voice` | No network for Piper | Check internet, retry |
| gTTS errors | No network | Hindi/Bhojpuri need internet |
| `Text is too long` | >5,000 chars in TTS tab | Shorten input text |

## Security Notes

- `.env` is gitignored — never commit API keys
- `artifacts/` and `uploads/` may contain user content — also gitignored
- Anthropic API calls send news text to Claude servers; do not upload sensitive data in production without review
