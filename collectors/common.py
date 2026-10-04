"""収集プログラム共通の道具。"""
import datetime as dt
import json
import os
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
HISTORY = DATA / "history"
REPORTS = DATA / "reports"
UA = "MusicRadar/0.1 (personal music trend research)"

_session = requests.Session()
_session.headers["User-Agent"] = UA


class Skip(Exception):
    """キー未設定などで、このソースを飛ばすときに投げる。"""


def config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise Skip(f"{name} が未設定")
    return value


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def get(url, params=None, headers=None, timeout=25, retries=2, pause=0.0):
    """GET して Response を返す。429/5xx は少し待って再試行。"""
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last = requests.HTTPError(f"{r.status_code} {url}")
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            if pause:
                time.sleep(pause)
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def get_json(url, **kw):
    return get(url, **kw).json()


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
