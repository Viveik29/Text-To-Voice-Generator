"""Generate agent-flow.png — agent-centric view of the News Analyst pipeline."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "agent-flow.png"
W, H = 1400, 2000

# Palette
BG = (11, 18, 32)
PANEL = (18, 26, 43)
CYAN = (34, 211, 238)
BLUE = (59, 130, 246)
VIOLET = (139, 92, 246)
PINK = (236, 72, 153)
GREEN = (34, 197, 94)
AMBER = (245, 158, 11)
TEAL = (20, 184, 166)
INK = (232, 238, 252)
MUTED = (148, 163, 184)
WHITE = (255, 255, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    radius: int = 16,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _arrow_down(draw: ImageDraw.ImageDraw, x: int, y1: int, y2: int, color: tuple[int, int, int]) -> None:
    draw.line([(x, y1), (x, y2 - 10)], fill=color, width=3)
    draw.polygon([(x, y2), (x - 8, y2 - 14), (x + 8, y2 - 14)], fill=color)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _text_block(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    lines: list[str],
    font,
    fill: tuple[int, int, int],
    line_gap: int = 6,
) -> int:
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        cy += font.size + line_gap
    return cy


def main() -> Path:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    title_f = _font(34, bold=True)
    h_f = _font(20, bold=True)
    sub_f = _font(15, bold=True)
    body_f = _font(13)
    small_f = _font(11)

    # Title
    title = "News Analyst Agent — How It Works"
    tw = draw.textlength(title, font=title_f)
    draw.text(((W - tw) / 2, 28), title, font=title_f, fill=CYAN)
    sub = "Agent's point of view  ·  Claude-powered educational content generator"
    sw = draw.textlength(sub, font=body_f)
    draw.text(((W - sw) / 2, 72), sub, font=body_f, fill=MUTED)

    y = 110

    # === AGENT IDENTITY ===
    box = (60, y, W - 60, y + 100)
    _rounded_rect(draw, box, (30, 41, 59), VIOLET, 18)
    draw.text((80, y + 16), "AGENT IDENTITY", font=sub_f, fill=VIOLET)
    draw.text((80, y + 42), "agents/news_analyst/  →  Claude (claude-sonnet-5)", font=h_f, fill=INK)
    draw.text(
        (80, y + 70),
        "Role: Hindi Educational Content Creator for UPSC · SSC · Banking · State PCS",
        font=body_f,
        fill=MUTED,
    )
    y += 120
    _arrow_down(draw, W // 2, y, y + 36, CYAN)
    y += 44

    # === INPUT ===
    box = (60, y, W - 60, y + 130)
    _rounded_rect(draw, box, (15, 76, 92), CYAN, 18)
    draw.text((80, y + 14), "WHAT THE AGENT RECEIVES (from pipeline/runner.py)", font=sub_f, fill=CYAN)
    inputs = [
        "• Clean article text (from paste, PDF TXT, or headline fetch)",
        "• Exam focus label (e.g. UPSC Prelims, SSC, Banking)",
        "• Optional article selector / page hint",
        "• System prompt + user prompt assembled by pipeline/analyzer.py",
    ]
    cy = y + 42
    for line in inputs:
        draw.text((90, cy), line, font=body_f, fill=INK)
        cy += 22
    y += 150
    _arrow_down(draw, W // 2, y, y + 36, BLUE)
    y += 44

    # === AGENT BRAIN ===
    box = (60, y, W - 60, y + 200)
    _rounded_rect(draw, box, (49, 46, 129), PINK, 18)
    draw.text((80, y + 14), "AGENT BRAIN — SYSTEM INSTRUCTION", font=sub_f, fill=PINK)
    rules = [
        "1. Read article ONLY to identify the topic — never rewrite the newspaper",
        "2. Generate ORIGINAL Hindi educational content (Devanagari)",
        "3. Teacher persona: calm senior coaching teacher, not news anchor",
        "4. Auto-explain: geography, constitution, laws, history, science, environment",
        "5. TTS rules: spoken Hindi only — no markdown, bullets, or symbols in scripts",
    ]
    cy = y + 44
    for line in rules:
        draw.text((90, cy), line, font=body_f, fill=INK)
        cy += 28
    y += 220
    _arrow_down(draw, W // 2, y, y + 36, VIOLET)
    y += 44

    # === PROCESSING ===
    box = (60, y, W - 60, y + 120)
    _rounded_rect(draw, box, (76, 29, 149), VIOLET, 18)
    draw.text((80, y + 14), "AGENT PROCESSING (analyzer.py)", font=sub_f, fill=VIOLET)
    steps = [
        "Stream to Claude API  →  Receive JSON response  →  Parse ExamNotesReport",
        "Retry if JSON invalid  ·  Fallback to markdown if needed",
    ]
    cy = y + 44
    for line in steps:
        draw.text((90, cy), line, font=body_f, fill=INK)
        cy += 26
    y += 140
    _arrow_down(draw, W // 2, y, y + 36, GREEN)
    y += 44

    # === 16 PARTS GRID ===
    draw.text((80, y), "AGENT OUTPUT — 16 EDUCATIONAL PARTS (generated in one JSON)", font=h_f, fill=GREEN)
    y += 36

    parts = [
        ("1", "Hindi Study Notes", CYAN),
        ("2", "Background", BLUE),
        ("3", "YouTube Script", TEAL),
        ("4", "PowerPoint", VIOLET),
        ("5", "Infographic", PINK),
        ("6", "Image Prompt", AMBER),
        ("7", "Instagram", PINK),
        ("8", "Telegram", TEAL),
        ("9", "PDF Notes", BLUE),
        ("10", "MCQs", GREEN),
        ("11", "PYQs", GREEN),
        ("12", "Mind Map", VIOLET),
        ("13", "Quick Revision", CYAN),
        ("14", "Keywords", AMBER),
        ("15", "Memory Tricks", PINK),
        ("16", "Expected Qs", GREEN),
    ]

    cols, rows = 4, 4
    cw, ch, gap = 300, 58, 14
    sx = 80
    for i, (num, label, color) in enumerate(parts):
        col = i % cols
        row = i // cols
        x1 = sx + col * (cw + gap)
        y1 = y + row * (ch + gap)
        x2, y2 = x1 + cw, y1 + ch
        _rounded_rect(draw, (x1, y1, x2, y2), PANEL, color, 12, 2)
        draw.text((x1 + 12, y1 + 8), f"PART {num}", font=small_f, fill=color)
        draw.text((x1 + 12, y1 + 28), label, font=body_f, fill=INK)

    y += 4 * (ch + gap) + 20
    _arrow_down(draw, W // 2, y, y + 36, AMBER)
    y += 44

    # === HANDOFF ===
    box = (60, y, W - 60, y + 150)
    _rounded_rect(draw, box, (20, 83, 45), GREEN, 18)
    draw.text((80, y + 14), "AFTER AGENT FINISHES — pipeline/runner.py takes over", font=sub_f, fill=GREEN)
    handoff = [
        "Save claude_response.json + claude_response.md under artifacts/<headline>/",
        "Split Parts 1–16 into educational_assets/ folder",
        "Generate report.pdf  ·  hindi_script.txt  ·  hindi_narration.mp3 (gTTS)",
        "Show results in Streamlit UI with download buttons",
    ]
    cy = y + 44
    for line in handoff:
        draw.text((90, cy), line, font=body_f, fill=INK)
        cy += 26

    y += 170

    # === FLOW SUMMARY BAR ===
    box = (60, y, W - 60, y + 72)
    _rounded_rect(draw, box, (30, 41, 59), CYAN, 14)
    flow = (
        "Article Text  →  Agent (Claude)  →  JSON (16 Parts)  →  "
        "Validate  →  Save Headline Folder  →  Hindi Audio"
    )
    fw = draw.textlength(flow, font=body_f)
    draw.text(((W - fw) / 2, y + 26), flow, font=body_f, fill=INK)

    # Footer
    foot = "TEXT_TO_VOICE_GENERATOR  ·  agents/news_analyst + pipeline/analyzer.py"
    fw2 = draw.textlength(foot, font=small_f)
    draw.text(((W - fw2) / 2, H - 36), foot, font=small_f, fill=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"Saved: {OUT} ({OUT.stat().st_size:,} bytes)")
    return OUT


if __name__ == "__main__":
    main()
