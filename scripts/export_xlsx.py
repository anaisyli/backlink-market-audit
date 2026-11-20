#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""profile.json → Excel（.xlsx），零依赖（只用标准库 zipfile 手写 OOXML）。

用法:
    python export_xlsx.py profile.json -o market-audit.xlsx

工作表:
    概览   全平台 KPI（供给、价格、DR、流量、语种、核验、dofollow）
    分类   每个分类一行（与看板总表同口径，可在 Excel 里自由筛选/排序）
    交叉   价格 × 质量交叉条件
    结构   语种分布 + 国家 Top
    对比   跨平台对比（profile 带 compare 时才有）
    口径   collection.caveats 与采集方法
"""
import argparse
import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape


def col_name(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def cell_xml(ref, v, style=0):
    st = f' s="{style}"' if style else ""
    if v is None or v == "":
        return f'<c r="{ref}"{st}/>'
    if isinstance(v, bool):
        v = "是" if v else "否"
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{st}><v>{v}</v></c>'
    txt = escape(str(v)).replace("\n", "&#10;")
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{txt}</t></is></c>'


def sheet_xml(rows, widths=None):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews>']
    if widths:
        out.append("<cols>" + "".join(
            f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)) + "</cols>")
    out.append("<sheetData>")
    for r, row in enumerate(rows):
        cells = "".join(cell_xml(f"{col_name(c)}{r + 1}", v, 1 if r == 0 else 0) for c, v in enumerate(row))
        out.append(f'<row r="{r + 1}">{cells}</row>')
    out.append("</sheetData>")
    if rows and len(rows) > 1:
        out.append(f'<autoFilter ref="A1:{col_name(len(rows[0]) - 1)}{len(rows)}"/>')
    out.append("</worksheet>")
    return "".join(out)


def write_xlsx(path, sheets):
    """sheets: [(name, rows, widths)]"""
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, (name, _, _) in enumerate(sheets, 1):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        wb.append(f'<sheet name="{escape(name[:31])}" sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{i}.xml"/>')
    n = len(sheets)
    rels.append(f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>')
    ct.append("</Types>")
    wb.append("</sheets></workbook>")
    rels.append("</Relationships>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FFE8F1FA"/></patternFill></fill></fills>'
              '<borders count="1"><border/></borders>'
              '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
              '<cellXfs count="2"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/></cellXfs>'
              '</styleSheet>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", styles)
        for i, (_, rows, widths) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(rows, widths))


def g(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def main():
    ap = argparse.ArgumentParser(description="profile.json → .xlsx")
    ap.add_argument("profile")
    ap.add_argument("-o", "--out", default="market-audit.xlsx")
    args = ap.parse_args()

    with open(args.profile, encoding="utf-8-sig") as f:
        P = json.load(f)
    plat, col, ov = P.get("platform") or {}, P.get("collection") or {}, P.get("overall") or {}
    cur = plat.get("currency") or "$"

    kpi = [["指标", "值", "说明"],
           ["平台", plat.get("name"), plat.get("entry")],
           ["可投放站点总量", plat.get("supply_total"), plat.get("supply_note")],
           ["采集日期", col.get("date"), col.get("method")],
           ["抽样记录 / 去重域名", f"{col.get('sample_records')} / {col.get('sample_domains')}", ""],
           [f"价格中位（{cur}）", g(ov, "price", "med"), f"P25 {g(ov, 'price', 'p25')} / P75 {g(ov, 'price', 'p75')} / P90 {g(ov, 'price', 'p90')}"],
           [f"≤{cur}50 占比 %", g(ov, "price", "le50"), f"≤{cur}100：{g(ov, 'price', 'le100')}%"],
           ["DR 中位", g(ov, "dr", "med"), f"DR≥30 {g(ov, 'dr', 'ge30')}% / DR≥50 {g(ov, 'dr', 'ge50')}% / DR≥70 {g(ov, 'dr', 'ge70')}%"],
           ["DA 中位", g(ov, "da", "med"), ""],
           ["自然流量中位", g(ov, "traffic", "med"), f"数据覆盖率 {g(ov, 'traffic', 'coverage')}（缺失≠0）"],
           ["英语站占比 %", g(ov, "language", "english_share"), f"最大语种 {g(ov, 'language', 'top')}"],
           ["平台核验占比 %", ov.get("verified_share"), ""],
           ["dofollow 占比 %", ov.get("dofollow_share"), ""],
           ["垃圾分中位", g(ov, "spam", "med"), f"≥30 占 {g(ov, 'spam', 'ge30')}%"]]

    seg_rows = [["分类", "ID", "供给量", "供给口径", "英语站", "英语占比%", "折扣数", "抽样条数",
                 f"中位价{cur}", f"P25{cur}", f"P75{cur}", f"≤{cur}50%", f"≤{cur}100%",
                 "DR中位", "DR≥30%", "DR≥50%", "DR≥70%", "DA中位", "流量中位", "流量覆盖率",
                 "dofollow%", "核验%", f"每{cur}100得DR"]]
    for s in P.get("segments") or []:
        tot, en = s.get("total"), s.get("english")
        pm, dm = g(s, "price", "med"), g(s, "dr", "med")
        seg_rows.append([
            s.get("name"), s.get("id"), tot,
            "精确" if s.get("total_exact", s.get("english") is not None) else "抽样",
            en, round(en / tot * 100, 1) if (en is not None and tot) else None, s.get("discount"),
            s.get("sample_n"), pm, g(s, "price", "p25"), g(s, "price", "p75"),
            g(s, "price", "le50"), g(s, "price", "le100"),
            dm, g(s, "dr", "ge30"), g(s, "dr", "ge50"), g(s, "dr", "ge70"), s.get("da_med"),
            g(s, "traffic", "med"), g(s, "traffic", "coverage"),
            s.get("dofollow_share"), s.get("verified_share"),
            round(dm / pm * 100, 2) if (pm and dm is not None and pm > 0) else None])

    sheets = [("概览", kpi, [22, 18, 60]),
              ("分类", seg_rows, [30, 8] + [11] * 21)]

    cross = ov.get("cross") or []
    if cross:
        sheets.append(("交叉", [["条件", "占比%", "站点数"]] +
                       [[c.get("cond"), c.get("share"), c.get("count")] for c in cross], [24, 10, 10]))

    struct = [["类型", "代码", "占比% / 数量"]]
    struct += [["语种", d.get("code"), d.get("share")] for d in g(ov, "language", "dist") or []]
    struct += [["国家", d.get("code"), d.get("count")] for d in ov.get("country") or []]
    if len(struct) > 1:
        sheets.append(("结构", struct, [10, 10, 14]))

    cmp_ = P.get("compare") or []
    if cmp_:
        conds = [c.get("cond") for c in cross]
        head = ["平台", "总量", "英语站", "总量口径", f"中位价{cur}", f"≤{cur}50%", f"≤{cur}100%",
                "DR中位", "DR≥30%", "DR≥50%", "流量中位", "备注"] + conds
        rows = [head]
        selfp = {"name": plat.get("name"), "supply_total": plat.get("supply_total"),
                 "supply_note": plat.get("supply_note"), "price": ov.get("price"), "dr": ov.get("dr"),
                 "traffic": ov.get("traffic"), "cross": cross, "note": "基准平台"}
        for p in [selfp] + cmp_:
            cmap = {c.get("cond"): c.get("share") for c in (p.get("cross") or [])}
            rows.append([p.get("name"), p.get("supply_total"), p.get("supply_english"), p.get("supply_note"),
                         g(p, "price", "med"), g(p, "price", "le50"), g(p, "price", "le100"),
                         g(p, "dr", "med"), g(p, "dr", "ge30"), g(p, "dr", "ge50"),
                         g(p, "traffic", "med"), p.get("note")] + [cmap.get(c) for c in conds])
        sheets.append(("对比", rows, [18, 11, 11, 26, 10, 9, 9, 8, 8, 8, 11, 40] + [14] * len(conds)))

    cav = [["#", "口径与限制"]] + [[i, c] for i, c in enumerate(col.get("caveats") or ["未声明口径限制"], 1)]
    sheets.append(("口径", cav, [5, 120]))

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_xlsx(out, sheets)
    print(f"已生成 {out}（{len(sheets)} 个工作表，{len(seg_rows) - 1} 个分类）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
