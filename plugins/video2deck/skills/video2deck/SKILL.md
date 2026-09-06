---
effort: medium
name: video2deck
description: 動画（ローカルMP4/MOV等、YouTubeリンク、X/Twitterの動画付きポスト）から「動画を見なくても内容が分かる」HTMLスライドデッキを生成する汎用スキル。文字起こし（Gemini API＝Win/Mac/Linux、または Apple SpeechAnalyzer＝macOS 26+ ローカル。どちらを使うか毎回選ぶ）／YouTube字幕と、ffmpegによる場面フレーム抽出を組み合わせ、スライド投影型動画は映された全スライドを取り込む。外国語動画は日本語化。最終成果物はCSS・JS・画像を全部埋め込んだ単一HTMLファイル（1ファイル渡せば誰でも見られる）。Triggers on 動画をスライドに, 動画からスライド, この動画をまとめて, ウェビナーをスライド化, 講演動画の要約, 動画を見る時間がない, video to slides, video to deck, YouTubeをスライドに, Xの動画をスライドに, ポストの動画をスライドに.
---

# video2deck — 動画 → 要点スライドデッキ生成

## ゴール

渡された動画1本につき、**動画を見なくても「何を話し、何を見せたか」が分かる** HTML スライドデッキを1つ作る。

- スライドを映しながら話す動画（ウェビナー・講演・授業）→ **映し出されたスライドをすべて取り込み**、各スライドに「そこで話された内容」の要約を付ける
- スライド投影のない動画（対談・実演デモ等）→ 場面転換フレーム＋トピック要約で構成
- 外国語動画 → 日本語主体＋原文キーワード併記で日本語化
- 粒度の目安：**約2分に1枚**（33分→16枚、51分→26枚程度）
- 各スライドに元動画へのタイムスタンプ（YouTubeは該当秒への直リンク）
- 入力は **ローカル動画ファイル／YouTube／X（Twitter）の動画付きポスト** に対応（オンライン動画の取得はいずれも yt-dlp）

## スキルのファイル配置（重要）

このスキルは補助スクリプトを同梱している。スキル起動時にハーネスが表示する
**「Base directory for this skill: …」** のパスを `$SKILL` とすると：

- `$SKILL/scripts/extract_frames.py` — 場面フレーム抽出
- `$SKILL/scripts/pack_single_html.py` — 単一HTML化パッカー
- `$SKILL/scripts/transcribe_gemini.py` — Gemini API 文字起こし（Windows / macOS / Linux）
- `$SKILL/scripts/transcribe-speechanalyzer.swift` — Apple SpeechAnalyzer ローカル文字起こしのソース（macOS 26+）
- `$SKILL/assets/deck.css`, `$SKILL/assets/deck.js` — デッキの見た目とナビ

以降のコマンド例の `$SKILL` は、この実際のパスに置き換えて実行すること。

## 前提ツール（最初に確認）

| ツール | 確認 | 無いとき |
|---|---|---|
| ffmpeg / ffprobe | `which ffmpeg ffprobe` | macOS `brew install ffmpeg` ／ Windows `winget install Gyan.FFmpeg` |
| yt-dlp（YouTube・X等のURL時のみ） | `which yt-dlp` | macOS `brew install yt-dlp` ／ Windows `winget install yt-dlp` |
| Python 3.9+ ＋ Pillow（コンタクトシート生成・**実質必須**） | `python3 -c "import PIL"` | `pip3 install Pillow`（Windows は `python` / `pip`） |
| 文字起こしエンジン（**ステップ2でどちらか選ぶ**） | 下記 | Gemini: API キー（環境変数 `GEMINI_API_KEY` か `~/.config/gemini/api_key`）／ SpeechAnalyzer: **macOS 26+** と `swiftc`（`xcode-select --install`） |

Windows では以降のコマンド例を Git Bash（Claude Code が使うシェル）でそのまま実行できる。
`python3` が無ければ `python` に読み替える。

**音源をクラウドに送るのは、ステップ2でユーザーが Gemini を選んだときだけ。** それ以外の外部サービス（他の文字起こしAPI・動画アップロード先）に音源・映像を送らない。SpeechAnalyzer を選んだ場合は端末内で完結させる。macOS 26 未満・非Macで Gemini も使えない場合のみ、ローカルWhisper（`mlx_whisper` 等）にフォールバックする（その場合も音源は外に出さない）。

## 出力構成

保存先：**動画ファイルと同じディレクトリ**に `<動画ベース名>_slides/`。YouTube・X等のURLの場合はカレントプロジェクト内に `<タイトルの短いslug>_slides/`。

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

字幕の品質判定：手動字幕（`subtitles`）があればそれを使う。自動字幕（`automatic_captions`）しか無い場合は冒頭を読んで判定し、**断片の重複だらけ・意味が取れない場合は字幕を捨てて、DL済み動画からステップ2の文字起こし**にかける。日本語動画は自動字幕があっても、句読点・固有名詞の精度でステップ2のエンジン（特に Gemini）が上回ることが多いので、原則ステップ2の文字起こしをベースにし、固有名詞だけ字幕と突き合わせて校正するとよい。

**C. X（Twitter）の動画付きポスト**（`x.com/…/status/…` / `twitter.com/…`）：

yt-dlp がそのまま対応しているので、メタデータ・映像取得はBと同じコマンドでよい。Bとの違いだけ押さえる：

- **字幕は存在しない** → 字幕取得はスキップし、常にステップ2の文字起こしへ
- 鍵アカウント・ログイン必須のポストは `--cookies-from-browser chrome` を付けて取得する
- タイトルはポスト本文の先頭から生成されて長いことが多い → `work/meta.json` の本文から**内容を表す短いslug**を自分で決める
- タイムスタンプの秒指定リンクは張れない（ステップ8参照）

### 2. 文字起こし（ローカル動画・Xの動画、または字幕が使えないYouTube）

#### 2-0. エンジンを選ぶ（毎回）

エンジンは2つ。**ユーザーが指定していなければ、作業を始める前に AskUserQuestion で1回だけ聞く**（推奨を先頭に）。

| | **Gemini API**（推奨） | **Apple SpeechAnalyzer** |
|---|---|---|
| 動く環境 | Windows / macOS / Linux | **macOS 26+ のみ** |
| 音声の行き先 | Google のクラウドに送る | **端末内で完結**（オフライン可） |
| 固有名詞・専門用語 | 強い（文脈で解決する） | 弱め（後で校正が要る） |
| 読みやすさ | 話者が変わるたびに改行 | 1段落に押し込みがち |
| 速さ | 実時間の30〜55倍速 | 実時間の約140倍速（83分≒2分半） |
| 費用 | 有料枠。100分で数十円程度 | 無料 |
| 必要なもの | API キー・ffmpeg | swiftc（初回ビルド）・ffmpeg |

判定の目安：

- **音源を外に出せない**（第三者の発言を含む会議・ゼミ・学生の録音で、組織の規程が許さない）→ SpeechAnalyzer
- それ以外 → Gemini。仕上がりがそのまま資料になる
- **Windows / Linux では選択肢を出さず Gemini 一択**。キーが無ければ設定手順（下記）を案内して止まる
- Gemini API の**無料枠は Google の規約で機密・個人情報の送信が禁止**されている。有料枠（Tier 1 以上）で使う

どちらの出力もタイムスタンプ付き1発話1行で、以降の手順は共通（Gemini は `[MM:SS]`、SpeechAnalyzer は `[HH:MM:SS]`）。

#### 2-A. Gemini API（Windows / macOS / Linux）

キーは環境変数 `GEMINI_API_KEY`、または `~/.config/gemini/api_key`（Windows は `%USERPROFILE%\.config\gemini\api_key`）にキーだけを1行で書く。発行は https://aistudio.google.com/apikey 。

```sh
python3 "$SKILL/scripts/transcribe_gemini.py" "input.mp4" transcript.txt --lang ja   # 英語は --lang en
```

- 動画をそのまま渡してよい（内部で 64kbps モノラル m4a に落として送る）
- 20MB を超えるぶんは Files API に上げて **1回で送る**。分割しない（分割すると後半が前半の固有名詞を知らないまま処理される）。9.5時間超だけ `--split`
- 送った音声は処理後にサーバから削除する
- 30分超は `run_in_background: true` で実行し完了を待つ
- 人名は滑らかに誤る（読みが同じ別の漢字を当てる）。**登壇者スライド・タイトルカードの表記が一次資料**。デッキに書く名前は画面側を採る

#### 2-B. Apple SpeechAnalyzer（macOS 26+・ローカル完結）

初回のみ、同梱ソースから文字起こしツールをビルドする（`swiftc` で数秒。2回目以降は再利用）：

```sh
BIN="work/transcribe-speechanalyzer"
[ -x "$BIN" ] || swiftc -O "$SKILL/scripts/transcribe-speechanalyzer.swift" -o "$BIN"

ffmpeg -hide_banner -loglevel error -nostats -y -i "input" -ac 1 -ar 16000 -c:a pcm_s16le work/audio.wav
"$BIN" work/audio.wav transcript.txt ja-JP   # 英語は en-US
```

- 30分超は `run_in_background: true` で実行し完了を待つ。初回は対象 locale のモデルを自動DLする
- 言語が不明なら冒頭2分だけ切り出して `ja-JP` で試し、破綻していれば `en-US` 等で再試行してから全編を回す
- 固有名詞の誤認識が残る（「機関別認証評価」「3ポリ」のような専門語）。重要語は文脈と画面で校正する

### 3. フレーム抽出

```sh
python3 "$SKILL/scripts/extract_frames.py" VIDEO work/frames
# 取りこぼしがあるとき: --threshold 0.04（感度上げ）
# ワイプ（発表者カメラ小窓）で誤検出が多いとき: --threshold 0.15〜0.3（感度下げ）
# 特定時刻を追加抽出: --at "734,1210"（秒）
```

`work/frames/frames.tsv` に「秒・時刻・ファイル名・シーンスコア・dup（重複マーク）」が出る。重複と推定されたフレームも削除はせず `dup=1` を立てるだけなので、最終判断は目視で行う。シーン検出が疎な動画（固定カメラの対談等）は自動で120秒間隔サンプリングに切り替わる。

### 4. コンタクトシート1枚で全体を把握する

`extract_frames.py` は個別フレームに加えて **`frames/contact.jpg`（一覧画像）** を作る。
サムネイルには連番と時刻が焼き込んである。

**まず、この1枚だけを Read する。個別フレームを1枚ずつ読まない。**

実測（33分の動画・34フレーム）:

| 読み方 | トークン |
|---|---|
| 個別34枚を Read | 41,779 |
| **コンタクトシート1枚（4列400px・既定）** | **4,742（89%削減）** |

**列数と大きさ**: 既定は4列400px。最初5列320pxにしたところ、日本語スライドの本文が読めず
**別スライドを同一と誤読する事故**が出た（2026-09-06）。文字の小さいスライドが続くときは
`--contact-width 540`（3列相当）まで上げてよい。それでも個別読みの80%減に収まる。

100分のウェビナーなら個別で12万トークンを超える。ここがこのスキルの最大のコスト源だった。
40枚を超えると `contact_01.jpg` `contact_02.jpg` … に自動で分割される。

一覧を見て、この2つを同時に判定する：

- **動画タイプ** — 画面の主役が投影スライドか（スライド投影型）、対談・実演か（非スライド型）
- **採用するフレームの番号** — 「3, 7, 12〜15, 20 を採用」のように番号で決める

### 5. スライド投影型：「映された全スライドを取り込む」保証

このスキルの中核要件。**コンタクトシート上で**取りこぼしゼロを確認する。

1. 一覧を時系列に見て、**投影スライドの切り替わりが全部捕捉されているか**確認する。
   `dup=1` でも本当に別スライドなら採用（白背景で本文だけ違うケースを取りこぼさない）
2. **段階表示（ビルド）は完成形の1枚だけ**採用する。
   一覧なら「13→14→15 は同じスライドに図が順次出ているだけ」が一目で分かる
3. transcript の話題転換（「次に」「こちらのスライド」等）とフレーム時刻を突き合わせ、
   **話題が変わっているのに画像が無い区間**を探す
4. 怪しい区間だけ、**その個別フレームを原寸で Read** して確かめる（数枚で足りる）
5. 広範囲に取りこぼしがあれば `--threshold 0.04` で再実行、
   ピンポイントなら `--at "秒"` で追加抽出
6. 採用フレームを `src/img/NN_slug.jpg`（例 `07_classroom.jpg`）にコピー・改名する

#### 白背景のスライドは既定のしきい値で系統的に落ちる（2026-09-06 実測）

Google 管理コンソールのような**白背景でレイアウトの似たスライド**は、シーン検出の
既定 `--threshold 0.08` を越えず、**33枚中10枚（30%）が1枚も抽出されなかった**実例がある。
このとき「怪しい区間だけ個別フレームを Read する」は使えない。**画像が1枚も無いのだから読めない。**

有効だった手順（管理画面・ダッシュボード系のウェビナーではこれを既定にする）:

1. **transcript の話題転換の時刻を先に列挙する**（「次に」「こちらの画面」「〜の設定です」）
2. コンタクトシートと突き合わせ、**話題が変わっているのにフレームが無い区間**を特定する
3. その時刻を `--at "1208,1393,1546,..."` で狙い撃ちして追加抽出する
4. **追加分だけの小さいコンタクトシートを自作して、1回だけ Read する**
   （個別に読まない。`make_contact_sheets` と同じ要領で Pillow で束ねればよい）

`--threshold 0.04` に下げる手もあるが、フレーム数が跳ねてシートが増えるので、
**先に transcript で当たりを付けるほうが速い**。

> **コンタクトシートを飛ばして個別フレームを読み始めない。**
> 「全部見ないと取りこぼすのでは」と思うかもしれないが、逆である。
> 並べて見るほうが切り替わりも重複も見つけやすく、14倍安い。
> 原寸が要るのは、文字が小さくて読めない数枚だけ。

### 6. フレームと文字起こしの対応付け → スライド設計

各採用フレームの時刻から次のフレームの時刻までに話された内容を transcript から拾い、そのスライドの要点（3〜6項目）にまとめる。

- **points には「画像の説明」ではなく「そこで話された内容」を書く**。画像に書かれていない口頭の補足・数字・注意点を優先する
- デッキ構成：表紙（.cover）→ 必要ならアジェンダ → 本文（1投影スライド=1枚）→ 大きな話題の変わり目に扉（.divider）→ まとめ（.full-text）
- 表紙には動画タイトル・登壇者・動画の長さ・「文字起こし（Gemini API／Apple SpeechAnalyzer）をもとに再構成」のように**実際に使ったエンジン名**で生成方法を記載

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
    <span class="tag">約NN分</span> 動画の文字起こし（使ったエンジン名）をもとに要点を再構成
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
- **X（Twitter）の動画は秒指定リンク非対応**なので、ローカル動画と同じく `<span class="ts">▶ 12:14</span>` のテキスト表記にする（表紙にはポストURLへのリンクを載せる）

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

**配布は単一HTMLファイル1つでよい**ことを明示しつつ、出力パス・スライド枚数・動画の長さ・文字起こし方式（Gemini / SpeechAnalyzer / YouTube字幕）・外国語なら翻訳方針・取りこぼし確認の結果を報告する。`work/` は削除してよい旨も伝える。

## 複数本を渡されたとき：1本1エージェントで並列に処理する

動画が2本以上あるときは、メインのセッションで順に処理しない。**1本につき1つのサブエージェント
（general-purpose）を同時に起動し、メインは結果の集約だけをする。** 理由は3つ揃っているから：

- 各本は互いに独立している（共有する状態が無い）
- 1本あたり数分かかる（文字起こし＋フレーム抽出の機械工程だけで、5.3時間ぶん7本が合計14分）
- コンタクトシートや確認用フレームの画像が、メインのコンテキストを埋めてしまう

やり方：

1. **エンジンの選択（ステップ2-0）は、委譲する前にメインで1回だけ聞く**。全本に同じ答えを適用する
2. 1メッセージ内で全エージェントを同時に起動する（順番に待たない）
3. 各エージェントへのプロンプトに必ず書くもの：
   - このスキルのパス（`$SKILL`）と「SKILL.md を読んでから始める」
   - 対象動画のパスと出力先フォルダ
   - 選んだ文字起こしエンジン
   - **「個別フレームを1枚ずつ Read しない。コンタクトシートで判定する」**（省くと各エージェントが個別読みを始める）
   - 報告の形式（出力パス・枚数・長さ・エンジン・取りこぼし確認の結果）と「検証していないことを完了と書かない」
4. メインは各報告を受けて、ステップ10の検証項目を抜き取りで確かめてからユーザーに報告する

1本だけなら委譲しない。委譲の往復のほうが高くつく。
