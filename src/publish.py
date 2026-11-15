"""Publishes a Reel through the Instagram API with Instagram Login (graph.instagram.com)."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "https://graph.instagram.com/v23.0"


def _request(method, url, params):
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Instagram API error {e.code}: {e.read().decode()[:600]}") from None


def check_video_url(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        print("Video URL reachable. Content-Type:", r.headers.get("Content-Type"),
              "Size:", r.headers.get("Content-Length"))


def publish_reel(video_url, caption):
    user, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    check_video_url(video_url)
    container = _request("POST", f"{HOST}/{user}/media", {
        "media_type": "REELS", "video_url": video_url, "caption": caption,
        "share_to_feed": "true", "access_token": token})["id"]
    print("Container created:", container)
    for _ in range(40):  # up to ~10 minutes
        time.sleep(15)
        status = _request("GET", f"{HOST}/{container}", {"fields": "status_code,status", "access_token": token})
        code = status.get("status_code")
        print("Status:", code, status.get("status", ""))
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {status}")
    else:
        raise RuntimeError("Timed out waiting for Instagram to process the video")
    media = _request("POST", f"{HOST}/{user}/media_publish", {"creation_id": container, "access_token": token})
    print("Published! Media id:", media.get("id"))
    return media.get("id")
