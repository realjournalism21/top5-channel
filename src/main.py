"""Entry point: pick topic -> write list with Gemini -> render video -> (optionally) post."""
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content as content_mod  # noqa: E402
import images  # noqa: E402
import render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
HISTORY = ROOT / "history.json"


def main():
    OUT.mkdir(exist_ok=True)
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {"posts": []}
    topics = json.loads((ROOT / "topics.json").read_text())
    posting = os.environ.get("POSTING") == "true"

    if "--sample" in sys.argv:
        content = json.loads((ROOT / "sample_content.json").read_text())
    else:
        # Rotate subjects. Real posts follow history length; test runs use the run number so they vary.
        idx = len(history["posts"]) if posting else int(os.environ.get("GITHUB_RUN_NUMBER", len(history["posts"])))
        topic = topics[idx % len(topics)]
        content = content_mod.generate(topic, [p["title"] for p in history["posts"]])
        content = images.attach(content, OUT)

    seconds = render.render(content, OUT / "video.mp4")
    caption = content_mod.build_caption(content)
    (OUT / "content.json").write_text(json.dumps({**content, "full_caption": caption}, indent=2, ensure_ascii=False))
    print(f"Rendered {seconds:.1f}s video: {content['title']}")

    if "--sample" in sys.argv:
        return
    history["posts"].append({"title": content["title"], "subject": content.get("subject", ""),
                             "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")})
    history["posts"] = history["posts"][-300:]
    HISTORY.write_text(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
