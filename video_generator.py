"""Video generation pipeline v8.6 - Smooth transitions + JA char limit.

v8.6 changes:
- Section cards 0.8→1.5s for clear phase boundaries
- All fad/animation speeds ~2x slower for smooth, calm transitions
- Per-sentence flashes softened (alpha + duration)
- JA subtitle auto font-size reduction for long text (>28 chars)
- CAPTION_LINGER 0.6→0.8 for longer word display

v8.5: Section transition cards (LISTEN/INSIGHT/KEY PHRASES/ANSWER)
v8.4: WORDS_PER_GROUP 10, WordEN 42pt, JASub 30pt, layout overhaul
"""

import json
import os
import subprocess

WIDTH = 1080
HEIGHT = 1920

# Phase timing
HOOK_DURATION = 3.5
NARRATION_OFFSET = 5.0       # HOOK_DURATION + SECTION_CARD_DURATION (card finishes before audio)
KEY_PHRASES_FALLBACK = 6.0   # fallback when no KP audio
ANSWER_DURATION = 3.5
OUTRO_DURATION = 3.0
WORDS_PER_GROUP = 10
CAPTION_LINGER = 0.8         # extra display time per word group for readability
SECTION_CARD_DURATION = 1.5  # section transition card overlay duration

FONT_EN = "Arial"
FONT_JA = "Noto Sans JP"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BG_DIR = os.path.join(PROJECT_DIR, "backgrounds")
AUDIO_DIR = os.path.join(PROJECT_DIR, "audio")

BRAND_NAME = "30-sec News English"

# Source colors (ASS BGR format)
SOURCE_COLORS = [
    "&H0066BBFF&",   # warm orange
    "&H00FFCC66&",   # cyan-blue
    "&H0066FFAA&",   # lime green
    "&H00DD88FF&",   # magenta-pink
]

ROLE_LABELS = {
    "FACT":    {"icon": "\u25A0", "color": "&H0066BBFF&"},
    "DETAIL":  {"icon": "\u25B6", "color": "&H00FFCC66&"},
    "COUNTER": {"icon": "\u25C6", "color": "&H004466FF&"},
    "OUTLOOK": {"icon": "\u2605", "color": "&H00AAFFAA&"},
}


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _get_theme_colors(theme: str) -> dict:
    from bg_generator import THEME_ACCENTS
    return THEME_ACCENTS.get(theme, THEME_ACCENTS["midnight"])


def _build_source_color_map(sources: list) -> dict:
    color_map = {}
    for i, src in enumerate(sources):
        color_map[src["name"]] = SOURCE_COLORS[i % len(SOURCE_COLORS)]
    return color_map


def _get_highlighted_word_indices(text: str, highlights: list) -> set:
    words = text.split()
    highlighted = set()
    positions = []
    pos = 0
    for i, word in enumerate(words):
        idx = text.find(word, pos)
        if idx == -1:
            idx = pos
        positions.append((idx, idx + len(word)))
        pos = idx + len(word)

    lower_text = text.lower()
    for hl in highlights:
        hl_lower = hl.lower()
        search_start = 0
        while True:
            idx = lower_text.find(hl_lower, search_start)
            if idx == -1:
                break
            hl_end = idx + len(hl)
            for wi, (ws, we) in enumerate(positions):
                if ws < hl_end and we > idx:
                    highlighted.add(wi)
            search_start = idx + len(hl)
    return highlighted


def _estimate_word_groups(timing_data: list, highlights: list, group_size: int = 3) -> list:
    all_groups = []
    for sent_idx, sent in enumerate(timing_data):
        words = sent["text"].split()
        if not words:
            continue
        total_chars = max(1, sum(len(w) for w in words))
        duration = sent["end_s"] - sent["start_s"]

        hl_indices = _get_highlighted_word_indices(sent["text"], highlights)

        cursor_time = sent["start_s"]
        groups = []
        for i in range(0, len(words), group_size):
            chunk_words = words[i:i + group_size]
            chunk_chars = max(1, sum(len(w) for w in chunk_words))
            chunk_dur = duration * (chunk_chars / total_chars)
            chunk_highlighted = [i + j in hl_indices for j in range(len(chunk_words))]
            groups.append({
                "words": chunk_words,
                "highlighted": chunk_highlighted,
                "start": cursor_time,
                "end": cursor_time + chunk_dur,
                "sentence_idx": sent_idx,
            })
            cursor_time += chunk_dur

        if len(groups) > 1 and len(groups[-1]["words"]) == 1:
            groups[-2]["words"].extend(groups[-1]["words"])
            groups[-2]["highlighted"].extend(groups[-1]["highlighted"])
            groups[-2]["end"] = groups[-1]["end"]
            groups.pop()

        all_groups.extend(groups)
    return all_groups


def _add_section_card(events, t, num, total, title_en, title_ja, accent, duration=None):
    """Add a section transition card overlay (dark scrim + title + JA)."""
    dur = duration if duration is not None else SECTION_CARD_DURATION
    t_end = t + dur

    if dur >= 1.2:
        # Full card (1.5s) - leisurely pace
        scrim_t = f"\\t(1000,1500,\\alpha&HFF&)"
        num_fad = "\\fad(200,350)"
        title_fad = "\\fad(150,400)"
        title_anim = "\\fscx120\\fscy120\\t(0,450,\\fscx100\\fscy100)"
        sub_fad = "\\fad(250,400)\\alpha&H40&"
        sub_delay = 0.25
    else:
        # Short card (0.8s) - quick label
        scrim_t = f"\\t(480,800,\\alpha&HFF&)"
        num_fad = "\\fad(100,200)"
        title_fad = "\\fad(80,250)"
        title_anim = "\\fscx115\\fscy115\\t(0,250,\\fscx100\\fscy100)"
        sub_fad = "\\fad(120,250)\\alpha&H40&"
        sub_delay = 0.12

    # Dark scrim
    events.append(
        f"Dialogue: 35,{_ass_time(t - 0.1)},{_ass_time(t_end)},Flash,,0,0,0,,"
        f"{{\\alpha&H10&{scrim_t}\\p1}}"
        f"m 0 0 l {WIDTH} 0 l {WIDTH} {HEIGHT} l 0 {HEIGHT}{{\\p0}}"
    )
    # Section number
    events.append(
        f"Dialogue: 40,{_ass_time(t + 0.08)},{_ass_time(t_end - 0.1)},SectionTitle,,0,0,0,,"
        f"{{\\an5\\pos(540,840)\\fs22\\c{accent}{num_fad}}}"
        f"\u2501\u2501  {num:02d} / {total:02d}  \u2501\u2501"
    )
    # Main title
    events.append(
        f"Dialogue: 40,{_ass_time(t + 0.08)},{_ass_time(t_end - 0.05)},SectionTitle,,0,0,0,,"
        f"{{\\an5\\pos(540,910){title_anim}{title_fad}}}"
        f"{title_en}"
    )
    # Japanese subtitle
    events.append(
        f"Dialogue: 40,{_ass_time(t + sub_delay)},{_ass_time(t_end - 0.05)},SectionSub,,0,0,0,,"
        f"{{\\an5\\pos(540,985){sub_fad}}}"
        f"{title_ja}"
    )


def _generate_ass(script: dict, timing_data: list, total_duration: float,
                  narr_sentence_count: int, kp_timing_data: list | None = None,
                  kp_phase_start: float = 0, insight_phase_start: float = 0) -> str:
    """Generate v8 ASS subtitle file."""
    narration = script["narration"]
    ja_segments = script["japanese_subtitle_segments"]
    key_phrases = script["key_phrases"]
    mission = script["mission"]
    topic = script["topic"]
    cta = script.get("cta", "")
    sources = script.get("sources", [])
    data_points = script.get("data_points", [])
    highlights = narration.get("highlights", [])
    theme = script.get("theme", "midnight")
    hook_text = script.get("hook_text", "")
    insight = script.get("insight", {})
    insight_ja = insight.get("ja", "")

    if not sources and script.get("source"):
        sources = [{"name": script["source"], "url": script.get("source_url", "")}]

    source_mentions = script.get("source_mentions", [])
    narration_structure = script.get("narration_structure", [])

    colors = _get_theme_colors(theme)
    accent = colors["accent"]
    highlight_clr = colors["highlight"]

    source_color_map = _build_source_color_map(sources)
    sent_source_map = {}
    for sm in source_mentions:
        sent_source_map[sm["sentence_idx"]] = sm["source"]
    sent_role_map = {}
    for ns in narration_structure:
        sent_role_map[ns["sentence_idx"]] = ns["role"]

    # Split timing into narration vs insight
    narr_timing = timing_data[:narr_sentence_count]
    insight_timing = timing_data[narr_sentence_count:]
    num_narr_sentences = len(narr_timing)

    word_groups = _estimate_word_groups(narr_timing, highlights, WORDS_PER_GROUP)

    # Insight word groups (no highlights)
    insight_word_groups = _estimate_word_groups(insight_timing, [], WORDS_PER_GROUP) if insight_timing else []

    # KP timing
    kp_count = len(key_phrases)
    if kp_timing_data and len(kp_timing_data) >= kp_count:
        kp_end = kp_phase_start + kp_timing_data[-1]["end_s"] + 0.5
    else:
        kp_end = kp_phase_start + KEY_PHRASES_FALLBACK

    # ================================================================
    # ASS HEADER
    # ================================================================
    ass = f"""[Script Info]
Title: {BRAND_NAME}
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brand,{FONT_EN},22,&H60FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,1,0,9,30,30,30,1
Style: Topic,{FONT_EN},30,&H00FFFFFF,&H000000FF,&HA0101028,&HA0101028,1,0,0,0,100,100,1,0,3,14,0,8,30,100,70,1
Style: AccentBar,{FONT_EN},2,{accent},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,80,100,120,1
Style: Source,{FONT_EN},18,&HA0FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,1,30,30,48,1
Style: SourceTag,{FONT_EN},20,{accent},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,2,0,1,1,0,7,30,100,176,1
Style: DataVal,{FONT_EN},80,{accent},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,3,8,60,120,400,1
Style: DataLabel,{FONT_EN},26,&H00FFFFFF,&H000000FF,&HC0101028,&HC0101028,0,0,0,0,100,100,0,0,3,10,0,8,80,120,500,1
Style: IntroHook,{FONT_JA},48,&H00FFFFFF,&H000000FF,&HA0101028,&HA0101028,1,0,0,0,100,100,0,0,3,20,0,8,60,120,500,1
Style: HookQ,{FONT_JA},50,&H00FFFFFF,&H000000FF,&HA0101028,&HA0101028,1,0,0,0,100,100,0,0,3,20,0,5,60,120,0,1
Style: HookLabel,{FONT_EN},32,{accent},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,3,0,1,3,0,8,20,100,560,1
Style: PhaseLabel,{FONT_EN},22,{accent},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,1,0,8,20,100,540,1
Style: Progress,{FONT_EN},24,{accent},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,6,0,1,0,0,7,30,100,152,1
Style: WordEN,{FONT_EN},42,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,2,8,50,50,660,1
Style: JASub,{FONT_JA},30,&H0000FFFF,&H000000FF,&HC0101028,&HC0101028,0,0,0,0,100,100,0,0,3,12,0,8,50,80,800,1
Style: KPNum,{FONT_EN},90,{accent},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,3,8,20,100,440,1
Style: KPPhrase,{FONT_EN},50,{highlight_clr},&H000000FF,&HC0101028,&HC0101028,1,0,0,0,100,100,0,0,3,18,0,8,60,120,620,1
Style: KPTrans,{FONT_JA},34,&H00FFFFFF,&H000000FF,&HC0101028,&HC0101028,0,0,0,0,100,100,0,0,3,12,0,8,80,120,740,1
Style: KPEx,{FONT_EN},24,&H80FFFFFF,&H000000FF,&HC0101028,&HC0101028,0,1,0,0,100,100,0,0,3,10,0,8,100,120,840,1
Style: KPDots,{FONT_EN},28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,8,0,1,0,0,8,20,100,920,1
Style: AnswerLabel,{FONT_EN},68,{accent},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,2,0,1,5,3,8,20,100,380,1
Style: AnswerText,{FONT_JA},38,&H00FFFFFF,&H000000FF,&HC0101028,&HC0101028,0,0,0,0,100,100,0,0,3,16,0,8,60,80,540,1
Style: CTA,{FONT_JA},30,{accent},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,8,20,100,740,1
Style: Replay,{FONT_JA},40,&H00FFFFFF,&H000000FF,&HC0101028,&HC0101028,1,0,0,0,100,100,0,0,3,16,0,5,60,120,0,1
Style: SourceCurrent,{FONT_EN},20,&H00FFFFFF,&H000000FF,&HC0101028,&HC0101028,1,0,0,0,100,100,1,0,3,8,0,7,30,100,200,1
Style: SentRole,{FONT_EN},16,&H80FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,1,0,7,30,100,228,1
Style: ConnBar,{FONT_EN},2,{accent},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,80,80,775,1
Style: SectionTitle,{FONT_EN},56,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,4,0,1,4,3,5,0,0,0,1
Style: SectionSub,{FONT_JA},28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,5,0,0,0,1
Style: Flash,{FONT_EN},10,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    # ================================================================
    # PERSISTENT ELEMENTS
    # ================================================================
    events.append(
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(total_duration)},Brand,,0,0,0,,"
        f"{{\\fad(800,400)\\alpha&H60&}}{BRAND_NAME}"
    )
    events.append(
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(total_duration)},Topic,,0,0,0,,"
        f"{{\\fad(200,400)}}  {topic}  "
    )
    events.append(
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(total_duration)},AccentBar,,0,0,0,,"
        f"{{\\fad(400,400)\\p1}}m 0 0 l 820 0 l 820 3 l 0 3{{\\p0}}"
    )
    if sources:
        events.append(
            f"Dialogue: 1,{_ass_time(0)},{_ass_time(total_duration)},SourceTag,,0,0,0,,"
            f"{{\\fad(400,400)}}{len(sources)} SOURCES"
        )

    # ================================================================
    # PHASE 1: HOOK (0 ~ 3.5s) - IntroHook → CHALLENGE → mission
    # ================================================================
    he = _ass_time(HOOK_DURATION)

    # Hook text (0.0 - 2.2s) - dramatic pop-in, gentler pace
    if hook_text:
        events.append(
            f"Dialogue: 15,{_ass_time(0.0)},{_ass_time(2.2)},IntroHook,,0,0,0,,"
            f"{{\\fscx130\\fscy130\\t(0,600,\\fscx100\\fscy100)\\fad(150,500)}}  {hook_text}  "
        )

    # CHALLENGE label (1.6 - 3.5s)
    events.append(
        f"Dialogue: 10,{_ass_time(1.6)},{he},HookLabel,,0,0,0,,"
        f"{{\\fscx120\\fscy120\\t(0,500,\\fscx100\\fscy100)\\fad(250,400)}}CHALLENGE"
    )

    # Mission question (2.0 - 3.5s)
    events.append(
        f"Dialogue: 15,{_ass_time(2.0)},{he},HookQ,,0,0,0,,"
        f"{{\\fscx108\\fscy108\\t(0,400,\\fscx100\\fscy100)\\fad(350,400)}}  {mission['ja']}  "
    )

    # ================================================================
    # PHASE 2: NARRATION - Word-by-word captions + progress dots
    # ================================================================
    narr_start = NARRATION_OFFSET
    narr_end = narr_timing[-1]["end_s"] + NARRATION_OFFSET if narr_timing else 28

    # Section card: LISTEN (plays during gap before narration audio starts)
    _add_section_card(events, narr_start - SECTION_CARD_DURATION, 1, 4,
                      "LISTEN", "\u30cb\u30e5\u30fc\u30b9\u3092\u8074\u3053\u3046", accent)
    events.append(
        f"Dialogue: 5,{_ass_time(narr_start + SECTION_CARD_DURATION)},{_ass_time(narr_end)},PhaseLabel,,0,0,0,,"
        f"{{\\fad(400,300)}}LISTEN"
    )

    # Per-sentence: progress dots + source badge + role label + connector
    for si in range(num_narr_sentences):
        s_start = narr_timing[si]["start_s"] + NARRATION_OFFSET
        s_end = narr_timing[si]["end_s"] + NARRATION_OFFSET

        # Progress dots
        dots_parts = []
        for di in range(num_narr_sentences):
            if di <= si:
                dots_parts.append("{\\c" + accent + "}\u25CF")
            else:
                dots_parts.append("{\\c&H60FFFFFF&}\u25CB")
        events.append(
            f"Dialogue: 5,{_ass_time(s_start)},{_ass_time(s_end)},Progress,,0,0,0,,"
            f"{{\\fad(300,200)}}{' '.join(dots_parts)}"
        )

        # Source badge
        src_name = sent_source_map.get(si)
        if src_name:
            src_color = source_color_map.get(src_name, accent)
            events.append(
                f"Dialogue: 6,{_ass_time(s_start)},{_ass_time(s_end)},SourceCurrent,,0,0,0,,"
                f"{{\\fad(350,250)\\c{src_color}}}  \u25C9 {src_name}  "
            )

        # Role label
        role = sent_role_map.get(si)
        if role and role in ROLE_LABELS:
            rl = ROLE_LABELS[role]
            events.append(
                f"Dialogue: 6,{_ass_time(s_start)},{_ass_time(s_end)},SentRole,,0,0,0,,"
                f"{{\\fad(350,250)\\c{rl['color']}}}{rl['icon']} {role}"
            )

        # Connector bar
        events.append(
            f"Dialogue: 4,{_ass_time(s_start)},{_ass_time(s_end)},ConnBar,,0,0,0,,"
            f"{{\\fad(350,250)\\p1}}m 0 0 l 800 0 l 800 2 l 0 2{{\\p0}}"
        )

    # Per-sentence colored flash (softened)
    for si in range(1, num_narr_sentences):
        flash_t = narr_timing[si]["start_s"] + NARRATION_OFFSET
        src_name = sent_source_map.get(si)
        flash_color = source_color_map.get(src_name, "&H00FFFFFF&") if src_name else "&H00FFFFFF&"
        events.append(
            f"Dialogue: 25,{_ass_time(flash_t - 0.02)},{_ass_time(flash_t + 0.22)},Flash,,0,0,0,,"
            f"{{\\c{flash_color}\\3c{flash_color}\\4c{flash_color}"
            f"\\alpha&HC8&\\t(0,220,\\alpha&HFF&)\\p1}}"
            f"m 0 0 l {WIDTH} 0 l {WIDTH} {HEIGHT} l 0 {HEIGHT}{{\\p0}}"
        )

    # Source name color map for word captions
    _source_word_colors = {}
    for src in sources:
        src_color = source_color_map.get(src["name"], accent)
        for w in src["name"].split():
            _source_word_colors[w.lower()] = src_color

    # Word-by-word English captions (with linger for readability)
    for gi, group in enumerate(word_groups):
        start = group["start"] + NARRATION_OFFSET
        raw_end = group["end"] + NARRATION_OFFSET
        # Extend display but don't overlap too much with next group
        if gi + 1 < len(word_groups):
            next_start = word_groups[gi + 1]["start"] + NARRATION_OFFSET
            end = min(raw_end + CAPTION_LINGER, next_start + 0.12)
        else:
            end = min(raw_end + CAPTION_LINGER, narr_end)
        parts = []
        for word, is_hl in zip(group["words"], group["highlighted"]):
            clean = word.strip(".,;:!?\"'()").lower()
            src_clr = _source_word_colors.get(clean)
            if is_hl:
                parts.append(
                    "{\\c&HE0DDFF&}" + word +
                    "{\\c&HFFFFFF&}"
                )
            elif src_clr:
                parts.append(
                    "{\\c&HE8E0E0&}" + word +
                    "{\\c&HFFFFFF&}"
                )
            else:
                parts.append(word)
        display_text = " ".join(parts)
        events.append(
            f"Dialogue: 10,{_ass_time(start)},{_ass_time(end)},WordEN,,0,0,0,,"
            f"{{\\fscx105\\fscy105\\t(0,300,\\fscx100\\fscy100)\\fad(200,150)}}{display_text}"
        )

    # Data point overlays
    for dp in data_points:
        si = dp.get("sentence_idx", 0)
        if si < len(narr_timing):
            dp_start = narr_timing[si]["start_s"] + NARRATION_OFFSET
            dp_end = narr_timing[si]["end_s"] + NARRATION_OFFSET
            events.append(
                f"Dialogue: 20,{_ass_time(dp_start)},{_ass_time(dp_end)},DataVal,,0,0,0,,"
                f"{{\\fscx130\\fscy130\\t(0,500,\\fscx100\\fscy100)\\fad(400,350)}}{dp['value']}"
            )
            events.append(
                f"Dialogue: 20,{_ass_time(dp_start + 0.2)},{_ass_time(dp_end)},DataLabel,,0,0,0,,"
                f"{{\\fad(450,350)}}  {dp['label']}  "
            )

    # --- Japanese subtitles (auto font-size for long text) ---
    for i, seg in enumerate(ja_segments):
        if i < len(narr_timing):
            start = narr_timing[i]["start_s"] + NARRATION_OFFSET
            if i + 1 < len(narr_timing):
                end = narr_timing[i + 1]["start_s"] + NARRATION_OFFSET
            else:
                end = narr_end
        else:
            start = narr_end - 1.0
            end = narr_end
        ja_text = seg["text"]
        ja_len = len(ja_text)
        if ja_len > 36:
            fs_tag = "\\fs22"
        elif ja_len > 28:
            fs_tag = "\\fs26"
        else:
            fs_tag = ""
        events.append(
            f"Dialogue: 10,{_ass_time(start)},{_ass_time(end)},JASub,,0,0,0,,"
            f"{{\\fad(300,200){fs_tag}}}  {ja_text}  "
        )

    # ================================================================
    # PHASE 2.5: INSIGHT (after narration, before key phrases)
    # ================================================================
    if insight_timing:
        ins_start = insight_timing[0]["start_s"] + NARRATION_OFFSET
        ins_end = insight_timing[-1]["end_s"] + NARRATION_OFFSET

        # Section card: INSIGHT (short card at narration end, before insight audio)
        _add_section_card(events, narr_end, 2, 4, "INSIGHT", "\u8003\u5bdf\u30bf\u30a4\u30e0",
                          accent, duration=0.8)
        events.append(
            f"Dialogue: 5,{_ass_time(ins_start + SECTION_CARD_DURATION)},{_ass_time(ins_end)},PhaseLabel,,0,0,0,,"
            f"{{\\fad(400,300)}}INSIGHT"
        )

        # Insight word groups (EN) with linger
        for gi, group in enumerate(insight_word_groups):
            g_start = group["start"] + NARRATION_OFFSET
            g_raw_end = group["end"] + NARRATION_OFFSET
            if gi + 1 < len(insight_word_groups):
                g_next = insight_word_groups[gi + 1]["start"] + NARRATION_OFFSET
                g_end = min(g_raw_end + CAPTION_LINGER, g_next + 0.12)
            else:
                g_end = min(g_raw_end + CAPTION_LINGER, ins_end)
            display = " ".join(group["words"])
            events.append(
                f"Dialogue: 10,{_ass_time(g_start)},{_ass_time(g_end)},WordEN,,0,0,0,,"
                f"{{\\fscx105\\fscy105\\t(0,300,\\fscx100\\fscy100)\\fad(200,150)}}{display}"
            )

        # Insight JA subtitle (auto-sized for long text)
        if insight_ja:
            ins_ja_len = len(insight_ja)
            if ins_ja_len > 40:
                ins_fs = "\\fs20"
            elif ins_ja_len > 30:
                ins_fs = "\\fs24"
            else:
                ins_fs = "\\fs26"
            events.append(
                f"Dialogue: 10,{_ass_time(ins_start + 0.15)},{_ass_time(ins_end)},JASub,,70,100,0,,"
                f"{{\\fad(400,300){ins_fs}}}  {insight_ja}  "
            )

        # Connector bar
        events.append(
            f"Dialogue: 4,{_ass_time(ins_start)},{_ass_time(ins_end)},ConnBar,,0,0,0,,"
            f"{{\\fad(350,250)\\p1}}m 0 0 l 800 0 l 800 2 l 0 2{{\\p0}}"
        )

    # ================================================================
    # PHASE 3: KEY PHRASES (dynamic timing from KP audio)
    # ================================================================
    kp_start = kp_phase_start

    # Section card: KEY PHRASES (card plays before kp_start, content starts at kp_start)
    _add_section_card(events, kp_start - SECTION_CARD_DURATION, 3, 4,
                      "KEY PHRASES", "\u91cd\u8981\u30d5\u30ec\u30fc\u30ba", accent)
    events.append(
        f"Dialogue: 5,{_ass_time(kp_start + SECTION_CARD_DURATION)},{_ass_time(kp_end)},PhaseLabel,,0,0,0,,"
        f"{{\\fad(400,300)}}KEY PHRASES"
    )

    for idx, kp in enumerate(key_phrases):
        # Dynamic timing from KP audio, or fallback to even split
        if kp_timing_data and idx < len(kp_timing_data):
            ps = kp_start + kp_timing_data[idx]["start_s"]
            pe = kp_start + kp_timing_data[idx]["end_s"] + 0.4
        else:
            per = (kp_end - kp_start) / kp_count
            ps = kp_start + idx * per
            pe = ps + per

        # Number
        events.append(
            f"Dialogue: 15,{_ass_time(ps)},{_ass_time(pe)},KPNum,,0,0,0,,"
            f"{{\\fscx140\\fscy140\\t(0,400,\\fscx100\\fscy100)\\fad(200,200)}}{idx + 1}"
        )
        # Phrase
        events.append(
            f"Dialogue: 10,{_ass_time(ps + 0.1)},{_ass_time(pe)},KPPhrase,,0,0,0,,"
            f"{{\\fscx108\\fscy108\\t(0,400,\\fscx100\\fscy100)\\fad(200,200)}}  {kp['en']}  "
        )
        # Translation
        events.append(
            f"Dialogue: 10,{_ass_time(ps + 0.2)},{_ass_time(pe)},KPTrans,,0,0,0,,"
            f"{{\\fad(300,200)}}  {kp['ja']}  "
        )
        # Example sentence
        example = kp.get("example", "")
        if example:
            events.append(
                f"Dialogue: 10,{_ass_time(ps + 0.35)},{_ass_time(pe)},KPEx,,0,0,0,,"
                f"{{\\fad(400,200)}}  \"{example}\"  "
            )

        # KP progress dots
        kp_dots = []
        for di in range(kp_count):
            if di <= idx:
                kp_dots.append("{\\c" + accent + "}\u25CF")
            else:
                kp_dots.append("{\\c&H60FFFFFF&}\u25CB")
        events.append(
            f"Dialogue: 5,{_ass_time(ps)},{_ass_time(pe)},KPDots,,0,0,0,,"
            f"{{\\fad(250,200)}}{' '.join(kp_dots)}"
        )

    # ================================================================
    # PHASE 4: ANSWER
    # ================================================================
    # Card plays first, then answer content starts
    ans_card_time = kp_end + 0.15
    ans_start = ans_card_time + SECTION_CARD_DURATION
    ans_end = ans_start + ANSWER_DURATION

    # Section card: ANSWER (card finishes at ans_start)
    _add_section_card(events, ans_card_time, 4, 4, "ANSWER", "\u7b54\u3048\u5408\u308f\u305b", accent)
    events.append(
        f"Dialogue: 15,{_ass_time(ans_start)},{_ass_time(ans_end)},AnswerLabel,,0,0,0,,"
        f"{{\\fscx160\\fscy160\\t(0,800,\\fscx100\\fscy100)\\blur2\\t(0,800,\\blur0)}}ANSWER"
    )
    events.append(
        f"Dialogue: 15,{_ass_time(ans_start + 0.3)},{_ass_time(ans_end)},AnswerText,,0,0,0,,"
        f"{{\\fscx90\\fscy90\\t(0,600,\\fscx100\\fscy100)\\fad(450,500)}}  {mission['answer_ja']}  "
    )
    events.append(
        f"Dialogue: 10,{_ass_time(ans_start + 0.7)},{_ass_time(ans_end)},CTA,,0,0,0,,"
        f"{{\\fad(500,500)}}{cta}"
    )

    # ================================================================
    # PHASE 5: OUTRO
    # ================================================================
    outro_start = ans_end + 0.10
    outro_end = outro_start + OUTRO_DURATION

    # Replay CTA (centered)
    events.append(
        f"Dialogue: 15,{_ass_time(outro_start)},{_ass_time(outro_end - 0.5)},Replay,,0,0,0,,"
        f"{{\\fscx105\\fscy105\\t(0,400,\\fscx100\\fscy100)\\fad(350,500)}}"
        f"  聞き取れた？もう一度聴こう！  "
    )

    # KP recap list (compact, semi-transparent)
    kp_recap = " \u00b7 ".join(kp["en"] for kp in key_phrases)
    events.append(
        f"Dialogue: 10,{_ass_time(outro_start + 0.3)},{_ass_time(outro_end - 0.3)},KPEx,,0,0,0,,"
        f"{{\\fad(400,400)\\alpha&H40&}}  {kp_recap}  "
    )

    # CTA
    if cta:
        events.append(
            f"Dialogue: 10,{_ass_time(outro_start + 0.6)},{_ass_time(outro_end)},CTA,,0,0,0,,"
            f"{{\\fad(500,500)}}{cta}"
        )

    # Loop hint: hook fades back in for seamless loop
    if hook_text:
        events.append(
            f"Dialogue: 10,{_ass_time(outro_end - 1.2)},{_ass_time(outro_end)},IntroHook,,0,0,0,,"
            f"{{\\fad(800,0)\\alpha&H60&}}  {hook_text}  "
        )
    events.append(
        f"Dialogue: 10,{_ass_time(outro_end - 0.8)},{_ass_time(outro_end)},HookLabel,,0,0,0,,"
        f"{{\\fad(600,0)\\alpha&H40&}}CHALLENGE"
    )

    return ass + "\n".join(events) + "\n"


def generate_video(script_path: str, audio_path: str, timing_path: str,
                    output_path: str, use_sd: bool = True,
                    narr_sentence_count: int | None = None,
                    kp_audio_path: str | None = None,
                    kp_timing_path: str | None = None):
    """Generate the final viral-ready video (v8)."""
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)
    with open(timing_path, "r", encoding="utf-8") as f:
        timing_data = json.load(f)

    theme = script.get("theme", "midnight")

    # Determine narr_sentence_count
    if narr_sentence_count is None:
        narr_sentence_count = len(timing_data)

    narr_timing = timing_data[:narr_sentence_count]
    insight_timing = timing_data[narr_sentence_count:]

    narr_end = narr_timing[-1]["end_s"] + NARRATION_OFFSET if narr_timing else 28
    all_audio_end = timing_data[-1]["end_s"] + NARRATION_OFFSET if timing_data else 28

    # Load KP timing if available
    kp_timing_data = None
    if kp_timing_path and os.path.exists(kp_timing_path):
        with open(kp_timing_path, "r", encoding="utf-8") as f:
            kp_timing_data = json.load(f)

    # Calculate phase starts (section card gaps included)
    kp_phase_start = all_audio_end + 0.15 + SECTION_CARD_DURATION  # card, then KP content
    insight_phase_start = narr_end + 0.15 if insight_timing else narr_end

    # KP duration
    if kp_timing_data:
        kp_duration = kp_timing_data[-1]["end_s"] + 0.5
    else:
        kp_duration = KEY_PHRASES_FALLBACK

    kp_end = kp_phase_start + kp_duration

    # Answer: card gap + content + outro
    total_duration = kp_end + 0.15 + SECTION_CARD_DURATION + ANSWER_DURATION + OUTRO_DURATION + 0.25

    # Ensure background
    bg_path = None
    if use_sd:
        try:
            from sd_bg_generator import ensure_sd_bg
            bg_path = ensure_sd_bg(script, BG_DIR)
        except Exception as e:
            print(f"SD background unavailable ({e}), using gradient fallback")
    if bg_path is None:
        from bg_generator import ensure_theme_bg
        bg_path = ensure_theme_bg(theme, BG_DIR)

    # Audio paths
    def _pick(name):
        v2 = os.path.join(AUDIO_DIR, f"{name}_v2.mp3")
        v1 = os.path.join(AUDIO_DIR, f"{name}.mp3")
        return v2 if os.path.exists(v2) else v1

    bgm_path = _pick("bgm_ambient")
    sfx_transition = _pick("sfx_transition")
    sfx_reveal = _pick("sfx_reveal")

    # Generate ASS
    ass_content = _generate_ass(
        script, timing_data, total_duration,
        narr_sentence_count, kp_timing_data,
        kp_phase_start, insight_phase_start
    )
    ass_path = output_path.replace(".mp4", ".ass")
    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    ass_ffmpeg = ass_path.replace("\\", "/").replace(":", "\\:")
    bg_ffmpeg = bg_path.replace("\\", "/").replace(":", "\\:")

    # ================================================================
    # AUDIO MIX (5 or 6 inputs)
    # ================================================================
    narr_delay_ms = int(NARRATION_OFFSET * 1000)
    # SFX plays when section card appears (before content starts)
    listen_card_ms = int(HOOK_DURATION * 1000)
    kp_card_ms = int((all_audio_end + 0.15) * 1000)
    kp_start_ms = int(kp_phase_start * 1000)
    ans_card_ms = int((kp_end + 0.15) * 1000)

    audio_inputs = [
        "-i", audio_path,       # [0] narration + insight
        "-i", bgm_path,         # [1] bgm
        "-i", sfx_transition,   # [2] LISTEN card SFX
        "-i", sfx_transition,   # [3] KEY PHRASES card SFX
        "-i", sfx_reveal,       # [4] ANSWER card SFX
    ]

    has_kp_audio = kp_audio_path and os.path.exists(kp_audio_path)
    if has_kp_audio:
        audio_inputs += ["-i", kp_audio_path]   # [5] KP example audio

    audio_filter = (
        f"[0:a]adelay={narr_delay_ms}|{narr_delay_ms},apad=whole_dur={total_duration:.2f}[narr];"
        f"[1:a]volume=0.10,afade=t=in:d=1.5,afade=t=out:st={total_duration - 2.5:.1f}:d=2.5[bgm];"
        f"[2:a]adelay={max(0, listen_card_ms - 150)}|{max(0, listen_card_ms - 150)},volume=0.5[sfx1];"
        f"[3:a]adelay={max(0, kp_card_ms - 150)}|{max(0, kp_card_ms - 150)},volume=0.5[sfx2];"
        f"[4:a]adelay={ans_card_ms}|{ans_card_ms},volume=0.6[sfx3];"
    )

    if has_kp_audio:
        audio_filter += (
            f"[5:a]adelay={kp_start_ms}|{kp_start_ms},volume=1.3[kpaudio];"
            f"[narr][bgm][sfx1][sfx2][sfx3][kpaudio]amix=inputs=6:duration=first:dropout_transition=2,"
            f"apad=whole_dur={total_duration:.2f}[aout]"
        )
    else:
        audio_filter += (
            f"[narr][bgm][sfx1][sfx2][sfx3]amix=inputs=5:duration=first:dropout_transition=2,"
            f"apad=whole_dur={total_duration:.2f}[aout]"
        )

    # ================================================================
    # VIDEO: Background + zoom + dark overlay + ASS + progress bar
    # ================================================================
    zoom_scale = 1.06
    scaled_w = int(WIDTH * zoom_scale)
    scaled_h = int(HEIGHT * zoom_scale)

    video_filter = (
        f"movie='{bg_ffmpeg}',loop=999:1:0,"
        f"scale={scaled_w}:{scaled_h},"
        f"zoompan=z='{zoom_scale}-0.0006*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={int(total_duration * 30)}:s={WIDTH}x{HEIGHT}:fps=30,"
        # Dark overlay behind text area for readability on SD backgrounds
        f"drawbox=x=0:y=100:w={WIDTH}:h=950:color=0x000000@0.45:t=fill,"
        # Progress bar bg
        f"drawbox=x=0:y={HEIGHT - 6}:w={WIDTH}:h=6:color=0xFFFFFF@0.12:t=fill,"
        # Progress bar animated
        f"drawbox=x=0:y={HEIGHT - 6}:w='(t/{total_duration:.2f})*{WIDTH}':h=6"
        f":color=0x00CCFF@0.85:t=fill,"
        # ASS subtitles
        f"ass='{ass_ffmpeg}'"
        f"[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *audio_inputs,
        "-filter_complex",
        f"{video_filter};{audio_filter}",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-shortest",
        "-t", f"{total_duration:.2f}",
        output_path,
    ]

    print(f"Generating video ({total_duration:.1f}s, theme={theme})...")
    result = subprocess.run(cmd, capture_output=True, timeout=300, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        stderr = result.stderr or ""
        print(f"FFmpeg error:\n{stderr[-3000:]}")
        raise RuntimeError("FFmpeg failed")

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Video saved: {output_path} ({file_size:.1f} MB)")
    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python video_generator.py <script.json>")
        sys.exit(1)

    script_file = sys.argv[1]
    base = os.path.dirname(os.path.abspath(script_file))

    with open(script_file, "r", encoding="utf-8") as f:
        script = json.load(f)

    sid = script["id"]
    audio_dir = os.path.join(base, "..", "audio")
    output_dir = os.path.join(base, "..", "output")
    os.makedirs(output_dir, exist_ok=True)

    audio_path = os.path.join(audio_dir, f"{sid}.mp3")
    timing_path = os.path.join(audio_dir, f"{sid}_timing.json")
    output_path = os.path.join(output_dir, f"{sid}.mp4")

    if not os.path.exists(audio_path):
        print(f"Audio not found: {audio_path}")
        sys.exit(1)

    generate_video(script_file, audio_path, timing_path, output_path)
