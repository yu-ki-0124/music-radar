"""X(旧Twitter)公式API。X_BEARER_TOKEN(有料プラン)があるときだけ、キーワードの投稿件数を取る。

ログインしての自動巡回は規約違反・凍結リスクがあるため行わない。
"""
from .common import env, get_json


def collect(cfg, ctx):
    token = env("X_BEARER_TOKEN")
    items = []
    for fid, words in cfg["keywords"].items():
        for w in words:
            data = get_json("https://api.x.com/2/tweets/counts/recent",
                            params={"query": f'"{w}" -is:retweet', "granularity": "day"},
                            headers={"Authorization": f"Bearer {token}"}, pause=1)
            items.append({"kind": "x_count", "format": fid, "keyword": w,
                          "daily": [[d["start"][:10], d["tweet_count"]] for d in data.get("data", [])]})
    return {"items": items}
