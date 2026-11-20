# market_profile.json 数据规范

`analyze.py` 的输出、`dashboard.py` 的唯一输入。改看板或接新平台时以本文为准。

顶层只有四个键：`platform` / `collection` / `overall` / `segments`，外加可选 `compare`。

```jsonc
{
  "platform":   { ... },   // 谁
  "collection": { ... },   // 怎么采的
  "overall":    { ... },   // 全平台画像
  "segments":   [ ... ],   // 每个分类一行
  "compare":    [ ... ]    // 可选，对比平台
}
```

---

## platform

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 显示名，看板标题用它 |
| `entry` | str | 真正的市场入口（不是品牌宣传站） |
| `currency` | str | 默认 `$`。模板里所有金额都用它 |
| `supply_total` | int | 可投放站点总量。**优先用平台精确计数**，别用抽样推算 |
| `supply_note` | str | 总量口径说明，如「全库精确」「已核验 + 英语」 |

## collection

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | str | 采集日期 `YYYY-MM-DD` |
| `method` | str | `exact`（全量精确）/ `mixed`（计数精确、分位抽样）/ `sampled`（全靠抽样） |
| `sample_records` | int | 抽样记录数（含重复域名） |
| `sample_domains` | int | 去重后域名数 |
| `caveats` | [str] | 直接渲染到「口径与限制」区。**这段决定报告能不能用，别写空话** |

## overall

```jsonc
{
  "price":  {"n":9102,"min":0.4,"p25":31.7,"med":89.4,"p75":241,"p90":743,"max":3676,
             "le25":15.8,"le50":31.7,"le100":53.3,"le200":68.5,"le500":85.7},
  "dr":     {"n":9102,"med":22.0,"p90":60.0,
             "ge10":62.5,"ge20":48.6,"ge30":39.8,"ge40":31.0,"ge50":19.3,"ge60":13.2,"ge70":5.7,"ge80":0.9},
  "da":     {"med":29.0,"ge50":31.2},
  "traffic":{"n":6688,"med":1914,"p90":211899,"coverage":0.735,
             "ge1k":35.2,"ge5k":24.7,"ge10k":20.2,"ge50k":9.6,"ge100k":5.2,"ge500k":0.7},
  "spam":   {"med":4.0,"p90":17.0,"ge30":5.3},
  "dofollow_share": 97.0,
  "verified_share": 3.2,
  "language":{"english_share":33.6,"top":"PL 34.4%","dist":[{"code":"PL","share":34.4}]},
  "country": [{"code":"PL","count":2804}],
  "cross":  [{"cond":"≤$50 且 DR≥30","share":5.7,"count":521}]
}
```

要点：

- **所有 `le*` / `ge*` 都是百分数（0–100），不是小数。** `le50 = 31.7` 意思是「≤$50 的占 31.7%」。
- `le*` 是累计占比（越小越便宜），`ge*` 也是累计（越大越权威）。看板就是靠这个画堆叠条和对比条。
- 分档键名规则：`le` / `ge` + 数值，**过千自动用 k**（`ge1k`、`ge10k`、`ge500k`），过百万用 M。写 `ge1000` 看板读不到。
- `traffic.coverage` = 有流量数据的站 / 全部站。**缺失不能当 0 算进中位数**，否则中位会被拉垮（实测能从 1914 掉到 234）。
- `language.english_share`：英语站占比，按 `GB`/`EN`/`US` 里最大的算。这是判断「池子是不是你的市场」最直接的指标。

## segments（每个分类一行）

```jsonc
{
  "id": "12", "name": "Finance, Loans, Insurance",
  "total": 2808,            // 该分类可投放站点数（优先精确计数）
  "english": 1032,          // 英语站数
  "discount": 163,          // 折扣报价数
  "fmt": {"sponsored_article":2773,"link_insertion":1043,"advertising_link":812},
  "sample_n": 298,          // 抽样条数
  "price": {"n":298,"min":0.4,"p25":41,"med":113,"p75":280,"p90":600,"max":3676,
            "le25":12,"le50":28,"le100":55,"le200":72,"le500":86},
  "dr":    {"n":298,"med":34,"p90":72,"ge10":80,"ge30":55,"ge50":36.1,"ge70":14.4},
  "da_med": 45.0,
  "traffic": {"n":260,"med":31335,"ge10k":62,"coverage":0.87},
  "dofollow_share": 98.0,
  "verified_share": 4.0,
  "english_share": 36.8,    // analyze.py 自动派生
  "cpdr": 30.1              // analyze.py 自动派生：每 $100 得多少 DR
}
```

- `fmt`（投放形式）可以缺；缺了看板就不显示「链接插入位最多」那个榜。
- `cpdr = dr.med / price.med * 100`，衡量「每花 100 美元买到多少 DR」，越大越划算。**要注意它偏向便宜但低质的分类**，只能当参考，不能单独排序。
- `total` 和 `sample_n` 是两回事：前者是分类供给量，后者是你实际抽了多少条来估分位数。两者都显示，读者才知道可信度。

## compare（可选，跨平台）

```jsonc
{
  "name": "Adsy",
  "supply_total": 103922,
  "supply_english": 48404,
  "supply_note": "展示 150k+，已核验 103,922",
  "price":  {"med":80.5,"le25":37.0,"le50":54.0,"le100":67.9,"le200":80.1,"le500":90.8},
  "dr":     {"med":18.0,"ge10":74.2,"ge30":46.2,"ge50":19.4,"ge70":5.5},
  "traffic":{"med":9920,"ge1k":75.2,"ge5k":60.7,"ge10k":49.8,"ge50k":23.6,"ge100k":12.9},
  "cross":  [{"cond":"≤$50 且 DR≥30","share":17.3}],
  "note": "已核验 + 英语口径，与本平台抽样口径不完全对等"
}
```

- 本平台那一列自动取 `overall`，不用手写。
- `cross` 的 `cond` 文本两边必须**完全一致**才能一一对齐（看板按数组下标匹配）。
- `note` 会显示在对比区顶部。口径不对等的对比，这句必须写，否则就是误导。

---

## 字段映射（--map）

`analyze.py` 的内置猜测覆盖了常见字段名，猜不到时自己写：

```json
{
  "fields": {
    "domain":   "domain",
    "segment":  "src_cat_name",
    "price":    "lowest_price",
    "dr":       "DR",
    "da":       "DA",
    "traffic":  ["gsc", "ahrefs_traf", "semrush", "semstorm"],
    "language": "lang",
    "country":  "country",
    "verified": "verified",
    "dofollow": "dofollow",
    "spam":     "spam"
  }
}
```

规则：

- `traffic` 可以是数组，脚本取**多源最大值**（一个站有多个流量源时，取最大的那个最接近真实自然流量）。
- `price` 要选**站点最低可购价**那一列（`lowest_price` / `price_min` / offer 列表里的最小值），不要用某一种投放形式的价格，否则跟别家不可比。
- `segment` 选**名字**字段（`src_cat_name`）而不是 ID，省掉一次 ID→名字的映射；只有 ID 时用 `--counts` 把名字带进来。
- 布尔字段（`verified` / `dofollow`）脚本认 `1/0`、`true/false`、`yes/no`。

## counts（精确计数）

```json
{
  "_total": 96330,
  "1": {"id":"1","name":"Local portals","total":5477,"english":17,"discount":1744,
        "fmt":{"sponsored_article":5459,"link_insertion":2285,"advertising_link":653}}
}
```

`_total` 是全库总量；其余键是分类 ID。`analyze.py` 会按 `name` 或 ID 自动匹配 `segments`。

## meta（补充元信息）

```json
{
  "collection": {"method":"mixed","date":"2026-09-28",
    "caveats":["行业数量为平台精确计数；价格与 DR 分位数来自分层抽样（9,102 域名）",
               "Linkhouse 仅 41% 英语站带 Ahrefs 流量数据，缺失按不达标计"]},
  "platform": {"supply_note":"全库精确计数"}
}
```

`meta` 里的键会**合并**进 profile 对应位置（浅合并），所以只写要覆盖/补充的部分。
