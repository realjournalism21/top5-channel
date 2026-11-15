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
      "fact": "one interesting sentence, max 130 chars", "source": "organisation + year, max 60 chars"}},
    ... one object each for ranks 4, 3, 2, 1 (in that order)
  ]
}}
"value" must be a positive number in the same unit for all five items."""

LIMITS = {"short": 16, "category": 18, "name": 40, "stat": 12, "stat_caption": 46, "fact": 130, "source": 60}


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
            if len(it[k]) > lim:
                raise ValueError(f"item {it['rank']} {k} too long ({len(it[k])}>{lim})")
        if not isinstance(it.get("value"), (int, float)) or it["value"] <= 0:
            raise ValueError(f"item {it['rank']} value must be a positive number")
    return c


def generate(topic, recent_titles):
    key = os.environ["GEMINI_API_KEY"]
    prompt = PROMPT.format(subject=topic["name"], hint=topic["hint"],
                           recent="; ".join(recent_titles[-40:]) or "none")
    last = None
    for model in MODELS:
        for attempt in range(2):
            try:
                p = prompt if attempt == 0 else prompt + f"\nFix this problem from your last answer: {last}"
                started = time.time()
                content = validate(_call(model.strip(), p, key))
                content["subject"] = topic["name"]
                print(f"Generated with {model} in {time.time() - started:.0f}s: {content['title']}")
                return content
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
