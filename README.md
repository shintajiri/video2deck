# video-to-slides

動画（ローカルの MP4/MOV 等、または YouTube リンク）から、**動画を見なくても内容が分かる**単一 HTML スライドを生成する [Claude Code](https://claude.com/claude-code) スキルです。

- 🎙 **ローカル文字起こし** — Apple SpeechAnalyzer をオンデバイスで実行。音源を外部サービスに送りません（会議・ゼミ・学会の録音でも安全）
- 🖼 **場面フレーム抽出** — ffmpeg のシーン検出で、スライド投影型の動画は**映し出された全スライドを取り込み**
- 🌏 **外国語対応** — 英語等の動画は日本語主体＋原文キーワード併記で日本語化
- 🔗 **タイムスタンプ** — 各スライドから元動画（YouTube は該当秒）へ
- 📦 **単一ファイル出力** — CSS・JS・画像を全部埋め込んだ HTML 1 つ。相手はダブルクリックするだけ

## 動作環境

- **macOS 26 以降**（SpeechAnalyzer API）＋ Xcode Command Line Tools（`xcode-select --install`）
- `ffmpeg` / `yt-dlp` … `brew install ffmpeg yt-dlp`
- Pillow（画像圧縮・任意）… `pip3 install Pillow`

macOS 26 未満・非 Mac では文字起こし（SpeechAnalyzer）が動きません。

## インストール

### 方法A：プラグイン マーケットプレイス（推奨）

Claude Code の中で：

```
/plugin marketplace add shintajiri/video-to-slides
/plugin install video-to-slides@video-to-slides
```

更新は `/plugin update video-to-slides`。

### 方法B：スキルだけを直接クローン

```sh
git clone https://github.com/shintajiri/video-to-slides.git /tmp/v2s
cp -R /tmp/v2s/plugins/video-to-slides/skills/video-to-slides ~/.claude/skills/
cp -R /tmp/v2s/plugins/video-to-slides/scripts ~/.claude/skills/video-to-slides/
cp -R /tmp/v2s/plugins/video-to-slides/assets  ~/.claude/skills/video-to-slides/
```

（バージョン管理・自動更新は付きません。個人利用向け）

## 使い方

Claude Code に動画のパスか YouTube の URL を渡して指示するだけです。

```
https://youtu.be/XXXXXXXX この動画をスライドにして
```

```
~/Movies/lecture.mp4 をスライドにまとめて
```

`<動画名>_slides/<日本語名>_スライド.html` が生成されます。この 1 ファイルを渡せば、誰でもブラウザで閲覧できます（`src/` は後日の編集用ソース、`work/` は削除可）。

## 仕組み

`plugins/video-to-slides/skills/video-to-slides/SKILL.md` が全手順です。補助スクリプト：

| ファイル | 役割 |
|---|---|
| `scripts/extract_frames.py` | ffmpeg シーン検出でフレーム抽出、重複マーク、`frames.tsv` 出力 |
| `scripts/pack_single_html.py` | 分割ソースを単一 HTML に固める（画像は base64 埋め込み・再圧縮） |
| `scripts/transcribe-speechanalyzer.swift` | SpeechAnalyzer 文字起こしツールのソース（初回に `swiftc` でビルド） |
| `assets/deck.css` `assets/deck.js` | デッキの見た目とキーボードナビ |

## ライセンス

MIT License
