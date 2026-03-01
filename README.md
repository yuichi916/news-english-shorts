# News English Shorts

YouTube Shorts向けの英語ニュース学習動画を自動生成するパイプライン。

30秒〜90秒のショート動画で、最新の英語ニュースをリスニング・フレーズ学習できるコンテンツを生成します。

例：youtube.com/shorts/h6OuTIT5xvc

## 動画の構成

| セクション | 内容 | 時間 |
|---|---|---|
| HOOK | トピック紹介 + リスニングチャレンジ | 3.5s |
| LISTEN | 英語ニュース音声 + 英語/日本語字幕 | ~25s |
| INSIGHT | 考察・分析 | ~8s |
| KEY PHRASES | 重要フレーズ3つ（英語・日本語・例文） | ~12s |
| ANSWER | チャレンジの答え合わせ | 3.5s |
| OUTRO | フォロー・保存CTA + ループヒント | 3.0s |

## セットアップ

### 必要環境

- Python 3.10+
- FFmpeg（PATHに追加済み）
- インターネット接続（edge-tts用）

### インストール

```bash
pip install edge-tts Pillow anthropic streamlit
```

### オプション

- **Stable Diffusion 背景**: SD WebUI reForge が `localhost:7860` で起動している場合、トピックに合わせたAI背景画像を自動生成。未起動の場合はグラデーション背景にフォールバック。
- **ElevenLabs TTS**: `ELEVENLABS_API_KEY` を設定すると高品質音声を利用可能。
- **スクリプト自動生成**: `ANTHROPIC_API_KEY` を設定するとClaude APIでスクリプトJSONを自動生成。

## 使い方

### Streamlit Web UI（推奨）

```bash
streamlit run app.py
```

ブラウザでGUIが開き、以下の機能を利用できます：

| タブ | 機能 |
|---|---|
| 📝 スクリプト生成 | トピック入力 → ニュース検索 → Claude APIでスクリプトJSON自動生成 |
| 📂 スクリプト管理 | スクリプトの閲覧・編集・バリデーション・削除 |
| 🎬 動画生成 | TTS設定・背景設定を選んで動画生成、プレーヤーで確認 |
| ⚡ バッチ処理 | 複数スクリプトを一括処理、進捗バー付き |

サイドバーにSD WebUI接続状態・APIキー設定状態・統計情報を表示。

### CLI

#### スクリプト自動生成

```bash
python script_generator.py --topic "AI regulation" --days 3
python script_generator.py --topic "Apple AI" --theme ocean --run
python script_generator.py --dry-run scripts/sample_iran_strikes.json  # バリデーションのみ
```

#### 単一スクリプトから動画生成

```bash
python main.py scripts/sample_iran_strikes.json
```

#### 全スクリプトをバッチ処理

```bash
python main.py --batch scripts
```

#### SD背景なしで生成（高速）

```bash
python main.py --batch scripts --no-sd
```

#### Smart背景（Claude AIでSDプロンプト生成）

```bash
python main.py scripts/sample_iran_strikes.json --smart-bg
```

#### ElevenLabs TTSで生成

```bash
python main.py scripts/sample_iran_strikes.json --tts elevenlabs
```

#### 音声の変更

```bash
python main.py scripts/sample_apple_ai.json --voice female_us
python main.py --list-voices  # 利用可能な音声一覧
```

## 出力ファイル

```
output/
  2026-03-01_iran_strikes.mp4              # 動画ファイル
  2026-03-01_iran_strikes_description.txt  # YouTube投稿用説明文
```

## スクリプト JSON の構造

`scripts/` ディレクトリにJSONファイルを追加するだけで新しい動画を生成できます。

```jsonc
{
  "id": "2026-03-01_iran_strikes",       // ファイル名のベース
  "date": "2026-03-01",
  "topic": "US and Israel launch ...",    // 画面上部に常時表示
  "theme": "midnight",                   // テーマ: midnight, ocean, ember, forest, purple
  "hook_text": "米イスラエルが...",         // 冒頭フック（日本語）
  "sources": [                           // 引用元ソース
    {"name": "Al Jazeera", "url": "..."}
  ],
  "mission": {                           // リスニングチャレンジ
    "ja": "作戦名は？英語で聞き取ろう",
    "answer_ja": "答え: Operation Epic Fury"
  },
  "narration": {                         // 英語ナレーション（5文程度）
    "text": "The United States and Israel launched ...",
    "highlights": ["massive", "Operation Epic Fury", ...]
  },
  "insight": {                           // 考察（英語 + 日本語）
    "en": "This is the largest ...",
    "ja": "これはイラク戦争以来..."
  },
  "japanese_subtitle_segments": [...],   // 日本語字幕（文ごと）
  "key_phrases": [                       // 学習フレーズ3つ
    {
      "en": "launch an operation",
      "ja": "作戦を開始する",
      "example": "The US launched a massive military operation."
    }
  ],
  "cta": "保存して3つのフレーズを覚えよう",
  "hashtags": ["#英語学習", "#Shorts", ...]
}
```

## プロジェクト構成

```
news-english-shorts/
├── app.py                # Streamlit Web UI
├── main.py               # エントリポイント（CLI）
├── script_generator.py   # スクリプト自動生成（Google News + Claude API）
├── video_generator.py    # 動画生成（ASS字幕 + FFmpeg合成）
├── tts_generator.py      # 音声生成（edge-tts / ElevenLabs + タイミングデータ）
├── bg_generator.py       # グラデーション背景生成（Pillow）
├── sd_bg_generator.py    # SD WebUI API 背景生成 + Smart BG（Claude AI）
├── scripts/              # ニューススクリプト（JSON）
├── backgrounds/          # 背景画像
├── audio/                # 生成された音声（.gitignore）
└── output/               # 生成された動画（.gitignore）
```

## テーマ

5種類のビジュアルテーマから選択できます。各テーマはグラデーション背景・アクセントカラー・ハイライトカラーを含みます。

| テーマ | 色調 | 向いているトピック |
|---|---|---|
| `midnight` | 紫・紺 | 政治・国際情勢 |
| `ocean` | 青・シアン | 経済・社会問題 |
| `ember` | 赤・オレンジ | テクノロジー・危機 |
| `forest` | 緑 | 環境・サイエンス |
| `purple` | 紫・ピンク | テック企業・プロダクト |

## TTS 音声オプション

### edge-tts（デフォルト）

| キー | 音声 |
|---|---|
| `male_us` | en-US-GuyNeural（デフォルト） |
| `female_us` | en-US-JennyNeural |
| `male_uk` | en-GB-RyanNeural |
| `female_uk` | en-GB-SoniaNeural |

### ElevenLabs（`--tts elevenlabs`）

| キー | 音声 |
|---|---|
| `el_brian` | Male, clear narrator（デフォルト） |
| `el_daniel` | Male, British |
| `el_adam` | Male, deep |
| `el_rachel` | Female, classic |
| `el_sarah` | Female, professional |

## ライセンス

MIT
