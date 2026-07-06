#!/usr/bin/env python3
"""
extract_frames.py — 動画から場面転換フレームを抽出する（video-to-slides スキル用）

ffmpeg のシーン検出で場面転換の時刻を取得し、各時刻のフレームを JPEG で保存する。
スライド投影型の動画ではスライドの切り替わりがそのままシーン検出に掛かるため、
「映されたスライドを全部取る」用途に使える。

Usage:
  python3 extract_frames.py VIDEO OUTDIR [options]

Options:
  --threshold FLOAT   シーン検出のしきい値 (default: 0.08。取りこぼしがあれば 0.04 まで下げる)
  --min-gap FLOAT     この秒数以内に連続する転換は1つに統合 (default: 3.0)
  --max-frames INT    最大フレーム数。超えたらスコア上位を採用 (default: 150)
  --offset FLOAT      検出時刻から何秒後のフレームを切り出すか (default: 0.6。転換直後のブレ回避)
  --at "T1,T2,..."    シーン検出に加えて指定秒のフレームも切り出す（取りこぼしの追加抽出用）
  --uniform-gap FLOAT 検出が疎なときに補う一定間隔サンプリングの間隔秒 (default: 120)

Output:
  OUTDIR/frame_NNN_HHMMSS.jpg
  OUTDIR/frames.tsv   (index, seconds, hh:mm:ss, filename, scene_score)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, **kw):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"command failed: {' '.join(cmd)}\n{e.stderr[-2000:]}\n")
        raise


def probe_duration(video):
    r = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    return float(r.stdout.strip())


def detect_scenes(video, threshold, tmpdir):
    """シーン転換の (秒, スコア) リストを返す"""
    meta = Path(tmpdir) / "scene_meta.txt"
    run([
        "ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(video),
        "-vf", f"select='gt(scene,{threshold})',metadata=print:file={meta}",
        "-an", "-f", "null", "-",
    ])
    scenes = []
    pts = None
    for line in meta.read_text().splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts = float(m.group(1))
            continue
        m = re.search(r"lavfi\.scene_score=([\d.]+)", line)
        if m and pts is not None:
            scenes.append((pts, float(m.group(1))))
            pts = None
    return scenes


def merge_close(times, min_gap):
    """min_gap 秒以内に連続する転換は最初の1つに統合（スコアは高い方を残す）"""
    merged = []
    for t, score in sorted(times):
        if merged and t - merged[-1][0] < min_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], score))
        else:
            merged.append((t, score))
    return merged


def hhmmss(sec):
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def extract_frame(video, t, path):
    run([
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(path),
    ])


def dedup_hashes(paths):
    """Pillow があれば average-hash で連続重複フレームを検出して返す（なければ空集合）。

    16x16 (256bit) で判定する。8x8 だと「白背景で本文テキストだけ違うスライド」を
    同一と誤判定し、実在するスライドを取りこぼす。
    """
    try:
        from PIL import Image
    except ImportError:
        return set()

    def signature(p):
        img = Image.open(p).convert("L").resize((16, 16))
        px = list(img.getdata())
        avg = sum(px) / len(px)
        bits = sum(1 << i for i, v in enumerate(px) if v > avg)
        return bits, avg

    dupes, prev = set(), None
    for p in paths:
        bits, avg = signature(p)
        same = (
            prev is not None
            and bin(bits ^ prev[0]).count("1") <= 6
            and abs(avg - prev[1]) < 4
        )
        if same:
            dupes.add(p)
        else:
            prev = (bits, avg)
    return dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--threshold", type=float, default=0.08)
    ap.add_argument("--min-gap", type=float, default=3.0)
    ap.add_argument("--max-frames", type=int, default=150)
    ap.add_argument("--offset", type=float, default=0.6)
    ap.add_argument("--at", default="")
    ap.add_argument("--uniform-gap", type=float, default=120.0)
    args = ap.parse_args()

    video = Path(args.video)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    duration = probe_duration(video)
    scenes = detect_scenes(video, args.threshold, outdir)

    # 冒頭（タイトル）と終盤は常に含める
    candidates = [(1.0, 1.0), (max(duration - 5.0, 1.0), 0.0)] + scenes

    # 手動追加分
    for tok in filter(None, (t.strip() for t in args.at.split(","))):
        candidates.append((float(tok), 1.0))

    # シーン検出が疎（uniform-gap の2倍あたり1つ未満）なら一定間隔で補う
    if len(scenes) < duration / (args.uniform_gap * 2):
        t = args.uniform_gap
        while t < duration - 10:
            candidates.append((t, 0.0))
            t += args.uniform_gap

    merged = merge_close(candidates, args.min_gap)
    if len(merged) > args.max_frames:
        top = sorted(merged, key=lambda x: -x[1])[: args.max_frames]
        merged = sorted(top)
        sys.stderr.write(
            f"warn: {len(candidates)} candidates > max-frames; kept top {args.max_frames} by score\n"
        )

    rows = []
    for i, (t, score) in enumerate(merged, 1):
        shot_t = min(t + args.offset, duration - 0.2)
        name = f"frame_{i:03d}_{hhmmss(t).replace(':', '')}.jpg"
        extract_frame(video, shot_t, outdir / name)
        rows.append((i, t, hhmmss(t), name, score))

    # 重複は削除せずマークのみ（「全スライド取り込み」の最終判断は目視に委ねる）
    dupes = dedup_hashes([outdir / r[3] for r in rows])

    tsv = outdir / "frames.tsv"
    lines = ["index\tseconds\ttimestamp\tfile\tscene_score\tdup"]
    lines += [
        f"{i}\t{t:.1f}\t{ts}\t{name}\t{score:.3f}\t{int((outdir / name) in dupes)}"
        for i, t, ts, name, score in rows
    ]
    tsv.write_text("\n".join(lines) + "\n")

    n_dup = len(dupes)
    print(
        f"duration: {duration:.0f}s  scenes detected: {len(scenes)}  "
        f"frames saved: {len(rows)} (dup-marked: {n_dup})"
    )
    print(f"list: {tsv}")


if __name__ == "__main__":
    main()
