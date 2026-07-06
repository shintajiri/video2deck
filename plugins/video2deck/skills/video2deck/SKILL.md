---
name: video2deck
description: 動画（ローカルMP4/MOV等 または YouTubeリンク）から「動画を見なくても内容が分かる」HTMLスライドデッキを生成する汎用スキル。文字起こし（Apple SpeechAnalyzer）／YouTube字幕と、ffmpegによる場面フレーム抽出を組み合わせ、スライド投影型動画は映された全スライドを取り込む。外国語動画は日本語化。最終成果物はCSS・JS・画像を全部埋め込んだ単一HTMLファイル（1ファイル渡せば誰でも見られる）。Triggers on 動画をスライドに, 動画からスライド, この動画をまとめて, ウェビナーをスライド化, 講演動画の要約, 動画を見る時間がない, video to slides, video to deck, YouTubeをスライドに.
---

# video2deck — 動画 → 要点スライドデッキ生成

## ゴール

渡された動画1本につき、**動画を見なくても「何を話し、何を見せたか」が分かる** HTML スライドデッキを1つ作る。

- スライドを映しながら話す動画（ウェビナー・講演・授業）→ **映し出されたスライドをすべて取り込み**、各スライドに「そこで話された内容」の要約を付ける
- スライド投影のない動画（対談・実演デモ等）→ 場面転換フレーム＋トピック要約で構成
- 外国語動画 → 日本語主体＋原文キーワード併記で日本語化
- 粒度の目安：**約2分に1枚**（33分→16枚、51分→26枚程度）
- 各スライドに元動画へのタイムスタンプ（YouTubeは該当秒への直リンク）

## スキルのファイル配置（重要）

このスキルは補助スクリプトを同梱している。スキル起動時にハーネスが表示する
**「Base directory for this skill: …」** のパスを `$SKILL` とすると：

- `$SKILL/scripts/extract_frames.py` — 場面フレーム抽出
- `$SKILL/scripts/pack_single_html.py` — 単一HTML化パッカー
- `$SKILL/scripts/transcribe-speechanalyzer.swift` — ローカル文字起こしツールのソース
- `$SKILL/assets/deck.css`, `$SKILL/assets/deck.js` — デッキの見た目とナビ

以降のコマンド例の `$SKILL` は、この実際のパスに置き換えて実行すること。

## 前提ツール（最初に確認）

| ツール | 確認 | 無いとき |
|---|---|---|
| ffmpeg / ffprobe | `which ffmpeg ffprobe` | `brew install ffmpeg` |
| yt-dlp（YouTube時のみ） | `which yt-dlp` | `brew install yt-dlp` |
| Swift（文字起こしビルド用） | `which swiftc` | Xcode Command Line Tools（`xcode-select --install`）。**macOS 26+ 必須**（SpeechAnalyzer API） |
| Pillow（画像圧縮・任意） | `python3 -c "import PIL"` | `pip3 install Pillow` |

**音源・映像は外部サービスにアップロードしない。文字起こしは常にローカル（SpeechAnalyzer）で完結させる。** 第三者の発言を含む録音（会議・ゼミ・学会）でも安全なように、クラウド文字起こしサービスに音源を送らないこと。macOS 26 未満や非Macでどうしても動かせない場合のみ、ローカルWhisper（`mlx_whisper` 等）にフォールバックする（その場合も音源は外に出さない）。

## 出力構成

保存先：**動画ファイルと同じディレクトリ**に `<動画ベース名>_slides/`。YouTube の場合はカレントプロジェクト内に `<タイトルの短いslug>_slides/`。

**最終成果物は単一の自己完結HTML**（CSS・JS・全画像を埋め込み済み。このファイル1つを渡せば誰でもブラウザで見られる）。

```
<name>_slides/
  <わかりやすい日本語名>_スライド.html  ← ★最終成果物（単一ファイル・配布用）
  transcript.txt      ← タイムスタンプ付き文字起こし／字幕（原語）
  src/index.html      ← 分割ソース版（後日の編集用）
  src/assets/         ← deck.css / deck.js（$SKILL/assets/ からコピー）
  src/img/NN_slug.jpg ← 採用フレーム（連番＋内容スラッグに改名）
  work/               ← 中間物（DL動画・全候補フレーム・frames.tsv等）。完成後は削除してよい
```

## 手順

### 1. 入力判定と素材取得

**A. ローカル動画**（mp4/mov/m4v/webm/mkv…）：そのままステップ2へ。`ffprobe` で長さを確認。

**B. YouTube URL**：

```sh
# メタデータ（title / duration / id / 字幕の有無）
yt-dlp --dump-json "URL" > work/meta.json

# 字幕取得（手動字幕優先、無ければ自動字幕）
yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "ja,en" \
  --convert-subs srt -o "work/sub" "URL"

# 映像取得（フレーム抽出に必須。1080p上限で十分）
yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" -o "work/video.mp4" "URL"
```

字幕の品質判定：手動字幕（`subtitles`）があればそれを使う。自動字幕（`automatic_captions`）しか無い場合は冒頭を読んで判定し、**断片の重複だらけ・意味が取れない場合は字幕を捨てて音声から SpeechAnalyzer で文字起こし**する（DL済み動画から音声を抽出すればよい）。日本語動画は自動字幕があっても、句読点・固有名詞の精度でSpeechAnalyzerが上回ることが多いので、原則ローカル文字起こしをベースにし、固有名詞だけ字幕と突き合わせて校正するとよい。

### 2. 文字起こし（ローカル動画、または字幕が使えないYouTube）

初回のみ、同梱ソースから文字起こしツールをビルドする（`swiftc` で数秒。2回目以降は再利用）：

```sh
BIN="work/transcribe-speechanalyzer"
[ -x "$BIN" ] || swiftc -O "$SKILL/scripts/transcribe-speechanalyzer.swift" -o "$BIN"

ffmpeg -y -i "input" -ac 1 -ar 16000 -c:a pcm_s16le work/audio.wav
"$BIN" work/audio.wav transcript.txt ja-JP   # 英語は en-US
```

- 30分超は `run_in_background: true` で実行し完了を待つ（83分≒2分半で処理される）。初回は対象 locale のモデルを自動DLする
- 言語が不明なら冒頭2分だけ切り出して `ja-JP` で試し、破綻していれば `en-US` 等で再試行してから全編を回す
- 出力は `[HH:MM:SS]` 付き1セグメント1行。このタイムスタンプが後のフレーム対応付けの鍵

### 3. フレーム抽出

```sh
python3 "$SKILL/scripts/extract_frames.py" VIDEO work/frames
# 取りこぼしがあるとき: --threshold 0.04（感度上げ）
# ワイプ（発表者カメラ小窓）で誤検出が多いとき: --threshold 0.15〜0.3（感度下げ）
# 特定時刻を追加抽出: --at "734,1210"（秒）
```

`work/frames/frames.tsv` に「秒・時刻・ファイル名・シーンスコア・dup（重複マーク）」が出る。重複と推定されたフレームも削除はせず `dup=1` を立てるだけなので、最終判断は目視で行う。シーン検出が疎な動画（固定カメラの対談等）は自動で120秒間隔サンプリングに切り替わる。

### 4. 動画タイプの判定

`work/frames/` の冒頭・中盤・終盤のフレームを数枚 **Read で目視**して判定する。

- **スライド投影型**：画面の主役が投影スライド → 「全スライド取り込み」保証（ステップ5）へ
- **非スライド型**：対談・実演・板書など → トピック単位で代表場面を選び、2〜3分に1枚で構成

### 5. スライド投影型：「映された全スライドを取り込む」保証

これはこのスキルの中核要件。以下で取りこぼしゼロを確認する：

1. `frames.tsv` の全フレームを時系列に目視し、**投影スライドの切り替わりが全部捕捉されているか**確認する（`dup=1` でも本当に別スライドなら採用、白背景で本文だけ違うケースを取りこぼさない）
2. transcript の話題転換（「次に」「こちらのスライド」等）とフレーム時刻を突き合わせ、**話題が変わっているのに画像が無い区間**を探す
3. 怪しい区間は `--at "秒"` でピンポイント追加抽出、広範囲なら `--threshold 0.04` で再実行
4. 段階表示（同一スライドに箇条書きが順次出るビルド）は**完成形の1枚**だけ採用でよい
5. 採用フレームを `src/img/NN_slug.jpg`（例 `07_classroom.jpg`）にコピー・改名する

### 6. フレームと文字起こしの対応付け → スライド設計

各採用フレームの時刻から次のフレームの時刻までに話された内容を transcript から拾い、そのスライドの要点（3〜6項目）にまとめる。

- **points には「画像の説明」ではなく「そこで話された内容」を書く**。画像に書かれていない口頭の補足・数字・注意点を優先する
- デッキ構成：表紙（.cover）→ 必要ならアジェンダ → 本文（1投影スライド=1枚）→ 大きな話題の変わり目に扉（.divider）→ まとめ（.full-text）
- 表紙には動画タイトル・登壇者・動画の長さ・「文字起こし（Apple SpeechAnalyzer）をもとに再構成」等の生成方法を記載

### 7. 外国語動画の日本語化

- 見出し（h2）・要点（points）・まとめは**すべて日本語**で書く
- 取り込んだ原語スライド画像の下の points には、日本語訳に加えて重要な専門用語の原文を `<span class="orig">(retrieval-augmented generation)</span>` の形で併記する
- 原題・原語は表紙の .meta に記載。transcript.txt は原語のまま保存する

### 8. HTML 生成

`$SKILL/assets/deck.css` と `$SKILL/assets/deck.js` を `src/assets/` へコピーし、次の骨格で `src/index.html` を書く（画像は `img/` を相対参照。単一ファイル化は次のステップで自動処理するので、ここでは分割ソースのまま書く）：

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>（動画タイトル） — 要点スライド</title>
<link rel="stylesheet" href="assets/deck.css">
</head>
<body>
<div class="progress"></div>

<!-- 1 表紙 -->
<section class="slide cover">
  <div class="brand">（シリーズ名・チャンネル名）</div>
  <h1>（タイトル）</h1>
  <p class="lead">（この動画が何の話か2〜3文）</p>
  <div class="meta">
    <span class="tag">登壇</span>（登壇者）<br>
    <span class="tag">約NN分</span> 動画の文字起こし（Apple SpeechAnalyzer）をもとに要点を再構成
  </div>
  <div class="foot"><span class="src">（出典）</span><span>1 / N</span></div>
</section>

<!-- 2 本文スライドの型 -->
<section class="slide">
  <div class="kicker">（セクション名）</div>
  <h2>そのスライドの主張を<span class="em">強調付き</span>で</h2>
  <div class="content">
    <img class="shot" src="img/02_slug.jpg" alt="（画像の内容）">
    <ul class="points">
      <li><b>キーワード</b>：話された内容の要約</li>
      <li class="ok">良い点・推奨事項</li>
      <li class="warn">注意点・制約</li>
      <li>訳語の併記例 <span class="orig">(original term)</span></li>
    </ul>
  </div>
  <div class="foot">
    <span class="src">（出典）</span>
    <a class="ts" href="https://youtu.be/VIDEOID?t=734" target="_blank" rel="noopener">▶ 12:14</a>
    <span>2 / N</span>
  </div>
</section>
<!-- ローカル動画のタイムスタンプはリンクにせず: <span class="ts">▶ 12:14</span> -->

<!-- 扉: <section class="slide divider"> ／ まとめ: <div class="full-text"> -->

<div class="nav">
  <button class="prev" aria-label="前へ">‹</button>
  <span class="counter">1 / N</span>
  <button class="next" aria-label="次へ">›</button>
</div>
<div class="hint">← → / Space で移動・印刷でPDF化</div>
<script src="assets/deck.js"></script>
</body>
</html>
```

- 画像と文字量のバランス：画像が横長スライドなら標準の `.content`、文字が多いときは `.content.text-wide`
- タイムスタンプはそのスライドの**話が始まる時刻**（フレーム時刻でよい）。YouTube は `https://youtu.be/<id>?t=<秒>`

### 9. 単一ファイル化（最終成果物の生成）

分割ソース版を検証（ステップ10の前半）してから、パッカーで単一HTMLに固める：

```sh
python3 "$SKILL/scripts/pack_single_html.py" \
  src/index.html "<わかりやすい日本語名>_スライド.html"
```

- CSS・JS はインライン化、画像は base64 data URI で埋め込まれる
- Pillow があれば画像は幅1600px・品質82に自動再圧縮（20枚規模で3〜5MB程度に収まる）
- `warn: unresolved local refs` が出たら埋め込み漏れ。正規表現に掛からない書き方（`<link>` の属性順など）をしていないか `src/index.html` を確認して直す

### 10. 検証（提示前に必ず）

分割ソース版で：
- [ ] `grep -o 'img/[^"]*' src/index.html | sort -u` と `ls src/img/` が一致（参照切れ・孤児画像なし）
- [ ] スライド投影型なら、frames.tsv の全転換が「採用」か「重複・ビルド途中として除外」かに仕分けされている（取りこぼしゼロ）
- [ ] タイムスタンプが単調増加、ページ番号 n/N が実枚数と一致
- [ ] 外国語動画：日本語主体になっているか、重要語に原文併記があるか

単一ファイル版で：
- [ ] `grep -c 'src="img/\|href="assets/\|src="assets/' <単一ファイル>.html` が 0（ローカル参照が残っていない）
- [ ] ファイルサイズが常識的（〜10MB。大きすぎるときは Pillow を入れて再パック）
- [ ] `open <単一ファイル>.html` で先頭・中間・末尾を目視（レイアウト崩れ・文字化け・画像欠けなし）

### 11. 報告

**配布は単一HTMLファイル1つでよい**ことを明示しつつ、出力パス・スライド枚数・動画の長さ・文字起こし方式（SpeechAnalyzer / YouTube字幕）・外国語なら翻訳方針・取りこぼし確認の結果を報告する。`work/` は削除してよい旨も伝える。
