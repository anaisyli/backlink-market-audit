# 外链平台调查 · 使用说明

给一个外链平台（卖外链位的网站）的网址，产出一份能直接拿去决策的看板：**有多少站、质量如何、多贵、哪类值得投、跟另一个平台比谁划算。**

本文件讲“怎么用”。流程细节在 [SKILL.md](SKILL.md)，字段定义在 [references/data-schema.md](references/data-schema.md)，已接入平台的接口与坑在 [references/platform-playbook.md](references/platform-playbook.md)。

---

## 一、你要给什么

只有 **1 个必填**，其余选填但会明显影响结论质量。

| 字段 | 必填 | 举例 | 不给会怎样 |
|---|---|---|---|
| **平台网址**（或已有的站点明细文件） | ✅ | `https://example-marketplace.com`、`sites.csv` | 没法开始 |
| 登录方式 | ○ | 谷歌账号一键 / 邮箱密码 / 邀请码 / 不用登录 | 先探路，需要登录时再问你 |
| 目标行业 / 关键词 | ○ | `crypto`、`finance`、`工业设备` | 只出全库画像，说不出“你要的那一类值不值得投” |
| 单条预算 | ○ | `≤$50`、`$100–200` | 交叉分析按默认档位（50/100/200） |
| 要不要对比 | ○ | `跟 B 平台比`、`跟上次那份比` | 不生成对比区 |
| 交付格式 | ○ | HTML 看板 / 加一份 Excel | 默认单文件 HTML 看板 |
| 币种 / 报告语言 | ○ | `€`、英文报告 | 默认 `$` + 中文 |

### 账号密码怎么处理

**不要发密码。** 会起一个专用浏览器窗口（独立的用户目录，不碰你的日常浏览器），**你自己在窗口里登录一次**，登录态留在这个目录里，之后的采集都复用它。

- 下次调查同一平台，说“用上次那个登录态”即可。
- 遇到验证码 / 人机验证，由你在窗口里完成。
- 浏览器用户目录、cookie、接口探测结果不会放进交付目录，也不会进任何发布包。

---

## 二、怎么说（可直接复制）

**最省事的一句话**

```
用 $backlink-market-audit 调查一下 https://xxx.com 这个外链平台的资源，出个看板
```

**完整版（推荐，一次说清）**

```
用 $backlink-market-audit 调查这个外链平台：
- 网址：https://app.xxx.com/market
- 登录：邮箱密码，我自己在弹窗里登
- 重点行业：crypto 和 finance
- 预算：单条不超过 $150
- 对比：跟 https://yyy.com 比谁划算
- 交付：HTML 看板 + Excel
```

**双平台只要结论**

```
A（网址…）和 B（网址…）哪个更值得投？我做 XX 行业，单条 ≤$100，给一份对比看板，直接说低预算选哪个。
```

**数据已经有了，只要看板**

```
这是站点明细 <文件路径>，平台叫 XXX，全库总量 N，直接出看板。
```

**只看某个垂直行业**

```
平台网址…，我只关心 crypto 类站点有多少、多贵、DR 够不够。不用全库报告，给数字和结论。
```

**更新旧报告**

```
上次那份 XXX 看板是 9 月的，重新采一遍，跟上次对比，标出变化。
```

最影响结果的三件事：**说清判断什么**（全库画像 / 某垂直池子 / 两平台谁划算，采集路径不同）、**给预算**（否则只能给分布，给不出“选哪档”）、**一开始就说要不要对比**（对比要多采一个平台，成本翻倍）。

---

## 三、拿到之后会做什么

| 步骤 | 做什么 | 你要做什么 |
|---|---|---|
| 0 摸入口 | 分辨宣传站 vs 真实市场（市场常在 `app.` / `panel.` 子域） | — |
| 1 登录 | 起专用浏览器窗口 | **在窗口里登录一次**（约 1 分钟） |
| 2 探接口 | 抓页面自己的 XHR/Fetch，找列表接口和计数接口 | — |
| 3 摸分类 | 确认分类数量/ID/名称、筛选参数格式、计数入口 | — |
| 4 计数 | 逐分类拿精确供给量 | — |
| 5 抽样 | 每分类等距取页，全库约 8,000–10,000 条 | — |
| 6 分析 | 归一化 → 分位数 / 分档 / 交叉 / 语种结构 | — |
| 7 出看板 | 生成单文件 HTML（可选 Excel），截图自查后交付 | 看一眼，说哪里要改 |

大致耗时：有 JSON 接口的平台 **30–60 分钟**；只能“改筛选 → 读页面总数”的平台每条要数十秒，**1–3 小时**，放后台跑；纯人工询价的平台做不了全库，会先告诉你。

---

## 四、交付物

```
<platform>-audit/
├── index.html          看板，双击就能开，单文件无外部依赖
├── profile.json        归一化数据（看板唯一输入，可手改后重渲染）
├── sites.jsonl         站点明细原始数据（不对外发布）
├── counts.json         平台精确计数（分类 × 总量/英语/折扣/投放形式）
├── market-audit.xlsx   （可选）概览 / 分类 / 交叉 / 结构 / 对比 / 口径
└── notes.md            口径说明 + 平台接口/参数/坑
```

看板板块：顶部 KPI · 同样预算能买到什么（价格×质量交叉）+ 语种/国家结构 · 权重滑杆 · 质量×价格气泡散点 · 价格结构堆叠条 · 各类供给量 · 可排序总表 · 榜单 · 跨平台对比区（有对比时）· 口径与限制。

样品：[assets/sample-output.html](assets/sample-output.html)（一份真实平台调查）和对应数据 [assets/sample-profile.json](assets/sample-profile.json)。

---

## 五、看板怎么读（5 分钟）

1. **先看口径区**：抽样估算的中位价和平台精确计数不是一回事；口径不对等时，对比区数字不能直接相减。
2. **看“同样预算能买到什么”**：`≤$50 且 DR≥30` 占多少，直接回答“我的预算能买到什么质量”。
3. **看语种/国家**：英语站占比低、国家集中在非目标市场，量再大也不是你的池子。
4. **拖滑杆**：把权重从“便宜”往“权威”拖，总表和散点颜色会重排。
5. **`每 $100 得 DR` 只能当参考**：它天然偏向便宜但低质的分类。
6. **`total` 和 `sample_n` 一起看**：前者是供给量，后者是用来估分位数的样本数；样本太少的分类结论可信度低。

---

## 六、口径红线

| 红线 | 说明 |
|---|---|
| 流量缺失 ≠ 流量为 0 | 很多平台只有部分站有流量数据。缺失单列覆盖率，不进中位数（混进去能把中位数拉低一个数量级）。 |
| 分类 ID 用错是静默失败 | 不报错，只返回别的分类的数据。每采一类抽 3 条核对。 |
| 平台分类 ≠ 站点真实主题 | 要确认某站真写某个垂直，抓首页 / sitemap 二次验证。 |
| 精确 vs 抽样不能混着比 | 一边“全库”一边“已核验+英语”，数量差几倍是口径差，不是平台差。 |
| 能服务端精筛就别抽样 | 平台支持价格/DR 区间筛选时直接拿精确计数。 |
| 凭据和原始数据不进发布目录 | 只发布看板 HTML（和 Excel）。 |

---

## 七、不用对话，手动跑

```bash
cd <skill目录>

# 1) 探接口（零依赖，Node ≥ 22）
node scripts/probe.mjs --url "https://app.xxx.com/market" --attach 9222                 # 连已登录、带调试端口的浏览器
node scripts/probe.mjs --url "https://app.xxx.com/market" --profile "<专用浏览器目录>"  # 或让脚本自己起无头浏览器
#   可选：--wait 15000（SPA 慢）/ --click "button.next"（要交互才发请求）/ --headed / --out <文件>

# 2) 先看字段名和内置猜测的映射
python scripts/analyze.py sites.jsonl --peek

# 3) 归一化（--map 只写猜错的字段；--counts 不给，总量只能报抽样数）
python scripts/analyze.py sites.jsonl --platform "Platform" --entry "app.xxx.com/market" \
  --map maps/platform.json --counts counts.json --meta meta.json -o profile.json
#   可选：--currency "€"  --top-segments 20  --bands bands.json  --date 2026-11-20

# 4) 出看板 / Excel（--strict：有结构性错误就退出）
python scripts/dashboard.py profile.json -o market-dashboard.html
python scripts/export_xlsx.py profile.json -o market-audit.xlsx

# 5) 跨平台对比
python scripts/make_compare.py a.json b.json -o merged.json --label "Platform B" --note "B 为已核验+英语口径"
python scripts/dashboard.py merged.json -o compare.html

# 6) 自测
python -m unittest discover -s tests -v
```

**交付前必须截图看一眼**（语法通过 ≠ 能显示）：

```bash
chrome --headless=new --disable-gpu \
  --window-size=1360,3400 --virtual-time-budget=5000 \
  --screenshot="<abs>/shot.png" "file:///<abs>/market-dashboard.html"
```

输出文件名用 ASCII，部分预览工具对非 ASCII 文件名支持不好。

---

## 八、目录结构

```
backlink-market-audit/
├── SKILL.md                     给 agent 的流程说明（11 个分析维度 + 六步法）
├── README.md                    本文件
├── agents/openai.yaml           Skill 界面元数据
├── scripts/
│   ├── probe.mjs                探接口：找列表/计数接口，打印字段名
│   ├── analyze.py               站点明细 → profile.json
│   ├── dashboard.py             profile.json → 单文件 HTML
│   ├── export_xlsx.py           profile.json → Excel（零依赖）
│   └── make_compare.py          多平台合并
├── assets/
│   ├── dashboard_template.html  看板模板（占位符 {{DATA_JSON}}）
│   ├── sample-output.html       样例成品
│   └── sample-profile.json      样例 profile
├── maps/                        已验证平台的字段映射 / 口径说明示例
├── references/
│   ├── data-schema.md           profile.json 完整字段规范
│   └── platform-playbook.md     平台类型判定 + 已接入平台的接口/参数/分类/坑
└── tests/                       端到端自测（合成数据，不联网）
```

**接新平台时**：把“入口 / 接口 / 参数 / 分类 / 坑”补进 `references/platform-playbook.md`，字段映射存成 `maps/<platform>.json`。

---

## 九、常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 看板全空、KPI 是 0 | 多半是登录态失效，市场页跳到了登录页。重新在专用窗口登录一次。 |
| probe 报“调试端口没起来” | 该浏览器目录正被另一个窗口占用。关掉它，或改用 `--attach <端口>`。 |
| 只采到 20–30 个站 | 分页参数没生效。查 `per_page` 上限和 `page` / `offset` 写法。 |
| 总量比预期小很多 | 没给 `--counts`，总量只能报抽样去重域名数。 |
| 某个分类数据明显不像它 | 分类 ID 错了（静默失败）。抽 3 条核对名称。 |
| 对比区数字差好几倍 | 口径不对等。看 `--note` 是否写清，别直接下结论。 |
| 看板打不开 / 预览空白 | 文件名改成 ASCII；确认是单文件、没引用外部 CDN。 |
| 想上线分享 | 只发布 HTML；`sites.jsonl`、cookie、浏览器目录、`probe-result.json` 都不要带。 |

---

## 十、做不到什么

- **不绕过登录、付费墙或验证码**。只拿你账号权限内能看到的数据。
- **不判断站点真实内容质量**。DR/流量/垃圾分是第三方指标；平台分类常不准。
- **纯人工询价平台做不了全库**，只能小样本核对。
- **不做投放后效果追踪**。只回答“买之前值不值”。
- **数据是采集时的快照**。库存变化快，超过一两个月的报告要重采。
