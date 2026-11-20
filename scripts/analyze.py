#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把站点明细归一化成 market_profile.json（看板的标准输入）。

用法:
    python analyze.py sites.jsonl --platform Linkhouse -o profile.json
    python analyze.py sites.csv --map maps/adsy.json --counts counts.json -o profile.json
    python analyze.py sites.jsonl --peek            # 只打印字段清单，帮助写 map

设计要点:
  * 平台字段名千差万别 → 用 --map 指定映射，未指定的走内置猜测。
  * 不同平台的"段"叫法不同（行业/分类/niche）→ 统一叫 segment。
  * 流量多源并存 → 取多源最大值，并单独记录覆盖率（缺失≠0）。
  * 计数若平台能给精确值 → 用 --counts 覆盖抽样推出的 total。
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

DEFAULT_BANDS = {
    "price": [10, 25, 50, 100, 200, 500],
    "dr": [10, 20, 30, 40, 50, 60, 70, 80],
    "traffic": [1000, 5000, 10000, 50000, 100000, 500000],
}

# 内置猜测：平台没给 map 时按这些常见字段名找
GUESS = {
    "domain": ["domain", "site", "host", "website", "url_host"],
    "segment": ["segment", "category", "cat_name", "src_cat_name", "page_category", "niche", "industry"],
    "price": ["price", "lowest_price", "price_min", "site_price", "min_price", "price_for_advertisers"],
    "dr": ["dr", "DR", "ahrefs_dr", "site_dr", "domain_rating"],
    "da": ["da", "DA", "moz_da", "domain_authority"],
    "traffic": ["traffic", "organic_traffic", "ahrefs_traf", "semrush", "semstorm", "gsc", "traffic_ahrefs", "site_traffic"],
    "language": ["lang", "language", "site_language"],
    "country": ["country", "geo", "site_country"],
    "verified": ["verified", "is_verified", "checked"],
    "dofollow": ["dofollow", "links_follow"],
    "spam": ["spam", "moz_spam_score", "spam_score"],
}


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
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).replace(",", "").replace("$", "").replace("€", "").strip()
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


def load_rows(path):
    if path.endswith(".jsonl") or path.endswith(".ndjson"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    elif path.endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                yield row
    else:
        raise SystemExit("只支持 .jsonl / .ndjson / .csv")


def build_map(row_keys, user_map):
    """确定每个标准字段实际用哪个键。"""
    m = dict(user_map or {})
    lower = {k.lower(): k for k in row_keys}
    for std, names in GUESS.items():
        if std in m:
            continue
        for cand in names:
            if cand in row_keys:
                m[std] = cand
                break
            if cand.lower() in lower:
                m[std] = lower[cand.lower()]
                break
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="站点明细 .jsonl/.csv")
    ap.add_argument("--platform", default="目标平台")
    ap.add_argument("--entry", default="")
    ap.add_argument("--currency", default="$")
    ap.add_argument("--map", dest="map_path", help="字段映射 JSON")
    ap.add_argument("--counts", help="平台精确计数 JSON（覆盖抽样推出的 total）")
    ap.add_argument("--meta", help="补充元信息 JSON（method/caveats/supply_note 等），会并入输出")
    ap.add_argument("--bands", help="分档配置 JSON，覆盖默认")
    ap.add_argument("-o", "--out", default="profile.json")
    ap.add_argument("--top-segments", type=int, default=0, help="只保留供给量前 N 个分类")
    ap.add_argument("--peek", action="store_true", help="只打印字段名与前两条记录")
    args = ap.parse_args()

    rows = list(load_rows(args.input))
    if not rows:
        raise SystemExit("输入为空")

    if args.peek:
        keys = sorted({k for r in rows[:200] for k in r.keys()})
        print(f"记录数 {len(rows)}，字段 {len(keys)} 个：")
        for k in keys:
            samples = [str(r.get(k))[:40] for r in rows[:60] if r.get(k) not in (None, "")]
            print(f"  {k:26} e.g. {samples[0] if samples else ''}")
        return 0

    with open(args.map_path, encoding="utf-8") as f:
        user_map = json.load(f)
    m = build_map(set(rows[0].keys()), user_map.get("fields", user_map))
    missing = [k for k in ("price", "dr", "segment") if k not in m]
    if missing:
        print(f"[warn] 未能识别字段 {missing}，请用 --map 指定。用 --peek 查看可用字段名。", file=sys.stderr)

    bands = dict(DEFAULT_BANDS)
    if args.bands:
        with open(args.bands, encoding="utf-8") as f:
            bands.update(json.load(f))

    traffic_keys = m.get("traffic")
    if isinstance(traffic_keys, str):
        traffic_keys = [traffic_keys]
    traffic_keys = traffic_keys or []

    def pick(r, std):
        k = m.get(std)
        if not k:
            return None
        return r.get(k) if isinstance(k, str) else None

    def traffic_of(r):
        vals = [num(r.get(k)) for k in traffic_keys]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    # ---------- 汇总 ----------
    by_seg = defaultdict(lambda: {"prices": [], "drs": [], "das": [], "traffics": [],
                                  "n": 0, "dofollow": 0, "dofollow_n": 0,
                                  "verified": 0, "verified_n": 0, "domains": set()})
    all_prices, all_drs, all_das, all_traffics = [], [], [], []
    langs, countries = Counter(), Counter()
    dof_n = dof_yes = ver_n = ver_yes = 0
    spams = []
    seen = set()

    for r in rows:
        dom = str(pick(r, "domain") or r.get("url") or "")
        seg_raw = pick(r, "segment")
        seg = str(seg_raw) if seg_raw not in (None, "") else "未分类"

        b = by_seg[seg]
        b["n"] += 1
        if dom:
            b["domains"].add(dom)
            seen.add(dom)

        p = num(pick(r, "price"))
        if p is not None and p > 0:
            b["prices"].append(p)
            all_prices.append(p)
        d = num(pick(r, "dr"))
        if d is not None:
            b["drs"].append(d)
            all_drs.append(d)
        a = num(pick(r, "da"))
        if a is not None:
            b["das"].append(a)
            all_das.append(a)
        # 流量 0 视同缺失（没有数据的站常被填 0，混进去会把中位数拉垮）
        t = traffic_of(r)
        if t is not None and t > 0:
            b["traffics"].append(t)
            all_traffics.append(t)
        df = truthy(pick(r, "dofollow"))
        if df is not None:
            b["dofollow_n"] += 1
            dof_n += 1
            if df:
                b["dofollow"] += 1
                dof_yes += 1
        vf = truthy(pick(r, "verified"))
        if vf is not None:
            b["verified_n"] += 1
            ver_n += 1
            if vf:
                b["verified"] += 1
                ver_yes += 1
        sp = num(pick(r, "spam"))
        if sp is not None:
            spams.append(sp)
        lg = pick(r, "language")
        if lg:
            langs[str(lg).upper()] += 1
        ct = pick(r, "country")
        if ct:
            countries[str(ct).upper()] += 1

    def bkey(b):
        """分档名：1000 -> 1k，1000000 -> 1M，50 -> 50。看板里按这个名字取数。"""
        if b >= 1000000:
            return f"{b/1000000:g}M"
        if b >= 1000:
            return f"{b/1000:g}k"
        return f"{b:g}"

    def dist(vals, band_key, prefix_le=True):
        """返回 {le25: 12.3, ...} 或 {ge1k: 45.6, ...}"""
        out = {}
        if not vals:
            return out
        sv = sorted(vals)
        n = len(sv)
        for b in bands[band_key]:
            pre = "le" if prefix_le else "ge"
            c = sum(1 for v in sv if (v <= b if prefix_le else v >= b))
            out[pre + bkey(b)] = round(c / n * 100, 1)
        return out

    def price_stats(vals):
        if not vals:
            return {}
        sv = sorted(vals)
        return {
            "n": len(sv),
            "min": round(sv[0], 2),
            "p25": round(pct_rank(sv, .25), 2),
            "med": round(pct_rank(sv, .50), 2),
            "p75": round(pct_rank(sv, .75), 2),
            "p90": round(pct_rank(sv, .90), 2),
            "max": round(sv[-1], 2),
            **dist(sv, "price", True),
        }

    def dr_stats(vals):
        if not vals:
            return {}
        sv = sorted(vals)
        return {"n": len(sv), "med": round(pct_rank(sv, .5), 1),
                "p90": round(pct_rank(sv, .9), 1), **dist(sv, "dr", False)}

    def traffic_stats(vals, denom):
        if not vals:
            return {"coverage": 0}
        sv = sorted(vals)
        st = {"n": len(sv), "med": round(pct_rank(sv, .5)),
              "p90": round(pct_rank(sv, .9)),
              "coverage": round(len(sv) / denom, 3) if denom else None,
              **dist(sv, "traffic", False)}
        return st

    # 精确计数（可选）
    counts = {}
    if args.counts and os.path.exists(args.counts):
        with open(args.counts, encoding="utf-8") as f:
            counts = json.load(f)

    def counts_for(seg_name, cat_id=None):
        if not counts:
            return {}
        if cat_id is not None and str(cat_id) in counts:
            return counts[str(cat_id)]
        for k, v in counts.items():
            if isinstance(v, dict) and v.get("name") == seg_name:
                return v
        return {}

    total_n = len(rows)
    segments = []
    for seg, b in by_seg.items():
        c = counts_for(seg)
        prices_sorted = sorted(b["prices"])
        seg_total = c.get("total") if c.get("total") is not None else len(b["domains"] or [1])
        item = {
            "id": c.get("id") or seg,
            "name": c.get("name") or seg,
            "total": seg_total,
            "english": c.get("english"),
            "discount": c.get("discount"),
            "fmt": {k: v for k, v in (c.get("fmt") or {}).items()} or None,
            "sample_n": b["n"],
            "price": price_stats(b["prices"]),
            "dr": dr_stats(b["drs"]),
            "da_med": round(pct_rank(sorted(b["das"]), .5), 1) if b["das"] else None,
            "traffic": traffic_stats(b["traffics"], b["n"]),
            "dofollow_share": round(b["dofollow"] / b["dofollow_n"] * 100, 1) if b["dofollow_n"] else None,
            "verified_share": round(b["verified"] / b["verified_n"] * 100, 1) if b["verified_n"] else None,
            "_price_le50": None,
        }
        if not item["fmt"]:
            item.pop("fmt")
        segments.append(item)

    if args.top_segments:
        segments.sort(key=lambda s: s["total"] or 0, reverse=True)
        segments = segments[:args.top_segments]

    # ---- 价格 × 质量交叉：同样预算能买到什么 ----
    CROSS = [(50, 30), (50, 50), (100, 30), (100, 50), (200, 50), (200, 70)]
    cross_pairs = [(num(pick(r, "price")), num(pick(r, "dr"))) for r in rows]
    cross_pairs = [(p, d) for p, d in cross_pairs if p is not None and p > 0 and d is not None]
    cross = []
    for max_p, min_d in CROSS:
        hit = sum(1 for p, d in cross_pairs if p <= max_p and d >= min_d)
        cross.append({
            "cond": f"\u2264{args.currency}{max_p} \u4e14 DR\u2265{min_d}",
            "share": round(hit / len(cross_pairs) * 100, 1) if cross_pairs else None,
            "count": hit,
        })

    overall = {
        "cross": cross,
        "price": price_stats(all_prices),
        "dr": dr_stats(all_drs),
        "da": {"med": round(pct_rank(sorted(all_das), .5), 1) if all_das else None,
               "ge50": round(sum(1 for v in all_das if v >= 50) / len(all_das) * 100, 1) if all_das else None},
        "traffic": traffic_stats(all_traffics, total_n),
        "dofollow_share": round(dof_yes / dof_n * 100, 1) if dof_n else None,
        "verified_share": round(ver_yes / ver_n * 100, 1) if ver_n else None,
        "spam": ({"med": round(pct_rank(sorted(spams), .5), 1),
                  "p90": round(pct_rank(sorted(spams), .9), 1),
                  "ge30": round(sum(1 for v in spams if v >= 30) / len(spams) * 100, 1)} if spams else {}),
    }
    if langs:
        tot = sum(langs.values())
        top = langs.most_common(8)
        en = max(langs.get("GB", 0), langs.get("EN", 0), langs.get("US", 0))
        overall["language"] = {
            "english_share": round(en / tot * 100, 1),
            "top": f"{top[0][0]} {round(top[0][1]/tot*100,1)}%",
            "dist": [{"code": k, "share": round(v / tot * 100, 1)} for k, v in top],
        }
    if countries:
        overall["country"] = [{"code": k, "count": v} for k, v in countries.most_common(12)]

    supply_total = None
    if counts:
        supply_total = counts.get("_total")
    if supply_total is None:
        supply_total = sum(s["total"] for s in segments if s.get("total")) or len(seen)

    profile = {
        "platform": {"name": args.platform, "entry": args.entry,
                     "currency": args.currency, "supply_total": supply_total},
        "collection": {"date": None, "method": "sampled",
                       "sample_records": len(rows), "sample_domains": len(seen),
                       "caveats": []},
        "overall": overall,
        "segments": sorted(segments, key=lambda s: s["total"] or 0, reverse=True),
    }

    if args.meta and os.path.exists(args.meta):
        with open(args.meta, encoding="utf-8") as f:
            meta = json.load(f)
        for k, v in meta.items():
            if isinstance(v, dict) and isinstance(profile.get(k), dict):
                profile[k].update(v)
            else:
                profile[k] = v

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=1)

    print(f"已写出 {args.out}：{len(segments)} 个分类 / {len(seen)} 个域名 / 总量 {supply_total}")
    print(f"  价格中位 {overall['price'].get('med')} | DR 中位 {overall['dr'].get('med')} | "
          f"流量中位 {overall['traffic'].get('med')}（覆盖 {overall['traffic'].get('coverage')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
