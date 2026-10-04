# Music Radar セットアップ手順

世界の音楽トレンドと、レコード・CD・カセットの動向を毎日自動収集し、iPhoneで見るためのアプリです。
GitHub が毎朝6:30(日本時間)に収集と集計を行い、結果をWebページとして公開します。PCの電源は不要です。

## 1. GitHub に置く

1. https://github.com で無料アカウントを作り、新しいリポジトリを作成(例: `music-radar`)。
   無料プランでページを公開するには **Public(公開)** を選びます。URLを知っている人は誰でも見られる点に注意。
2. このフォルダの中身を push します。

```bash
git init -b main
```
```bash
git add . && git commit -m "Music Radar"
```
```bash
git remote add origin https://github.com/<あなたのユーザー名>/music-radar.git
```
```bash
git push -u origin main
```

3. リポジトリの **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする。
4. **Actions** タブ → **daily** → **Run workflow** で1回手動実行。終わると
   `https://<ユーザー名>.github.io/music-radar/` で見られます。

## 2. iPhone で見る

Safari で上のURLを開き、共有ボタン →「ホーム画面に追加」。アプリのようにアイコンから開けます。

## 3. キーを登録する(任意。入れるほど精度が上がる)

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** に、下の名前で登録します。
未登録のものは自動で飛ばされ、画面の「データの取得状況」に「未設定」と出ます。

| 名前 | 何が増えるか | 取得先 | 費用 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | 週次・月次の文章レポート | https://console.anthropic.com | 従量課金(月100〜300円程度の見込み) |
| `YOUTUBE_API_KEY` | 各国のYouTube急上昇(音楽)と再生数 | Google Cloud Console で「YouTube Data API v3」を有効化しAPIキー作成 | 無料 |
| `LASTFM_API_KEY` | 世界・国別の再生ランキング、ジャンル規模 | https://www.last.fm/api/account/create | 無料 |
| `DISCOGS_TOKEN` | 取得が速くなり、相場(最安値・出品数)も表示 | https://www.discogs.com/settings/developers →「Generate new token」 | 無料 |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | 海外掲示板(r/vinyl など)の盛り上がり | https://www.reddit.com/prefs/apps で「script」アプリ作成 | 無料 |
| `X_BEARER_TOKEN` | Xでのキーワード投稿件数 | X Developer Portal(有料プラン) | 有料 |

レポートのモデルを変えたいときは、同じ画面の **Variables** に `MUSIC_RADAR_MODEL`(例: `claude-sonnet-5-5`)を登録します。
未設定なら `claude-opus-5-5` を使います。

## 4. 見たい対象を変える

`config.yaml` を編集します。国、追跡ジャンル、RSS、掲示板、キーワードを増減できます。

## 5. 公式統計を更新する(年2回ほど)

新品の統計は次の2つのファイルが土台です。日本の今年の途中経過は毎月自動で取り込まれるので、手作業は下の2点だけです。

- `data/history/formats.csv` … 年ごとの確定値。年が明けて前年の数字が発表されたら1行ずつ追記。
  - 日本: 日本レコード協会「レコード産業 年次推移」 https://www.riaj.or.jp/data/annual/10years/ar_anlg/ (アナログ)、`ar_cd/`、`ar_tape/`
  - 米国: RIAA Year-End Revenue Report https://www.riaa.com/reportcat/sales-revenue/
- `data/history/formats_ytd.csv` … 米国の上半期の数字。毎年9月ごろ RIAA Mid-Year Report が出たら書き換え。

## 手元のPCで試す

```bash
pip install -r requirements.txt
```
```bash
python -m collectors.run
```
```bash
python -m analysis.build
```
```bash
python -m http.server 8765 --directory site
```

ブラウザで http://localhost:8765 を開きます。レポートは `python -m analysis.report weekly`(要 `ANTHROPIC_API_KEY`)。

## 仕組みと注意

- `collectors/` が収集 → `data/snapshots/日付.json`、`analysis/` が点数化と年次予想 → `site/data/latest.json`、`site/` が画面。
- 前週比の指標は、収集が1週間分たまってから出ます。
- 今年の見込みは「去年の実績 ×(今年の累計 ÷ 前年の同じ時期)」。その先は、最近の伸びが年々弱まる前提で延ばしています。
  各グラフの「予想の当たりやすさ」のずれが大きいもの(特にカセット)は当てにしすぎないでください。
- 中古の需要は Discogs の「欲しい」「持っている」の登録数から見ています。実際の売値・出品数は `DISCOGS_TOKEN` を登録すると表示されます。
- X はログインしての自動巡回を行いません(規約違反・凍結リスクのため)。公式APIキーがある場合のみ件数を取得します。
