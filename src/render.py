"""Renders a vertical 1080x1920 Top 5 countdown video in the @top5rankingsforyou style.

Each countdown slide has an optional photo card. Slides without a photo use the plain layout.
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
BG_TOP, BG_BOT = (8, 12, 32), (26, 14, 52)
PANEL, PANEL_EDGE = (15, 20, 48), (32, 40, 82)
WHITE, MUTED, DIM = (255, 255, 255), (140, 150, 185), (44, 52, 96)
GREEN, GOLD = (74, 222, 128), (255, 194, 75)
ACCENTS = {5: (255, 169, 77), 4: (116, 167, 255), 3: (94, 224, 181),
           2: (199, 155, 255), 1: (74, 222, 128)}
HANDLE = "@top5rankingsforyou"
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MUSIC = Path(__file__).resolve().parent.parent / "assets" / "music" / "track.mp3"
MUSIC_VOLUME = 0.7

INTRO_S, ITEM_S, OUTRO_S, FADE_S = 2.4, 3.0, 3.4, 0.4

# Layout numbers (pixels) for a slide without a photo and for a slide with one.
GEOM_PLAIN = dict(dots_y=130, circ=(70, 200, 190, 320), num_font=84, tag_font=34,
                  title_y=420, title_sizes=range(88, 47, -4), image=None,
                  panel=(70, 640, 1010, 1190), hdr_y=690, bars_top=745, row_h=88, bar_dy=18, bar_h=40,
                  lab_dy=38, lab_font=30, stat_y=1330, stat_font=130, cap_y=1385, cap_font=34,
                  fact_y=1450, fact_font=34, fact_lh=46, src_y=1640)
GEOM_IMG = dict(dots_y=100, circ=(70, 160, 170, 260), num_font=72, tag_font=32,
                title_y=370, title_sizes=range(80, 43, -4), image=(70, 500, 1010, 850),
                panel=(70, 875, 1010, 1225), hdr_y=912, bars_top=945, row_h=54, bar_dy=10, bar_h=32,
                lab_dy=26, lab_font=26, stat_y=1350, stat_font=112, cap_y=1400, cap_font=32,
                fact_y=1462, fact_font=32, fact_lh=42, src_y=1610)

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
    draw.text((cx, cy - r * 0.60), "TOP", font=font("Bold", int(r * 0.42)), fill=WHITE, anchor="mm")
    draw.text((cx, cy + r * 0.22), "5", font=font("Bold", int(r * 0.82)), fill=GOLD, anchor="mm")
    for i in range(5):
        x = cx + (i - 2) * r * 0.16
        draw.ellipse([x - 5, cy + r * 0.80 - 5, x + 5, cy + r * 0.80 + 5], fill=GOLD)


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


def photo_card(path, w, h):
    """Photo shown whole (never cropped) on a blurred, darkened copy of itself, with rounded corners."""
    src = Image.open(path).convert("RGB")
    scale = max(w / src.width, h / src.height)
    big = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1))
    left, top = (big.width - w) // 2, (big.height - h) // 2
    card = big.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(28))
    card = ImageEnhance.Brightness(card).enhance(0.45)
    fit_scale = min((w - 40) / src.width, (h - 30) / src.height)
    fg = src.resize((max(1, int(src.width * fit_scale)), max(1, int(src.height * fit_scale))))
    fg_mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(fg_mask).rounded_rectangle([0, 0, fg.width, fg.height], radius=18, fill=255)
    card.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2 - 6), fg_mask)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=32, fill=255)
    return card, mask


def has_photo(item):
    f = item.get("image_file")
    return bool(f) and Path(f).exists()


def build_item(content, item, index):
    g = GEOM_IMG if has_photo(item) else GEOM_PLAIN
    rank, accent = item["rank"], ACCENTS[item["rank"]]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dots(d, index + 1, 5, accent, 70, g["dots_y"])
    x0, y0, x1, y1 = g["circ"]
    d.ellipse([x0, y0, x1, y1], fill=accent)
    cy = (y0 + y1) // 2
    d.text(((x0 + x1) // 2, cy), str(rank), font=font("Bold", g["num_font"]), fill=(10, 14, 36), anchor="mm")
    d.text((x1 + 25, cy), item["category"].upper(), font=font("Bold", g["tag_font"]), fill=accent, anchor="lm")
    # title
    fnt, lines = fit(d, item["name"].upper(), "Bold", 940, 2, g["title_sizes"])
    y = g["title_y"]
    for line in lines:
        d.text((70, y), line, font=fnt, fill=WHITE, anchor="ls")
        y += int(fnt.size * 1.18)
    # photo card
    if g["image"]:
        ix0, iy0, ix1, iy1 = g["image"]
        card, mask = photo_card(item["image_file"], ix1 - ix0, iy1 - iy0)
        layer.paste(card, (ix0, iy0), mask)
        credit = item.get("image_credit", "")
        if credit:
            d.text((ix0 + 22, iy1 - 14), credit, font=font("Regular", 20), fill=(235, 238, 250),
                   anchor="ls", stroke_width=2, stroke_fill=(0, 0, 0))
    # chart panel
    d.rounded_rectangle(list(g["panel"]), radius=32, fill=PANEL, outline=PANEL_EDGE, width=3)
    d.text((110, g["hdr_y"]), content["metric_label"].upper(), font=font("Bold", 26), fill=MUTED, anchor="lm")
    # stat, caption, fact, source
    d.text((70, g["stat_y"]), item["stat"], font=font("Bold", g["stat_font"]), fill=accent, anchor="ls")
    d.text((70, g["cap_y"]), item["stat_caption"], font=font("Medium", g["cap_font"]), fill=WHITE, anchor="ls")
    fact_fnt = font("Regular", g["fact_font"])
    y = g["fact_y"]
    for line in wrap(d, item["fact"], fact_fnt, 940)[:3]:
        d.text((70, y), line, font=fact_fnt, fill=(205, 212, 235), anchor="ls")
        y += g["fact_lh"]
    d.text((70, g["src_y"]), "Source: " + item["source"], font=font("Regular", 24), fill=MUTED, anchor="ls")
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


def draw_bars(frame, content, item, local_t, fade):
    """Countdown bar chart: revealed ranks stay, current one grows, upcoming ones are hidden."""
    g = GEOM_IMG if has_photo(item) else GEOM_PLAIN
    current_rank = item["rank"]
    d = ImageDraw.Draw(frame)
    items = {it["rank"]: it for it in content["items"]}
    vmax = max(it["value"] for it in content["items"])
    grow = ease((local_t - 0.35) / 1.0)
    x0, bar_max = 110, 430
    top, row_h, bdy, bh, ldy = g["bars_top"], g["row_h"], g["bar_dy"], g["bar_h"], g["lab_dy"]
    radius = bh // 2
    for n, rank in enumerate([5, 4, 3, 2, 1]):
        it, y = items[rank], top + n * row_h
        accent = ACCENTS[rank]
        d.rounded_rectangle([x0 + 330, y + bdy, x0 + 330 + bar_max, y + bdy + bh], radius=radius,
                            fill=blend(PANEL, DIM, fade * 0.6))
        if rank < current_rank:   # not revealed yet
            d.text((x0, y + ldy), f"#{rank}  ?", font=font("Bold", g["lab_font"]),
                   fill=blend(PANEL, DIM, fade), anchor="lm")
            continue
        frac = max(0.05, it["value"] / vmax) * (grow if rank == current_rank else 1.0)
        color = accent if rank == current_rank else blend(PANEL, accent, 0.45)
        text_c = WHITE if rank == current_rank else MUTED
        d.rounded_rectangle([x0 + 330, y + bdy, x0 + 330 + max(bh, bar_max * frac), y + bdy + bh],
                            radius=radius, fill=blend(PANEL, color, fade))
        label = f"#{rank}  {it['short']}"
        fnt = font("Bold", g["lab_font"])
        while d.textlength(label, font=fnt) > 310 and fnt.size > 18:
            fnt = font("Bold", fnt.size - 2)
        d.text((x0, y + ldy), label, font=fnt, fill=blend(PANEL, text_c, fade), anchor="lm")


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

    video_in = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if MUSIC.exists():   # background music, faded out at the end; silent track if the file is missing
        audio_in = ["-stream_loop", "-1", "-i", str(MUSIC)]
        audio_fx = ["-af", f"volume={MUSIC_VOLUME},afade=t=out:st={total - 1.2:.2f}:d=1.2"]
    else:
        audio_in = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        audio_fx = []
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *video_in, *audio_in, "-t", f"{total:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           *audio_fx, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        t = f / FPS
        acc = 0.0
        for kind, dur, layer, item in segments:
            if t < acc + dur or (kind, dur) == (segments[-1][0], segments[-1][1]):
                local = t - acc
                break
            acc += dur
        e = 1.0 if kind == "intro" else ease(local / FADE_S)
        frame = bg.copy()
        shifted = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shifted.paste(layer, (0, int(40 * (1 - e))))
        alpha = shifted.getchannel("A").point(lambda v: int(v * e))
        shifted.putalpha(alpha)
        frame.paste(shifted, (0, 0), shifted)
        if kind == "item":
            draw_bars(frame, content, item, local, e)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return total
