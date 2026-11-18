"""Finds a free-to-use photo on Wikimedia Commons for each item.

Photos are optional: if nothing suitable is found (or anything goes wrong), the slide simply
uses the layout without a photo. Only licences that allow reuse with credit are accepted.
"""
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "Top5RankingsBot/1.0 (https://github.com/realjournalism21/top5-channel; automated Instagram channel)"}
GENERIC_WORDS = {"bottle", "photo", "picture", "image", "of", "the", "a", "an", "flag", "and", "in", "on", "at", "for"}


def _get_json(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return json.load(r)


def _licence_ok(name):
    lic = name.lower().strip()
    if not lic or any(bad in lic for bad in ("-nc", "-nd", " nc", " nd", "fair use", "gfdl", "non-commercial")):
        return False
    return lic.startswith(("cc by", "cc0", "cc-by", "public domain", "pd", "attribution"))


def _keyword(query):
    words = [w for w in re.findall(r"[A-Za-zÀ-ɏ0-9]+", query.lower()) if w not in GENERIC_WORDS]
    words = [w for w in words if not w.isdigit()] or words
    return max(words, key=len) if words else ""


def find(query):
    """Returns {'url', 'credit'} for the best matching permissively licensed photo, or None."""
    key = _keyword(query)
    if not key:
        return None
    data = _get_json({
        "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 12,
        "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 1600,
    })
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for page in pages:
        info = (page.get("imageinfo") or [None])[0]
        if not info or info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if info.get("width", 0) < 900 or info.get("height", 0) < 600:
            continue
        title = page.get("title", "").lower()
        if key not in title or any(x in title for x in ("logo", "diagram", "map of", "screenshot")):
            continue
        meta = info.get("extmetadata", {})
        licence = meta.get("LicenseShortName", {}).get("value", "")
        if not _licence_ok(licence):
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
        artist = re.sub(r"\s+", " ", artist)[:32] or "Wikimedia Commons"
        return {"url": info.get("thumburl") or info["url"], "credit": f"Photo: {artist} / {licence}"[:60]}
    return None


MAP_TITLES = ["File:{p} (orthographic projection).svg", "File:{p} in its region.svg",
              "File:{p} location map.svg", "File:{p} (rotated).svg"]


def _credit(meta, licence, prefix):
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
    artist = re.sub(r"\s+", " ", artist)[:32] or "Wikimedia Commons"
    return f"{prefix}: {artist} / {licence}"[:60]


def find_map(place):
    """Location map of a country/region: the standard 'orthographic projection' globe on Wikimedia Commons."""
    place = str(place).strip()
    candidates = []
    data = _get_json({"action": "query", "titles": "|".join(t.format(p=place) for t in MAP_TITLES),
                      "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 1400})
    candidates += [p for p in data.get("query", {}).get("pages", {}).values() if "missing" not in p]
    if not candidates:   # fall back to a search for an SVG locator map that names the place
        data = _get_json({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 8,
                          "gsrsearch": f"{place} orthographic projection filetype:drawing", "prop": "imageinfo",
                          "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 1400})
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        key = _keyword(place)
        candidates += [p for p in pages if key in p.get("title", "").lower()
                       and "orthographic" in p.get("title", "").lower()]
    for page in candidates:
        info = (page.get("imageinfo") or [None])[0]
        if not info or not info.get("thumburl"):
            continue
        meta = info.get("extmetadata", {})
        licence = meta.get("LicenseShortName", {}).get("value", "")
        if not _licence_ok(licence):
            continue
        return {"url": info["thumburl"], "credit": _credit(meta, licence, "Map"), "is_map": True}
    return None


def map_card(img, w=1500, h=1570):
    """Puts a (possibly transparent) locator map on a dark navy canvas, centred with a margin."""
    canvas = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(canvas)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=(int(10 + 14 * t), int(16 + 6 * t), int(44 + 20 * t)))
    img = img.convert("RGBA")
    scale = min(1180 / img.width, 1180 / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2), img)
    return canvas


def download(url, path, as_map=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(10_000_000)
    img = Image.open(io.BytesIO(raw))
    img = map_card(img) if as_map else img.convert("RGB")
    img.save(path, "JPEG", quality=90)


def attach(content, out_dir):
    """Adds image_file + image_credit to every item that gets a suitable photo."""
    out_dir = Path(out_dir)
    for item in content["items"]:
        query = item.get("image_query")
        if not query or str(query).lower() in ("null", "none"):
            print(f"#{item['rank']} {item['short']}: no photo requested")
            continue
        try:
            is_map = item.get("image_kind") == "map"
            hit = find_map(query) if is_map else find(query)
            if not hit:
                print(f"#{item['rank']} {item['short']}: no suitable photo for '{query}'")
                continue
            path = out_dir / f"img_{item['rank']}.jpg"
            download(hit["url"], path, as_map=is_map)
            item["image_file"], item["image_credit"] = str(path), hit["credit"]
            print(f"#{item['rank']} {item['short']}: photo found ({hit['credit']})")
        except Exception as e:  # photos are optional, never fail the whole video
            print(f"#{item['rank']} {item['short']}: photo lookup failed: {type(e).__name__}: {e}")
        time.sleep(1)
    return content
