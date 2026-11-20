#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把站点明细归一化成 market_profile.json（看板的标准输入）。

用法:
    python analyze.py sites.jsonl --peek                       # 只打印字段清单，帮助写 map
    python analyze.py sites.jsonl --platform "Platform" -o profile.json
    python analyze.py sites.csv --map maps/platform.json --counts counts.json \
        --meta meta.json -o profile.json

设计要点:
  * 平台字段名千差万别 → 用 --map 指定映射；没给或没写全的字段走内置猜测。
  * 不同平台的"段"叫法不同（行业/分类/niche）→ 统一叫 segment。
  * 流量多源并存 → 取多源最大值，并单独记录覆盖率（缺失≠0，0 也视为缺失）。
  * 同一域名会出现在多个分类 → 分类内按域名去重；全平台统计按域名全局去重。
  * 平台能给精确计数 → 用 --counts 覆盖抽样推出的 total。
"""
import argparse
import csv
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

DEFAULT_BANDS = {
    "price": [10, 25, 50, 100, 200, 500],
    "dr": [10, 20, 30, 40, 50, 60, 70, 80],
    "traffic": [1000, 5000, 10000, 50000, 100000, 500000],
    # 价格 × 质量交叉：[最高价, 最低 DR]
    "cross": [[50, 30], [50, 50], [100, 30], [100, 50], [200, 50], [200, 70]],
}

# 内置猜测：没给 map 或 map 没写的标准字段，按这些常见字段名找（大小写不敏感）
GUESS = {
    "domain": ["domain", "site", "host", "website", "url_host", "url"],
    "segment": ["segment", "category", "cat_name", "src_cat_name", "category_name",
                "page_category", "niche", "industry", "topic"],
    "price": ["price", "lowest_price", "price_min", "min_price", "site_price", "price_for_advertisers"],
    "dr": ["dr", "ahrefs_dr", "site_dr", "domain_rating"],
    "da": ["da", "moz_da", "domain_authority"],
    "traffic": ["traffic", "organic_traffic", "ahrefs_traf", "ahrefs_traffic", "semrush",
                "semrush_traffic", "semstorm", "gsc", "traffic_ahrefs", "site_traffic"],
    "language": ["lang", "language", "site_language"],
    "country": ["country", "geo", "site_country"],
    "verified": ["verified", "is_verified", "checked"],
    "dofollow": ["dofollow", "is_dofollow", "links_follow"],
    "spam": ["spam", "spam_score", "moz_spam_score"],
}
LIST_FIELDS = {"traffic"}          # 允许映射到多个源字段
ENGLISH_CODES = {"EN", "GB", "US", "UK", "ENG", "ENGLISH", "EN-US", "EN-GB", "EN_US", "EN_GB"}


def pct_rank(sorted_vals, q):
    """线性插值分位数，q 取 0–1。"""
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
        if s.lower() in ("none", "null", "-", "n/a", "na", ""):
            return None
        return float(s)
    except Exception:
        return None


def truthy(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return True
    if s in ("0", "false", "no", "n", "f", ""):
        return False
    return None


def norm_domain(v):
    s = str(v or "").strip().lower()
    for pre in ("https://", "http://"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.split("/")[0]
    return s[4:] if s.startswith("www.") else s


def load_rows(path):
    low = path.lower()
    if low.endswith(".jsonl") or low.endswith(".ndjson"):
        bad = 0
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                if isinstance(obj, dict):
                    yield obj
        if bad:
            print(f"[warn] 跳过 {bad} 行无法解析的 JSON", file=sys.stderr)
    elif low.endswith(".json"):
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):  # 常见形态 {"data":[...]} / {"items":[...]}
            data = next((v for v in data.values() if isinstance(v, list)), [])
        for obj in data:
            if isinstance(obj, dict):
                yield obj
    elif low.endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)
    else:
        raise SystemExit("只支持 .jsonl / .ndjson / .json / .csv")


def get_path(obj, path):
    """读取顶层键或点号嵌套路径（如 channel.metrics.domainRating、products.0.price）。"""
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def path_exists(rows, path):
    for r in rows:
        if isinstance(r, dict) and path in r:
            return True
        cur = r
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                ok = False
                break
        if ok:
            return True
    return False


def build_map(row_keys, user_map, sample_rows=()):
    """确定每个标准字段实际用哪个键（支持点号嵌套路径）；返回 (map, 警告列表)。"""
    m, warns = {}, []
    lower = {k.lower(): k for k in row_keys}
    for std, val in (user_map or {}).items():
        cands = val if isinstance(val, list) else [val]
        hit, missing = [], []
        for c in cands:
            cs = str(c)
            if cs.lower() in lower:
                hit.append(lower[cs.lower()])
            elif "." in cs and path_exists(sample_rows, cs):
                hit.append(cs)
            else:
                missing.append(c)
        if missing:
            warns.append(f"--map 中 {std} 指定的字段 {missing} 在数据里不存在")
        if hit:
            m[std] = hit if std in LIST_FIELDS else hit[0]
    for std, names in GUESS.items():
        if std in m:
            continue
        if std in LIST_FIELDS:
            hit = [lower[c] for c in names if c in lower]
            if hit:
                m[std] = hit
            continue
        for cand in names:
            if cand in lower:
                m[std] = lower[cand]
                break
    return m, warns


def main():
    ap = argparse.ArgumentParser(description="站点明细 → market_profile.json")
    ap.add_argument("input", help="站点明细 .jsonl/.ndjson/.json/.csv")
    ap.add_argument("--platform", default="目标平台")
    ap.add_argument("--entry", default="", help="真实市场入口 URL")
    ap.add_argument("--currency", default="$")
    ap.add_argument("--date", default=None, help="采集日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--map", dest="map_path", help="字段映射 JSON（可选，缺省走内置猜测）")
    ap.add_argument("--counts", help="平台精确计数 JSON（覆盖抽样推出的 total）")
    ap.add_argument("--meta", help="补充元信息 JSON（method/caveats/supply_note 等），浅合并进输出")
    ap.add_argument("--bands", help="分档 JSON，可覆盖 price/dr/traffic/cross")
    ap.add_argument("-o", "--out", default="profile.json")
    ap.add_argument("--top-segments", type=int, default=0, help="只保留供给量前 N 个分类")
    ap.add_argument("--peek", action="store_true", help="只打印字段名与示例值")
    args = ap.parse_args()

    rows = list(load_rows(args.input))
    if not rows:
        raise SystemExit("输入为空")
    row_keys = {k for r in rows[:500] for k in r.keys()}

    if args.peek:
        keys = sorted(row_keys)
        print(f"记录数 {len(rows)}，字段 {len(keys)} 个：")
        for k in keys:
            samples = [str(r.get(k))[:40] for r in rows[:100] if r.get(k) not in (None, "")]
            print(f"  {k:26} e.g. {samples[0] if samples else ''}")
        guessed, _ = build_map(row_keys, {})
        print("\n内置猜测的映射（不对就写 --map 覆盖）：")
        print(json.dumps({"fields": guessed}, ensure_ascii=False, indent=2))
        return 0

    user_map = {}
    if args.map_path:
        with open(args.map_path, encoding="utf-8-sig") as f:
            raw_map = json.load(f)
        user_map = raw_map.get("fields", raw_map)
    m, map_warns = build_map(row_keys, user_map, rows[:500])
    for w in map_warns:
        print(f"[warn] {w}", file=sys.stderr)
    missing = [k for k in ("domain", "price", "dr", "segment") if k not in m]
    if missing:
        print(f"[warn] 未能识别字段 {missing}，请用 --map 指定。用 --peek 查看可用字段名。", file=sys.stderr)

    bands = {k: list(v) for k, v in DEFAULT_BANDS.items()}
    if args.bands:
        with open(args.bands, encoding="utf-8-sig") as f:
            bands.update(json.load(f))

    traffic_keys = m.get("traffic") or []

    def pick(r, std):
        k = m.get(std)
        return get_path(r, k) if isinstance(k, str) else None

    def traffic_of(r):
        vals = [num(get_path(r, k)) for k in traffic_keys]
        vals = [v for v in vals if v is not None and v > 0]  # 0 视同缺失
        return max(vals) if vals else None

    def parse(r):
        dom = norm_domain(pick(r, "domain"))
        seg_raw = pick(r, "segment")
        return {
            "domain": dom,
            "segment": str(seg_raw).strip() if seg_raw not in (None, "") else "未分类",
            "price": (lambda p: p if p is not None and p > 0 else None)(num(pick(r, "price"))),
            "dr": num(pick(r, "dr")),
            "da": num(pick(r, "da")),
            "traffic": traffic_of(r),
            "dofollow": truthy(pick(r, "dofollow")),
            "verified": truthy(pick(r, "verified")),
            "spam": num(pick(r, "spam")),
            "language": str(pick(r, "language") or "").strip().upper() or None,
            "country": str(pick(r, "country") or "").strip().upper() or None,
        }

    recs = [parse(r) for r in rows]

    # 分类内去重（同一分类重复抓到的同一站只算一次）；无域名的记录原样保留
    by_seg = defaultdict(list)
    seg_seen = defaultdict(set)
    for x in recs:
        if x["domain"]:
            if x["domain"] in seg_seen[x["segment"]]:
                continue
            seg_seen[x["segment"]].add(x["domain"])
        by_seg[x["segment"]].append(x)

    # 全平台去重（同一站出现在多个分类只算一次，否则多分类站点权重被放大）
    uniq, seen = [], set()
    for x in recs:
        if x["domain"]:
            if x["domain"] in seen:
                continue
            seen.add(x["domain"])
        uniq.append(x)

    def bkey(b):
        """分档名：1000 -> 1k，1000000 -> 1M，50 -> 50。看板按这个名字取数。"""
        if b >= 1000000:
            return f"{b / 1000000:g}M"
        if b >= 1000:
            return f"{b / 1000:g}k"
        return f"{b:g}"

    def dist(sv, band_key, le):
        out, n = {}, len(sv)
        if not n:
            return out
        for b in bands[band_key]:
            c = sum(1 for v in sv if (v <= b if le else v >= b))
            out[("le" if le else "ge") + bkey(b)] = round(c / n * 100, 1)
        return out

    def vals(xs, k):
        return sorted(x[k] for x in xs if x[k] is not None)

    def price_stats(xs):
        sv = vals(xs, "price")
        if not sv:
            return {}
        return {"n": len(sv), "min": round(sv[0], 2),
                "p25": round(pct_rank(sv, .25), 2), "med": round(pct_rank(sv, .5), 2),
                "p75": round(pct_rank(sv, .75), 2), "p90": round(pct_rank(sv, .9), 2),
                "max": round(sv[-1], 2), **dist(sv, "price", True)}

    def dr_stats(xs):
        sv = vals(xs, "dr")
        if not sv:
            return {}
        return {"n": len(sv), "med": round(pct_rank(sv, .5), 1),
                "p90": round(pct_rank(sv, .9), 1), **dist(sv, "dr", False)}

    def traffic_stats(xs):
        sv = vals(xs, "traffic")
        cov = round(len(sv) / len(xs), 3) if xs else None
        if not sv:
            return {"n": 0, "coverage": cov}
        return {"n": len(sv), "med": round(pct_rank(sv, .5)), "p90": round(pct_rank(sv, .9)),
                "coverage": cov, **dist(sv, "traffic", False)}

    def share(xs, k):
        known = [x[k] for x in xs if x[k] is not None]
        return round(sum(1 for v in known if v) / len(known) * 100, 1) if known else None

    # ---- 精确计数（可选）----
    counts = {}
    if args.counts:
        if not os.path.exists(args.counts):
            raise SystemExit(f"--counts 文件不存在：{args.counts}")
        with open(args.counts, encoding="utf-8-sig") as f:
            counts = json.load(f)

    def counts_for(seg):
        """segment 既可能是名字也可能是 ID：先按 ID 键找，再按 name 找。"""
        if not counts:
            return {}
        v = counts.get(seg)
        if isinstance(v, dict):
            return v
        for v in counts.values():
            if isinstance(v, dict) and (str(v.get("name", "")).strip() == seg or str(v.get("id", "")) == seg):
                return v
        return {}

    segments, unmatched = [], []
    for seg, xs in by_seg.items():
        c = counts_for(seg)
        if counts and not c:
            unmatched.append(seg)
        item = {
            "id": str(c.get("id") or seg),
            "name": c.get("name") or seg,
            "total": c["total"] if c.get("total") is not None else len(xs),
            "total_exact": c.get("total") is not None,
            "english": c.get("english"),
            "discount": c.get("discount"),
            "sample_n": len(xs),
            "price": price_stats(xs),
            "dr": dr_stats(xs),
            "da_med": (lambda sv: round(pct_rank(sv, .5), 1) if sv else None)(vals(xs, "da")),
            "traffic": traffic_stats(xs),
            "dofollow_share": share(xs, "dofollow"),
            "verified_share": share(xs, "verified"),
        }
        if c.get("fmt"):
            item["fmt"] = dict(c["fmt"])
        segments.append(item)
    if unmatched:
        print(f"[warn] {len(unmatched)} 个分类在 --counts 里没对上（{', '.join(unmatched[:5])}…），"
              f"其 total 退回抽样条数", file=sys.stderr)

    segments.sort(key=lambda s: s["total"] or 0, reverse=True)
    if args.top_segments:
        segments = segments[:args.top_segments]

    # ---- 价格 × 质量交叉：同样预算能买到什么（全局去重样本）----
    pairs = [(x["price"], x["dr"]) for x in uniq if x["price"] is not None and x["dr"] is not None]
    cross = []
    for max_p, min_d in bands["cross"]:
        hit = sum(1 for p, d in pairs if p <= max_p and d >= min_d)
        cross.append({"cond": f"≤{args.currency}{max_p:g} 且 DR≥{min_d:g}",
                      "share": round(hit / len(pairs) * 100, 1) if pairs else None,
                      "count": hit})

    das, spams = vals(uniq, "da"), vals(uniq, "spam")
    overall = {
        "price": price_stats(uniq),
        "dr": dr_stats(uniq),
        "da": {"med": round(pct_rank(das, .5), 1) if das else None,
               "ge50": round(sum(1 for v in das if v >= 50) / len(das) * 100, 1) if das else None},
        "traffic": traffic_stats(uniq),
        "spam": ({"med": round(pct_rank(spams, .5), 1), "p90": round(pct_rank(spams, .9), 1),
                  "ge30": round(sum(1 for v in spams if v >= 30) / len(spams) * 100, 1)} if spams else {}),
        "dofollow_share": share(uniq, "dofollow"),
        "verified_share": share(uniq, "verified"),
        "cross": cross,
    }
    langs = Counter(x["language"] for x in uniq if x["language"])
    if langs:
        tot = sum(langs.values())
        top = langs.most_common(8)
        en = sum(v for k, v in langs.items() if k in ENGLISH_CODES)
        overall["language"] = {
            "english_share": round(en / tot * 100, 1),
            "coverage": round(tot / len(uniq), 3),
            "top": f"{top[0][0]} {round(top[0][1] / tot * 100, 1)}%",
            "dist": [{"code": k, "share": round(v / tot * 100, 1)} for k, v in top],
        }
    countries = Counter(x["country"] for x in uniq if x["country"])
    if countries:
        overall["country"] = [{"code": k, "count": v} for k, v in countries.most_common(12)]

    supply_total = counts.get("_total") if counts else None
    exact = supply_total is not None
    if supply_total is None:
        supply_total = len(seen) or len(uniq)  # 抽样口径：只能报去重域名数

    profile = {
        "platform": {"name": args.platform, "entry": args.entry, "currency": args.currency,
                     "supply_total": supply_total,
                     "supply_note": "平台精确计数" if exact else "抽样去重域名数（非全库）"},
        "collection": {"date": args.date or datetime.date.today().isoformat(),
                       "method": "mixed" if counts else "sampled",
                       "sample_records": len(rows), "sample_domains": len(seen),
                       "caveats": []},
        "overall": overall,
        "segments": segments,
    }

    if args.meta:
        if not os.path.exists(args.meta):
            raise SystemExit(f"--meta 文件不存在：{args.meta}")
        with open(args.meta, encoding="utf-8-sig") as f:
            meta = json.load(f)
        for k, v in meta.items():
            if isinstance(v, dict) and isinstance(profile.get(k), dict):
                profile[k].update(v)
            else:
                profile[k] = v

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=1)

    print(f"已写出 {out}：{len(segments)} 个分类 / {len(seen)} 个去重域名 / 总量 {supply_total}"
          f"（{'精确' if exact else '抽样'}）")
    print(f"  价格中位 {overall['price'].get('med')} | DR 中位 {overall['dr'].get('med')} | "
          f"流量中位 {overall['traffic'].get('med')}（覆盖 {overall['traffic'].get('coverage')}）")
    if not profile["collection"].get("caveats"):
        print("[warn] collection.caveats 为空：交付前用 --meta 写清口径（精确/抽样、缺失率、核验口径）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
