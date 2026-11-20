#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把另一个平台的 profile 合并成看板的"跨平台对比"项。

用法:
    python make_compare.py platform_a.json platform_b.json -o merged.json
    python make_compare.py main.json other.json -o merged.json --label "Platform B" --note "B 为已核验+英语口径"
    python make_compare.py main.json a.json b.json c.json -o merged.json   # 支持多平台

前提：每个平台都先用 analyze.py 各自跑出 profile.json（同一套字段口径）。
这一步只搬运 overall 数字，不做二次计算。
"""
import argparse
import json
import sys


def to_compare(prof, label=None, note=None):
    plat = prof.get("platform") or {}
    ov = prof.get("overall") or {}
    coll = prof.get("collection") or {}
    en_share = (ov.get("language") or {}).get("english_share")
    total = plat.get("supply_total")
    item = {
        "name": label or plat.get("name") or "对比平台",
        "supply_total": total,
        "supply_english": round(total * en_share / 100) if (total and en_share is not None) else None,
        "supply_note": plat.get("supply_note") or "",
        "price": ov.get("price") or {},
        "dr": ov.get("dr") or {},
        "traffic": ov.get("traffic") or {},
        "cross": ov.get("cross") or None,
    }
    if note:
        item["note"] = note
    elif coll.get("method"):
        item["note"] = f"{coll['method']} 口径"
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("main", help="基准平台 profile.json")
    ap.add_argument("others", nargs="+", help="一个或多个对比平台 profile.json")
    ap.add_argument("-o", "--out", default="merged.json")
    ap.add_argument("--label", action="append", help="对比平台显示名，按顺序对应，可重复")
    ap.add_argument("--note", action="append", help="对比脚注，按顺序对应，可重复")
    ap.add_argument("--replace", action="store_true", help="覆盖已有 compare，而不是追加")
    args = ap.parse_args()

    with open(args.main, encoding="utf-8") as f:
        base = json.load(f)

    if args.replace or not base.get("compare"):
        base["compare"] = []

    labels = args.label or []
    notes = args.note or []
    for i, path in enumerate(args.others):
        with open(path, encoding="utf-8") as f:
            prof = json.load(f)
        item = to_compare(
            prof,
            label=labels[i] if i < len(labels) else None,
            note=notes[i] if i < len(notes) else None,
        )
        if not item["price"] and not item["dr"]:
            print(f"[warn] {path} 的 overall 里没有 price/dr，对比区会几乎是空的", file=sys.stderr)
        base_conds = [c.get("cond") for c in ((base.get("overall") or {}).get("cross") or [])]
        item_conds = [c.get("cond") for c in (item["cross"] or [])]
        if base_conds and item_conds and base_conds != item_conds:
            print(f"[warn] {path} 的 cross 条件与基准平台不一致（币种或 --bands 不同），"
                  f"看板只对齐 cond 文本完全相同的行", file=sys.stderr)
        if (prof.get("platform") or {}).get("currency", "$") != (base.get("platform") or {}).get("currency", "$"):
            print(f"[warn] {path} 的币种与基准平台不同，价格对比无意义，先统一币种", file=sys.stderr)
        base["compare"].append(item)
        print(f"+ {item['name']}  总量 {item['supply_total']}  "
              f"价格中位 {(item['price'] or {}).get('med')}  DR 中位 {(item['dr'] or {}).get('med')}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=1)
    print(f"已写出 {args.out}，共 {len(base['compare'])} 个对比平台")
    return 0


if __name__ == "__main__":
    sys.exit(main())
