#!/usr/bin/env python3
"""Gemini API で音声・動画を文字起こしする（Windows / macOS / Linux 共通）。

    python3 transcribe_gemini.py <入力の音声か動画> [出力.txt] [--lang ja] [--model gemini-3.8-flash]

API キーの置き場所（どちらか）:
  * 環境変数 GEMINI_API_KEY
  * ファイル ~/.config/gemini/api_key（Windows では %USERPROFILE%\\.config\\gemini\\api_key）
    キーは https://aistudio.google.com/apikey で発行できる。

設計の要点
  * 20MB を超える入力は Files API にアップロードして **1回で送る**（分割しない）。
    1リクエストで音声 9.5 時間まで扱えるので、講義や会議はまず分割不要。
    分割すると後半のモデルが前半を知らず、固有名詞の学習が効かなくなる
  * 9.5 時間を超えるものだけ --split を付けたときに分割して結合する（重なり 2 秒・時刻補正あり）
  * thinkingBudget=0。文字起こしは推論タスクではなく、thinking を許すと
    「整えよう」として言い直し・要約が混ざるうえ課金だけ増える
  * 逐語性を優先するプロンプト。聞き取れない箇所は [不明]、自信の無い語には (?)
  * 出力は [MM:SS] 付きで1発話1行。SpeechAnalyzer 版（[HH:MM:SS]）とほぼ同じ形式

注意
  * **音声をクラウド（Google）に送る。** 会議・ゼミなど第三者の発言を含む録音を送ってよいかは
    自分の組織の規程で判断すること。ローカル完結が要るなら macOS の SpeechAnalyzer 版を使う
  * Gemini API の無料枠は、Google の利用規約で機密・個人情報の送信が禁じられている。
    有料枠（Tier 1 以上）で使うこと
  * 必要な外部コマンドは ffmpeg / ffprobe だけ（音声の抽出と長さの取得に使う）
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"
FILES = "https://generativelanguage.googleapis.com/v1beta/{name}"
KEY_FILE = pathlib.Path.home() / ".config" / "gemini" / "api_key"

MAX_INLINE = 18 * 1024 * 1024      # 20MB 上限に対する安全マージン。超えたら Files API
MAX_ONE_REQUEST_SEC = 9.5 * 3600   # 1リクエストで扱える音声長の上限（公式）
CHUNK_SEC = 900                    # 分割時の1片の長さ（15分）
OVERLAP_SEC = 2                    # 継ぎ目の欠落を防ぐ重なり

LANG_NAMES = {"ja": "日本語", "en": "英語", "zh": "中国語", "ko": "韓国語",
              "es": "スペイン語", "fr": "フランス語", "de": "ドイツ語"}

PROMPT = """この音声を文字起こししてください。音声の言語は{lang}です。文字起こしも{lang}のまま書いてください。

条件：
- 要約・整形・言い換えを一切しないでください。話された言葉をそのまま書いてください
- 言い淀みや言い直しも省かずに書いてください
- 発話のまとまりごとに改行し、行頭に [MM:SS] 形式で開始時刻を付けてください
- 聞き取れなかった箇所は、推測で埋めずに [不明] と書いてください
- 固有名詞・専門用語は、確信が持てない場合に限り、その語の直後に (?) を付けてください
- 前置きや説明を書かず、文字起こしだけを出力してください"""


def api_key() -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    sys.exit(
        "ERROR: Gemini の API キーが見つかりません。\n"
        "  環境変数 GEMINI_API_KEY を設定するか、次のファイルにキーだけを書いてください:\n"
        f"    {KEY_FILE}\n"
        "  キーの発行: https://aistudio.google.com/apikey")


def need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        sys.exit(
            f"ERROR: {cmd} が見つかりません。音声の変換に必要です。\n"
            "  Windows: winget install Gyan.FFmpeg（または ffmpeg の zip を展開して bin を PATH に）\n"
            "  macOS  : brew install ffmpeg\n"
            "  Linux  : apt install ffmpeg")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, errors="replace")


def to_m4a(src: pathlib.Path, dst: pathlib.Path, ss: float | None = None,
           dur: float | None = None) -> pathlib.Path:
    """音声を 64kbps モノラル m4a に変換（必要なら区間を切り出す）。動画を渡してもよい。"""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)]
    run(cmd)
    return dst


def duration_sec(p: pathlib.Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)])
    return float(r.stdout.strip())


def upload_file(path: pathlib.Path, key: str) -> str:
    """Files API に再開可能アップロードし、ACTIVE になった file の URI を返す。"""
    mime = mimetypes.guess_type(path.name)[0] or "audio/mp4"
    size = path.stat().st_size
    start = urllib.request.Request(
        f"{UPLOAD}?key={key}",
        data=json.dumps({"file": {"display_name": path.name}}).encode(),
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(start, timeout=120) as r:
        session_url = r.headers.get("X-Goog-Upload-URL")
    if not session_url:
        sys.exit("ERROR: アップロードURLが返りませんでした")

    put = urllib.request.Request(
        session_url, data=path.read_bytes(),
        headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                 "X-Goog-Upload-Command": "upload, finalize"},
    )
    with urllib.request.urlopen(put, timeout=1800) as r:
        info = json.load(r)["file"]

    name, uri = info["name"], info["uri"]
    for _ in range(120):                       # 音声は取り込み処理が入るので ACTIVE を待つ
        if info.get("state") == "ACTIVE":
            return uri
        if info.get("state") == "FAILED":
            sys.exit(f"ERROR: アップロード処理に失敗: {info}")
        time.sleep(2)
        with urllib.request.urlopen(FILES.format(name=name) + f"?key={key}", timeout=60) as r:
            info = json.load(r)
    sys.exit("ERROR: ファイルが ACTIVE になりませんでした")


def delete_file(uri: str, key: str) -> None:
    """使い終わったらサーバから消す（既定でも48時間で消えるが、残さない）。"""
    try:
        name = "files/" + uri.rstrip("/").split("/")[-1]
        req = urllib.request.Request(FILES.format(name=name) + f"?key={key}", method="DELETE")
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:
        pass


def call(model: str, audio: pathlib.Path | None, prompt: str, key: str,
         file_uri: str | None = None) -> tuple[str, dict]:
    if file_uri:
        part = {"fileData": {"mimeType": "audio/mp4", "fileUri": file_uri}}
    else:
        mime = mimetypes.guess_type(audio.name)[0] or "audio/mp4"
        part = {"inlineData": {"mimeType": mime,
                               "data": base64.b64encode(audio.read_bytes()).decode()}}
    body = {
        "contents": [{"parts": [{"text": prompt}, part]}],
        "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingBudget": 0}},
    }
    req = urllib.request.Request(API.format(model=model) + f"?key={key}",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 503) and attempt < 3:
                wait = 5 * (attempt + 1)
                print(f"  [{e.code}] 混雑。{wait}秒待って再試行", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"ERROR: HTTP {e.code}\n{msg}")
    else:
        sys.exit("ERROR: 再試行しても失敗しました")

    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    if not text:
        sys.exit(f"ERROR: 空の応答（finishReason={cand.get('finishReason')}）")
    return text, d.get("usageMetadata", {})


def shift(text: str, offset: int) -> str:
    """[MM:SS] を offset 秒ぶんずらす（分割した2片目以降のため）。"""
    def f(m):
        t = int(m.group(1)) * 60 + int(m.group(2)) + offset
        return f"[{t // 60:02d}:{t % 60:02d}]"
    return re.sub(r"\[(\d{1,3}):(\d{2})\]", f, text)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows の cp932 コンソールで日本語が落ちないように
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Gemini で音声・動画を文字起こし（クロスプラットフォーム）")
    ap.add_argument("input", type=pathlib.Path, help="音声または動画ファイル")
    ap.add_argument("output", type=pathlib.Path, nargs="?", default=None,
                    help="出力テキスト（既定: <入力>.gemini.txt）")
    ap.add_argument("--lang", default="ja",
                    help="音声の言語コード（ja/en/zh/...。既定 ja）。文字起こしはその言語のまま出す")
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--prompt-file", type=pathlib.Path, default=None,
                    help="独自のプロンプトをファイルから読む（話者分離など）")
    ap.add_argument("--split", action="store_true",
                    help="9.5時間を超える音声を分割して処理する。既定では分割しない")
    a = ap.parse_args()
    if not a.input.exists():
        sys.exit(f"ERROR: ファイルがありません: {a.input}")

    need("ffmpeg"); need("ffprobe")
    key = api_key()
    out = a.output or a.input.with_suffix(".gemini.txt")
    work = pathlib.Path(tempfile.mkdtemp(prefix="transcribe_gemini_"))
    if a.prompt_file:
        prompt = a.prompt_file.read_text(encoding="utf-8")
    else:
        prompt = PROMPT.format(lang=LANG_NAMES.get(a.lang, a.lang))

    total = duration_sec(a.input)
    whole = to_m4a(a.input, work / "all.m4a")
    t0 = time.time()
    size = whole.stat().st_size
    uploaded_uri = None

    if size <= MAX_INLINE:
        print(f"  1本で送信（{size / 1024 / 1024:.1f} MB・{total / 60:.1f}分）", flush=True)
        text, usage = call(a.model, whole, prompt, key)
        usages = [usage]
    elif total <= MAX_ONE_REQUEST_SEC:
        # 20MB は「リクエストの大きさ」の上限であって音声長の上限ではない。
        # Files API に上げれば 9.5 時間まで1回で送れる。
        print(f"  {size / 1024 / 1024:.1f} MB・{total / 60:.1f}分 → Files API にアップロードして1回で送信",
              flush=True)
        uploaded_uri = upload_file(whole, key)
        print(f"  アップロード完了。文字起こし中（推定 {total * 32 / 1000:.0f}k トークン）", flush=True)
        text, usage = call(a.model, None, prompt, key, file_uri=uploaded_uri)
        usages = [usage]
    elif not a.split:
        sys.exit(
            f"ERROR: 音声が {total / 3600:.1f} 時間あり、1リクエストの上限 9.5 時間を超えています。\n"
            "  分割すると後半のモデルが前半を知らないまま処理され、質が落ちます。\n"
            "  それでも分割してよければ --split を付けて実行してください。")
    else:
        n = int(total // (CHUNK_SEC - OVERLAP_SEC)) + 1
        print(f"  {total / 3600:.1f}時間 → 9.5時間の上限を超えるため {n}片に分割", flush=True)
        parts, usages = [], []
        for i in range(n):
            ss = i * (CHUNK_SEC - OVERLAP_SEC)
            if ss >= total:
                break
            c = to_m4a(a.input, work / f"c{i}.m4a", ss=ss, dur=CHUNK_SEC)
            print(f"  [{i + 1}/{n}] {ss // 60:.0f}分〜 を送信 ({c.stat().st_size / 1024 / 1024:.1f} MB)")
            t, u = call(a.model, c, prompt, key)
            parts.append(shift(t, int(ss)) if i else t)
            usages.append(u)
        text = "\n".join(parts)

    if uploaded_uri:
        delete_file(uploaded_uri, key)
    shutil.rmtree(work, ignore_errors=True)

    text = re.sub(r"\n{2,}", "\n", text).strip() + "\n"
    out.write_text(text, encoding="utf-8")
    el = time.time() - t0
    tin = sum(u.get("promptTokenCount", 0) for u in usages)
    tout = sum(u.get("candidatesTokenCount", 0) for u in usages)
    print(f"  完了: {out}  {len(text)}文字", flush=True)
    print(f"  所要 {el:.1f} 秒（音声 {total / 60:.1f} 分 → 実時間比 {total / max(el, 0.1):.1f}倍速）", flush=True)
    print(f"  トークン 入力{tin:,} / 出力{tout:,}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
