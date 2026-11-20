# 平台实战手册

各平台的具体取数套路。新平台照「通用判定流程」走一遍，把结果补到下面。

---

## 先判断平台属于哪一类

| 类型 | 特征 | 取数方式 | 成本 |
|---|---|---|---|
| **A. SPA + JSON API** | 打开市场页有 `api.xxx.com` / `/api/` 请求 | `probe.mjs` 找到接口，直连翻页 | 最低，全量可行 |
| **B. 有"筛选后总数"计数** | 任意筛选后页面上的数字会变 | 改参数读计数，拿精确供给量 | 极低，几十次请求覆盖全部分类 |
| **C. 服务端渲染列表** | 列表直接躺在 HTML 里 | 解析 HTML（表格/卡片），翻页 URL | 中，慢 10 倍 |
| **D. 纯人工/表单询价** | 没有公开列表，要发询价单 | 只能小样本人工核对，做不了全库 | 很高，先劝退用户 |

判断方法：`node scripts/probe.mjs --url <市场页> --attach 9222`（或先关掉登录窗口再传 `--profile <已登录目录>`），看输出的候选接口。
有列表接口 → A；有数字型接口 → B；都没有但页面能看到列表 → C。

**附加属性：检索额度（会直接掐死采集计划）**

A/B 型平台也可能把「检索」当计费资源——免费或未开户账号只有几次到一百次目录检索，用完后目录整页变
「Search limit reached」，API 对目录接口一律 `403 Access Denied.`（`/api/thematics` 这类元数据接口通常还活着）。

**这不是封号，也不会随时间自动恢复**：实测响应头 `remaining` 一直是满值、`reset` 为负，说明限流窗口早过期，
真正卡住的是账号角色（如出现类似 `*_CATALOG_SEARCH_LIMITED` 的权限标记）→ 要充值 / 完成开户 / 下首单才解除。

识别信号（开工 5 分钟内查完）：① 目录接口响应头带 `ratelimit-limit` / `x-ratelimit-remaining`；
② 页面出现 "Search limit reached" / "search credit"；③ 账号 `state` 为 `uncompleted`、`tags` 含 `advertiser_onboarding`。

**登录是前置条件**。绝大多数平台的市场页要登录才有数据，先按 SKILL.md 第 1 步起一个带调试端口的专用 Chrome，让人工完成登录。

---

## Linkhouse（已验证，2026-09）

**入口**：`linkhouse.net` 是 WordPress 宣传站，**真市场在 `app.linkhouse.co`**
→ `https://app.linkhouse.co/panel/advertiser/market`（未登录 302 到 `/login`）

**登录**：邮箱密码（带 Cloudflare Turnstile）或 Google 一键登录。Google 登录必须人工点。

**接口**：

| 用途 | 路径 |
|---|---|
| 列表 | `GET /api/search-market-refactored` |
| 计数 | `GET /api/search-market-count`（加 `only_count=1`，返回 `{"response": 96330}`） |

固定参数：`sort=priority&by=desc&per_page=100&spring25_filters_enabled=1&offer_type=&sale=0`

**已验证可用的筛选参数**（2026-09 实测）：

- `page_category[]=<id>`、`lang[]=GB`、`country[]=US`、`offer_type[]=1`、`sale=1`、`multiple=<关键词>`
- **必须用数组形式**：写成 `page_category=39` 会 **HTTP 500**
- `multiple=crypto` 这类自由搜索可用

**分类 ID**：37 个，**ID 不连续且没有 13**，用错会静默返回别的分类。权威表：

```
1 Local portals        2 General topics        3 Business, Company, Ecommerce
4 Animals              5 IT, Computers, GSM, New technologies
6 Family, Child, Pregnancy, Parenting
7 Household appliances, Home, Interiors        8 Beauty, Cosmetics
9 Health, Medicine     10 Female               11 Wedding
12 Finance, Loans, Insurance                   14 Entertainment, Lifestyle
15 Education, Science, Training                16 Construction, Gardening
17 Sport, Fitness, Sports clubs                18 Diet, Food, Culinary, Weight loss
19 Tourism, Holidays, Travel                   20 Transport, Logistics
21 Photography, Video  22 Automotive           23 Culture, Art, Film, Music
24 Fashion             25 Work                 26 Economy, Industry
27 Law, Taxes          28 Games                29 Marketing, Advertising
30 Man                 31 Ecology, Agriculture, Forestry
32 Catering, Gastronomy                        33 Religion
34 Other               35 Energy, Photovoltaics, RES
36 Real Estate         38 News Portals         39 Crypto
```

**已知缺口**：min-max 型筛选（DR/价格/流量区间）参数格式没试出来。
`dr_min/dr_max`、`dr[from]/dr[to]` 全部无效，后者还会让请求挂死。**只能拉样本后本地筛。**

**记录里的可用字段**：`domain` `lang` `country` `page_category` `src_cat_name` `DR` `DA` `AS` `TF` `CF`
`spam` `gsc` `ahrefs_traf` `semrush` `semstorm` `ref_domains` `verified` `dofollow` `price_min` `lowest_price`
`offer_types` `tags` `html_pages`
报价口径：站点最低可购价 = `lowest_price`（= offer 列表里 `price_for_advertisers` 的最小值）。

**该平台画像**（供对照）：全库 96,330 站，英语仅 33.6%（波兰语 34.4%，基本盘在中东欧），
DR 中位 22，价格中位 $89，平台标记已核验仅 3.2%。

---

## Adsy（已验证，2026-10）

**入口**：`cp.adsy.com/marketer/platform`

**取数原理（关键）**：`#index_search_count` 是**唯一计数入口**，且随**任意筛选条件实时更新**。

- 该元素**不在原始 HTML 里**，是前端渲染出来的。用同步 XHR 直接请求 `/marketer/platform...` 拿不到计数；
  带 `X-PJAX` / `X-Requested-With` 头会返回 **401**。所以只能「导航 → 读 DOM」。
- 代价：**约 1 分钟/条**（导航 + 等前端渲染）。批量查询必须后台跑，别指望秒回。

**可用筛选参数**（服务端精确筛选，这正是 Linkhouse 缺的能力）：

```
SiteSearch[verified]=1          SiteSearch[site_language_id]=5     (5 = 英语)
SiteSearch[siteCategory][]=<id> SiteSearch[sitePriceMin/Max]
SiteSearch[siteDrMin/Max]       SiteSearch[siteDaMin/Max]
SiteSearch[siteAsMin/Max]       SiteSearch[semrush_ref_domains]
SiteSearch[organic_traffic]     SiteSearch[semrush_total_traffic]
SiteSearch[keyword]
```

**加速**：URL 追加 `&per-page=10`（默认 30 张重卡片/页），加载明显变快。

**坑**：

- `SiteSearch[keyword]` 对行业词（winch/hoist/crane）**完全无效**，返回数值几乎一致 = 噪声，别用。
- 巨型 UGC 平台（sites.google / reddit / medium）RD 几十万到千万、无行业栏目，必须整类剔除。
- **链接农场判据**：价格恰为 `$15.75` 且自然流量 ≈ 0。**不要加 DR 条件**——实测站群 DR 能到 61–77。

**该平台画像**：展示 150k+，已核验 103,922，英语 52,286，已核验+英语 48,404；
≤$50 占 54.0%，DR 中位 18。低预算段比 Linkhouse 强得多（≤$50 且 DR≥30：Adsy 17.3% vs LH 4.4%）。

---

## 典型模式：带检索额度的 SPA + REST API 平台

很多现代外链市场采用“宣传站 + `app.` React/Vue SPA + 独立 REST API”架构，同时把目录检索当成计费资源。接这类平台重点注意以下几项：

- **登录**：由用户在专用浏览器窗口手动完成（页面有 cookie 同意条时先关掉再操作）。不要写脚本自动填密码。
- **鉴权与请求上下文**：除 `Authorization: Bearer <token>` 外，常额外校验前端固定的 client 头或 locale 头，缺一即 403。优先在已登录浏览器页面上下文内发 `fetch`（经由 CDP），避免把 token 落盘到宿主机。
- **元数据先查，不耗目录额度**：先查用户信息接口（确认账号状态、角色与额度标记）和分类元数据接口（确认分类树与**拒收类目**），这类接口通常不扣目录检索额度。
- **嵌套字段**：若列表接口把指标嵌在子对象里（如 `channel.metrics.domainRating`、`minPrice.amount`），可直接在 `analyze.py --map` 中写点号路径，无需单独写脚本拍平。

### 三个常见硬限制

1. **检索额度（最要命）**：目录检索按次计费。额度耗尽后目录接口一律 `403 Access Denied`，页面显示 `"Search limit reached"`。
   **额度以响应头 `ratelimit-limit` 实测为准**，别信第三方二手文章里的数字；解除靠充值 / 完成开户 / 下首单，不会随时间自动恢复。因此务必**先抽样、计数放最后**。
2. **分页 / 总量硬顶**：部分 API 把 `totalItems` 恒封顶在固定上限（如 `10,000`），翻到上限之外直接报错。此时全库总量只能标为「可检索上限」，不能当真实全库总量报。
3. **503 抖动**：短时间连发同一接口可能随机返回 503（响应头正常），做退避重试即可，别误判为封号。

### 拒收类目提前排查

部分平台在分类元数据里会明确标出拒收类目（如 `type=refused`，常见包括 Adult、Gambling、CBD/Cannabis、Tobacco、Alcohol、Trading、Cryptocurrencies、Politics 等）。开工前先核对用户目标行业是否在拒收清单里，避免白耗一轮额度。

---

## 新平台接入清单

按顺序做，每步都留记录（写进本文件的平台小节）：

1. `probe.mjs` 探接口 → 判定 A/B/C/D 类型
2. 确认分类体系：数量、ID、名字，**抽 3 条人工核对 ID 是否对得上名字**
3. 确认筛选参数格式：数组还是标量、大小写、区间怎么传
4. 找一个分类跑通 1 页，确认字段齐全（价格/DR/流量/语言至少各有其一），并确认是否有**检索额度/翻页上限**、列表响应是否自带 `total`
5. 采集顺序：
   - **无检索额度**：先跑全量计数矩阵（便宜先跑），再分层抽样（等距取页，别取头部）
   - **有检索额度**：**先抽样，计数放最后**（顺手从列表响应收 `total`，剩余额度再补核心计数，避免额度耗尽却没拿到明细样本）
6. `analyze.py --peek` 看字段名 → 写 `--map`
7. `analyze.py` → `dashboard.py` → 截图验证

**每接一个新平台，把「接口 / 参数 / 分类 / 坑」四段补到本文件对应小节**，下一个平台能省一半时间。
