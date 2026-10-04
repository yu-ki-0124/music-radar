// Music Radar 画面。data/latest.json を読んで描くだけ(計算は analysis/ 側)。
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = (v) => (v == null ? '–' : Math.abs(v) >= 100 ? Math.round(v).toLocaleString('ja-JP') : (+v.toFixed(1)).toLocaleString('ja-JP'));
const signed = (v, unit = '%') => (v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v)}${unit}`);
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const safeUrl = (u) => (/^https?:\/\//.test(u || '') ? u : '#');
const REGION = { all: '全体', jp: '日本', us: '米国', gb: '英国', kr: '韓国', de: 'ドイツ', fr: 'フランス', br: 'ブラジル', mx: 'メキシコ', in: 'インド', ng: 'ナイジェリア', au: '豪州', id: 'インドネシア', global: '世界' };
const FORMATS = ['vinyl', 'cd', 'cassette'];
const FLABEL = { vinyl: 'レコード', cd: 'CD', cassette: 'カセット' };
// 統計の単位を読みやすい単位に直す(千枚→万枚、百万円→億円)
const UNIT = { '千枚': [10, '万枚'], '千巻': [10, '万本'], '百万円': [100, '億円'], '百万枚': [1, '百万枚'] };

let D;
const charts = [];
const state = { format: 'cd', region: 'jp', chartRegion: 'all', artists: 'rising', news: 'cd' };

// ---- 小さなMarkdown表示(見出し・箇条書き・太字だけ。HTMLはすべてエスケープ) ----
function md(text) {
  const out = [];
  let list = false;
  for (const raw of text.split('\n')) {
    const line = esc(raw).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    const h = line.match(/^(#{1,4})\s+(.*)/);
    const li = line.match(/^\s*[-*]\s+(.*)/);
    if (list && !li) { out.push('</ul>'); list = false; }
    if (h) out.push(`<h3>${h[2]}</h3>`);
    else if (li) { if (!list) { out.push('<ul>'); list = true; } out.push(`<li>${li[1]}</li>`); }
    else if (line.trim()) out.push(`<p>${line}</p>`);
  }
  if (list) out.push('</ul>');
  return out.join('');
}

// ---- グラフ: 実績=実線、予想=破線、幅=薄い帯 ----
function lineChart(canvas, series, opts = {}) {
  const years = [...new Set(series.flatMap((s) => [...s.years, ...(s.forecast ? s.forecast.years : [])]))].sort();
  const datasets = [];
  for (const s of series) {
    const color = css(s.color);
    const at = (ys, vs) => years.map((y) => { const i = ys.indexOf(y); return i < 0 ? null : vs[i]; });
    datasets.push({ label: s.label, data: at(s.years, s.values), borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.2 });
    if (s.forecast) {
      const f = s.forecast, lastY = s.years.at(-1), lastV = s.values.at(-1);
      const join = (vs) => at([lastY, ...f.years], [lastV, ...vs]);
      datasets.push({ label: `${s.label}(予想)`, data: join(f.base), borderColor: color, backgroundColor: color, borderWidth: 2, borderDash: [5, 4], pointRadius: 0, pointHoverRadius: 4, tension: 0.2 });
      if (f.lo) {
        datasets.push({ label: '_lo', data: join(f.lo), borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, band: true });
        datasets.push({ label: '_hi', data: join(f.hi), borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, fill: '-1', backgroundColor: color + '26', band: true });
      }
    }
  }
  const grid = css('--line'), tick = css('--text-3');
  charts.push(new Chart(canvas, {
    type: 'line',
    data: { labels: years, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => !item.dataset.band && item.parsed.y != null,
          callbacks: { title: (c) => `${c[0].label}年`, label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}${opts.unit || ''}` },
        },
        refLine: opts.ref,
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: tick, maxRotation: 0, autoSkipPadding: 12 }, border: { color: grid } },
        y: { beginAtZero: true, max: opts.max, grid: { color: grid }, ticks: { color: tick, maxTicksLimit: 5, callback: (v) => fmt(v) }, border: { display: false } },
      },
    },
    plugins: [{
      id: 'refLine', // 基準線(例: 50%)
      afterDraw(c, _a, ref) {
        if (typeof ref !== 'number') return;
        const y = c.scales.y.getPixelForValue(ref), { left, right } = c.chartArea;
        c.ctx.save(); c.ctx.strokeStyle = tick; c.ctx.setLineDash([2, 3]); c.ctx.beginPath(); c.ctx.moveTo(left, y); c.ctx.lineTo(right, y); c.ctx.stroke(); c.ctx.restore();
      },
    }],
  }));
}

function tableOf(series, unit) {
  const years = [...new Set(series.flatMap((s) => [...s.years, ...(s.forecast ? s.forecast.years : [])]))].sort();
  const rows = years.map((y) => `<tr><td>${y}年</td>${series.map((s) => {
    const i = s.years.indexOf(y), j = s.forecast ? s.forecast.years.indexOf(y) : -1;
    return i >= 0 ? `<td>${fmt(s.values[i])}</td>` : j >= 0 ? `<td class="fc">${fmt(s.forecast.base[j])}${s.forecast.lo ? `(${fmt(s.forecast.lo[j])}〜${fmt(s.forecast.hi[j])})` : ''}</td>` : '<td>–</td>';
  }).join('')}</tr>`).join('');
  return `<details><summary>数字で見る</summary><div class="scroll"><table><tr><th>年</th>${series.map((s) => `<th>${esc(s.label)}${unit ? `(${esc(unit)})` : ''}</th>`).join('')}</tr>${rows}</table></div><p class="note">斜体は予想(かっこ内は少なめ〜多めの幅)</p></details>`;
}

function chartCard(title, lead, series, opts = {}) {
  const id = `c${Math.random().toString(36).slice(2)}`;
  queueMicrotask(() => lineChart($(id), series, opts));
  return `<div class="card"><h3>${esc(title)}</h3>${lead ? `<p class="lead">${lead}</p>` : ''}<div class="chart"><canvas id="${id}" role="img" aria-label="${esc(title)}"></canvas></div>
    <div class="legend"><span><i></i>実績</span><span><i class="dash"></i>予想${series[0].forecast && series[0].forecast.lo ? '(薄い帯は少なめ〜多めの幅)' : ''}</span></div>${opts.after || ''}${tableOf(series, opts.unit)}</div>`;
}

// 統計1系列を、読みやすい単位に直してグラフ用に整える
function scaled(s, color) {
  const [div, unit] = UNIT[s.unit] || [1, s.unit];
  const sc = (a) => a.map((v) => +(v / div).toFixed(2));
  const f = s.forecast;
  return { label: s.label, color, unit, years: s.years, values: sc(s.values), forecast: f && { ...f, base: sc(f.base), lo: sc(f.lo), hi: sc(f.hi) }, raw: s };
}

function seg(id, options, current) {
  return `<div class="seg" id="${id}">${options.map(([v, label]) => `<button data-v="${v}" aria-pressed="${v === current}">${esc(label)}</button>`).join('')}</div>`;
}
function onSeg(id, key, tab) {
  const el = $(id);
  if (el) el.onclick = (e) => { const v = e.target.dataset.v; if (v) { state[key] = v; render(tab); } };
}

function spark(values) {
  if (!values || values.length < 3) return '';
  const w = 96, h = 22, max = Math.max(...values), min = Math.min(...values), r = max - min || 1;
  const pts = values.map((v, i) => `${(i * w / (values.length - 1)).toFixed(1)},${(h - 2 - (v - min) * (h - 4) / r).toFixed(1)}`).join(' ');
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="var(--vinyl)" stroke-width="1.5"/></svg>`;
}

function artistRow(a, i, full = true) {
  const links = full ? `<div class="meta"><a href="https://www.youtube.com/results?search_query=${encodeURIComponent(a.name)}" target="_blank" rel="noopener">YouTubeで聴く</a> ・ <a href="https://www.discogs.com/search/?type=artist&q=${encodeURIComponent(a.name)}" target="_blank" rel="noopener">Discogsで盤を探す</a></div>` : '';
  return `<div class="row"><div class="rank">${i + 1}</div><div class="body">
    <div class="name">${esc(a.name)}${a.new ? '<span class="chip">初登場</span>' : ''}</div>
    ${a.genre ? `<div class="meta">${esc(a.genre)}</div>` : ''}
    <ul class="why">${(full ? a.reasons : a.reasons.slice(-1)).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>${full ? spark(a.spark) : ''}${links}
  </div><div class="score"><b>${a.score}</b><small>注目度</small></div></div>`;
}

function nowCard(n) {
  return `<div class="card now"><div class="now-head"><h3>${esc(n.label)}</h3><span class="verdict ${cls(n.growth_pct)}">${esc(n.verdict)}</span></div>
    <ul class="why">${n.lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul></div>`;
}

// ---- まとめ ----
function renderHome() {
  const rep = D.reports.weekly || D.reports.monthly;
  const report = rep
    ? `<h2>今週の読み</h2><div class="card report">${md(rep.md)}</div>${D.reports.weekly && D.reports.monthly ? `<details class="card report"><summary>今月のまとめを読む</summary>${md(D.reports.monthly.md)}</details>` : ''}`
    : '';
  $('tab-home').innerHTML = `
    <h2>レコード・CD・カセットのいま</h2>
    <p class="lead">新品の生産(公式統計)と、中古の人気を合わせて見た現状です。</p>
    ${D.media.now.map(nowCard).join('')}
    ${report}
    <h2>いま伸びているアーティスト</h2>
    <div class="card">${D.artists.slice(0, 5).map((a, i) => artistRow(a, i, false)).join('')}</div>
    <p class="note">つづきは「アーティスト」タブへ。</p>
    <details class="card"><summary>データの取得状況(${D.date} 時点)</summary>
      ${D.sources.map((x) => `<div class="row"><div class="body"><div class="name">${esc(x.name)}</div><div class="meta">${esc(x.note || '')}</div></div><div class="score"><small>${x.ok ? `${x.count}件` : x.skipped ? '未設定' : '失敗'}</small></div></div>`).join('')}
      ${rep ? '' : '<p class="note">文章での解説は、APIキー登録後に毎週月曜に自動で追加されます。</p>'}
    </details>`;
}

// ---- メディア(1媒体ずつ表示) ----
function renderMedia() {
  const m = D.media, f = state.format;
  const now = m.now.find((n) => n.format === f);
  const d = m.demand;

  // 中古の需要
  const genreRows = d.by_genre.filter((r) => r[f]).sort((a, b) => b[f].ratio - a[f].ratio);
  const gRow = (r) => `<tr><td>${esc(r.genre)}</td><td><b>${r[f].ratio}</b>倍</td><td>${fmt(r[f].want)}人</td>${d.since ? `<td class="${cls(r[f].want_change_pct)}">${signed(r[f].want_change_pct)}</td>` : ''}</tr>`;
  const gHead = `<tr><th>ジャンル</th><th>品薄度</th><th>欲しい人</th>${d.since ? '<th>前回比</th>' : ''}</tr>`;
  const pick = (w, i) => `<div class="row"><div class="rank">${i + 1}</div><div class="body"><a class="name" href="${safeUrl(w.url)}" target="_blank" rel="noopener">${esc(w.title)}</a><div class="meta">${esc([w.style, w.country, w.year].filter(Boolean).join(' ・'))}</div><div class="meta">欲しい ${fmt(w.want)}人 / 持っている ${fmt(w.have)}人${w.lowest_jpy ? ` ・最安 ¥${fmt(w.lowest_jpy)}(出品${w.for_sale}点)` : ''}</div></div><div class="score"><b>${w.ratio}</b><small>倍</small></div></div>`;
  const used = genreRows.length ? `
    <h2>中古の需要</h2>
    <p class="lead">世界最大の中古盤サイト Discogs の登録から。<b>品薄度</b>は「欲しい人 ÷ 持っている人」。1倍を超えると、欲しい人のほうが多い状態です。</p>
    <div class="card"><h3>品薄なジャンル(${FLABEL[f]})</h3>
      <div class="scroll"><table>${gHead}${genreRows.slice(0, 8).map(gRow).join('')}</table></div>
      ${genreRows.length > 8 ? `<details><summary>全ジャンルを見る</summary><div class="scroll"><table>${gHead}${genreRows.slice(8).map(gRow).join('')}</table></div></details>` : ''}
      <p class="note">各ジャンルで「欲しい」登録が多い上位50作品の合計。${d.since ? `前回比は ${esc(d.since)} との比較。` : '前回比は1週間分たまると表示されます。'}</p></div>
    <div class="card"><h3>仕入れ候補(${FLABEL[f]})</h3><p class="lead">欲しい人が多いのに、持っている人が少ない盤。</p>
      ${(d.picks[f] || []).slice(0, 6).map(pick).join('')}
      ${(d.picks_japan[f] || []).length ? `<details><summary>日本盤だけ見る</summary>${d.picks_japan[f].map(pick).join('')}</details>` : ''}</div>` : '';

  // 新品の生産量
  const regions = [...new Set(m.series.filter((s) => s.format === f && s.forecast).map((s) => s.region))];
  if (!regions.includes(state.region)) state.region = regions[0];
  const card = (metric, title) => {
    const s = m.series.find((x) => x.id === `${state.region}_${f}_${metric}`);
    if (!s || !s.forecast) return '';
    const g = scaled(s, `--${f}`), fc = g.forecast, y = s.ytd;
    const lead = (fc.nowcast
      ? `<b>${fc.years[0]}年の見込み: 約${fmt(fc.base[0])}${g.unit}(前年より <span class="${cls(y.yoy_pct)}">${signed(y.yoy_pct)}</span>)</b><br>${esc(y.period)}の実績が前年の同じ時期より ${signed(y.yoy_pct)} だったことから計算。<br>`
      : '')
      + `${fc.years.at(-1)}年の予想: 約${fmt(fc.base.at(-1))}${g.unit}(少なめ ${fmt(fc.lo.at(-1))} 〜 多め ${fmt(fc.hi.at(-1))})`;
    const after = (fc.mape != null ? `<p class="note">予想の当たりやすさ: 同じ方法で過去3年を予想すると、平均 ${fc.mape}% のずれ${fc.mape >= 30 ? '。ずれが大きいので参考程度に' : ''}。</p>` : '')
      + `<p class="note">出典: ${[...new Map([...(y ? [y.source] : []), ...s.sources.slice(-1)].map((u) => [new URL(u).hostname.replace('www.', ''), u])).entries()].map(([host, u]) => `<a href="${safeUrl(u)}" target="_blank" rel="noopener">${esc(host)}</a>`).join('、')}</p>`;
    return chartCard(title, lead, [g], { unit: g.unit, after });
  };
  const bal = f === 'cassette' ? '' : m.balance.filter((b) => b.region === state.region).map((b) => {
    const split = b.years.indexOf(b.actual_until) + 1;
    const ser = { label: 'レコードの割合', color: '--vinyl', years: b.years.slice(0, split), values: b.vinyl_pct.slice(0, split), forecast: { years: b.years.slice(split), base: b.vinyl_pct.slice(split) } };
    return chartCard(`レコードとCD、どちらが多い?(${b.metric})`, `レコードとCDを合わせた${b.metric}のうち、レコードが占める割合。点線の50%より下ならCDのほうが多い。<br>いま <b>${b.vinyl_pct[split - 1]}%</b> → ${b.years.at(-1)}年 ${b.vinyl_pct.at(-1)}%`, [ser], { unit: '%', ref: 50, max: 100 });
  }).join('');
  const production = regions.length ? `
    <h2>新品の生産量(参考)</h2>
    <p class="lead">業界団体の公式統計(日本は生産、米国は出荷)。新品がたくさん出ると、数年後に中古の流通量も増えます。</p>
    ${regions.length > 1 ? seg('seg-region', regions.map((r) => [r, REGION[r]]), state.region) : ''}
    ${card('units', `${REGION[state.region]}で作られた${FLABEL[f]}の枚数`)}${card('value', `${REGION[state.region]}で作られた${FLABEL[f]}の金額`)}${bal}` : '';

  $('tab-media').innerHTML = `
    ${seg('seg-format', FORMATS.map((x) => [x, FLABEL[x]]), f)}
    ${now ? nowCard(now) : ''}${used}${production}`;
  onSeg('seg-format', 'format', 'media');
  onSeg('seg-region', 'region', 'media');
}

// ---- アーティスト ----
function renderArtists() {
  const list = state.artists === 'rising' ? D.artists.slice(0, 30) : D.frontier.slice(0, 30);
  const lead = state.artists === 'rising'
    ? '各国のランキングに入った数と、Wikipediaで調べる人の増え方から「注目度」(0〜100)を出しています。'
    : 'まだ世界的には知られていないのに、急に調べられたり、複数の国でランクインし始めた名前です。';
  $('tab-artists').innerHTML = `
    ${seg('seg-artists', [['rising', 'いま伸びている'], ['frontier', 'これから来そう']], state.artists)}
    <p class="lead">${lead}</p>
    <div class="card">${list.map((a, i) => artistRow(a, i)).join('') || '<p class="lead">該当なし</p>'}</div>
    ${D.days_collected < 8 ? '<p class="note">順位の上がり下がりは、1週間分のデータがたまると表示されます。</p>' : ''}`;
  onSeg('seg-artists', 'artists', 'artists');
}

// ---- ジャンル ----
function renderGenres() {
  const g = D.genres;
  const word = (s) => (s == null ? '–' : s >= 54 ? '伸びている' : s >= 47 ? '横ばい' : '下がり気味');
  const tracked = g.tracked.map((t, i) => `<details class="card"><summary><b>${esc(t.name)}</b><span class="chip ${t.score >= 54 ? 'up' : t.score < 47 ? 'down' : ''}">${word(t.score)}</span><div class="meta">${t.reasons.map(esc).join(' / ')}</div></summary><div data-lazy="${i}"></div></details>`).join('');
  const regions = Object.keys(g.charts);
  const rows = (g.charts[state.chartRegion] || []).map((r, i) => `<div class="row"><div class="rank">${i + 1}</div><div class="body"><div class="name">${esc(r.genre)}</div></div><div class="score"><b>${r.share}%</b>${r.delta != null ? `<small class="${cls(r.delta)}">${signed(r.delta, 'pt')}</small>` : ''}</div></div>`).join('');
  $('tab-genres').innerHTML = `
    <h2>ジャンルごとの流れ</h2>
    <p class="lead">タップすると、年ごとの推移と今後5年の予想グラフが開きます。</p>${tracked}
    <h2>いま売れている曲のジャンル</h2>
    <p class="lead">各国の人気ランキング上位に、どのジャンルが何%入っているか。</p>
    ${seg('seg-chart-region', regions.map((r) => [r, REGION[r] || r]), state.chartRegion)}
    <div class="card">${rows}</div>`;
  // グラフは開いたときに描く
  $('tab-genres').querySelectorAll('details.card').forEach((el, i) => el.addEventListener('toggle', () => {
    const slot = el.querySelector('[data-lazy]');
    if (!el.open || slot.dataset.done) return;
    slot.dataset.done = '1';
    const t = g.tracked[i];
    slot.innerHTML = (t.discogs ? chartCard('新しく出る作品に占める割合', '新譜1,000作品のうち、このジャンルが何作品あるか。', [{ label: t.name, color: '--vinyl', ...t.discogs }], { unit: '作品' }) : '')
      + (t.wiki ? chartCard('調べる人の多さ', 'Wikipediaでこのジャンルが見られた回数(全体100万回あたり)。', [{ label: t.name, color: '--cd', ...t.wiki }], { unit: '回' }) : '')
      || '<p class="lead">年ごとのデータはまだありません。</p>';
  }));
  onSeg('seg-chart-region', 'chartRegion', 'genres');
}

// ---- ニュース ----
function renderNews() {
  const item = (n) => `<div class="row"><div class="body"><a href="${safeUrl(n.link)}" target="_blank" rel="noopener"><div class="name">${esc(n.title)}</div><div class="meta">${esc(n.source || (n.sub ? `r/${n.sub}` : ''))}${n.date ? ` ・${esc(n.date)}` : ''}</div></a></div></div>`;
  const list = state.news === 'all' ? D.ideas.news : (D.ideas.by_format[state.news] || []);
  $('tab-news').innerHTML = `
    ${seg('seg-news', [...FORMATS.map((x) => [x, FLABEL[x]]), ['all', '音楽全般']], state.news)}
    <p class="lead">${state.news === 'all' ? '音楽メディア各社のこの1週間の見出し。' : `この2週間の「${FLABEL[state.news]}」に関するニュース(Googleニュースより)。`}</p>
    <div class="card news">${list.map(item).join('') || '<p class="lead">記事はありません。</p>'}</div>
    ${state.news === 'all' && D.ideas.reddit.length ? `<h2>海外掲示板で話題</h2><div class="card news">${D.ideas.reddit.slice(0, 20).map(item).join('')}</div>` : ''}`;
  onSeg('seg-news', 'news', 'news');
}

const RENDER = { home: renderHome, media: renderMedia, artists: renderArtists, genres: renderGenres, news: renderNews };
let current = 'home';
function render(tab) {
  current = tab;
  charts.splice(0).forEach((c) => c.destroy());
  for (const t of Object.keys(RENDER)) $(`tab-${t}`).hidden = t !== tab;
  document.querySelectorAll('#tabs button').forEach((b) => b.setAttribute('aria-selected', b.dataset.tab === tab));
  RENDER[tab]();
}

$('tabs').onclick = (e) => { const t = e.target.dataset.tab; if (t) { render(t); scrollTo(0, 0); } };
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => render(current));

fetch('data/latest.json', { cache: 'no-store' })
  .then((r) => r.json())
  .then((d) => {
    D = d;
    $('updated').textContent = `${d.date} 更新`;
    render('home');
  })
  .catch((e) => { $('tab-home').innerHTML = `<div class="card">データを読み込めませんでした(${esc(e.message)})</div>`; });
