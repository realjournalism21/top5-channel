"""Asks the free Gemini API for a Top 5 list and validates it."""
import json
import os
import re
import time
import urllib.error
import urllib.request

# Free-tier models first; the script tries the next one if a model is unavailable.
MODELS = os.environ.get(
    "GEMINI_MODELS",
    "gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite",
).split(",")

PROMPT = """You write the content for "Top 5", a short-video Instagram channel (@top5rankingsforyou).
Create ONE Top 5 countdown list about this subject: {subject} ({hint}).

Rules:
- Use only stable, widely documented facts (records, official statistics, history). No live prices, no breaking news, no opinions.
- Every number must be one you are highly confident about. If unsure, pick a different item. Round numbers sensibly.
- All five items must be measured by the SAME numeric metric so they can be ranked and shown as bars.
- Rank 5 is the least extreme, rank 1 the most extreme/surprising. Interesting and surprising beats obvious.
- Every sentence in "fact" must be something you are CERTAIN is true. Avoid claims like "banned", "illegal", "only", "first", "record", "warnings" unless you are certain. Prefer plain measurable facts.
- "source" must be a specific real publication or dataset you are sure exists (for example "UN World Population Prospects 2024", "IUCN Red List", "FIFA records"). Never write generic sources such as "Manufacturer Specifications" or "Company data". Do not cite Guinness World Records unless that exact record exists.
- Prefer items that can be shown with a picture: countries and cities (shown as a map), animals, landmarks, buildings, vehicles, foods, products. Avoid ranking people.
- Do not repeat these recent titles: {recent}
- Plain English for an international audience. No emojis.

Return ONLY JSON in exactly this shape:
{{
  "title": "short list title, max 34 chars, e.g. Biggest Countries by Population",
  "subtitle": "max 40 chars, e.g. UN estimates, 2024",
  "metric_label": "what the bars show with unit, max 40 chars, e.g. Population (millions)",
  "caption": "1-2 sentence Instagram caption, max 220 chars, no hashtags",
  "hashtags": ["#top5", "..."],
  "items": [
    {{"rank": 5, "short": "max 16 chars", "category": "max 18 chars, e.g. Asia", "name": "full headline, max 40 chars",
      "value": 251.0, "stat": "big number text, max 12 chars, e.g. 251M", "stat_caption": "max 46 chars, what the stat means",
      "fact": "one interesting sentence, max 140 chars", "source": "organisation + year, max 60 chars",
      "image_kind": "map" if the item is a country, state, region or city (a location map is shown); "photo" for a physical thing (animal, landmark, building, vehicle, food, product, object); null for a person or something abstract",
      "image_query": "for kind map: ONLY the exact place name in English, e.g. India or Indonesia; for kind photo: 3-6 words naming exactly this item as it would be titled on Wikimedia Commons, e.g. Stroh 80 rum bottle; null if image_kind is null"}},
    ... one object each for ranks 4, 3, 2, 1 (in that order)
  ]
}}
"value" must be a positive number in the same unit for all five items."""

GENERIC_SOURCE = re.compile(r"manufacturer|company (data|website|specification)|various|general knowledge|internet|online|wikipedia|unknown|n/a", re.I)
LIMITS = {"short": 16, "category": 18, "name": 40, "stat": 12, "stat_caption": 46, "fact": 150, "source": 60}
TRIMMABLE = ("short", "category", "name", "stat_caption", "source")   # slightly long -> shortened, not rejected


def _trim(text, lim):
    """Shortens text to lim characters at a word boundary (hard cut if it is a single long word)."""
    if len(text) <= lim:
        return text
    cut = text[:lim + 1].rsplit(" ", 1)[0] if " " in text[:lim + 1] else text[:lim]
    return cut.rstrip(" ,;:-&").strip() or text[:lim]


def _clean(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def _call(model, prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=75) as r:
        data = json.load(r)
    parts = data["candidates"][0]["content"]["parts"]
    return _clean("".join(p.get("text", "") for p in parts if not p.get("thought")))


def validate(c):
    for k in ("title", "subtitle", "metric_label", "caption", "hashtags", "items"):
        if k not in c:
            raise ValueError(f"missing {k}")
    if len(c["title"]) > 40 or len(c["subtitle"]) > 46 or len(c["metric_label"]) > 46:
        raise ValueError("title/subtitle/metric_label too long")
    items = c["items"]
    if [i.get("rank") for i in items] != [5, 4, 3, 2, 1]:
        raise ValueError("items must be ranks 5,4,3,2,1 in order")
    for it in items:
        for k, lim in LIMITS.items():
            if not isinstance(it.get(k), str) or not it[k].strip():
                raise ValueError(f"item {it.get('rank')} missing {k}")
            if len(it[k]) > lim and k in TRIMMABLE and len(it[k]) <= lim * 1.5:
                it[k] = _trim(it[k].strip(), lim)
            if len(it[k]) > lim:
                raise ValueError(f"item {it['rank']} {k} too long ({len(it[k])}>{lim})")
        if GENERIC_SOURCE.search(it["source"]):
            raise ValueError(f"item {it['rank']} source is too generic: {it['source']}")
        q = it.get("image_query")
        if it.get("image_kind") not in (None, "map", "photo"):
            raise ValueError(f"item {it['rank']} image_kind must be map, photo or null")
        if q is not None and (not isinstance(q, str) or len(q) > 70):
            raise ValueError(f"item {it['rank']} image_query must be text under 70 chars or null")
        if not isinstance(it.get("value"), (int, float)) or it["value"] <= 0:
            raise ValueError(f"item {it['rank']} value must be a positive number")
    return c


REVIEW_PROMPT = """You are a strict fact-checker. Below is the JSON for a short Top 5 video. Check EVERY number, ranking and sentence.
Rules:
- Keep an item only if you are certain its number is right and that it belongs in this ranking. If not, replace it with a better-known item that fits the same metric.
- If a "fact" sentence contains anything you are not certain of (words like banned, only, first, record, illegal, warnings), rewrite it as a plain statement you are certain of.
- If a "source" is not a real, specific publication or dataset you are sure exists, replace it with one you are sure exists.
- Keep the exact same JSON shape and keys (including image_kind and image_query), ranks 5,4,3,2,1 in that order, and the same length limits. Return ONLY the corrected JSON.
JSON:
__PAYLOAD__"""


def review(content, key):
    keep = ("title", "subtitle", "metric_label", "caption", "hashtags", "items")
    prompt = REVIEW_PROMPT.replace("__PAYLOAD__", json.dumps({k: content[k] for k in keep}, ensure_ascii=False))
    for model in MODELS:
        try:
            fixed = validate(_call(model.strip(), prompt, key))
            fixed["subject"] = content.get("subject", "")
            print(f"Fact-check pass done with {model}")
            return fixed
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"[{model}] fact-check failed: {type(e).__name__}: {e}")
    print("Fact-check pass skipped (kept the original list)")
    return content


def generate(topic, recent_titles):
    key = os.environ["GEMINI_API_KEY"]
    prompt = PROMPT.format(subject=topic["name"], hint=topic["hint"],
                           recent="; ".join(recent_titles[-40:]) or "none")
    last = None
    for round_no in range(2):            # second round after a pause, in case Gemini was just busy
        if round_no:
            print("All models failed - waiting 60s and trying again")
            time.sleep(60)
        for model in MODELS:
            for attempt in range(3):
                try:
                    p = prompt if attempt == 0 else prompt + f"\nFix this problem from your last answer: {last}"
                    started = time.time()
                    content = validate(_call(model.strip(), p, key))
                    content["subject"] = topic["name"]
                    print(f"Generated with {model} in {time.time() - started:.0f}s: {content['title']}")
                    return review(content, key)
                except (OSError, KeyError, ValueError, json.JSONDecodeError) as e:
                    detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else ""
                    last = f"{type(e).__name__}: {e} {detail}"
                    print(f"[{model}] attempt {attempt + 1} failed: {last}")
                    if isinstance(e, (urllib.error.HTTPError, TimeoutError, urllib.error.URLError)):
                        break  # model unavailable / slow / bad key -> try the next model
    raise RuntimeError(f"All Gemini attempts failed. Last error: {last}")


def build_caption(content):
    tags = " ".join(t if t.startswith("#") else "#" + t for t in content["hashtags"][:8])
    return f"{content['caption']}\n\nLike and subscribe for the top 5 • @top5rankingsforyou\n\n{tags}"
