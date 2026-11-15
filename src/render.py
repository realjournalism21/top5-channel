"""Renders a vertical 1080x1920 Top 5 countdown video in the @top5rankingsforyou style."""
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
BG_TOP, BG_BOT = (8, 12, 32), (26, 14, 52)
PANEL, PANEL_EDGE = (15, 20, 48), (32, 40, 82)
WHITE, MUTED, DIM = (255, 255, 255), (140, 150, 185), (44, 52, 96)
GREEN, GOLD = (74, 222, 128), (255, 194, 75)
ACCENTS = {5: (255, 169, 77), 4: (116, 167, 255), 3: (94, 224, 181),
           2: (199, 155, 255), 1: (74, 222, 128)}
HANDLE = "@top5rankingsforyou"
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

INTRO_S, ITEM_S, OUTRO_S, FADE_S = 2.4, 3.0, 3.4, 0.4

_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / f"Poppins-{weight}.ttf"), size)
    return _font_cache[key]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def blend(c1, c2, a):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * a) for i in range(3))


def make_background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=blend(BG_TOP, BG_BOT, y / H))
    return img


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(draw, text, weight, max_w, max_lines, sizes):
    for size in sizes:
        fnt = font(weight, size)
        lines = wrap(draw, text, fnt, max_w)
        if len(lines) <= max_lines:
            return fnt, lines
    return fnt, lines[:max_lines]


def dots(draw, filled, total, color, x, y):
    for i in range(total):
        draw.ellipse([x + i * 34, y, x + i * 34 + 16, y + 16],
                     fill=color if i < filled else DIM)


def draw_logo(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 22, 60), outline=(40, 48, 110), width=4)
    draw.text((cx, cy - r * 0.42), "TOP", font=font("Bold", int(r * 0.6)), fill=WHITE, anchor="mm")
    draw.text((cx, cy + r * 0.10), "5", font=font("Bold", int(r * 1.05)), fill=GOLD, anchor="mm")
    for i in range(5):
        x = cx + (i - 2) * r * 0.16
        draw.ellipse([x - 5, cy + r * 0.78 - 5, x + 5, cy + r * 0.78 + 5], fill=GOLD)


def build_intro(content):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((70, 640), "TOP 5", font=font("Bold", 250), fill=WHITE, anchor="ls")
    fnt, lines = fit(d, content["title"].upper(), "Bold", 940, 3, range(96, 55, -4))
    y = 790
    for line in lines:
        d.text((70, y), line, font=fnt, fill=GREEN, anchor="ls")
        y += int(fnt.size * 1.2)
    d.text((70, y + 20), content["subtitle"].upper(), font=font("Medium", 34), fill=WHITE, anchor="ls")
    dots(d, 5, 5, GREEN, 70, y + 80)
    return layer


def build_item(content, item, index):
    rank, accent = item["rank"], ACCENTS[item["rank"]]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dots(d, index + 1, 5, accent, 70, 130)
    # rank circle + category
    d.ellipse([70, 200, 190, 320], fill=accent)
    d.text((130, 262), str(rank), font=font("Bold", 84), fill=(10, 14, 36), anchor="mm")
    d.text((215, 262), item["category"].upper(), font=font("Bold", 34), fill=accent, anchor="lm")
    # title
    fnt, lines = fit(d, item["name"].upper(), "Bold", 940, 2, range(88, 47, -4))
    y = 420
    for line in lines:
        d.text((70, y), line, font=fnt, fill=WHITE, anchor="ls")
        y += int(fnt.size * 1.18)
    # chart panel
    d.rounded_rectangle([70, 640, 1010, 1190], radius=32, fill=PANEL, outline=PANEL_EDGE, width=3)
    d.text((110, 690), content["metric_label"].upper(), font=font("Bold", 26), fill=MUTED, anchor="lm")
    # stat
    d.text((70, 1330), item["stat"], font=font("Bold", 130), fill=accent, anchor="ls")
    d.text((70, 1385), item["stat_caption"], font=font("Medium", 34), fill=WHITE, anchor="ls")
    fact_fnt = font("Regular", 34)
    y = 1450
    for line in wrap(d, item["fact"], fact_fnt, 940)[:3]:
        d.text((70, y), line, font=fact_fnt, fill=(205, 212, 235), anchor="ls")
        y += 46
    d.text((70, 1640), "Source: " + item["source"], font=font("Regular", 24), fill=MUTED, anchor="ls")
    return layer


def build_outro():
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    draw_logo(d, W // 2, 560, 230)
    d.text((W // 2, 930), "LIKE &", font=font("Bold", 130), fill=WHITE, anchor="mm")
    d.text((W // 2, 1060), "SUBSCRIBE", font=font("Bold", 130), fill=GOLD, anchor="mm")
    d.text((W // 2, 1180), "for the top 5", font=font("Bold", 62), fill=GREEN, anchor="mm")
    d.rounded_rectangle([W // 2 - 300, 1260, W // 2 + 300, 1350], radius=45, fill=PANEL, outline=PANEL_EDGE, width=3)
    d.text((W // 2, 1305), HANDLE, font=font("Medium", 40), fill=WHITE, anchor="mm")
    d.text((W // 2, 1440), "New Top 5s every day", font=font("Regular", 32), fill=MUTED, anchor="mm")
    return layer


def draw_bars(frame, content, current_rank, local_t, fade):
    """Countdown bar chart: revealed ranks stay, current one grows, upcoming ones are hidden."""
    d = ImageDraw.Draw(frame)
    items = {it["rank"]: it for it in content["items"]}
    vmax = max(it["value"] for it in content["items"])
    grow = ease((local_t - 0.35) / 1.0)
    top, row_h, x0, bar_max = 745, 88, 110, 430
    for n, rank in enumerate([5, 4, 3, 2, 1]):
        it, y = items[rank], top + n * row_h
        accent = ACCENTS[rank]
        d.rounded_rectangle([x0 + 330, y + 18, x0 + 330 + bar_max, y + 58], radius=20,
                            fill=blend(PANEL, DIM, fade * 0.6))
        if rank < current_rank:   # not revealed yet
            d.text((x0, y + 38), f"#{rank}  ?", font=font("Bold", 30), fill=blend(PANEL, DIM, fade), anchor="lm")
            continue
        frac = max(0.05, it["value"] / vmax) * (grow if rank == current_rank else 1.0)
        color = accent if rank == current_rank else blend(PANEL, accent, 0.45)
        text_c = WHITE if rank == current_rank else MUTED
        d.rounded_rectangle([x0 + 330, y + 18, x0 + 330 + max(24, bar_max * frac), y + 58],
                            radius=20, fill=blend(PANEL, color, fade))
        label = f"#{rank}  {it['short']}"
        fnt = font("Bold", 30)
        while d.textlength(label, font=fnt) > 310 and fnt.size > 20:
            fnt = font("Bold", fnt.size - 2)
        d.text((x0, y + 38), label, font=fnt, fill=blend(PANEL, text_c, fade), anchor="lm")


def render(content, out_path):
    bg = make_background()
    intro = build_intro(content)
    items = sorted(content["items"], key=lambda i: -i["rank"])
    layers = [build_item(content, it, n) for n, it in enumerate(items)]
    outro = build_outro()
    segments = [("intro", INTRO_S, intro, None)]
    segments += [("item", ITEM_S, lay, it) for lay, it in zip(layers, items)]
    segments += [("outro", OUTRO_S, outro, None)]
    total = sum(s[1] for s in segments)

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        t = f / FPS
        acc = 0.0
        for kind, dur, layer, item in segments:
            if t < acc + dur or (kind, dur) == (segments[-1][0], segments[-1][1]):
                local = t - acc
                break
            acc += dur
        e = ease(local / FADE_S)
        frame = bg.copy()
        shifted = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shifted.paste(layer, (0, int(40 * (1 - e))))
        alpha = shifted.getchannel("A").point(lambda v: int(v * e))
        shifted.putalpha(alpha)
        frame.paste(shifted, (0, 0), shifted)
        if kind == "item":
            draw_bars(frame, content, item["rank"], local, e)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return total
