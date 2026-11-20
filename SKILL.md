---
name: backlink-market-audit
description: "任意外链交易平台（Backlink Marketplace）的供给与性价比调查，输入平台网址（+账号密码/已登录的 Chrome 目录），自动探测数据接口、采集站点明细、按供给量/质量/价格/流量/语言结构多维分析，产出单文件可交互 HTML 看板 + Excel，并支持多平台横向对比。适用于 Linkhouse、Adsy、collaborator.pro、Getfluence、白杨SEO 等任何卖外链位的平台。触发词：外链平台调查、外链资源分析、这个外链平台值不值得投、外链市场调研、backlink marketplace 分析、外链平台对比、给我做个外链看板、Linkhouse 外链、Adsy 外链、批量买外链怎么选平台。"
agent_created: true
---

# 外链市场调查（通用版）

给一个外链平台的网址，产出一份能直接拿去决策的看板：**这个平台有多少站、质量如何、多贵、哪个行业值得投、跟另一个平台比谁划算。**

不是只针对某一个平台。所有平台的数据都归一化到同一套字段（见 `references/data-schema.md`），所以任意平台都能套进同一个看板，也才能横向比。

---

## 分析维度（这 11 项是看板的骨架，缺一不可）

原版调查就是按这张表做的，新平台照抄：

| # | 维度 | 具体指标 | 看板位置 |
|---|---|---|---|
| 1 | **平台摸底** | 真市场入口（宣传站 vs 应用站）、登录方式、投放形式（客座/Link Insertion/广告链接/新闻提及） | 标题栏 |
| 2 | **供给量** | 全库总量；按分类的数量矩阵：总量 / 英语 / 折扣 / 各投放形式 | 供给条 + 总表 |
| 3 | **质量** | DR 中位与分档（≥10/20/30/40/50/60/70/80）、DA、Moz 垃圾分、平台「已核验」标记占比 | KPI + 散点 + 总表 |
| 4 | **价格** | 中位 / P25 / P75 / P90 / min / max；≤$25/50/100/200/500 累计占比；折扣占比；dofollow 占比 | KPI + 价格堆叠条 |
| 5 | **自然流量** | 多源取最大（Ahrefs/Semrush/GSC/Semstorm）；≥1K/5K/10K/50K/100K/500K 占比；**数据覆盖率单列**（缺失≠0） | KPI + 对比区 |
| 6 | **语言/地域结构** | 英语站占比、最大语种、国家 Top12——决定「这个池子是不是你的目标市场」 | KPI + 口径区 |
| 7 | **派生指标** | 英语占比、每 $100 得多少 DR、可调权重的综合分 | 总表 + 滑杆 |
| 8 | **价格 × 质量交叉** | ≤$50 且 DR≥30、≤$100 且 DR≥50、≤$200 且 DR≥70……「同样预算能买到什么」 | 交叉块 |
| 9 | **行业画像** | 每个分类的单点结论：量、质、价三者是否打架（例：News Portals 最贵却 DR≥50 只占 8%） | 榜单 |
| 10 | **跨平台对比** | 两/多个平台同口径比：供给规模、价格分布、质量分布、流量分布、交叉条件、垂直池规模 | 对比区 |
| 11 | **口径声明** | 哪些是精确值、哪些是抽样、缺失率多少——不写清楚这份报告就不能用 | 口径区 |

**必须给出的判断，而不只是数据**：哪类值得投、哪类直接跳过、低预算该去哪个平台、某垂直行业（crypto/finance/health）在哪个平台有池子。

---

## 六步流程

### 第 0 步：摸清平台长什么样

先打开 `linkhouse.net` 这类「品牌域名」，多半只是 WordPress 宣传页，真正的市场在 `app.xxx.com` 或 `panel.xxx.com`。判断顺序：

1. 看宣传站的「Login / Marketplace / Advertiser」按钮跳到哪；
2. `probe.mjs` 扫一遍，看有没有 JSON 接口（有 = SPA + API，最省事）；
3. 没有接口就看 HTML 是不是服务端渲染（列表直接在 DOM 里 = 只能解析 HTML，慢 10 倍，但可行）。

### 第 1 步：拿到登录态

按平台支持的方式，**优先复用已登录的 Chrome 目录**，不要在脚本里存密码：

```bash
# 启动带调试端口的 Chrome（用专用 profile，避免污染日常浏览器）
"C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9222 --remote-allow-origins=* \
  --user-data-dir="C:/Users/<you>/.workbuddy/chrome-profile-<platform>" \
  "https://app.<platform>.com/market"
```

用户在弹出的窗口里完成登录（Google 一键 / 邮箱密码 / 邀请码都行，人工做这一步最快最稳）。之后所有探测和采集都带 `--profile` 指向这个目录，免登录。

Cookie 落到 Python 侧时，**只取目标域名的 cookie**，拼成 `Cookie:` 头；`httpOnly` 的 session 项拿不到属正常，用浏览器侧发请求或直接从 CDP 读。

### 第 2 步：找出数据接口和分类体系

```bash
node scripts/probe.mjs --url "https://app.xxx.com/market" --profile "<chrome目录>"
```

输出会直接告诉你有几个候选接口、谁像列表接口（带条数和字段名）、谁像计数接口（返回一个数字）。
把字段名抄下来写 `--map`。

**同时确认三件事**（写进 `references/platform-playbook.md` 的对应平台小节）：

- **分类体系**：有几个分类、ID 是什么、名字叫什么。ID 常常不连续或有缺号，用错会**静默返回别的分类**，必须逐一对名称。
- **筛选参数**：语言、国家、投放形式、价格/DR 区间怎么传。数组参数写成 `x=1` 还是 `x[]=1` 差别很大（写错可能 500 或静默失效）。
- **计数入口**：如果平台有个「筛选后总数」的接口或 DOM 节点，它就是金矿——改一个参数就能拿精确供给量，比抽样估算准得多。Adsy 的 `#index_search_count` 就是这样，而且它随任意筛选实时变化。

### 第 3 步：采集

两种数据都要，缺一不可：

- **精确计数矩阵**：每个分类 × {总量, 英语, 折扣, 各投放形式}。便宜、准、必做。
- **站点明细抽样**：每个分类在排名区间内**等距取页**（不要取前 N 页，头部站点质量偏高，会系统性高估），落到 `sites.jsonl`。目标每类 100–300 条，全库 8,000–10,000 条够用。

单页 `per_page` 能开多大开多大（100 通常可行），单页体积过大时按字段裁剪再存。

**分页要防重复**：同一站点可能在多个分类出现，最后按域名去重。

### 第 4 步：归一化

```bash
python scripts/analyze.py sites.jsonl --platform "Platform" \
  --map maps/platform.json --counts counts.json \
  --meta meta.json -o profile.json
```

- `--map`：字段映射，没写就用内置猜测；`--peek` 可以先看有哪些字段名。
- `--counts`：平台精确计数，覆盖抽样推出的 total（**这一步不做，总量会差一个数量级**）。
- `--meta`：补 `method` / `caveats` / `supply_note`，直接进看板的口径区。

输出的 `profile.json` 就是看板唯一输入。中途换平台不用改看板。

### 第 5 步：出看板

```bash
python scripts/dashboard.py profile.json -o market-dashboard.html
```

单文件、零外链、可直接双击打开或上线。顶部 KPI、权重滑杆、质量×价格气泡散点、价格结构堆叠条、可排序总表、四个榜单、口径声明全部由数据驱动。

**交付前必须实际渲染验证一次**（历史教训：语法过 ≠ 能跑）：

```bash
"C:/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu \
  --window-size=1360,3000 --virtual-time-budget=5000 \
  --screenshot="C:/abs/path/shot.png" "file:///C:/abs/path/market-dashboard.html"
```

看截图确认：KPI 有数字、散点有气泡、表格有行、没有空白区块。文件名用 **ASCII**（中文文件名在预览面板里曾整份不显示）。

### 第 6 步：跨平台对比

每个平台各自跑第 3–5 步，然后合并：

```bash
python scripts/make_compare.py platform_a.json platform_b.json -o merged.json \
  --note "Platform B 为已核验英语口径"
python scripts/dashboard.py merged.json -o compare-dashboard.html
```

对比前**必须对齐口径**，否则结论是错的：

- 一边是「全库」、一边是「已核验+英语」→ 数量差 3 倍不是平台差距，是口径差距。
- 一边精确计数、一边抽样估算 → 在 `note` 里写清楚，看板会自动显示在对比区顶部。
- 流量口径要统一到同一个数据源（Ahrefs / Semrush 不能混），并在口径区注明覆盖率。

---

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/probe.mjs` | 打开目标页，抓出它自己的 XHR/Fetch 请求，识别列表接口/计数接口并打印字段名。零依赖（Node ≥22 内置 WebSocket）。 |
| `scripts/analyze.py` | 站点明细（jsonl/csv）→ `profile.json`；算分位数、分档占比、价格×质量交叉、语言地域结构。 |
| `scripts/dashboard.py` | `profile.json` → 单文件 HTML 看板；带 schema 校验和缺字段提示。 |
| `scripts/make_compare.py` | 多个 profile 合并成对比看板。 |
| `assets/dashboard_template.html` | 看板模板（要改样式/加板块就改这里，占位符 `{{DATA_JSON}}`）。 |

`references/data-schema.md` 是 `profile.json` 的完整字段说明，改模板前先读它。
`references/platform-playbook.md` 是各平台的具体套路（Linkhouse、Adsy 已验证的经验，含参数格式和坑）。
`README.md` 是给用户看的使用说明（要提供哪些字段、可以怎么说、交付物长什么样）——用户问「怎么用」时直接指过去。

---

## 必须守住的几条

1. **口径先于结论**。抽样估算出来的「中位价」和平台精确计数不是一回事，报告里必须分开写。看板的「口径与限制」区不是摆设。
2. **流量缺失 ≠ 流量为 0**。很多平台只给部分站点流量数据，缺失的要单独算覆盖率，不能拉低中位数。
3. **分类 ID 用错是静默失败**。不会报错，只会给你别的分类的数据。每采一个分类，抽 3 条结果人工看一眼是不是真的属于这个分类。
4. **平台分类 ≠ 站点真实主题**。平台的一级归类经常不准，要判断某站是否真写某个垂直，得抓首页/sitemap 二次验证。
5. **能精筛就别抽样**。平台支持服务端价格/DR 区间筛选的话（Adsy 支持，Linkhouse 不支持），直接拿精确数，别绕。
6. **凭据不落库**。`cookies.json` 这类文件不要跟交付物放一起，更不要进发布目录。
