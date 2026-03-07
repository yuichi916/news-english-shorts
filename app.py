"""News English Shorts — Streamlit UI.

Launch:
    streamlit run app.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import urllib.request
import urllib.error

import streamlit as st

from youtube_uploader import (
    has_client_secret,
    is_authenticated,
    authenticate,
    logout,
    upload_video,
    build_metadata,
)

# ── Project paths ──────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
AUDIO_DIR = os.path.join(PROJECT_DIR, "audio")

# ── Imports from existing modules ──────────────────────────────────────────────
from script_generator import (
    search_news,
    generate_script,
    validate_script,
    VALID_THEMES,
    _make_slug,
    MAX_RETRIES,
)
from tts_generator import VOICES, ELEVENLABS_VOICES, DEFAULT_VOICE, DEFAULT_RATE
from main import process_script
from sd_bg_generator import SD_API_URL

# ── Helper functions ───────────────────────────────────────────────────────────

def check_sd_webui() -> bool:
    """Return True if SD WebUI is reachable."""
    try:
        req = urllib.request.Request(SD_API_URL, method="GET")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def check_api_key(name: str) -> bool:
    """Return True if the environment variable *name* is set and non-empty."""
    return bool(os.environ.get(name))


@st.cache_data(ttl=10)
def list_scripts() -> list[str]:
    """Return sorted list of script JSON paths in scripts/."""
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    return sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.json")))


def _count_videos() -> int:
    """Count mp4 files in output/."""
    if not os.path.isdir(OUTPUT_DIR):
        return 0
    return len(glob.glob(os.path.join(OUTPUT_DIR, "*.mp4")))


def _load_script(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _basename(path: str) -> str:
    return os.path.basename(path)


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="News English Shorts",
    page_icon="🎬",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("News English Shorts")
    st.caption("30秒ニュース英語 動画パイプライン")

    st.divider()
    st.subheader("ステータス")

    sd_ok = check_sd_webui()
    anthropic_ok = check_api_key("ANTHROPIC_API_KEY")
    elevenlabs_ok = check_api_key("ELEVENLABS_API_KEY")

    st.markdown(
        f"- SD WebUI: {'🟢 接続済み' if sd_ok else '🔴 未接続'}\n"
        f"- ANTHROPIC_API_KEY: {'🟢 設定済み' if anthropic_ok else '🔴 未設定'}\n"
        f"- ELEVENLABS_API_KEY: {'🟢 設定済み' if elevenlabs_ok else '⚪ 未設定'}"
    )

    st.divider()
    st.subheader("YouTube")

    if not has_client_secret():
        st.warning("client_secret.json が未配置です。Google Cloud Console からダウンロードしてプロジェクトルートに配置してください。")
    else:
        yt_authed = is_authenticated()
        st.markdown(f"- YouTube: {'🟢 認証済み' if yt_authed else '🔴 未認証'}")

        if yt_authed:
            if st.button("YouTube ログアウト", key="yt_logout"):
                logout()
                st.rerun()
        else:
            if st.button("YouTube 認証", key="yt_auth", type="primary"):
                try:
                    authenticate()
                    st.success("認証に成功しました!")
                    st.rerun()
                except Exception as e:
                    st.error(f"認証エラー: {e}")

    st.divider()
    st.subheader("統計")

    scripts = list_scripts()
    st.metric("スクリプト数", len(scripts))
    st.metric("動画数", _count_videos())

    st.divider()
    st.caption(f"**scripts/** `{SCRIPTS_DIR}`")
    st.caption(f"**output/** `{OUTPUT_DIR}`")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_gen, tab_manage, tab_video, tab_batch = st.tabs(
    ["📝 スクリプト生成", "📂 スクリプト管理", "🎬 動画生成", "⚡ バッチ処理"]
)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Tab 1: スクリプト生成                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_gen:
    st.header("スクリプト生成")

    col1, col2 = st.columns([2, 1])
    with col1:
        topic = st.text_input("トピック（英語推奨）", placeholder="e.g. AI regulation in EU")
    with col2:
        days = st.slider("検索期間（日）", min_value=1, max_value=14, value=3)

    theme = st.selectbox("テーマ", ["auto"] + VALID_THEMES)

    if st.button("🔍 スクリプトを生成", disabled=not topic, type="primary"):
        with st.status("スクリプトを生成中...", expanded=True) as status:
            # Step 1: search news
            st.write("📰 ニュースを検索中...")
            try:
                articles = search_news(topic, days)
            except Exception as e:
                articles = []
                st.warning(f"ニュース検索に失敗: {e}")

            if articles:
                st.write(f"  {len(articles)} 件の記事を取得")
            else:
                st.write("  記事が見つかりません。トピック名のみで生成します。")

            # Step 2: generate with retries
            prev_errors: list[str] | None = None
            script_data = None

            for attempt in range(1, MAX_RETRIES + 1):
                if attempt > 1:
                    st.write(f"🔄 リトライ {attempt}/{MAX_RETRIES}（{len(prev_errors)} 件のエラーを修正中）...")
                else:
                    st.write("🤖 Claude API でスクリプトを生成中...")

                try:
                    script_data = generate_script(
                        topic, articles,
                        theme=theme if theme != "auto" else None,
                        prev_errors=prev_errors,
                    )
                except json.JSONDecodeError as e:
                    prev_errors = [f"Invalid JSON: {e}"]
                    st.warning(f"JSON パースエラー: {e}")
                    if attempt == MAX_RETRIES:
                        status.update(label="生成失敗", state="error")
                        st.error(f"{MAX_RETRIES} 回のリトライ後も生成に失敗しました。")
                    continue
                except Exception as e:
                    status.update(label="生成失敗", state="error")
                    st.error(f"API エラー: {e}")
                    break

                errors = validate_script(script_data)
                if not errors:
                    st.write("✅ バリデーション OK")
                    break
                else:
                    st.warning(f"バリデーションエラー ({len(errors)} 件):")
                    for e in errors:
                        st.write(f"  - {e}")
                    prev_errors = errors
                    if attempt == MAX_RETRIES:
                        status.update(label="バリデーション失敗", state="error")
                        st.error("リトライ上限に達しました。生成されたスクリプトにはエラーが含まれています。")

            if script_data is not None:
                status.update(label="生成完了", state="complete")
                st.session_state["generated_script"] = script_data

    # Show generated script
    if "generated_script" in st.session_state:
        script_data = st.session_state["generated_script"]
        st.subheader("プレビュー")

        col_info, col_save = st.columns([3, 1])
        with col_info:
            st.write(f"**ID:** {script_data.get('id', '—')}")
            st.write(f"**テーマ:** {script_data.get('theme', '—')}")
            st.write(f"**ソース数:** {len(script_data.get('sources', []))}")
        with col_save:
            if st.button("💾 保存", type="primary"):
                os.makedirs(SCRIPTS_DIR, exist_ok=True)
                from datetime import datetime
                slug = _make_slug(topic if topic else script_data.get("topic", "untitled"))
                today = datetime.now().strftime("%Y-%m-%d")
                filename = f"{today}_{slug}.json"
                save_path = os.path.join(SCRIPTS_DIR, filename)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(script_data, f, ensure_ascii=False, indent=2)
                st.success(f"保存しました: {filename}")
                list_scripts.clear()
                del st.session_state["generated_script"]
                st.rerun()

        st.json(script_data)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Tab 2: スクリプト管理                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_manage:
    st.header("スクリプト管理")

    scripts = list_scripts()
    if not scripts:
        st.info("scripts/ フォルダにスクリプトがありません。")
    else:
        selected_file = st.selectbox(
            "スクリプトを選択",
            scripts,
            format_func=_basename,
            key="manage_select",
        )

        if selected_file:
            data = _load_script(selected_file)

            # Basic info
            col1, col2, col3 = st.columns(3)
            col1.metric("ID", data.get("id", "—"))
            col2.metric("テーマ", data.get("theme", "—"))
            col3.metric("ソース数", len(data.get("sources", [])))

            # Validation
            if st.button("🔍 バリデーションチェック"):
                errors = validate_script(data)
                if errors:
                    st.error(f"バリデーションエラー ({len(errors)} 件):")
                    for e in errors:
                        st.write(f"- {e}")
                else:
                    st.success("バリデーション OK ✅")

            # JSON editor
            st.subheader("JSON 編集")
            json_text = st.text_area(
                "スクリプト JSON",
                value=json.dumps(data, ensure_ascii=False, indent=2),
                height=400,
                key=f"editor_{selected_file}",
            )

            col_save, col_delete = st.columns([1, 1])
            with col_save:
                if st.button("💾 上書き保存"):
                    try:
                        parsed = json.loads(json_text)
                        with open(selected_file, "w", encoding="utf-8") as f:
                            json.dump(parsed, f, ensure_ascii=False, indent=2)
                        st.success("保存しました。")
                        list_scripts.clear()
                    except json.JSONDecodeError as e:
                        st.error(f"JSON パースエラー: {e}")

            with col_delete:
                if st.button("🗑️ 削除", type="secondary"):
                    st.session_state["confirm_delete"] = selected_file

                if st.session_state.get("confirm_delete") == selected_file:
                    st.warning(f"**{_basename(selected_file)}** を削除しますか？")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("はい、削除する", type="primary"):
                            os.remove(selected_file)
                            st.success("削除しました。")
                            list_scripts.clear()
                            del st.session_state["confirm_delete"]
                            st.rerun()
                    with c2:
                        if st.button("キャンセル"):
                            del st.session_state["confirm_delete"]
                            st.rerun()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Tab 3: 動画生成                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_video:
    st.header("動画生成")

    scripts = list_scripts()
    if not scripts:
        st.info("scripts/ フォルダにスクリプトがありません。")
    else:
        selected_script = st.selectbox(
            "スクリプトを選択",
            scripts,
            format_func=_basename,
            key="video_select",
        )

        st.subheader("TTS 設定")
        col_engine, col_voice, col_rate = st.columns(3)
        with col_engine:
            tts_engine = st.selectbox("TTSエンジン", ["edge-tts", "ElevenLabs"], key="v_engine")
        with col_voice:
            if tts_engine == "edge-tts":
                voice_options = list(VOICES.keys())
                voice_key = st.selectbox("音声", voice_options, key="v_voice")
                voice = VOICES[voice_key]
            else:
                voice_options = list(ELEVENLABS_VOICES.keys())
                voice_key = st.selectbox("音声", voice_options, key="v_voice_el")
                voice = ELEVENLABS_VOICES[voice_key]
        with col_rate:
            rate = st.text_input("話速", value=DEFAULT_RATE, key="v_rate")

        st.subheader("背景設定")
        bg_mode = st.radio(
            "背景モード",
            ["グラデーション（SD不要）", "SD WebUI", "SD + Smart (Claude AI)"],
            index=2,
            horizontal=True,
            key="v_bg",
        )
        use_sd = bg_mode != "グラデーション（SD不要）"
        smart_bg = bg_mode == "SD + Smart (Claude AI)"

        if use_sd and not sd_ok:
            st.warning("SD WebUI に接続できません。グラデーション背景にフォールバックする可能性があります。")

        st.subheader("アバター設定")
        col_av_on, col_av_char = st.columns(2)
        with col_av_on:
            v_avatar_enabled = st.checkbox("アバター表示（口パク）", value=True, key="v_avatar")
        with col_av_char:
            v_avatar_character = st.text_input("キャラクター", value="zundamon", key="v_avatar_char",
                                                disabled=not v_avatar_enabled)

        if st.button("🎬 動画を生成", type="primary", key="v_run"):
            engine_arg = "elevenlabs" if tts_engine == "ElevenLabs" else "edge"

            with st.status("動画を生成中...", expanded=True) as status:
                try:
                    st.write("🔊 TTS 音声を生成中...")
                    if v_avatar_enabled:
                        st.write("🤖 アバター動画を生成中...")
                    st.write("🎥 動画をレンダリング中...")
                    output_path = process_script(
                        selected_script,
                        voice=voice,
                        rate=rate,
                        use_sd=use_sd,
                        smart_bg=smart_bg,
                        tts_engine=engine_arg,
                        avatar_enabled=v_avatar_enabled,
                        avatar_character=v_avatar_character,
                    )
                    status.update(label="生成完了", state="complete")
                    st.session_state["last_video"] = output_path
                    st.session_state["last_script_path"] = selected_script
                except Exception as e:
                    status.update(label="生成失敗", state="error")
                    st.error(f"エラー: {e}")

        # Show result
        if "last_video" in st.session_state:
            output_path = st.session_state["last_video"]
            if os.path.exists(output_path):
                st.subheader("生成結果")
                st.video(output_path)

                # YouTube description
                desc_path = output_path.replace(".mp4", "_description.txt")
                if os.path.exists(desc_path):
                    with open(desc_path, "r", encoding="utf-8") as f:
                        desc_text = f.read()
                    with st.expander("YouTube 説明文"):
                        st.code(desc_text, language=None)

                # Download button
                with open(output_path, "rb") as f:
                    st.download_button(
                        "⬇️ ダウンロード",
                        data=f,
                        file_name=os.path.basename(output_path),
                        mime="video/mp4",
                    )

                # ── YouTube Upload ────────────────────────────────
                st.subheader("YouTube にアップロード")

                if not has_client_secret():
                    st.warning("client_secret.json が未配置です。")
                elif not is_authenticated():
                    st.info("サイドバーから YouTube 認証を行ってください。")
                else:
                    # Build default metadata from script
                    script_path = st.session_state.get("last_script_path")
                    _meta_defaults = {"title": "", "description": "", "tags": []}
                    if script_path and os.path.exists(script_path):
                        _sd = _load_script(script_path)
                        _desc = ""
                        _desc_path = output_path.replace(".mp4", "_description.txt")
                        if os.path.exists(_desc_path):
                            with open(_desc_path, "r", encoding="utf-8") as _f:
                                _desc = _f.read()
                        _meta_defaults = build_metadata(_sd, _desc)

                    yt_title = st.text_input(
                        "タイトル",
                        value=_meta_defaults["title"],
                        key="yt_title",
                    )
                    yt_desc = st.text_area(
                        "説明文",
                        value=_meta_defaults["description"],
                        height=150,
                        key="yt_desc",
                    )
                    yt_tags = st.text_input(
                        "タグ（カンマ区切り）",
                        value=", ".join(_meta_defaults["tags"]),
                        key="yt_tags",
                    )
                    yt_privacy = st.selectbox(
                        "公開設定",
                        ["private", "unlisted", "public"],
                        format_func=lambda x: {"private": "非公開", "unlisted": "限定公開", "public": "公開"}[x],
                        key="yt_privacy",
                    )

                    if st.button("📤 YouTube にアップロード", type="primary", key="yt_upload"):
                        tags_list = [t.strip() for t in yt_tags.split(",") if t.strip()]
                        with st.status("アップロード中...", expanded=True) as up_status:
                            try:
                                st.write("📤 YouTube に動画をアップロード中...")
                                video_id = upload_video(
                                    output_path,
                                    title=yt_title,
                                    description=yt_desc,
                                    tags=tags_list,
                                    privacy=yt_privacy,
                                )
                                up_status.update(label="アップロード完了", state="complete")
                                yt_url = f"https://youtube.com/shorts/{video_id}"
                                st.success(f"アップロード完了!")
                                st.markdown(f"[{yt_url}]({yt_url})")
                                st.session_state["last_yt_url"] = yt_url
                            except Exception as e:
                                up_status.update(label="アップロード失敗", state="error")
                                st.error(f"アップロードエラー: {e}")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Tab 4: バッチ処理                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
with tab_batch:
    st.header("バッチ処理")

    scripts = list_scripts()
    if not scripts:
        st.info("scripts/ フォルダにスクリプトがありません。")
    else:
        select_all = st.checkbox("全て選択", key="batch_all")
        default_selection = scripts if select_all else []
        selected_scripts = st.multiselect(
            "処理するスクリプトを選択",
            scripts,
            default=default_selection,
            format_func=_basename,
            key="batch_select",
        )

        st.subheader("TTS 設定")
        col_engine, col_voice, col_rate = st.columns(3)
        with col_engine:
            b_tts_engine = st.selectbox("TTSエンジン", ["edge-tts", "ElevenLabs"], key="b_engine")
        with col_voice:
            if b_tts_engine == "edge-tts":
                b_voice_options = list(VOICES.keys())
                b_voice_key = st.selectbox("音声", b_voice_options, key="b_voice")
                b_voice = VOICES[b_voice_key]
            else:
                b_voice_options = list(ELEVENLABS_VOICES.keys())
                b_voice_key = st.selectbox("音声", b_voice_options, key="b_voice_el")
                b_voice = ELEVENLABS_VOICES[b_voice_key]
        with col_rate:
            b_rate = st.text_input("話速", value=DEFAULT_RATE, key="b_rate")

        st.subheader("背景設定")
        b_bg_mode = st.radio(
            "背景モード",
            ["グラデーション（SD不要）", "SD WebUI", "SD + Smart (Claude AI)"],
            index=2,
            horizontal=True,
            key="b_bg",
        )
        b_use_sd = b_bg_mode != "グラデーション（SD不要）"
        b_smart_bg = b_bg_mode == "SD + Smart (Claude AI)"

        if b_use_sd and not sd_ok:
            st.warning("SD WebUI に接続できません。グラデーション背景にフォールバックする可能性があります。")

        st.subheader("アバター設定")
        col_b_av_on, col_b_av_char = st.columns(2)
        with col_b_av_on:
            b_avatar_enabled = st.checkbox("アバター表示（口パク）", value=True, key="b_avatar")
        with col_b_av_char:
            b_avatar_character = st.text_input("キャラクター", value="zundamon", key="b_avatar_char",
                                                disabled=not b_avatar_enabled)

        if st.button("⚡ バッチ処理を開始", type="primary", disabled=not selected_scripts, key="b_run"):
            b_engine_arg = "elevenlabs" if b_tts_engine == "ElevenLabs" else "edge"
            total = len(selected_scripts)
            progress = st.progress(0, text=f"0/{total} 完了")
            results: list[dict] = []

            for i, script_path in enumerate(selected_scripts):
                script_name = _basename(script_path)
                with st.status(f"処理中: {script_name}", expanded=True) as status:
                    try:
                        st.write("🔊 TTS 音声を生成中...")
                        st.write("🎥 動画をレンダリング中...")
                        output_path = process_script(
                            script_path,
                            voice=b_voice,
                            rate=b_rate,
                            use_sd=b_use_sd,
                            smart_bg=b_smart_bg,
                            tts_engine=b_engine_arg,
                            avatar_enabled=b_avatar_enabled,
                            avatar_character=b_avatar_character,
                        )
                        status.update(label=f"完了: {script_name}", state="complete")
                        results.append({
                            "スクリプト": script_name,
                            "ステータス": "✅ 成功",
                            "出力": os.path.basename(output_path),
                        })
                    except Exception as e:
                        status.update(label=f"失敗: {script_name}", state="error")
                        st.error(f"エラー: {e}")
                        results.append({
                            "スクリプト": script_name,
                            "ステータス": "❌ 失敗",
                            "出力": str(e),
                        })

                progress.progress((i + 1) / total, text=f"{i + 1}/{total} 完了")

            st.subheader("結果")
            st.dataframe(results, use_container_width=True)

            # Store batch results for upload
            st.session_state["batch_results"] = results

    # ── Batch YouTube Upload ──────────────────────────────────────
    if "batch_results" in st.session_state:
        batch_results = st.session_state["batch_results"]
        successful = [r for r in batch_results if r["ステータス"] == "✅ 成功"]

        if successful:
            st.subheader("YouTube に一括アップロード")

            if not has_client_secret():
                st.warning("client_secret.json が未配置です。")
            elif not is_authenticated():
                st.info("サイドバーから YouTube 認証を行ってください。")
            else:
                batch_privacy = st.selectbox(
                    "公開設定",
                    ["private", "unlisted", "public"],
                    format_func=lambda x: {"private": "非公開", "unlisted": "限定公開", "public": "公開"}[x],
                    key="batch_yt_privacy",
                )

                if st.button("📤 全てアップロード", type="primary", key="batch_yt_upload"):
                    total_up = len(successful)
                    up_progress = st.progress(0, text=f"0/{total_up} アップロード完了")
                    upload_results: list[dict] = []

                    for idx, result in enumerate(successful):
                        video_file = os.path.join(OUTPUT_DIR, result["出力"])
                        if not os.path.exists(video_file):
                            upload_results.append({
                                "スクリプト": result["スクリプト"],
                                "ステータス": "❌ ファイル未発見",
                                "YouTube URL": "",
                            })
                            continue

                        # Load script for metadata
                        script_name = result["スクリプト"]
                        script_file = os.path.join(SCRIPTS_DIR, script_name)
                        meta = {"title": script_name, "description": "", "tags": []}
                        if os.path.exists(script_file):
                            sd = _load_script(script_file)
                            desc_file = video_file.replace(".mp4", "_description.txt")
                            desc_txt = ""
                            if os.path.exists(desc_file):
                                with open(desc_file, "r", encoding="utf-8") as df:
                                    desc_txt = df.read()
                            meta = build_metadata(sd, desc_txt)

                        try:
                            vid = upload_video(
                                video_file,
                                title=meta["title"],
                                description=meta["description"],
                                tags=meta["tags"],
                                privacy=batch_privacy,
                            )
                            yt_url = f"https://youtube.com/shorts/{vid}"
                            upload_results.append({
                                "スクリプト": script_name,
                                "ステータス": "✅ 成功",
                                "YouTube URL": yt_url,
                            })
                        except Exception as e:
                            upload_results.append({
                                "スクリプト": script_name,
                                "ステータス": f"❌ {e}",
                                "YouTube URL": "",
                            })

                        up_progress.progress((idx + 1) / total_up, text=f"{idx + 1}/{total_up} アップロード完了")

                    st.subheader("アップロード結果")
                    st.dataframe(upload_results, use_container_width=True)
