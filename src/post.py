"""Second step: posts out/content.json's caption + the already-uploaded video (VIDEO_URL) to Instagram."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402

data = json.loads((Path(__file__).resolve().parent.parent / "out" / "content.json").read_text())
publish.publish_reel(os.environ["VIDEO_URL"], data["full_caption"])
