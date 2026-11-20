#!/usr/bin/env node
/**
 * probe.mjs — 外链平台接口探测器（零依赖，只用 Node 内置 WebSocket + Chrome CDP）
 *
 * 作用：打开目标平台页面，抓取它自己发出的 XHR/Fetch 请求，找出
 *       ① 返回 JSON 的列表接口 ② 返回数字的计数接口，并打印字段名。
 *       这一步是"任意平台都能调查"的关键——不用猜接口，让它自己招。
 *
 * 用法:
 *   node probe.mjs --url "https://app.linkhouse.co/panel/advertiser/market"
 *   node probe.mjs --url "..." --profile "C:/Users/EDY/.workbuddy/chrome-profile-linkhouse"
 *   node probe.mjs --url "..." --click "button.next" --wait 12000
 *
 * 参数:
 *   --url       必填，要打开的页面
 *   --profile   可选，Chrome 用户数据目录（带登录态就填已有 profile，能免登录）
 *   --port      CDP 端口，默认 9333
 *   --wait      导航后等待毫秒数，默认 9000（SPA 慢的话加长）
 *   --click     可选，导航后先点某个元素再等（CSS 选择器）
 *   --json      只输出 JSON（给脚本用）
 *
 * 输出：候选接口清单 + 各自的结构摘要 + 建议
 */

import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME_CANDIDATES = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
];

// ---------- 参数 ----------
const argv = process.argv.slice(2);
const arg = (k, d = null) => {
  const i = argv.indexOf("--" + k);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : d;
};
const has = (k) => argv.includes("--" + k);

const URL_TARGET = arg("url");
const PROFILE = arg("profile");
const PORT = parseInt(arg("port", "9333"), 10);
const WAIT = parseInt(arg("wait", "9000"), 10);
const CLICK = arg("click");
const JSON_ONLY = has("json");

if (!URL_TARGET) {
  console.error("缺少 --url。用法: node probe.mjs --url <平台地址> [--profile <chrome目录>]");
  process.exit(1);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- 找 Chrome ----------
import { existsSync } from "node:fs";
let chromePath = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chromePath) {
  console.error("找不到 Chrome。请把可执行文件路径加到 CHROME_CANDIDATES。");
  process.exit(1);
}

// ---------- 启动 ----------
const userDir = PROFILE || mkdtempSync(join(tmpdir(), "probe-"));
const args = [
  `--remote-debugging-port=${PORT}`,
  "--remote-allow-origins=*",
  `--user-data-dir=${userDir}`,
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  "about:blank",
];
const child = spawn(chromePath, args, { stdio: "ignore", detached: false });

let wsUrl = null;
for (let i = 0; i < 40; i++) {
  await sleep(250);
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
    const j = await r.json();
    if (j.webSocketDebuggerUrl) { wsUrl = j.webSocketDebuggerUrl; break; }
  } catch { /* 还没起来 */ }
}
if (!wsUrl) {
  console.error("Chrome 调试端口没起来。可能已有实例占用了该端口，换个 --port 试试。");
  child.kill();
  process.exit(1);
}

// ---------- CDP 客户端 ----------
let msgId = 0;
const pending = new Map();
const ws = new WebSocket(wsUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

function send(method, params = {}, sessionId) {
  const id = ++msgId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}

const events = [];
let sessionId = null;
let lastNetAt = Date.now();

ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
    return;
  }
  if (m.method) {
    events.push({ ...m, _session: m.sessionId });
    if (m.method.startsWith("Network.")) lastNetAt = Date.now();
  }
};

// 建一个新页面并附着
const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const att = await send("Target.attachToTarget", { targetId, flatten: true });
sessionId = att.sessionId;

const on = (ev) => events.filter((e) => e.method === ev && (!e._session || e._session === sessionId));

await send("Network.enable", { maxTotalBufferSize: 200 * 1024 * 1024 }, sessionId);
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);

// 注入钩子：记录页面自己发起的请求（补充 CDP 抓不全的情况）
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `
    window.__probe = [];
    const _o = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function(m,u){ try{window.__probe.push({m:m,u:String(u)});}catch(e){} return _o.apply(this,arguments); };
    const _f = window.fetch;
    window.fetch = function(u,o){ try{window.__probe.push({m:(o&&o.method)||'GET',u:String(u&&u.url||u)});}catch(e){} return _f.apply(this,arguments); };
  `,
}, sessionId);

await send("Page.navigate", { url: URL_TARGET }, sessionId);

if (CLICK) {
  await sleep(Math.min(4000, WAIT / 2));
  await send("Runtime.evaluate", {
    expression: `(function(){var el=document.querySelector(${JSON.stringify(CLICK)});if(el){el.click();return 'clicked';}return 'not found';})()`,
  }, sessionId).catch(() => {});
}

// 等网络安静下来再收工：有请求就一直等，静默 3s 结束；上限 WAIT+8s
const navAt = Date.now();
lastNetAt = Date.now();
const deadline = Date.now() + WAIT + 8000;
while (Date.now() < deadline) {
  await sleep(400);
  if (Date.now() - lastNetAt > 3000 && Date.now() - navAt > 2500) break;
}

// ---------- 收请求 ----------
const reqs = new Map();
for (const e of on("Network.requestWillBeSent")) {
  const p = e.params;
  reqs.set(p.requestId, {
    id: p.requestId,
    url: p.request.url,
    method: p.request.method,
    type: p.type,
    postData: p.request.postData || null,
    headers: p.request.headers || {},
  });
}

const candidates = [];
for (const e of on("Network.responseReceived")) {
  const p = e.params;
  const req = reqs.get(p.requestId);
  if (!req) continue;
  const type = (p.type || "").toLowerCase();
  if (!["xhr", "fetch"].includes(type)) continue;
  const mime = (p.response.mimeType || "").toLowerCase();
  if (!mime.includes("json")) continue;
  candidates.push({ ...req, mime, status: p.response.status, size: p.response.encodedDataLength });
}

// 页面 URL 里带 hash/query 的也算
const pageReqs = candidates.filter((c) => !/\.(png|jpg|svg|css|woff2?|ico)(\?|$)/i.test(c.url));

// ---------- 取响应体、分析结构 ----------
function summarize(obj, depth = 0) {
  if (Array.isArray(obj)) {
    const first = obj.find((x) => x && typeof x === "object");
    return {
      kind: "array",
      len: obj.length,
      fields: first ? Object.keys(first).slice(0, 60) : [],
      sample: first || null,
    };
  }
  if (obj && typeof obj === "object") {
    const out = { kind: "object", keys: Object.keys(obj).slice(0, 40), parts: {} };
    for (const [k, v] of Object.entries(obj)) {
      if (Array.isArray(v)) {
        const f = v.find((x) => x && typeof x === "object");
        out.parts[k] = { type: "array", len: v.length, fields: f ? Object.keys(f).slice(0, 50) : [] };
      } else if (v && typeof v === "object") {
        out.parts[k] = { type: "object", keys: Object.keys(v).slice(0, 20) };
      } else {
        out.parts[k] = { type: typeof v, value: typeof v === "string" ? v.slice(0, 120) : v };
      }
    }
    return out;
  }
  return { kind: typeof obj, value: obj };
}

// 关键字段关键词（判断是不是"站点数据"）
const HINTS = {
  price: /price|cost|rate|报价|价格/i,
  dr: /^(dr|ahrefs_dr|domain_rating|site_dr)$/i,
  da: /^(da|moz_da|domain_authority)$/i,
  traffic: /traffic|visit|流量/i,
  category: /categor|niche|industry|segment|分类/i,
  domain: /domain|site|url|host|website/i,
  lang: /lang|language|语种/i,
  verified: /verif|checked|审核|核验/i,
};

const results = [];
let idx = 0;
for (const c of pageReqs.slice(0, 40)) {
  let body = null;
  try {
    const r = await send("Network.getResponseBody", { requestId: c.id }, sessionId);
    body = r.base64Encoded ? Buffer.from(r.body, "base64").toString("utf8") : r.body;
  } catch {
    continue;
  }
  if (!body || body.length > 8 * 1024 * 1024) continue;

  let parsed;
  try { parsed = JSON.parse(body); } catch { continue; }

  const sum = summarize(parsed);
  // 命中检测：在所有字段名里找关键词
  const allFields = [];
  if (sum.fields) allFields.push(...sum.fields);
  if (sum.parts) for (const p of Object.values(sum.parts)) if (p.fields) allFields.push(...p.fields);
  const hits = [];
  for (const [k, re] of Object.entries(HINTS)) {
    if (allFields.some((f) => re.test(f))) hits.push(k);
  }

  // 数字型响应 → 计数接口候选
  const isCount = sum.kind === "number" ||
    (sum.parts && Object.values(sum.parts).some((p) => p.type === "number" && /count|total|response|found/i.test(JSON.stringify(p))));

  const isList = (sum.kind === "array" && sum.len > 0) ||
    (sum.parts && Object.values(sum.parts).some((p) => p.type === "array" && p.len > 0 && p.fields && p.fields.length > 3));

  const score = (isList ? 3 : 0) + (isCount ? 3 : 0) + hits.length;
  idx++;
  results.push({
    idx,
    url: c.url,
    method: c.method,
    status: c.status,
    sizeKB: Math.round((c.size || body.length) / 1024),
    score,
    role: isList ? (isCount ? "列表+计数" : "列表") : isCount ? "计数" : "其他",
    hits,
    structure: sum,
    postData: c.postData ? c.postData.slice(0, 300) : null,
  });
}

results.sort((a, b) => b.score - a.score);

// 页面自己记录的请求（可能与 CDP 抓到的重复）
let injected = [];
try {
  const r = await send("Runtime.evaluate", {
    expression: "JSON.stringify((window.__probe||[]).slice(0,60))",
    returnByValue: true,
  }, sessionId);
  injected = JSON.parse(r.result.value || "[]");
} catch { /* 忽略 */ }

child.kill();

// ---------- 输出 ----------
if (JSON_ONLY) {
  console.log(JSON.stringify({ page: URL_TARGET, candidates: results, seenRequests: injected }, null, 2));
  process.exit(0);
}

const strongList = results.filter((r) => r.score >= 2);
const weakList = results.filter((r) => r.score < 2);

console.log(`\n探测页面：${URL_TARGET}`);
console.log(`抓到 XHR/Fetch JSON 响应 ${pageReqs.length} 个，其中 ${strongList.length} 个像数据接口\n`);

if (!results.length) {
  console.log("没找到像样的 JSON 接口。可能原因：");
  console.log("  · 页面需要登录：加 --profile 指向已登录的 Chrome 目录");
  console.log("  · 数据是服务端渲染的：不用找接口，直接解析 HTML");
  console.log("  · SPA 加载慢：加 --wait 15000");
  console.log("  · 需要先交互才发请求：加 --click \"选择器\"");
} else {
  if (weakList.length) {
    console.log(`另有 ${weakList.length} 个 JSON 响应不像数据接口（可能是不相关的小接口）：`);
    for (const w of weakList) console.log(`   · ${w.method} ${w.status} ${w.sizeKB}KB  ${w.url.slice(0, 110)}`);
    console.log("");
  }
  for (const r of strongList) {
    console.log(`── [${r.idx}] ${r.role}  评分 ${r.score}  ${r.method} ${r.status}  ${r.sizeKB} KB`);
    console.log(`   ${r.url}`);
    if (r.hits.length) console.log(`   命中字段：${r.hits.join(", ")}`);
    const s = r.structure;
    if (s.kind === "array") {
      console.log(`   顶层：数组 ${s.len} 条，字段 ${s.fields.length} 个`);
      console.log(`   字段：${s.fields.slice(0, 24).join(", ")}`);
    } else if (s.kind === "object") {
      console.log(`   顶层键：${s.keys.join(", ")}`);
      for (const [k, v] of Object.entries(s.parts || {})) {
        if (v.type === "array" && v.len)
          console.log(`     · ${k} → 数组[${v.len}]：${(v.fields || []).slice(0, 16).join(", ")}`);
        else if (v.type === "number")
          console.log(`     · ${k} → 数字 ${v.value}`);
      }
    } else {
      console.log(`   顶层：${s.kind} ${JSON.stringify(s.value).slice(0, 100)}`);
    }
    if (r.postData) console.log(`   请求体：${r.postData}`);
    console.log("");
  }
  if (strongList.length) {
    console.log("下一步：");
    console.log("  · 列表接口 → 改造成采集脚本，翻页 + 分页参数看响应里的 meta");
    console.log("  · 计数接口 → 只改一个筛选参数就能拿精确供给量，最省成本");
    console.log("  · 字段名拿去写 --map（见 references/data-schema.md）");
  } else {
    console.log("没有强候选接口。换个思路：");
    console.log("  · 加 --profile 带上登录态重试；或 --click 触发列表加载");
    console.log("  · 数据若是服务端渲染，直接抓 HTML 用正则/表格解析");
  }
}

writeFileSync(join(process.cwd(), "probe-result.json"), JSON.stringify({ page: URL_TARGET, candidates: results }, null, 2));
console.log(`\n完整结果已写入 probe-result.json`);
process.exit(0);
