# video2deck

動画（ローカルの MP4/MOV 等、YouTube リンク、**X/Twitter の動画付きポスト**）から、**動画を見なくても内容が分かる**単一 HTML スライドを生成する [Claude Code](https://claude.com/claude-code) スキルです。

- 📥 **入力は3系統** — ローカル動画ファイル／YouTube／X（Twitter）の動画付きポスト（オンライン動画の取得は yt-dlp）
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

X の動画は字幕が無いため自動的にローカル文字起こし（SpeechAnalyzer）になります。鍵アカウント等ログインが必要なポストは、スキルが `--cookies-from-browser chrome` で取得します。

`<動画名>_slides/<日本語名>_スライド.html` が生成されます。この 1 ファイルを渡せば、誰でもブラウザで閲覧できます（`src/` は後日の編集用ソース、`work/` は削除可）。

## 仕組み

`plugins/video2deck/skills/video2deck/SKILL.md` が全手順です。補助スクリプト：

| ファイル | 役割 |
|---|---|
| `scripts/extract_frames.py` | ffmpeg シーン検出でフレーム抽出、重複マーク、`frames.tsv` 出力 |
| `scripts/pack_single_html.py` | 分割ソースを単一 HTML に固める（画像は base64 埋め込み・再圧縮） |
| `scripts/transcribe-speechanalyzer.swift` | SpeechAnalyzer 文字起こしツールのソース（初回に `swiftc` でビルド） |
| `assets/deck.css` `assets/deck.js` | デッキの見た目とキーボードナビ |

## ライセンス

MIT License
