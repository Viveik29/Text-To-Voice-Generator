"""CLI: generate Hindi speech from text or a .txt file."""

from __future__ import annotations

import argparse
import sys

from tts_engine import AVAILABLE_VOICES, read_text_file, synthesize


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hindi speech with neural edge-tts voices")
    parser.add_argument("text", nargs="?", help="Hindi text to convert to speech")
    parser.add_argument("--file", "-f", help="Path to a UTF-8 .txt file")
    parser.add_argument(
        "-v",
        "--voice",
        default="hi-IN-SwaraNeural",
        choices=list(AVAILABLE_VOICES.values()),
        help="Voice model ID",
    )
    parser.add_argument("-o", "--output", default=None, help="Output filename")
    parser.add_argument("-s", "--speed", type=float, default=1.0, help="Speed multiplier (0.5-2.0)")
    parser.add_argument(
        "--format",
        dest="output_format",
        default="wav",
        choices=["wav", "mp3"],
        help="Output format (default: wav)",
    )
    args = parser.parse_args()

    if args.file:
        try:
            text = read_text_file(args.file)
        except (ValueError, FileNotFoundError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        text = args.text
    else:
        parser.error("Provide Hindi text or use --file with a .txt path.")

    try:
        path = synthesize(
            text,
            args.voice,
            speed=args.speed,
            output_format=args.output_format,
            output_name=args.output,
        )
        print(f"Saved: {path}")
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
