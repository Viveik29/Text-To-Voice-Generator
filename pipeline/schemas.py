"""Structured educational content output for competitive exam topics."""

from pydantic import BaseModel, Field, field_validator, model_validator


def _coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        lines = [ln.strip().lstrip("•-* ").strip() for ln in value.splitlines()]
        return [ln for ln in lines if ln]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class ExamNotesReport(BaseModel):
    """Hindi educational multi-asset pack generated from one news topic."""

    title: str = ""
    topic: str = ""
    source_hint: str = ""
    date_hint: str = ""
    theme: str = ""
    gs_paper_mapping: str = ""
    upsc_subjects: list[str] = Field(default_factory=list)
    state_pcs_subjects: list[str] = Field(default_factory=list)
    exam_focus: str = ""
    exam_one_liner: str = ""
    executive_summary: list[str] = Field(default_factory=list)
    prelims_relevance: str = "Medium"
    mains_relevance: str = "Medium"
    interview_relevance: str = "Low"
    state_pcs_relevance: str = "Medium"

    # PART 1–16 (Hindi educational assets)
    hindi_study_notes: str = ""
    complete_background: str = ""
    youtube_script: str = ""
    youtube_meta: str = ""
    powerpoint_slides: str = ""
    infographic_spec: str = ""
    image_generation_prompt: str = ""
    instagram_carousel: str = ""
    telegram_notes: str = ""
    pdf_notes: str = ""
    mcqs: str = ""
    pyqs: str = ""
    mind_map: str = ""
    quick_revision: list[str] = Field(default_factory=list)
    keywords: str = ""
    memory_tricks: str = ""
    expected_questions: str = ""

    full_report_markdown: str = ""
    narration_script: str = ""
    hindi_summary: list[str] = Field(default_factory=list)
    hindi_narration_script: str = ""

    @field_validator("hindi_summary", "executive_summary", "quick_revision", mode="before")
    @classmethod
    def _coerce_lists(cls, value: object) -> list[str]:
        return _coerce_str_list(value)

    @model_validator(mode="after")
    def _sync_spoken_scripts(self) -> "ExamNotesReport":
        spoken = (self.hindi_narration_script or self.youtube_script or self.narration_script or "").strip()
        if spoken:
            if not self.hindi_narration_script.strip():
                self.hindi_narration_script = spoken
            if not self.youtube_script.strip():
                self.youtube_script = spoken
            # Primary narration for the app is always Hindi spoken script
            self.narration_script = spoken
        if not self.topic.strip() and self.title.strip():
            self.topic = self.title
        if not self.full_report_markdown.strip():
            parts = [
                ("## भाग 1 — हिंदी स्टडी नोट्स", self.hindi_study_notes),
                ("## भाग 2 — पूर्ण पृष्ठभूमि", self.complete_background),
                ("## भाग 3 — YouTube स्क्रिप्ट", self.youtube_script),
                ("## भाग 4 — PowerPoint", self.powerpoint_slides),
                ("## भाग 5 — इन्फोग्राफिक", self.infographic_spec),
                ("## भाग 6 — Image Prompt", self.image_generation_prompt),
                ("## भाग 7 — Instagram Carousel", self.instagram_carousel),
                ("## भाग 8 — Telegram Notes", self.telegram_notes),
                ("## भाग 9 — PDF Notes", self.pdf_notes),
                ("## भाग 10 — MCQs", self.mcqs),
                ("## भाग 11 — PYQs", self.pyqs),
                ("## भाग 12 — Mind Map", self.mind_map),
                (
                    "## भाग 13 — Quick Revision",
                    "\n".join(f"- {b}" for b in self.quick_revision),
                ),
                ("## भाग 14 — Keywords", self.keywords),
                ("## भाग 15 — Memory Tricks", self.memory_tricks),
                ("## भाग 16 — Expected Questions", self.expected_questions),
            ]
            blocks = [f"{h}\n\n{b.strip()}" for h, b in parts if b and str(b).strip()]
            if blocks:
                self.full_report_markdown = "\n\n".join(blocks)
        return self


NewsAnalysis = ExamNotesReport
