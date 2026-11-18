"""Renders a vertical 1080x1920 Top 5 countdown video in the @top5rankingsforyou style.

Photo-first design: every countdown slide opens with a large slowly-zooming photo. Slides without a
photo get an animated "poster" with the giant rank number instead. No bar charts.
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



HERO_H = 1130          # height of the photo / poster area at the top of each slide


def cover(path, w, h, zoom_extra=1.14):
    """Photo scaled to fill w x h with spare pixels so it can zoom slowly (Ken Burns)."""
    src = Image.open(path).convert("RGB")
    scale = max(w * zoom_extra / src.width, h * zoom_extra / src.height)
    return src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1), Image.LANCZOS)


def zoom_crop(big, w, h, progress, drift=(0.0, 0.0)):
    """Window onto `big` that shrinks as progress goes 0 -> 1 (looks like a slow zoom-in)."""
    z0 = min(big.width / (w * 1.14), big.height / (h * 1.14))   # largest window that keeps the w:h shape
    cur = z0 * (1.14 - 0.14 * progress)     # 1.14 -> 1.00 of the extra margin, i.e. zoom in
    cw, ch = w * cur, h * cur
    cx = big.width / 2 + drift[0] * progress * (big.width - cw) / 2
    cy = big.height / 2 + drift[1] * progress * (big.height - ch) / 2
    box = (max(0.0, cx - cw / 2), max(0.0, cy - ch / 2),
           min(float(big.width), cx + cw / 2), min(float(big.height), cy + ch / 2))
    return big.resize((w, h), Image.BILINEAR, box=box)


def vgrad(w, h, c, a0, a1, y0=0.0, y1=1.0):
    """Vertical alpha gradient layer of colour c (alpha a0 at fraction y0 -> a1 at y1)."""
    g = Image.new("L", (1, h))
    px = g.load()
    for y in range(h):
        t = max(0.0, min(1.0, (y / h - y0) / max(1e-6, (y1 - y0))))
        px[0, y] = int(a0 + (a1 - a0) * t)
    g = g.resize((w, h))
    layer = Image.new("RGBA", (w, h), c + (255,))
    layer.putalpha(g)
    return layer


def has_photo(item):
    f = item.get("image_file")
    return bool(f) and Path(f).exists()


def poster(accent, rank):
    """Hero for a slide without a photo: tinted glow with a giant rank number."""
    img = Image.new("RGB", (W, HERO_H))
    d = ImageDraw.Draw(img)
    for y in range(HERO_H):
        d.line([(0, y), (W, y)], fill=blend(blend(BG_TOP, accent, 0.30), BG_TOP, y / HERO_H))
    glow = Image.new("RGB", (W, HERO_H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 420, 250, W // 2 + 420, 1000], fill=blend((0, 0, 0), accent, 0.55))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L")), 0.7)
    d = ImageDraw.Draw(img)
    d.text((W // 2, 640), str(rank), font=font("Bold", 760), fill=blend(blend(BG_TOP, accent, 0.30), accent, 0.5), anchor="mm")
    return img


def build_intro_bg(content):
    """Backdrop of the opening frame (= the Reel cover): the #1 photo, darkened, if there is one."""
    pick = next((it for it in sorted(content["items"], key=lambda i: i["rank"]) if has_photo(it)), None)
    return cover(pick["image_file"], W, H) if pick else None


def build_intro(content, has_bg):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if has_bg:   # scrim so the text stays readable on any photo
        layer.alpha_composite(vgrad(W, H, (6, 8, 24), 40, 215, 0.25, 0.7))
    d = ImageDraw.Draw(layer)
    d.text((70, 640), "TOP 5", font=font("Bold", 250), fill=WHITE, anchor="ls")
    fnt, lines = fit(d, content["title"].upper(), "Bold", 940, 3, range(96, 55, -4))
    y = 790
    for line in lines:
        d.text((70, y), line, font=fnt, fill=GREEN, anchor="ls", stroke_width=2 if has_bg else 0, stroke_fill=(0, 0, 0))
        y += int(fnt.size * 1.2)
    d.text((70, y + 20), content["subtitle"].upper(), font=font("Medium", 34), fill=WHITE, anchor="ls")
    dots(d, 5, 5, GREEN, 70, y + 80)
    return layer


def build_item(content, item, index):
    """Static text layer drawn above the hero: scrims, rank badge, title, stat, fact, source."""
    rank, accent = item["rank"], ACCENTS[item["rank"]]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(vgrad(W, 330, (4, 6, 20), 150, 0), (0, 0))                          # top scrim
    layer.alpha_composite(vgrad(W, 520, BG_TOP, 0, 255, 0.0, 0.95), (0, HERO_H - 520))        # photo -> background
    d = ImageDraw.Draw(layer)
    dots(d, index + 1, 5, accent, 70, 96)
    d.ellipse([70, 160, 190, 280], fill=accent)
    d.text((130, 220), str(rank), font=font("Bold", 84), fill=(10, 14, 36), anchor="mm")
    d.text((215, 220), item["category"].upper(), font=font("Bold", 34), fill=accent, anchor="lm",
           stroke_width=3, stroke_fill=(0, 0, 0))
    fnt, lines = fit(d, item["name"].upper(), "Bold", 940, 2, range(88, 47, -4))
    y = HERO_H - 70 - (len(lines) - 1) * int(fnt.size * 1.15)
    for line in lines:
        d.text((70, y), line, font=fnt, fill=WHITE, anchor="ls", stroke_width=3, stroke_fill=(0, 0, 0))
        y += int(fnt.size * 1.15)
    d.text((70, 1330), item["stat"], font=font("Bold", 128), fill=accent, anchor="ls")
    d.text((70, 1392), item["stat_caption"], font=font("Medium", 36), fill=WHITE, anchor="ls")
    fact_fnt = font("Regular", 34)
    y = 1470
    for line in wrap(d, item["fact"], fact_fnt, 940)[:3]:
        d.text((70, y), line, font=fact_fnt, fill=(205, 212, 235), anchor="ls")
        y += 46
    d.text((70, 1850), "Source: " + item["source"], font=font("Regular", 24), fill=MUTED, anchor="ls")
    credit = item.get("image_credit", "") if has_photo(item) else ""
    if credit:
        d.text((W - 40, HERO_H - 14), credit, font=font("Regular", 20), fill=(235, 238, 250), anchor="rs",
               stroke_width=2, stroke_fill=(0, 0, 0))
    return layer


def draw_ladder(frame, content, item, local_t, fade):
    """Replaces the old bar chart: five rank chips; revealed ones fill in, the current one pulses."""
    d = ImageDraw.Draw(frame)
    current = item["rank"]
    names = {it["rank"]: it["short"] for it in content["items"]}
    cy, r = 1672, 34
    for n, rank in enumerate([5, 4, 3, 2, 1]):
        cx = 70 + r + n * 196
        accent = ACCENTS[rank]
        if rank > current:
            fill, txt = blend(BG_TOP, accent, 0.55 * fade), (10, 14, 36)
        elif rank == current:
            pulse = 1 + 0.10 * abs(((local_t * 1.6) % 2) - 1)
            rr = int(r * pulse)
            d.ellipse([cx - rr - 7, cy - rr - 7, cx + rr + 7, cy + rr + 7], outline=blend(BG_TOP, accent, fade), width=3)
            fill, txt = blend(BG_TOP, accent, fade), (10, 14, 36)
        else:
            fill, txt = DIM, MUTED
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        d.text((cx, cy), str(rank), font=font("Bold", 38), fill=txt, anchor="mm")
        if rank >= current:
            label = names[rank]
            fnt = font("Medium", 24)
            while d.textlength(label, font=fnt) > 170 and fnt.size > 16:
                fnt = font("Medium", fnt.size - 2)
            d.text((cx, cy + r + 30), label, font=fnt, fill=blend(BG_TOP, WHITE if rank == current else MUTED, fade), anchor="mm")


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


def render(content, out_path):
    bg = make_background()
    items = sorted(content["items"], key=lambda i: -i["rank"])
    intro_photo = build_intro_bg(content)
    intro = build_intro(content, intro_photo is not None)
    layers = [build_item(content, it, n) for n, it in enumerate(items)]
    outro = build_outro()
    # per-item hero images, prepared once
    heroes = []
    for it in items:
        heroes.append(cover(it["image_file"], W, HERO_H) if has_photo(it) else poster(ACCENTS[it["rank"]], it["rank"]))
    drifts = [(1, 0.3), (-1, -0.3), (0.6, -0.5), (-0.6, 0.5), (1, -0.3)]
    segments = [("intro", INTRO_S, intro, None, None, None)]
    segments += [("item", ITEM_S, lay, it, hero, drifts[n % 5])
                 for n, (lay, it, hero) in enumerate(zip(layers, items, heroes))]
    segments += [("outro", OUTRO_S, outro, None, None, None)]
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
        for seg in segments:
            kind, dur = seg[0], seg[1]
            if t < acc + dur or seg is segments[-1]:
                local = t - acc
                break
            acc += dur
        _, dur, layer, item, hero, drift = seg
        e = 1.0 if kind == "intro" else ease(local / FADE_S)
        frame = bg.copy()
        if kind == "intro" and intro_photo is not None:
            dark = ImageEnhance.Brightness(zoom_crop(intro_photo, W, H, local / dur)).enhance(0.85)
            frame.paste(dark, (0, 0))
        if kind == "item":
            prog = local / dur
            if has_photo(item):
                img = zoom_crop(hero, W, HERO_H, prog, drift)
            else:   # poster: slow scale-up of the giant number area
                img = hero
            img = ImageEnhance.Brightness(img).enhance(0.35 + 0.65 * e)
            frame.paste(img, (0, 0))
        shifted = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shifted.paste(layer, (0, int(40 * (1 - e))))
        alpha = shifted.getchannel("A").point(lambda v: int(v * e))
        shifted.putalpha(alpha)
        frame.paste(shifted, (0, 0), shifted)
        if kind == "item":
            draw_ladder(frame, content, item, local, e)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return total
