"""CLI: generate speech from the command line."""

import argparse
import sys
from tts_engine import AVAILABLE_VOICES, synthesize

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate speech with Piper TTS (CPU, offline)")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument("-v", "--voice", default="en-US-lessac-medium", choices=list(AVAILABLE_VOICES.values()), help="Voice model ID")
    parser.add_argument("-o", "--output", default=None, help="Output filename (default: auto)")
    parser.add_argument("-s", "--speed", type=float, default=1.0, help="Speed multiplier (default: 1.0)")
    parser.add_argument("--volume", type=float, default=1.0, help="Volume multiplier (default: 1.0)")
    args = parser.parse_args()

    try:
        path = synthesize(args.text, args.voice, speed=args.speed, volume=args.volume, output_name=args.output)
        print(f"✅ Saved: {path}")
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
