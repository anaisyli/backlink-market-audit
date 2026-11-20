#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用外链市场看板生成器。

用法:
    python dashboard.py profile.json                 # -> market-dashboard.html
    python dashboard.py profile.json -o out.html
    python dashboard.py profile.json --strict        # 缺关键字段直接报错

输入是 market_profile.json（schema 见 references/data-schema.md），
输出是单文件、零外链、可直接双击打开或上线的 HTML 看板。
"""
import argparse
import json
import os
import re
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(SKILL_ROOT, "assets", "dashboard_template.html")

REQUIRED_TOP = ["platform", "segments"]
RECOMMENDED = {
    "platform.supply_total": "总量 KPI 会显示 —",
    "collection.method": "口径标签缺失，报告可信度无法判断",
    "overall.price.med": "KPI 与跨平台对比会缺价格行",
    "overall.dr.med": "KPI 与散点图会缺质量维度",
    "segments[].price.med": "散点图与价格堆叠条会漏掉该分类",
    "segments[].dr.med": "该分类无法进入综合分排序",
}


def _get(d, path):
    cur = d
    for p in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
        if cur is None:
            return None
    return cur


def lint(profile):
    """返回 (errors, warnings)。"""
    errs, warns = [], []
    for k in REQUIRED_TOP:
        if not profile.get(k):
            errs.append(f"缺少顶层字段 `{k}`")

    segs = profile.get("segments") or []
    if segs and not isinstance(segs, list):
        errs.append("`segments` 必须是数组")
    bad = [i for i, s in enumerate(segs) if not isinstance(s, dict) or not s.get("name")]
    if bad:
        errs.append(f"segments[{bad[:5]}] 缺少 name")

    for path, why in RECOMMENDED.items():
        if path.endswith("[].price.med") or path.endswith("[].dr.med"):
            key = path.split(".")[-2]
            miss = [s.get("name") for s in segs if not _get(s, key + ".med")]
            if miss:
                warns.append(f"{len(miss)} 个分类缺 `{key}.med`（{', '.join(miss[:3])}…）→ {why}")
        elif _get(profile, path) is None:
            warns.append(f"缺 `{path}` → {why}")

    # 百分比字段越界检查
    for s in segs:
        for grp in ("price", "dr", "traffic"):
            g = s.get(grp) or {}
            for k, v in g.items():
                if k.startswith(("le", "ge")) and isinstance(v, (int, float)) and not (0 <= v <= 100):
                    warns.append(f"`{s.get('name')}` 的 {grp}.{k}={v} 不在 0–100，可能用了小数而非百分数")
                    break

    return errs, warns


def normalize(profile):
    """补默认值，避免模板里到处判空。"""
    p = dict(profile)
    p.setdefault("platform", {})
    p.setdefault("collection", {})
    p.setdefault("overall", {})
    p.setdefault("segments", [])
    p.setdefault("compare", [])
    p["platform"].setdefault("currency", "$")
    p["platform"].setdefault("name", "目标平台")

    col = p["collection"]
    if not col.get("date"):
        col["date"] = datetime.date.today().isoformat()

    # 逐分类派生指标
    for s in p["segments"]:
        s.setdefault("price", {})
        s.setdefault("dr", {})
        s.setdefault("traffic", {})
        tot, en = s.get("total"), s.get("english")
        if en is not None and tot:
            s["english_share"] = round(en / tot * 100, 1)
        pm = s["price"].get("med")
        dm = s["dr"].get("med")
        s["cpdr"] = round(dm / pm * 100, 2) if (pm and dm and pm > 0) else None
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", help="market_profile.json 路径")
    ap.add_argument("-o", "--out", default="market-dashboard.html")
    ap.add_argument("--strict", action="store_true", help="有 error 就退出")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(args.profile, "r", encoding="utf-8") as f:
        raw = json.load(f)

    errs, warns = lint(raw)
    if not args.quiet:
        for e in errs:
            print(f"[ERROR] {e}", file=sys.stderr)
        for w in warns:
            print(f"[warn]  {w}", file=sys.stderr)
    if errs and args.strict:
        print("存在结构性错误，已中止（去掉 --strict 可强行生成）。", file=sys.stderr)
        return 2

    profile = normalize(raw)

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    # 防止数据里的 </script> 提前闭合脚本块
    payload = payload.replace("</", "<\\/")
    html = html.replace("{{DATA_JSON}}", payload)

    # 标题：模板内 <title> 换成平台名
    name = profile["platform"].get("name") or "外链市场"
    html = re.sub(r"<title>.*?</title>",
                  f"<title>{name} 外链市场调查</title>", html, count=1, flags=re.S)

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(out)
    if not args.quiet:
        print(f"已生成 {out}（{size/1024:.1f} KB，{len(profile['segments'])} 个分类"
              f"{'，含 ' + str(len(profile['compare'])) + ' 个对比平台' if profile['compare'] else ''}）")
        if warns:
            print(f"有 {len(warns)} 条提示，见上方 warn。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
