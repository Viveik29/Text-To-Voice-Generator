"""Claude agent configuration for competitive exam news analysis."""

import os

from agents.news_analyst.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
SYSTEM_INSTRUCTION = SYSTEM_PROMPT
