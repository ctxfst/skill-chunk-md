#!/usr/bin/env python3
"""
CtxFST shape layer: link notes to recurring problem shapes.

A note is linked to a *shape card*, a hand-written description of a problem
that keeps coming back in different years with different objects, never to
another note. Each card is a probe over note embeddings: the mean of its
confirmed instances minus half the mean of its rejected notes (Rocchio). Every
review makes the probe sharper; no structure is extracted from the notes.

Pipeline:
    build    notes -> units -> text embeddings (no LLM)
    similar  nearest units to one unit
    link     per card: probe ranks all units -> top k -> anchored LLM judge -> review.md
             (--no-judge skips the LLM at a small cost in ranking quality)
    review   apply the marks in review.md to the cards ([x] confirm, [-] reject)
    eval     per-card ranking quality against a gold file {unit_id: [card_id, ...]}

Units: a note with %% chunk-start %% markers gives one unit per chunk
(`path#chunk-id`); any other note is one unit (`path`, no .md).

Usage:
    python shape_layer.py build NOTES_DIR --out INDEX_DIR [--list paths.txt] [--exclude 'private/*']
    python shape_layer.py similar INDEX_DIR UNIT_ID [--top 10]
    python shape_layer.py link INDEX_DIR --cards CARDS_DIR [--top 40 | --all]
    python shape_layer.py review INDEX_DIR --cards CARDS_DIR
    python shape_layer.py eval INDEX_DIR --cards CARDS_DIR --gold gold.json

Configuration (environment variables, or KEY=VALUE lines in a file passed with --env):
    CTXFST_LLM_URL     OpenAI-compatible chat completions URL (link only)
    CTXFST_LLM_MODEL   model name
    CTXFST_LLM_KEY     bearer token
    CTXFST_EMBED_URL   embeddings URL (default https://api.voyageai.com/v1/embeddings)
    CTXFST_EMBED_MODEL default voyage-3.5
    CTXFST_EMBED_KEY   bearer token

Requires numpy. Note text is sent to the configured APIs; use --exclude for
anything that must not leave the machine.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import numpy as np
except ImportError:
    print("Error: numpy required. Install with: pip install numpy")
    sys.exit(1)

TEXT_CAP = 1200       # characters of a unit shown to the LLM judge (tested value)
EMBED_CAP = 4000
BATCH = 8
NEG_WEIGHT = 0.5      # Rocchio weight of the rejected-notes mean
VERDICT = {'收': 2, '邊界': 1, '退': 0}
VERDICT_EN = {'收': 'accept', '邊界': 'borderline', '退': 'reject'}

# Card sections given to the judge (Chinese heading, English alias)
CARD_KEEP = (('問題形狀', 'problem shape'), ('核心張力', 'core tension'),
             ('最像但不同的線', 'near misses'), ('觸發條件', 'triggers'))
CARD_INSTANCES = ('化身清單', 'instances')
CARD_REJECTED = ('退回', 'rejected')



# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def sha(*parts):
    return hashlib.sha1('\x00'.join(parts).encode()).hexdigest()


def jload(p, default):
    p = Path(p)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def jsave(p, obj):
    p = Path(p)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, p)


def load_env(path):
    if path:
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            m = re.match(r'^([A-Z_]+)=(.+)$', line.strip())
            if m:
                os.environ.setdefault(m.group(1), m.group(2).strip())


def env(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        sys.exit(f'Error: set {name} (environment or --env file)')
    return v


def post(url, payload, key, timeout):
    req = urllib.request.Request(url, json.dumps(payload).encode(), method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(prompt, tries=4):
    err = ''
    for k in range(tries):
        try:
            d = post(env('CTXFST_LLM_URL'), {'model': env('CTXFST_LLM_MODEL'), 'temperature': 0,
                                            'max_tokens': 16000,
                                            'messages': [{'role': 'user', 'content': prompt}]},
                     env('CTXFST_LLM_KEY'), 300)
            c = d['choices'][0]['message']['content']
            if c and c.strip():
                return c
            err = 'empty response'
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
            err = str(e)[:160]
        time.sleep(10 * (k + 1))
    raise RuntimeError(err)


def jsonl(raw):
    for line in raw.splitlines():
        line = line.strip().strip('`').strip()
        if line.startswith('{'):
            try:
                yield json.loads(line)
            except ValueError:
                pass


def run_batches(items, make_prompt, parse, cache_path, label, rounds=3):
    """items: [(cache_key, payload)]. Results are cached by key; cached keys are skipped.
    Items lost to timeouts or bad output are retried in smaller batches, up to `rounds` passes,
    so one note the model refuses does not keep failing its whole batch."""
    cache = jload(cache_path, {})
    for r in range(rounds):
        todo = [it for it in items if it[0] not in cache]
        if not todo:
            break
        if r:
            print(f'  retry {r}: {len(todo)} items')
        _pass(todo, max(BATCH >> r, 1), make_prompt, parse, cache, cache_path, label if not r else None, len(items))
    missing = sum(it[0] not in cache for it in items)
    if missing:
        print(f'  {missing} items still missing; rerun the same command to fill them')
    return cache


def _pass(todo, size, make_prompt, parse, cache, cache_path, label, total):
    batches = [todo[i:i + size] for i in range(0, len(todo), size)]
    if label:
        print(f'{label}: {total} items, {total - len(todo)} cached, {len(batches)} batches')

    def one(b):
        try:
            return b, parse(chat(make_prompt([p for _, p in b])), len(b))
        except Exception as e:  # noqa: BLE001 - report and continue; rerun fills gaps
            return b, e

    with ThreadPoolExecutor(4) as ex:
        for n, (b, res) in enumerate(ex.map(one, batches), 1):
            if isinstance(res, Exception):
                print(f'  ! batch {n}/{len(batches)}: {res}')
                continue
            for i, (key, _) in enumerate(b):
                if i in res:
                    cache[key] = res[i]
            jsave(cache_path, cache)
            print(f'  batch {n}/{len(batches)}: {sum(i in res for i in range(len(b)))}/{len(b)}')


def embed(texts, cache_path):
    cache = jload(cache_path, {})
    url = env('CTXFST_EMBED_URL', 'https://api.voyageai.com/v1/embeddings')
    need = sorted({t for t in texts if sha(t) not in cache})
    for i in range(0, len(need), 32):
        part = need[i:i + 32]
        payload = {'model': env('CTXFST_EMBED_MODEL', 'voyage-3.5'), 'input': part}
        if 'voyage' in url:
            payload['input_type'] = 'document'
        d = post(url, payload, env('CTXFST_EMBED_KEY'), 120)
        for t, row in zip(part, sorted(d['data'], key=lambda r: r['index'])):
            cache[sha(t)] = row['embedding']
        jsave(cache_path, cache)
    out = {}
    for t in texts:
        v = np.asarray(cache[sha(t)], dtype=np.float32)
        out[t] = v / np.linalg.norm(v)
    return out


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

CHUNK_RE = re.compile(r'%%\s*chunk-start\s+id=["\']([^"\']+)["\']\s*%%(.*?)%%\s*chunk-end\s*%%', re.S | re.I)


def clean(text):
    if text.startswith('---'):
        parts = text.split('---', 2)
        text = parts[2] if len(parts) == 3 else text
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'https?://\S+', '(link)', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def read_units(root, paths=None, exclude=(), cut_at=()):
    root = Path(root)
    files = [root / (p if p.endswith('.md') else p + '.md') for p in paths] if paths \
        else sorted(root.rglob('*.md'))
    units = {}
    for f in files:
        rel = f.relative_to(root).with_suffix('').as_posix()
        if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel + '.md', g) for g in exclude):
            continue
        raw = f.read_text(encoding='utf-8', errors='ignore')
        for pat in cut_at:                     # drop generated blocks appended to notes
            m = re.search(pat, raw)
            if m:
                raw = raw[:raw.rfind('\n', 0, m.start()) + 1]
        title = f.stem
        chunks = CHUNK_RE.findall(raw)
        if chunks:
            for cid, body in chunks:
                units[f'{rel}#{cid}'] = (title, clean(body))
        else:
            units[rel] = (title, clean(raw))
    # The title goes first: some notes are a title and nothing else.
    return {k: f'# {t}\n\n{b}'.strip() for k, (t, b) in units.items()}


def body_chars(text):
    """Characters of real body text: no title line, links, or whitespace."""
    body = text.split('\n', 1)[1] if text.startswith('# ') and '\n' in text else ''
    return len(re.sub(r'\(link\)|\[[^\]]*\]|\s', '', body))


# ---------------------------------------------------------------------------
# build: embeddings only
# ---------------------------------------------------------------------------

def cmd_build(args):
    out = Path(args.out)
    (out / 'cache').mkdir(parents=True, exist_ok=True)
    paths = [l.strip() for l in Path(args.list).read_text(encoding='utf-8').splitlines() if l.strip()] \
        if args.list else None
    units = read_units(args.notes, paths, args.exclude, args.cut_at)
    ids = sorted(units)
    print(f'{len(ids)} units')
    text = {u: units[u][:EMBED_CAP] for u in ids}
    vec = embed(list(text.values()), out / 'cache' / 'embeddings.json')
    np.savez_compressed(out / 'vectors.npz', ids=np.array(ids), raw=np.stack([vec[text[u]] for u in ids]))
    jsave(out / 'units.json', {u: {'text': units[u][:TEXT_CAP], 'body_chars': body_chars(units[u])} for u in ids})
    print(f'wrote {out}/units.json, vectors.npz')


class Index:
    def __init__(self, d):
        d = Path(d)
        self.dir = d
        self.units = jload(d / 'units.json', None)
        if self.units is None:
            sys.exit(f'Error: {d}/units.json not found; run build first')
        z = np.load(d / 'vectors.npz')
        self.ids = [str(x) for x in z['ids']]
        self.pos = {u: i for i, u in enumerate(self.ids)}
        self.raw = z['raw']

    def rows(self, units):
        return [self.pos[u] for u in units]


def cmd_similar(args):
    ix = Index(args.index)
    if args.unit not in ix.pos:
        sys.exit(f'Error: unknown unit {args.unit}')
    sims = ix.raw @ ix.raw[ix.pos[args.unit]]
    for i in [i for i in np.argsort(-sims) if ix.ids[i] != args.unit][:args.top]:
        print(f'{sims[i]:.3f}  {ix.ids[i]}')


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

LINK_RE = re.compile(r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]')


def flat_links(line):
    return LINK_RE.sub(lambda m: m.group(2) or os.path.basename(m.group(1)), line)


def parse_card(path):
    """-> {'id', 'title', 'path', 'text' (sections given to the judge), 'head' (instance table header),
    'rows': [(link, row)] confirmed instances, 'rejected': [link]}"""
    text = Path(path).read_text(encoding='utf-8')
    m = re.search(r'^# (.+)$', text, re.M)
    title = m.group(1).strip() if m else Path(path).stem
    keep, head, rows, rejected, shape = [], '', [], [], ''
    for sec in re.split(r'^## ', text, flags=re.M)[1:]:
        name, _, body = sec.partition('\n')
        low = name.lower()
        if any(low.startswith(a) or name.startswith(z) for z, a in CARD_KEEP):
            keep.append('## ' + name + '\n' + flat_links(body).strip())
            if name.startswith(CARD_KEEP[0][0]) or low.startswith(CARD_KEEP[0][1]):
                shape = next((p.strip() for p in flat_links(body).split('\n\n')
                              if p.strip() and not p.lstrip().startswith('>')), '')
        elif name.startswith(CARD_INSTANCES[0]) or low.startswith(CARD_INSTANCES[1]):
            table = [l for l in body.splitlines() if l.startswith('|')]
            head = '\n'.join(table[:2])
            for l in table[2:]:
                lm = LINK_RE.search(l)
                if lm:
                    rows.append((lm.group(1).strip(), flat_links(l)))
        elif name.startswith(CARD_REJECTED[0]) or low.startswith(CARD_REJECTED[1]):
            rejected += [m.group(1).strip() for m in LINK_RE.finditer(body)]
    if not keep:
        sys.exit(f'Error: {path} has none of the sections {[z for z, _ in CARD_KEEP]}')
    return {'id': Path(path).stem, 'title': title, 'path': Path(path), 'shape': shape,
            'zh': '問題形狀' in text,
            'text': f'# {title}\n\n' + '\n\n'.join(keep), 'head': head, 'rows': rows, 'rejected': rejected}


def card_paths(arg):
    """A cards directory (every .md in it) or a glob pattern such as 'claims/*shape*.md'."""
    p = Path(arg)
    paths = sorted(p.glob('*.md')) if p.is_dir() else sorted(Path().glob(arg)) if not p.is_absolute() \
        else sorted(Path(p.anchor).glob(str(p.relative_to(p.anchor))))
    if not paths:
        sys.exit(f'Error: no cards found at {arg}')
    return paths


def resolve(link, ix):
    """Card links may omit folders; match by full path, then by basename."""
    if link in ix.pos:
        return [link]
    return [u for u in ix.ids
            if u.split('#')[0] == link or os.path.basename(u.split('#')[0]) == os.path.basename(link)]


def resolve_all(links, ix):
    return sorted({u for l in links for u in resolve(l, ix)})


JUDGE_PROMPT = '''下面是一張「主題線卡」，描述一個會在不同年份、不同對象上反覆出現的**問題形狀**。
接著是 {n} 篇筆記。逐篇判斷：這篇是不是**這張卡的形狀**又出現了一次。

判法：
- 先把筆記拆成角色：誰在做／對什麼做／想達成什麼／被什麼擋住／用了什麼手段。
- 再跟卡的問題形狀逐一對位，列出**對不上的角色**。
- 只看角色結構。主題詞彙、工具名、文體、格式相同都不算；對象完全不同但角色對得上，算。
- 卡的〈最像但不同的線〉列了容易誤收的類型，照它排除。
- 判定三級：收（角色都對得上）／邊界（部分對得上）／退。材料太少判不出形狀的，最多判邊界。

# 主題線卡

{card}

# 筆記

{items}

# 輸出
{n} 行 JSONL，一行一篇，順序同上，不要其他文字：
{{"i":1,"對不上":["…"],"判定":"收|邊界|退"}}'''


def parse_verdicts(raw, n):
    out = {}
    for d in jsonl(raw):
        i = int(d.get('i', 0)) - 1
        if 0 <= i < n and d.get('判定') in VERDICT:
            out[i] = {'verdict': d['判定'], 'mismatch': d.get('對不上') or []}
    return out


def judge(ix, card, units, label):
    """Anchored judging. Instance rows of the units in a batch are removed from that
    batch's examples, so a unit is never judged against its own row (leave-one-out)."""
    inst = {r_link: resolve(r_link, ix) for r_link, _ in card['rows']}

    def mk(batch):
        rows = [row for link, row in card['rows'] if not set(inst[link]) & set(batch)]
        ex = f'\n\n## 化身清單（過去確認過的例子；不代表全部）\n\n{card["head"]}\n' + '\n'.join(rows) \
            if rows else ''
        items = '\n\n'.join(f'--- {i} ---\n{ix.units[u]["text"]}' for i, u in enumerate(batch, 1))
        return JUDGE_PROMPT.format(n=len(batch), card=card['text'] + ex, items=items)
    # Key covers the card text and the unit text, so editing either re-judges.
    ck = sha(card['text'], card['head'], *[r for _, r in card['rows']])
    key = {u: sha('judge-v1', ck, ix.units[u]['text']) for u in units}
    cache = run_batches([(key[u], u) for u in units], mk, parse_verdicts,
                        ix.dir / 'cache' / 'judge.json', label)
    return {u: cache[key[u]] for u in units if key[u] in cache}


# ---------------------------------------------------------------------------
# Probe: one direction per card, learned from review
# ---------------------------------------------------------------------------

def probe(ix, pos, neg, card_text=None):
    """Rocchio: mean(confirmed) - NEG_WEIGHT * mean(rejected). With no confirmed
    instance yet, the card text itself is embedded and used as the direction."""
    if pos:
        v = ix.raw[ix.rows(pos)].mean(0)
    else:
        v = embed([card_text], ix.dir / 'cache' / 'embeddings.json')[card_text]
    if neg:
        v = v - NEG_WEIGHT * ix.raw[ix.rows(neg)].mean(0)
    return v


def cmd_link(args):
    ix = Index(args.index)
    cards = [parse_card(p) for p in card_paths(args.cards)]
    links, report = [], []
    for card in cards:
        pos = resolve_all([l for l, _ in card['rows']], ix)
        neg = resolve_all(card['rejected'], ix)
        score = ix.raw @ probe(ix, pos, neg, card['text'])
        order = [ix.ids[i] for i in np.argsort(-score)]
        cand = order if args.all else [u for u in order if u not in pos and u not in neg
                                       and ix.units[u].get('body_chars', args.min_body) >= args.min_body][:args.top]
        res = {u: None for u in cand} if args.no_judge else judge(ix, card, cand, f'judge "{card["title"]}"')
        for u, r in res.items():
            links.append({'card': card['id'], 'unit': u, 'verdict': r and VERDICT_EN[r['verdict']],
                          'mismatch': r['mismatch'] if r else [], 'probe': round(float(score[ix.pos[u]]), 4),
                          'known': 'instance' if u in pos else 'rejected' if u in neg else None})
        new = [l for l in links if l['card'] == card['id'] and not l['known'] and l['verdict'] != 'reject']
        report += review_section(card, new, ix, len(pos))
    zh = any(c['zh'] for c in cards)
    cmd = (f'python3 {Path(__file__).resolve()} review "{Path(args.index).resolve()}" '
           f'--cards "{args.cards}"')
    jsave(ix.dir / 'links.json', links)
    (ix.dir / 'review.md').write_text((REVIEW_HEAD_ZH if zh else REVIEW_HEAD_EN).format(cmd=cmd)
                                      + '\n'.join(report), encoding='utf-8')
    print(f'wrote {ix.dir}/links.json and review.md')


REVIEW_HEAD_ZH = '''# 待審：這些筆記是不是同一個問題又出現了一次？

每張卡描述一個會反覆出現的問題。下面每篇筆記，是程式覺得「可能又是這個問題」的候選。

**怎麼審**：先讀卡的〈問題形狀〉，再點開筆記，問自己一句：**這篇是不是同一個問題又出現了一次？**換了對象、換了工具、換了年代都算；只是主題相近不算。

- 是 → 把 `[ ]` 改成 `[x]`
- 不是 → 改成 `[-]`。退回很有用，下次就不會再推類似的筆記。
- 不確定 → 不用動

「AI 判收」「AI 判邊界」只是排閱讀順序用的，大約一半準，不必照它判。

**審完後**跑下面這行（或直接告訴 Claude）：

```
{cmd}
```

打勾的筆記會加進該卡的〈化身清單〉，打叉的加進〈退回〉。

---

'''

REVIEW_HEAD_EN = '''# Review: is each note another instance of the card's problem?

Read the card's problem shape, open each note, and ask: **is this the same problem again?** A different object, tool, or year still counts; a similar topic alone does not.

- Yes → change `[ ]` to `[x]`
- No → change it to `[-]`. Rejections are useful: similar notes will not be suggested again.
- Unsure → leave it

The judge's accept/borderline labels only set the reading order; about half are right.

When done, run:

```
{cmd}
```

---

'''


def excerpt(text, n=90):
    body = text.split('\n', 1)[1] if text.startswith('# ') and '\n' in text else text
    body = re.sub(r'\(link\)|[#>*`|_]|\[\[|\]\]', ' ', body)
    body = re.sub(r'\s+', ' ', body).strip()
    return body[:n] + ('…' if len(body) > n else '')


def review_section(card, new, ix, n_pos):
    """One card's part of review.md. The `<!-- card: id -->` marker and the
    `- [ ] … [[unit]]` lines are what `review` parses; everything else is for the reader."""
    zh = card['zh']
    link = lambda u: f'[[{u}|{os.path.basename(u.split("#")[0])}]]'
    out = [f'## {card["title"]}', f'<!-- card: {card["id"]} -->', '',
           f'卡：[[{card["id"]}]]' if zh else f'Card: [[{card["id"]}]]', '']
    if card['shape']:
        out += [f'> **{"問題形狀" if zh else "Problem shape"}**：{card["shape"].replace("**", "")}', '']
    if card['rows']:
        ex = '、'.join(f'[[{l}|{os.path.basename(l)}]]' for l, _ in card['rows'][:3])
        out += [(f'已確認 {n_pos} 篇，例如 {ex}。' if zh else f'{n_pos} confirmed, e.g. {ex}.'), '']
    groups = [('accept', 'AI 判收：角色都對得上' if zh else 'Judge: accept'),
              ('borderline', 'AI 判邊界：部分對得上' if zh else 'Judge: borderline'),
              (None, '依相似度排序' if zh else 'By probe score')]
    for v, label in groups:
        items = sorted((l for l in new if l['verdict'] == v), key=lambda l: -l['probe'])
        if not items:
            continue
        out += [f'### {label}（{len(items)}）', '']
        for l in items:
            out.append(f'- [ ] {link(l["unit"])}')
            ex = excerpt(ix.units[l['unit']]['text'])
            if ex:
                out.append(f'    - {"開頭" if zh else "Starts"}：{ex}')
            if l['mismatch']:
                why = '；'.join(map(str, l['mismatch']))
                out.append(f'    - {"不像的地方" if zh else "Does not fit"}：{why}')
        out.append('')
    if not new:
        out += ['（這次沒有新的候選）' if zh else '(no new candidates)', '']
    return out


# ---------------------------------------------------------------------------
# review: write marks back into the cards
# ---------------------------------------------------------------------------

REVIEW_RE = re.compile(r'^- \[([xX-])\] [^\[]*\[\[([^\]]+)\]\]')


def add_to_card(path, confirm, reject):
    """Append confirmed notes to the instance table and rejected ones to the rejected
    section, creating either section if missing. Returns (added, rejected) counts."""
    text = Path(path).read_text(encoding='utf-8')
    zh = '問題形狀' in text
    card = parse_card(path)
    have = {l for l, _ in card['rows']} | set(card['rejected'])
    confirm = [u for u in dict.fromkeys(confirm) if u not in have]
    reject = [u for u in dict.fromkeys(reject) if u not in have and u not in confirm]
    lines = text.rstrip('\n').split('\n')

    def section(names):
        for i, l in enumerate(lines):
            if l.startswith('## ') and (l[3:].startswith(names[0]) or l[3:].lower().startswith(names[1])):
                end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith('## ')), len(lines))
                return i, end
        return None

    if confirm:
        sec = section(CARD_INSTANCES)
        if sec is None:
            lines += ['', '## ' + ('化身清單' if zh else 'Instances'), '',
                      '| 年份 | 筆記 | 那次的對象 | 那次的做法 |' if zh else '| Year | Note | Object | Means |',
                      '|---|---|---|---|']
            sec = section(CARD_INSTANCES)
        i, end = sec
        table = [j for j in range(i, end) if lines[j].startswith('|')]
        ncol = lines[table[0]].count('|') - 1 if table else 4
        new = ['| ' + ' | '.join(['' if c != 1 else f'[[{u}]]' for c in range(ncol)]) + ' |' for u in confirm]
        at = (table[-1] + 1) if table else end
        lines[at:at] = new
    if reject:
        sec = section(CARD_REJECTED)
        if sec is None:
            lines += ['', '## ' + ('退回' if zh else 'Rejected'), '']
            sec = section(CARD_REJECTED)
        _, end = sec
        while end > 0 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = [f'- [[{u}]]' for u in reject]
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(confirm), len(reject)


def cmd_review(args):
    ix_dir = Path(args.index)
    marks, card = {}, None
    for line in (ix_dir / 'review.md').read_text(encoding='utf-8').splitlines():
        m = re.match(r'<!-- card: (.+) -->', line)
        if m:
            card = m.group(1)
            marks.setdefault(card, ([], []))
            continue
        m = REVIEW_RE.match(line)
        if m and card:
            unit = m.group(2).split('|')[0]
            marks[card][0 if m.group(1).lower() == 'x' else 1].append(unit)
    paths = {p.stem: p for p in card_paths(args.cards)}
    for cid, (confirm, reject) in marks.items():
        path = paths.get(cid)
        if (confirm or reject) and path:
            a, r = add_to_card(path, confirm, reject)
            print(f'{cid}: {a} instances added (fill in the empty columns), {r} rejected')


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def auc(pos, neg):
    if not pos or not neg:
        return float('nan')
    p, n = np.asarray(pos, dtype=float)[:, None], np.asarray(neg, dtype=float)[None]
    return float(((p > n) + 0.5 * (p == n)).mean())


def cmd_eval(args):
    """Per-card ranking quality, leave-one-out: each unit is scored by a probe built
    without it. gold: {unit_id: [card_id, ...]}; units absent from gold are distractors.
    With no real rejections yet, --simulate-review N treats the N non-gold units nearest
    the card's other instances as rejected, i.e. what a reviewer would have seen."""
    ix = Index(args.index)
    gold = {u: set(c) for u, c in jload(args.gold, {}).items()}
    cards = {c['id']: c for c in (parse_card(p) for p in card_paths(args.cards))}
    links = jload(ix.dir / 'links.json', [])
    J = {(l['card'], l['unit']): VERDICT[{b: a for a, b in VERDICT_EN.items()}[l['verdict']]]
         for l in links if l['verdict']}
    rows = []
    for cid, card in cards.items():
        members = [u for u in ix.ids if cid in gold.get(u, ())]
        real_neg = resolve_all(card['rejected'], ix)
        s_near, s_probe, s_judge, s_both, y = [], [], [], [], []
        for u in ix.ids:
            pos = [m for m in members if m != u]
            if not pos:
                continue
            near = ix.raw[ix.rows(pos)] @ ix.raw[ix.pos[u]]
            neg = [n for n in real_neg if n != u]
            if args.simulate_review:
                sims = (ix.raw @ ix.raw[ix.rows(pos)].T).max(1)
                neg += [ix.ids[i] for i in np.argsort(-sims)
                        if ix.ids[i] not in members and ix.ids[i] != u][:args.simulate_review]
            p = float(probe(ix, pos, sorted(set(neg))) @ ix.raw[ix.pos[u]])
            y.append(u in members)
            s_near.append(float(near.max()))
            s_probe.append(p)
            s_judge.append(J.get((cid, u)))
            s_both.append(None if J.get((cid, u)) is None else J[(cid, u)] + p)

        def a(s):
            pairs = [(x, t) for x, t in zip(s, y) if x is not None]
            return auc([x for x, t in pairs if t], [x for x, t in pairs if not t])
        rows.append((cid, len(members), a(s_near), a(s_probe), a(s_judge), a(s_both)))
    print('| card | instances | nearest instance | probe | judge | judge + probe |\n|---|---:|---:|---:|---:|---:|')
    for r in rows:
        print(f'| {r[0]} | {r[1]} | ' + ' | '.join('—' if np.isnan(x) else f'{x:.3f}' for x in r[2:]) + ' |')
    m = [np.nanmean([r[k] for r in rows]) for k in range(2, 6)]
    print('| mean | | ' + ' | '.join('—' if np.isnan(x) else f'{x:.3f}' for x in m) + ' |')
    if J:
        acc = [(c, u) for (c, u), x in J.items() if x == 2]
        tp = sum(c in gold.get(u, ()) for c, u in acc)
        n_true = sum(len(c & set(cards)) for c in gold.values())
        wrong = sum(bool(gold.get(u)) and c not in gold[u] for c, u in acc)
        print(f'\njudge accept: precision {tp / max(len(acc), 1):.0%} ({tp}/{len(acc)}), '
              f'recall {tp / max(n_true, 1):.0%}, gold units accepted into a wrong card {wrong}')


def main():
    ap = argparse.ArgumentParser(description='CtxFST shape layer')
    ap.add_argument('--env', help='file with KEY=VALUE lines (CTXFST_* settings)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('notes')
    b.add_argument('--out', required=True)
    b.add_argument('--list', help='file with one note path per line (relative to NOTES, .md optional)')
    b.add_argument('--exclude', nargs='*', default=[], help='glob patterns of paths never read')
    b.add_argument('--cut-at', nargs='*', default=[], metavar='REGEX',
                   help='truncate a note at the line matching this (e.g. a generated footer)')
    s = sub.add_parser('similar')
    s.add_argument('index')
    s.add_argument('unit')
    s.add_argument('--top', type=int, default=10)
    l = sub.add_parser('link')
    l.add_argument('index')
    l.add_argument('--cards', required=True, help='cards directory or glob pattern')
    l.add_argument('--top', type=int, default=40, help='candidates per card')
    l.add_argument('--all', action='store_true', help='judge every unit against every card (for eval)')
    l.add_argument('--min-body', type=int, default=20,
                   help='skip candidates with less body text than this (link-only clippings)')
    l.add_argument('--no-judge', action='store_true',
                   help='rank by probe only (no LLM; slightly worse ranking)')
    r = sub.add_parser('review')
    r.add_argument('index')
    r.add_argument('--cards', required=True)
    e = sub.add_parser('eval')
    e.add_argument('index')
    e.add_argument('--cards', required=True)
    e.add_argument('--gold', required=True)
    e.add_argument('--simulate-review', type=int, default=0, metavar='N')
    args = ap.parse_args()
    load_env(args.env)
    {'build': cmd_build, 'similar': cmd_similar, 'link': cmd_link, 'review': cmd_review,
     'eval': cmd_eval}[args.cmd](args)


if __name__ == '__main__':
    main()
