# video2deck

動画（ローカルの MP4/MOV 等、YouTube リンク、**X/Twitter の動画付きポスト**）から、**動画を見なくても内容が分かる**単一 HTML スライドを生成する [Claude Code](https://claude.com/claude-code) スキルです。

- 📥 **入力は3系統** — ローカル動画ファイル／YouTube／X（Twitter）の動画付きポスト（オンライン動画の取得は yt-dlp）
- 🎙 **文字起こしエンジンを選べる** — **Gemini API**（Windows / macOS / Linux。固有名詞に強い）か **Apple SpeechAnalyzer**（macOS 26+。端末内で完結、音源を外に出さない）。毎回どちらを使うか確認します
- 🖼 **場面フレーム抽出** — ffmpeg のシーン検出で、スライド投影型の動画は**映し出された全スライドを取り込み**
- 🗂 **コンタクトシート** — 抽出フレームを連番・時刻入りの一覧画像にまとめ、Claude はまずそれ1枚だけを見る（個別に読む場合と比べてトークン約89%減、実測）
- 🌏 **外国語対応** — 英語等の動画は日本語主体＋原文キーワード併記で日本語化
- 🔗 **タイムスタンプ** — 各スライドから元動画（YouTube は該当秒）へ
- 📦 **単一ファイル出力** — CSS・JS・画像を全部埋め込んだ HTML 1 つ。相手はダブルクリックするだけ

## 動作環境

| | Windows | macOS | Linux |
|---|---|---|---|
| フレーム抽出・デッキ生成 | ○ | ○ | ○ |
| 文字起こし：Gemini API | ○ | ○ | ○ |
| 文字起こし：SpeechAnalyzer | × | ○（macOS 26 以降） | × |

共通で必要なもの：

- `ffmpeg` / `ffprobe` … macOS `brew install ffmpeg`、Windows `winget install Gyan.FFmpeg`
- `yt-dlp`（YouTube / X の URL を渡すときだけ）… `brew install yt-dlp` / `winget install yt-dlp`
- Python 3.9 以上 ＋ Pillow（コンタクトシート生成に実質必須）… `pip3 install Pillow`

### Gemini API を使う場合

1. https://aistudio.google.com/apikey でキーを発行する
2. 環境変数 `GEMINI_API_KEY` に入れるか、`~/.config/gemini/api_key`（Windows は `%USERPROFILE%\.config\gemini\api_key`）にキーだけを1行で書く

音声は Google のクラウドに送られます。**無料枠は Google の利用規約で機密・個人情報の送信が禁じられている**ので、有料枠（Tier 1 以上）で使ってください。費用の目安は 100 分の音声で数十円です。第三者の発言を含む録音を送ってよいかは、所属組織の規程で判断してください。

### SpeechAnalyzer を使う場合

- macOS 26 以降 ＋ Xcode Command Line Tools（`xcode-select --install`）
- 初回に同梱の Swift ソースを `swiftc` でビルドします（数秒）。音声は端末の外に出ません

## インストール

### 方法A：プラグイン マーケットプレイス（推奨）

Claude Code の中で：

```
/plugin marketplace add shintajiri/video2deck
/plugin install video2deck@video2deck
```

更新は `/plugin update video2deck`。

### 方法B：スキルだけを直接クローン

```sh
git clone https://github.com/shintajiri/video2deck.git /tmp/v2d
cp -R /tmp/v2d/plugins/video2deck/skills/video2deck ~/.claude/skills/
cp -R /tmp/v2d/plugins/video2deck/scripts ~/.claude/skills/video2deck/
cp -R /tmp/v2d/plugins/video2deck/assets  ~/.claude/skills/video2deck/
```

（バージョン管理・自動更新は付きません。個人利用向け）

## 使い方

Claude Code に動画のパスか URL（YouTube／X のポスト）を渡して指示するだけです。

```
https://youtu.be/XXXXXXXX この動画をスライドにして
```

```
https://x.com/user/status/XXXXXXXX このポストの動画をスライドにして
```

```
~/Movies/lecture.mp4 をスライドにまとめて
```

文字起こしが必要なとき、Claude は **Gemini か SpeechAnalyzer か**を確認します（Windows / Linux では Gemini だけ）。「Gemini で」「ローカルで」のように最初の指示に書いておけば聞かれません。X の動画は字幕が無いため常に文字起こしになります。鍵アカウント等ログインが必要なポストは、スキルが `--cookies-from-browser chrome` で取得します。

`<動画名>_slides/<日本語名>_スライド.html` が生成されます。この 1 ファイルを渡せば、誰でもブラウザで閲覧できます（`src/` は後日の編集用ソース、`work/` は削除可）。

## 仕組み

`plugins/video2deck/skills/video2deck/SKILL.md` が全手順です。補助スクリプト：

| ファイル | 役割 |
|---|---|
| `scripts/transcribe_gemini.py` | Gemini API 文字起こし（クロスプラットフォーム）。20MB 超は Files API で 1 回送信、処理後にサーバから削除 |
| `scripts/transcribe-speechanalyzer.swift` | Apple SpeechAnalyzer 文字起こしツールのソース（macOS 26+。初回に `swiftc` でビルド） |
| `scripts/extract_frames.py` | ffmpeg シーン検出でフレーム抽出、重複マーク、`frames.tsv` 出力、コンタクトシート `contact.jpg` 生成（`--no-contact` で無効化） |
| `scripts/pack_single_html.py` | 分割ソースを単一 HTML に固める（画像は base64 埋め込み・再圧縮） |
| `assets/deck.css` `assets/deck.js` | デッキの見た目とキーボードナビ |

## 更新履歴

- **1.3.0**（2026-09-06）— 文字起こしエンジンの選択式化。Gemini API 版スクリプトを同梱し、Windows / Linux でも全工程が動くようになった。SpeechAnalyzer は macOS 26+ のローカル完結オプションとして継続。前提ツールと手順を Windows 向けに補記
- 1.2.0（2026-09-06）— フレーム一覧のコンタクトシート化（個別 Read の約1/10 のトークンで全体を判定）。白背景で似たレイアウトのスライドがシーン検出をすり抜ける問題への手順（transcript の話題転換から `--at` で狙い撃ち）。デッキ CSS の修正：右下ナビと出典行の重なり、操作ヒントを右上に移動、印刷時に狭幅レイアウトが効いて2カラムが崩れる問題
- 1.1.0 — X（Twitter）の動画付きポストを入力に追加
- 1.0.0 — 初版
