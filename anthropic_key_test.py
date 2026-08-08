"""Quick check that ANTHROPIC_API_KEY is valid."""

import os

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
    max_tokens=200,
    messages=[
        {
            "role": "user",
            "content": "Hello Claude! Tell me one fun fact about AI.",
        }
    ],
)

print(response.content[0].text)
