"""Script Generator - Auto-generate script JSON for News English Shorts.

Uses Google News RSS for article search and Claude API for JSON generation.

Usage:
  python script_generator.py --topic "Iran strikes" --days 3
  python script_generator.py --topic "AI regulation" --days 7 --theme ocean
  python script_generator.py --topic "Apple AI" --days 3 --run
  python script_generator.py --topic "Apple AI" --days 3 --run --no-sd
  python script_generator.py --dry-run scripts/sample_iran_strikes.json
  python script_generator.py                              # interactive mode
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import anthropic


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
SAMPLE_PATH = os.path.join(SCRIPTS_DIR, "sample_iran_strikes.json")

VALID_THEMES = ["midnight", "ocean", "ember", "forest", "purple"]
VALID_ROLES = ["FACT", "DETAIL", "COUNTER", "OUTLOOK"]
MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# 1. Google News RSS search
# ---------------------------------------------------------------------------

def search_news(topic: str, days: int = 3) -> list[dict]:
    """Search Google News RSS and return top 5 articles."""
    query = urllib.parse.quote(topic)
    url = (
        f"https://news.google.com/rss/search?"
        f"q={query}+when:{days}d&hl=en&gl=US&ceid=US:en"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"  Warning: Google News search failed: {e}")
        return []

    root = ET.fromstring(xml_data)
    articles = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        source = item.findtext("source", "")
        if title:
            articles.append({"title": title, "url": link, "source": source})
        if len(articles) >= 5:
            break

    return articles


# ---------------------------------------------------------------------------
# 2. Claude API — JSON generation
# ---------------------------------------------------------------------------

def _load_sample() -> str:
    """Load sample script JSON as few-shot exemplar."""
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        return f.read()


SYSTEM_PROMPT = """\
You are a script writer for "News English Shorts" — 48-second YouTube Shorts \
that teach Japanese learners English through real news.

You MUST output a single JSON object (inside a ```json code fence) that \
strictly follows the schema below. Do NOT output anything else.

## JSON Schema

{
  "id": "<YYYY-MM-DD>_<slug>",          // date + lowercase snake_case slug
  "date": "<YYYY-MM-DD>",
  "topic": "<English topic headline>",
  "theme": "<midnight|ocean|ember|forest|purple>",
  "hook_text": "<Japanese hook question — short, catchy>",

  "sources": [                           // 3+ credible sources
    {"name": "<outlet>", "url": "<url>"}
  ],

  "mission": {
    "ja": "<Japanese listening challenge question>",
    "answer_ja": "答え: <English answer>（<Japanese transliteration>）"
  },

  "source_mentions": [                   // exactly 5 items, one per sentence
    {"sentence_idx": 0, "source": "<outlet>"},
    ...
  ],

  "narration_structure": [               // exactly 5 items
    {"sentence_idx": 0, "role": "FACT"},
    {"sentence_idx": 1, "role": "DETAIL"},
    {"sentence_idx": 2, "role": "FACT"},
    {"sentence_idx": 3, "role": "COUNTER"},
    {"sentence_idx": 4, "role": "OUTLOOK"}
  ],

  "narration": {
    "text": "<exactly 5 English sentences, period-separated>",
    "highlights": ["<word1>", "<word2>", ...]   // 8+ highlight words/phrases
  },

  "insight": {
    "en": "<1-2 sentence English insight/analysis>",
    "ja": "<Japanese translation of insight>"
  },

  "japanese_subtitle_segments": [        // exactly 5 items
    {"text": "<Japanese translation of sentence 1>", "start": 0.0},
    {"text": "<Japanese translation of sentence 2>", "start": 4.5},
    {"text": "<...>", "start": 9.0},
    {"text": "<...>", "start": 13.5},
    {"text": "<...>", "start": 17.5}
  ],

  "data_points": [],                     // optional, can be empty

  "key_phrases": [                       // exactly 3
    {
      "en": "<English phrase>",
      "ja": "<Japanese meaning>",
      "example": "<example sentence using the phrase>"
    }
  ],

  "cta": "保存して3つのフレーズを覚えよう",
  "hashtags": ["#英語学習", "#英語ニュース", "<topic tag>", ...]
}

## CRITICAL RULES

1. narration.text MUST have exactly 5 sentences (split by period).
2. narration.highlights MUST have 8 or more items.
3. sources MUST have 3 or more items with real outlet names.
4. key_phrases MUST have exactly 3 items, each with en, ja, example.
5. japanese_subtitle_segments MUST have exactly 5 items with text and start.
6. source_mentions MUST have exactly 5 items with sentence_idx 0-4.
7. narration_structure MUST have exactly 5 items; role MUST be one of: FACT, DETAIL, COUNTER, OUTLOOK.
8. mission MUST have ja and answer_ja.
9. insight MUST have en and ja.
10. theme MUST be one of: midnight, ocean, ember, forest, purple.
11. ALL numbers in narration.text MUST be spelled out for TTS (e.g. "two hundred million" not "200 million").
12. key_phrases[].example sentences MUST also spell out numbers.
13. hook_text should be a short, catchy Japanese question/statement.
14. id format: YYYY-MM-DD_lowercase_slug (max 30 char slug).
15. Use today's date for the id and date fields.
"""


def generate_script(topic: str, articles: list[dict],
                    theme: str | None = None,
                    prev_errors: list[str] | None = None) -> dict:
    """Call Claude API to generate a script JSON."""
    sample_json = _load_sample()

    # Build user prompt
    article_text = ""
    if articles:
        article_text = "## Recent articles on this topic:\n"
        for i, a in enumerate(articles, 1):
            article_text += f"{i}. {a['title']}"
            if a.get("source"):
                article_text += f" — {a['source']}"
            if a.get("url"):
                article_text += f"\n   {a['url']}"
            article_text += "\n"

    theme_instruction = ""
    if theme and theme != "auto":
        theme_instruction = f'\nUse theme: "{theme}"'
    else:
        theme_instruction = "\nChoose the most appropriate theme based on the topic."

    today = datetime.now().strftime("%Y-%m-%d")

    user_prompt = f"""Generate a News English Shorts script JSON for:

Topic: {topic}
Date: {today}

{article_text}
{theme_instruction}

Use the article information to write factual, informative narration. \
Reference the actual news sources in the sources array.

## Example output (for reference only — adapt to the new topic):

```json
{sample_json}
```
"""

    if prev_errors:
        error_text = "\n".join(f"- {e}" for e in prev_errors)
        user_prompt += f"""

## IMPORTANT: Previous attempt had validation errors. Fix ALL of these:
{error_text}
"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract JSON from response
    response_text = message.content[0].text
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try parsing the whole response as JSON
        json_str = response_text.strip()

    return json.loads(json_str)


# ---------------------------------------------------------------------------
# 3. Validation (16 checks)
# ---------------------------------------------------------------------------

def validate_script(data: dict) -> list[str]:
    """Validate script JSON and return list of error messages."""
    errors = []

    # --- Required top-level fields ---
    required_fields = [
        "id", "date", "topic", "theme", "hook_text", "sources", "mission",
        "narration", "insight", "japanese_subtitle_segments", "key_phrases",
        "cta", "hashtags", "source_mentions", "narration_structure",
    ]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors  # Can't validate further without required fields

    # --- theme ---
    if data["theme"] not in VALID_THEMES:
        errors.append(
            f'theme must be one of {VALID_THEMES}, got "{data["theme"]}"'
        )

    # --- sources ---
    if len(data["sources"]) < 3:
        errors.append(f"sources must have 3+ items, got {len(data['sources'])}")

    # --- narration.text: exactly 5 sentences ---
    narration = data.get("narration", {})
    text = narration.get("text", "")
    # Split on period followed by space or end-of-string (avoids "Investing.com" etc.)
    sentences = [s.strip() for s in re.split(r"\.\s+|\.\s*$", text) if s.strip()]
    if len(sentences) != 5:
        errors.append(
            f"narration.text must have exactly 5 sentences (period-separated), "
            f"got {len(sentences)}"
        )

    # --- narration.highlights: 8+ ---
    highlights = narration.get("highlights", [])
    if len(highlights) < 8:
        errors.append(
            f"narration.highlights must have 8+ items, got {len(highlights)}"
        )

    # --- key_phrases: exactly 3 ---
    kp = data.get("key_phrases", [])
    if len(kp) != 3:
        errors.append(f"key_phrases must have exactly 3 items, got {len(kp)}")
    for i, phrase in enumerate(kp):
        for key in ("en", "ja", "example"):
            if key not in phrase:
                errors.append(f"key_phrases[{i}] missing '{key}'")

    # --- japanese_subtitle_segments: exactly 5 ---
    jss = data.get("japanese_subtitle_segments", [])
    if len(jss) != 5:
        errors.append(
            f"japanese_subtitle_segments must have 5 items, got {len(jss)}"
        )
    for i, seg in enumerate(jss):
        if "text" not in seg:
            errors.append(f"japanese_subtitle_segments[{i}] missing 'text'")
        if "start" not in seg:
            errors.append(f"japanese_subtitle_segments[{i}] missing 'start'")

    # --- source_mentions: exactly 5, sentence_idx 0-4 ---
    sm = data.get("source_mentions", [])
    if len(sm) != 5:
        errors.append(f"source_mentions must have 5 items, got {len(sm)}")
    for i, mention in enumerate(sm):
        idx = mention.get("sentence_idx")
        if idx is None or idx not in range(5):
            errors.append(
                f"source_mentions[{i}].sentence_idx must be 0-4, got {idx}"
            )

    # --- narration_structure: exactly 5, valid roles ---
    ns = data.get("narration_structure", [])
    if len(ns) != 5:
        errors.append(
            f"narration_structure must have 5 items, got {len(ns)}"
        )
    for i, entry in enumerate(ns):
        role = entry.get("role")
        if role not in VALID_ROLES:
            errors.append(
                f"narration_structure[{i}].role must be one of {VALID_ROLES}, "
                f"got \"{role}\""
            )

    # --- mission ---
    mission = data.get("mission", {})
    if "ja" not in mission:
        errors.append("mission missing 'ja'")
    if "answer_ja" not in mission:
        errors.append("mission missing 'answer_ja'")

    # --- insight ---
    insight = data.get("insight", {})
    if "en" not in insight:
        errors.append("insight missing 'en'")
    if "ja" not in insight:
        errors.append("insight missing 'ja'")

    # --- Numbers spelled out in narration ---
    digit_pattern = re.compile(r"\b\d{2,}\b")  # 2+ digit numbers
    if digit_pattern.search(text):
        found = digit_pattern.findall(text)
        errors.append(
            f"narration.text contains unspelled numbers (TTS requires spelled-out): "
            f"{found}"
        )

    return errors


# ---------------------------------------------------------------------------
# 4. CLI / Interactive
# ---------------------------------------------------------------------------

def _make_slug(topic: str) -> str:
    """Convert topic to a filename-safe slug."""
    slug = topic.lower()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug).strip("_")
    return slug[:30]


def interactive_prompt() -> tuple[str, int, str]:
    """Prompt user for topic, days, and theme interactively."""
    topic = input("Topic (English): ").strip()
    if not topic:
        print("Topic is required.")
        sys.exit(1)

    days_input = input("Search period (days) [3]: ").strip()
    days = int(days_input) if days_input else 3

    theme_input = input(
        "Theme (auto/midnight/ocean/ember/forest/purple) [auto]: "
    ).strip().lower()
    theme = theme_input if theme_input else "auto"

    return topic, days, theme


def main():
    parser = argparse.ArgumentParser(
        description="Script Generator - Auto-generate script JSON for News English Shorts"
    )
    parser.add_argument("--topic", help="News topic (English recommended)")
    parser.add_argument("--days", type=int, default=3, help="Search period in days (default: 3)")
    parser.add_argument(
        "--theme", default="auto",
        help="Theme: auto/midnight/ocean/ember/forest/purple (default: auto)"
    )
    parser.add_argument(
        "--run", action="store_true",
        help="Run video generation pipeline after script creation"
    )
    parser.add_argument(
        "--no-sd", action="store_true",
        help="Disable Stable Diffusion backgrounds (with --run)"
    )
    parser.add_argument(
        "--smart-bg", action="store_true",
        help="Use Claude AI for SD background prompts (with --run)"
    )
    parser.add_argument(
        "--voice", default="male_us",
        help="TTS voice for --run (default: male_us)"
    )
    parser.add_argument(
        "--tts", choices=["edge", "elevenlabs"], default="edge",
        help="TTS engine for --run (default: edge)"
    )
    parser.add_argument(
        "--dry-run", metavar="FILE",
        help="Validate an existing JSON file (no API calls)"
    )

    args = parser.parse_args()

    # --- Dry-run mode: validate existing JSON ---
    if args.dry_run:
        print(f"Validating: {args.dry_run}")
        with open(args.dry_run, "r", encoding="utf-8") as f:
            data = json.load(f)
        errors = validate_script(data)
        if errors:
            print(f"\nValidation FAILED ({len(errors)} errors):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("Validation PASSED")
            return

    # --- Get topic (CLI or interactive) ---
    if args.topic:
        topic = args.topic
        days = args.days
        theme = args.theme
    else:
        topic, days, theme = interactive_prompt()

    # --- Step 1: Search news ---
    print(f"\n[1/3] Searching Google News: \"{topic}\" (past {days} days)...")
    articles = search_news(topic, days)
    if articles:
        print(f"  Found {len(articles)} articles:")
        for a in articles:
            source = f" — {a['source']}" if a.get("source") else ""
            print(f"    - {a['title']}{source}")
    else:
        print("  No articles found. Generating from topic name only.")

    # --- Step 2: Generate script with retries ---
    print(f"\n[2/3] Generating script JSON via Claude API ({MODEL})...")
    os.makedirs(SCRIPTS_DIR, exist_ok=True)

    prev_errors = None
    script_data = None

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"\n  Retry {attempt}/{MAX_RETRIES} (fixing {len(prev_errors)} errors)...")

        try:
            script_data = generate_script(
                topic, articles,
                theme=theme if theme != "auto" else None,
                prev_errors=prev_errors,
            )
        except json.JSONDecodeError as e:
            prev_errors = [f"Invalid JSON in API response: {e}"]
            print(f"  JSON parse error: {e}")
            if attempt == MAX_RETRIES:
                print(f"\nFailed after {MAX_RETRIES} attempts.")
                sys.exit(1)
            continue
        except anthropic.APIError as e:
            print(f"\nClaude API error: {e}")
            sys.exit(1)

        errors = validate_script(script_data)
        if not errors:
            print("  Validation passed!")
            break
        else:
            print(f"  Validation failed ({len(errors)} errors):")
            for e in errors:
                print(f"    - {e}")
            prev_errors = errors
            if attempt == MAX_RETRIES:
                print(f"\nFailed after {MAX_RETRIES} attempts.")
                sys.exit(1)

    # --- Step 3: Save ---
    today = datetime.now().strftime("%Y-%m-%d")
    slug = _make_slug(topic)
    filename = f"{today}_{slug}.json"
    output_path = os.path.join(SCRIPTS_DIR, filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    print(f"\n[3/3] Saved: {output_path}")

    # --- Optional: run video pipeline ---
    if args.run:
        print("\nStarting video generation pipeline...")
        sys.path.insert(0, PROJECT_DIR)
        from main import process_script
        from tts_generator import VOICES

        voice = VOICES.get(args.voice, args.voice)
        use_sd = not args.no_sd
        smart_bg = args.smart_bg
        process_script(output_path, voice=voice, use_sd=use_sd,
                       smart_bg=smart_bg, tts_engine=args.tts)


if __name__ == "__main__":
    main()
