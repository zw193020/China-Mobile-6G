/* 中国移动资费监控面板 - 前端逻辑（支持远程实时数据源 + 本地快照兜底） */
"use strict";
let DATA = "./data/";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
));
const cache = {};

const FETCH_TIMEOUT = 20000; // 20s 超时，避免弱网下无限“加载中”卡死
function fetchTimeout(url, init) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT);
  return fetch(url, Object.assign({}, init || {}, { signal: ctrl.signal }))
    .catch((e) => {
      if (e && e.name === "AbortError") throw new Error("加载超时，请检查网络后重试");
      throw e;
    })
    .finally(() => clearTimeout(t));
}

function loadJson(file) {
  if (cache[file]) return Promise.resolve(cache[file]);
  return fetchTimeout(DATA + file)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { cache[file] = j; return j; });
}

/* ---------- 远程实时数据源 ----------
   网站自带的 data/ 是部署时的快照。若在「关于」页填写了 GitHub 仓库（user/repo），
   页面会先探测该仓库上的最新数据（jsDelivr / GitHub raw），谁更新用谁；
   两者都取不到时自动回退本地快照，保证任何网络环境都能打开。 */
const REPO_KEY = "trf_github_repo";
let DATA_SRC = "local";

function repoOf() {
  let v = "";
  try { v = localStorage.getItem(REPO_KEY) || ""; } catch (e) {}
  if (!v && window.DEFAULT_REPO) v = window.DEFAULT_REPO;
  return String(v).trim().replace(/^https?:\/\/github\.com\//i, "").replace(/\/$/, "");
}
function remoteBases() {
  const r = repoOf();
  if (!r || r.indexOf("/") < 0) return [];
  return [
    "https://cdn.jsdelivr.net/gh/" + r + "@main/site/data/",
    "https://raw.githubusercontent.com/" + r + "/main/site/data/"
  ];
}
let _baseReady = null;
function initDataBase() {
  if (_baseReady) return _baseReady;
  const bases = remoteBases();
  if (!bases.length) { DATA_SRC = "local"; _baseReady = Promise.resolve(); return _baseReady; }
  const probe = Promise.all(bases.map((b) =>
    fetchTimeout(b + "latest.json", { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((j) => ({ base: b, updated: j.updated || "" }))
      .catch(() => null)
  ));
  // 远程探测最多等 8 秒，超时直接用本地快照，避免弱网下首屏卡住
  _baseReady = Promise.race([
    probe,
    new Promise((res) => setTimeout(() => res(null), 8000))
  ]).then((res) => {
    const ok = res.filter(Boolean);
    if (!ok.length) { DATA_SRC = "local"; return; }
    ok.sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
    DATA = ok[0].base;
    delete cache["latest.json"];
    DATA_SRC = "remote";
    return;
  }).catch(() => { DATA_SRC = "local"; });
  return _baseReady;
}

/* ---------- 板块索引：SECTIONS / 省份列表（来自 latest.json） ---------- */
let SECTIONS = [];        // [{section,name,total,updated}]
let DEF_SECTION = "hunan"; // 默认省份
const PROV_KEY = "trf_selected_prov";

function provList() {
  return SECTIONS.filter((s) => s.section !== "quanguo");
}
function secName(sec) {
  const s = SECTIONS.find((x) => x.section === sec);
  return s ? s.name : sec;
}

/* 加载 latest.json 并填充省份下拉（幂等，只填一次） */
let sectorsLoaded = null;
function ensureSections() {
  if (sectorsLoaded) return sectorsLoaded;
  sectorsLoaded = loadJson("latest.json").then((d) => {
    SECTIONS = d.sections || [];
    DEF_SECTION = d.default || DEF_SECTION;
    fillProvSelects();
    return d;
  }).catch(() => {});
  return sectorsLoaded;
}

function fillProvSelects() {
  const provEl = $("pProv");
  const oProv = $("oProv");
  const opts = provList().map((s) => '<option value="' + esc(s.section) + '">' + esc(s.name) + "</option>").join("");
  if (provEl && provEl.options.length === 0) {
    provEl.innerHTML = opts;
    // 记忆上次选择，否则默认省份
    let mem = "";
    try { mem = localStorage.getItem(PROV_KEY) || ""; } catch (e) {}
    provEl.value = provList().some((s) => s.section === mem) ? mem : DEF_SECTION;
    provEl.addEventListener("change", () => {
      const v = provEl.value;
      try { localStorage.setItem(PROV_KEY, v); } catch (e) {}
      if (oProv && oProv.options.length) oProv.value = v;  // 同步总览页省份面板
      listState.prov = null;         // 清空缓存重载
      renderList("prov");
    });
  }
  if (oProv && oProv.options.length === 0) {
    oProv.innerHTML = opts;
    let mem = "";
    try { mem = localStorage.getItem(PROV_KEY) || ""; } catch (e) {}
    oProv.value = provList().some((s) => s.section === mem) ? mem : DEF_SECTION;
    oProv.addEventListener("change", () => {
      const v = oProv.value;
      try { localStorage.setItem(PROV_KEY, v); } catch (e) {}
      if (provEl && provEl.options.length) provEl.value = v;  // 同步省份 tab 下拉
      renderProvPanel();            // 总览页省份统计联动
    });
  }
  const hfEl = $("hProvFilter");
  if (hfEl && hfEl.options.length === 0) {
    let hopts = '<option value="">全部省份</option>';
    hopts += provList().map((s) => '<option value="' + esc(s.section) + '">' + esc(s.name) + "</option>").join("");
    hfEl.innerHTML = hopts;
    hfEl.addEventListener("change", () => renderHistory());
  }
}

/* ---------- Tab 切换（支持 hash 直达，如 #history / #prov） ---------- */
const TAB_SHOWN = {};
function goTab(v) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
  $("view-" + v).classList.add("active");
  if (TAB_SHOWN[v]) return;
  TAB_SHOWN[v] = true;
  if (v === "overview") renderOverview();
  else if (v === "quanguo") renderList("quanguo");
  else if (v === "prov") { ensureSections(); renderList("prov"); }
  else if (v === "history") { ensureSections(); renderHistory(); }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    goTab(tab.dataset.view);
    try { history.replaceState(null, "", "#" + tab.dataset.view); } catch (e) {}
  });
});

/* ---------- 数据总览 ---------- */
let LATEST = null; // 最近一次 latest.json（省份面板联动直接读内存，不重复请求）
function renderOverview() {
  loadJson("latest.json").then((d) => {
    LATEST = d;
    SECTIONS = d.sections || [];
    DEF_SECTION = d.default || DEF_SECTION;
    fillProvSelects();
    $("stTotal").textContent = (d.quanguo_total == null) ? "-" : fmt(d.quanguo_total);
    $("stAllProv").textContent = (d.prov_total == null) ? "-" : fmt(d.prov_total);
    $("updateTime").textContent = "更新于 " + (d.updated || "未知");
    $("updateTime").title = (DATA_SRC === "remote")
      ? "来自 GitHub 仓库实时数据" : "来自站点自带数据快照";
    document.title = "中国移动资费监控 · 更新于 " + (d.updated || "");
    renderProvPanel();   // 顶部个人/政企卡 + 省份面板统一按所选省份联动（不必再渲染全网口径）
  }).catch((e) => {
    $("stTotal").textContent = "加载失败";
    $("updateTime").textContent = "加载失败";
    $("distBars").innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
}
function fmt(n) { return (n === undefined || n === null) ? "-" : n.toLocaleString("zh-CN"); }
function confStat(el, cur) {
  el.innerHTML = (cur == null) ? "-" : fmt(cur);
}

/* 总览页顶部「个人/政企」卡 + 「省份资费统计」面板：全部随 oProv 下拉切换实时联动 */
function renderProvPanel() {
  const provEl = $("oProv");
  if (!provEl) return;
  if (!provEl.options.length) fillProvSelects();
  const sec = provEl.value || DEF_SECTION;
  const st = (LATEST && LATEST.prov_stats) ? (LATEST.prov_stats[sec] || null) : null;
  const name = secName(sec);
  $("opLabel").textContent = name + "资费总数";
  $("stQuanguoLabel").textContent = name + "个人资费";
  $("stGqLabel").textContent = name + "政企资费";
  $("distDesc").textContent = name + "口径 · 六大类分布";
  if (!st) {
    confStat($("opTotal"), null);
    confStat($("stQuanguo"), null);
    confStat($("stGq"), null);
    $("distBars").innerHTML = '<div class="empty">暂无该省统计</div>';
    return;
  }
  confStat($("opTotal"), st.total);
  confStat($("stQuanguo"), st.personal);
  confStat($("stGq"), st.gq);
  renderBarsBox($("distBars"), st.dist || {});
}

function renderBarsBox(box, dist) {
  if (!box) return;
  const labels = ["个人资费·套餐", "个人资费·加装包", "个人资费·营销活动", "政企资费·套餐", "政企资费·加装包", "政企资费·营销活动"];
  const rows = [];
  let max = 1;
  labels.forEach((lab) => {
    const [own, type] = lab.split("·");
    const n = ((dist[own] || {})[type]) || 0;
    rows.push({ lab, n }); if (n > max) max = n;
  });
  if (!rows.some((r) => r.n > 0)) {
    box.innerHTML = '<div class="empty">暂无分类统计</div>';
    return;
  }
  box.innerHTML = rows.map((r, i) => (
    '<div class="bar-row"><span>' + r.lab + '</span>' +
    '<div class="bar-track"><div class="bar-fill' + (i > 2 ? " alt" : "") + '" style="width:' + Math.max((r.n / max) * 100, 2) + '%"></div></div>' +
    '<span class="bar-num">' + fmt(r.n) + "</span></div>"
  )).join("");
}

/* ---------- 列表（全国 / 省份） ---------- */
const PAGE_SIZE = 20;
const listState = {};    // section -> {items,page,q,own,type}
function liveSec() {
  const el = document.getElementById("pProv");
  return (el && el.value) || DEF_SECTION;
}
function getSt(section) {
  if (!listState[section]) listState[section] = { items: null, page: 1, q: "", own: "", type: "", sort: null, order: null };
  return listState[section];
}
function domMap(section) {
  if (section === "quanguo") {
    return { list: "qList", pager: "qPager", cnt: "qCount", search: "qSearch", own: "qOwn", type: "qType", reload: "qReload" };
  }
  return { list: "pList", pager: "pPager", cnt: "pCount", search: "pSearch", own: null, type: "pType", reload: "pReload" };
}

function renderList(section) {
  // "prov" 为省份 tab 的占位 section，需解析为下拉当前所选省份（data/ 下按省份文件名存储）
  const rawKey = section; // 原始视图键：quanguo / prov（用于定位排序条）
  if (section === "prov") { section = ((document.getElementById("pProv") || {}).value || "hunan"); }
  if (section !== "quanguo") { ensureSections(); }
  const st = getSt(section);
  const idm = domMap(section);
  const listEl = $(idm.list);
  const file = section === "quanguo" ? "quanguo.json" : section + ".json";
  const label = section === "quanguo" ? "全国" : (secName(section) || section);
  const qEl = $(idm.search);
  if (!st.items) {
    listEl.innerHTML = '<div class="loading">加载' + esc(label) + "资费数据（约 2MB，请稍候）…</div>";
  }
  loadJson(file).then((d) => {
    st.items = d.items || [];
    $("updateTime").textContent = "更新于 " + (d.timestamp || "未知");
    if (section !== "quanguo") { $("pProv").value = (provList().some((s) => s.section === section) ? section : $("pProv").value); }
    drawList(section);
  }).catch((e) => {
    listEl.innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
  // 绑定筛选控件（同一 DOM 只绑一次；省份切换不重复绑定，仅更新数据缓存）
  if (!qEl.dataset.bound) {
    const secOf = () => (rawKey === "quanguo" ? "quanguo" : liveSec());
    const stOf = () => getSt(secOf());
    qEl.dataset.bound = "1";
    qEl.addEventListener("input", () => { const st = stOf(); st.q = qEl.value.trim().toLowerCase(); st.page = 1; drawList(secOf()); });
    const ownEl = idm.own ? $(idm.own) : null;
    const typeEl = $(idm.type);
    if (ownEl) ownEl.addEventListener("change", () => { const st = stOf(); st.own = ownEl.value; st.page = 1; drawList(secOf()); });
    if (typeEl) typeEl.addEventListener("change", () => { const st = stOf(); st.type = typeEl.value; st.page = 1; drawList(secOf()); });
    $(idm.reload).addEventListener("click", () => { const st = stOf(); st.items = null; renderList(secOf()); });
    setupSortBar(rawKey);
  }
}

/* ---------- 资费排序（最新上架 / 价格 / 方向） ---------- */
function timeOf(it) {
  const f = it.fields || {};
  const s = f["上线日期"] || "";
  if (s) {
    const m = s.match(/20\d{2}\D+(\d{1,2})\D+(\d{1,2})/);
    if (m) { const y = s.match(/20\d{2}/)[0]; return new Date(+y, (+m[1]) - 1, +m[2]).getTime(); }
  }
  const vp = f["有效期限"] || "";
  const vm = vp.match(/20\d{2}/);
  return vm ? new Date(+vm[0], 0, 1).getTime() : 0;
}
function priceOf(it) {
  const f = it.fields || {};
  const raw = f["资费标准"] || "";
  const m = String(raw).match(/\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : 0;
}
function sortFiltered(arr, st) {
  const dir = (st.order == null ? -1 : st.order) < 0 ? -1 : 1; // 默认降序
  arr.sort(function (a, b) {
    if (!st.sort) return 0;
    const av = st.sort === "price" ? priceOf(a) : timeOf(a);
    const bv = st.sort === "price" ? priceOf(b) : timeOf(b);
    if (av === 0 && bv !== 0) return 1;  // 无法解析的排后
    if (bv === 0 && av !== 0) return -1;
    if (av === bv) return 0;
    return (av > bv ? 1 : -1) * dir;
  });
}
function setupSortBar(rawKey) {
  if (rawKey !== "quanguo" && rawKey !== "prov") return;
  const bar = document.getElementById((rawKey === "quanguo" ? "q" : "p") + "SortBar");
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  bar.querySelectorAll(".sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sec = rawKey === "quanguo" ? "quanguo" : liveSec();
      const st = getSt(sec);
      const sort = btn.dataset.sort;
      if (sort === "dir") { st.order = (st.order == null ? -1 : st.order) * -1; }
      else { st.sort = sort; st.order = sort === "price" ? 1 : -1; }
      st.page = 1;
      syncSortUI(bar, st);
      drawList(sec);
    });
  });
  syncSortUI(bar, getSt(rawKey === "quanguo" ? "quanguo" : liveSec()));
}
function syncSortUI(bar, st) {
  if (!bar) return;
  bar.querySelectorAll(".sort-btn[data-sort]").forEach((b) => {
    const s = b.dataset.sort;
    if (s !== "dir") b.classList.toggle("active", !!st.sort && st.sort === s);
  });
  const d = bar.querySelector('.sort-btn[data-sort="dir"]');
  if (d) d.textContent = (st.order == null ? -1 : st.order) < 0 ? "降序 ↓" : "升序 ↑";
}

function filterItems(st) {
  const src = st.items || [];
  const out = [];
  for (const it of src) {
    if (st.own && (it.fields && it.fields["归属"]) !== st.own) continue;
    if (st.type && (it.fields && it.fields["资费类型"]) !== st.type) continue;
    if (st.q) {
      const f = it.fields || {};
      const vals = Object.values(f).filter((v) => v != null && v !== "").join(" ");
      const hay = (it.name + " " + vals).toLowerCase();
      if (!hay.includes(st.q)) continue;
    }
    out.push(it);
  }
  return out;
}

function drawList(section) {
  if (section !== "quanguo") section = liveSec();
  const st = getSt(section);
  const idm = domMap(section);
  const listEl = $(idm.list);
  const pagerEl = $(idm.pager);
  const cntEl = $(idm.cnt);
  const filtered = filterItems(st);
  if (st.sort) { sortFiltered(filtered, st); }
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  if (st.page > totalPages) st.page = totalPages;
  const start = (st.page - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(start, start + PAGE_SIZE);
  cntEl.textContent = "共 " + fmt(filtered.length) + " 条";
  if (!pageItems.length) { listEl.innerHTML = '<div class="empty">没有匹配的资费条目</div>'; }
  else {
    listEl.innerHTML = pageItems.map((it, i) => itemHtml(it, start + i)).join("");
    listEl.querySelectorAll(".item").forEach((el) => {
      el.addEventListener("click", () => {
        const d = el.querySelector(".detail");
        if (d) d.classList.toggle("open");
      });
    });
  }
  pagerEl.innerHTML =
    '<button ' + (st.page <= 1 ? "disabled" : "") + ' data-p="-1">上一页</button>' +
    '<span class="page-info">第 ' + st.page + " / " + totalPages + " 页</span>" +
    '<button ' + (st.page >= totalPages ? "disabled" : "") + ' data-p="1">下一页</button>';
  pagerEl.querySelectorAll("button[data-p]").forEach((b) => {
    b.addEventListener("click", () => { st.page += Number(b.dataset.p); drawList(section); window.scrollTo({ top: 0, behavior: "smooth" }); });
  });
}

function fieldsTable(f) {
  f = f || {};
  const keys = Object.keys(f);
  const mainKeys = ["资费标准", "方案编号", "资费类型", "归属", "适用范围", "适用地区", "上线日期", "下线日期", "有效期限"];
  const detailRows = mainKeys.filter((k) => f[k]).map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(f[k]) + "</td></tr>"
  ).join("");
  const otherRows = keys.filter((k) => !mainKeys.includes(k) && f[k]).map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(f[k]) + "</td></tr>"
  ).join("");
  return '<table>' + detailRows + otherRows + '</table>';
}

function itemHtml(it, idx) {
  const f = it.fields || {};
  const own = f["归属"] || "";
  const type = f["资费类型"] || "";
  const price = f["资费标准"] || "";
  const scope = f["适用范围"] ? f["适用范围"].replace(/^限/, "限 ") : "";
  const facts = [];
  if (scope) facts.push("<span>适用：" + esc(scope) + "</span>");
  if (f["国内通话"]) facts.push("<span>通话 <b>" + esc(f["国内通话"]) + "</b></span>");
  if (f["国内通用流量"]) facts.push("<span>流量 <b>" + esc(f["国内通用流量"]) + "</b></span>");
  if (f["宽带"] && f["宽带"] !== "無" && f["宽带"] !== "无") facts.push("<span>宽带 <b>" + esc(f["宽带"]) + "</b></span>");
  return (
    '<div class="item">' +
      '<div class="item-head">' +
        '<span class="item-name">' + esc(it.name) + "</span>" +
        (own ? '<span class="tag ' + (own.indexOf("政企") >= 0 ? "own-gq" : "") + '">' + esc(own) + "</span>" : "") +
        (type ? '<span class="tag ' + (type === "加装包" ? "type-jz" : type === "营销活动" ? "type-yx" : "") + '">' + esc(type) + "</span>" : "") +
        (price ? '<span class="tag">' + esc(price) + "</span>" : "") +
      "</div>" +
      (facts.length ? '<div class="item-facts">' + facts.join("") + "</div>" : "") +
      '<div class="detail">' + fieldsTable(f) + "</div>" +
    "</div>"
  );
}

/* ---------- 变化历史（按省份分组 + 筛选） ---------- */
const _histCache = new Map();   // ts -> 历史记录对象，供「修改业务」明细弹窗查询
function aesc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

function histDetail(d, sec, ts) {
  if (!d || typeof d !== "object") return "";
  let html = "";
  const kinds = [
    ["added", "add", "新增", "showAddDetail"],
    ["removed", "del", "下架", null],
    ["modified", "mod", "修改", "showModDetail"],
  ];
  kinds.forEach(([key, cls, lab, fn]) => {
    const n = d[key] || 0;
    if (!n) return;
    html += '<div class="tl-sec"><span class="chip ' + cls + '">' + lab + " " + n + " 条</span>";
    const names = Array.isArray(d[key + "_names"]) ? d[key + "_names"] : null;
    if (names && names.length) {
      if (fn) {
        // 新增/修改业务：可点击查看详情（新增看完整配置，修改看字段级明细）
        const dk = d[key + "_details"];
        html += '<ul class="tl-names">' + names.map((x) =>
          '<li><a class="tl-mod" href="javascript:void(0)" ' +
          'data-ts="' + aesc(ts) + '" data-sec="' + aesc(sec) + '" data-name="' + aesc(x) + '" ' +
          'title="点击查看该业务详情" ' +
          'onclick="event.stopPropagation();' + fn + '(this.dataset.ts,this.dataset.sec,this.dataset.name)">' +
          esc(x) + "</a>" +
          (dk && dk[x] ? '<span class="mod-badge">查看详情</span>' : "") +
          "</li>"
        ).join("") + "</ul>";
      } else {
        html += '<ul class="tl-names">' + names.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>";
      }
    } else {
      html += '<div class="tl-none">本次' + lab + " " + n + " 条，名称未记录，可在对应资费列表查看</div>";
    }
    html += "</div>";
  });
  return html;
}

/* 修改业务明细弹窗：展示该业务本次被修改的字段（旧值 → 新值） */
function showModDetail(ts, sec, name) {
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const details = (d && d.modified_details) ? d.modified_details[name] : null;
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  if (!details || !details.length) {
    openModal(name, head + '<div class="res-row">该记录未保存字段级修改明细。</div>' +
      '<div class="res-row sub">可在「' + esc(secName(sec)) + '资费」列表查看该业务当前配置。</div>');
    return;
  }
  const rows = details.map((dt) => {
    const pf = esc(dt.field || "");
    const normV = (v) => (typeof v === "string" && /^0{2,}$/.test(v) ? "全国（不限定省份）" : v);
    const pv = esc(normV(dt.from) || "（空）");
    const nv = esc(normV(dt.to) || "（空）");
    return '<div class="mod-row">' +
      '<div class="mod-f">' + pf + "</div>" +
      '<div class="mod-v">' +
      '<div class="mod-old" title="修改前">' + pv + "</div>" +
      '<div class="mod-arrow">→</div>' +
      '<div class="mod-new" title="修改后">' + nv + "</div>" +
      "</div></div>";
  }).join("");
  openModal(name, head +
    '<div class="res-row sub">该业务本次字段级修改（共 ' + details.length + " 项）：</div>" +
    '<div class="mod-diff">' + rows + "</div>");
}

/* 新增业务明细弹窗：展示该业务新增时的完整配置（字段表格） */
function showAddDetail(ts, sec, name) {
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  const renderFields = (f) => {
    if (!f || !Object.keys(f).length) {
      openModal(name, head + '<div class="res-row">该记录未保存新增业务完整配置。</div>' +
        '<div class="res-row sub">可在「' + esc(secName(sec)) + '资费」列表查看该业务当前配置。</div>');
      return;
    }
    openModal(name, head +
      '<div class="res-row sub">该业务本次新增，完整配置如下：</div>' +
      '<div class="mod-diff">' + fieldsTable(f) + "</div>");
  };
  // 优先读历史记录中保存的新增时字段快照
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const snap = (d && d.added_details && d.added_details[name]) || null;
  if (snap) { renderFields(snap); return; }
  // 兜底：从当前板块数据按名称查找该业务字段
  const file = sec === "quanguo" ? "quanguo.json" : sec + ".json";
  loadJson(file).then((j) => {
    const items = (j && j.items) || [];
    const nm = String(name == null ? "" : name).trim();
    const it = items.find((x) => x && String(x.name || "").trim() === nm);
    renderFields(it ? (it.fields || {}) : null);
  }).catch((e) => {
    openModal(name, head + '<div class="res-row">加载详情失败：' + esc(e.message) + "</div>");
  });
}

function renderHistory() {
  const filter = $("hProvFilter") ? $("hProvFilter").value : "";
  Promise.all([ensureSections().catch(() => {}), loadJson("history.json")])
    .then(([, list]) => {
      const box = $("historyBox");
      if (!Array.isArray(list) || !list.length) {
        box.innerHTML = '<div class="empty">暂无资费变化记录（首次基线已建立，后续检测到变更会自动记录）</div>';
        return;
      }
      box.innerHTML = '<div class="tl">' + list.map((r, idx) => {
        _histCache.set(r.ts, r);
        const parts = [];
        const details = [];
        SECTIONS.forEach((secObj, si) => {
          const sec = secObj.section;
          if (filter && filter !== sec) return;
          const d = r[sec];
          if (!d || d.note === "baseline") return;
          const head = secName(sec);
          const chips = [];
          if (d.added) chips.push('<span class="chip add">新增 ' + d.added + "</span>");
          if (d.removed) chips.push('<span class="chip del">下架 ' + d.removed + "</span>");
          if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + "</span>");
          if (chips.length) {
            parts.push("<div><b>" + esc(head) + "</b>：" + chips.join("") + "</div>");
            const detail = histDetail(d, sec, r.ts);
            if (detail) details.push('<div class="tl-sec-title">' + esc(head) + "</div>" + detail);
          }
        });
        if (!parts.length) {
          return (
            '<div class="tl-item"><div class="tl-time">' + esc(r.ts || "") + "</div>" +
            '<div class="tl-chips"><span class="chip">无变化</span></div></div>'
          );
        }
        const open = idx === list.length - 1; // 默认展开最新一条
        return (
          '<div class="tl-item' + (open ? " open" : "") + '" tabindex="0" role="button" aria-expanded="' + open + '">' +
          '<div class="tl-head"><div class="tl-time">' + esc(r.ts || "") + "</div><span class=\"tl-arrow\"></span></div>" +
          '<div class="tl-chips">' + parts.join("") + "</div>" +
          '<div class="tl-body">' + details.join("") + "</div></div>"
        );
      }).join("") + "</div>";

      box.querySelectorAll(".tl-item").forEach((item) => {
        const toggle = () => {
          const open = item.classList.toggle("open");
          item.setAttribute("aria-expanded", open ? "true" : "false");
        };
        item.addEventListener("click", (e) => {
          if (e.target.closest && e.target.closest("a")) return;
          toggle();
        });
        item.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
        });
      });
    }).catch((e) => {
      $("historyBox").innerHTML = '<div class="empty">历史数据加载失败：' + esc(e.message) + "</div>";
    });
}

/* 启动：先解析数据源，再按 hash 直达（如 #history 直达变化历史），默认总览 */
(function boot() {
  const raw = (location.hash || "").replace("#", "").trim();
  const valid = ["overview", "quanguo", "prov", "history", "about"].indexOf(raw) >= 0;
  initDataBase().then(() => goTab(valid ? raw : "overview"));
})();

/* ---------- 检测资费（刷新按钮） ---------- */
const RK = "trf_last_check";
const btnRefresh = $("refreshBtn");

function fetchNoCache(file) {
  return fetchTimeout(DATA + file, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { delete cache[file]; return j; });
}

function openModal(title, html) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  $("modalMask").classList.add("show");
}
function closeModal() { $("modalMask").classList.remove("show"); $("modalMask").classList.remove("warn"); }

function initModal() {
  $("modalClose").addEventListener("click", closeModal);
  $("modalOk").addEventListener("click", closeModal);
  $("modalMask").addEventListener("click", (e) => { if (e.target === $("modalMask")) closeModal(); });
}

/* 关于页：GitHub 仓库（实时数据源）设置 */
function initSettings() {
  const inp = $("repoInput"), btn = $("repoSave"), hint = $("repoHint");
  if (!inp || !btn) return;
  inp.value = repoOf();
  if (hint && repoOf()) hint.textContent = "当前已绑定仓库：" + repoOf() + "（清空可恢复使用站点自带快照）";
  btn.addEventListener("click", () => {
    const v = inp.value.trim();
    try { v ? localStorage.setItem(REPO_KEY, v) : localStorage.removeItem(REPO_KEY); } catch (e) {}
    location.reload();
  });
}

function describeHistory(hist) {
  if (!Array.isArray(hist) || !hist.length) return "";
  const heads = SECTIONS.length ? SECTIONS : [{ section: "quanguo", name: "全网(全国)" }, { section: "hunan", name: "湖南" }];
  return hist.map((r) => {
    const t = esc(r.ts || "变更记录");
    const parts = [];
    heads.forEach((s) => {
      const d = r[s.section]; if (!d) return;
      const chips = [];
      if (d.added) chips.push('<span class="chip add">新增 ' + d.added + " 条</span>");
      if (d.removed) chips.push('<span class="chip del">下架 ' + d.removed + " 条</span>");
      if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + " 条</span>");
      if (chips.length) parts.push('<div class="res-row"><b>' + esc(s.name) + "</b>：" + chips.join(" ") + "</div>");
    });
    return parts.length ? '<div class="res-hsev">' + t + parts.join("") + "</div>" : "";
  }).join("");
}

let checking = false;
function doCheck() {
  if (checking) return;
  checking = true;
  btnRefresh.classList.add("busy");
  const oldText = btnRefresh.textContent;
  btnRefresh.textContent = "检测中…";
  Promise.all([fetchNoCache("latest.json"), fetchNoCache("history.json")])
    .then(([latest, hist]) => {
      SECTIONS = latest.sections || SECTIONS;
      DEF_SECTION = latest.default || DEF_SECTION;
      if ($("pProv") && $("pProv").options.length === 0) fillProvSelects();
      const updated = (latest && latest.updated) || "";
      const hlen = Array.isArray(hist) ? hist.length : 0;
      let prev = null;
      try { prev = JSON.parse(localStorage.getItem(RK) || "null"); } catch (e) { prev = null; }
      const snap = { updated: updated, hlen: hlen };
      if (!prev) {
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("检测完成",
          '<div class="res-row">已建立首次检测基线。</div>' +
          '<div class="res-row sub">数据快照时间：' + esc(updated || "未知") + "</div>" +
          '<div class="res-row sub">历史变更记录：' + hlen + " 条</div>");
      } else if (hlen > (prev.hlen || 0)) {
        const newHist = Array.isArray(hist) ? hist.slice(prev.hlen || 0) : [];
        const detail = describeHistory(newHist) ||
          '<div class="res-row">检测到资费变化，可到「变化历史」页查看详情。</div>';
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("检测到资费变化", detail + '<div class="res-row sub">快照时间：' + esc(updated || "未知") + "</div>");
      } else if (updated && prev.updated !== updated) {
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("数据快照已更新",
          '<div class="res-row">资费数据快照已更新，新增/下架条数为 0，可能为字段级微调。</div>' +
          '<div class="res-row sub">快照时间：' + esc(updated) + "</div>");
      } else {
        openModal("无变化",
          '<div class="res-row ok">暂未检测到资费变化。</div>' +
          '<div class="res-row sub">数据快照时间：' + esc(updated || "未知") + "</div>");
      }
      if ($("updateTime")) $("updateTime").textContent = "更新于 " + (updated || "未知");
    })
    .catch((e) => {
      openModal("检测失败", '<div class="res-row">数据获取失败：' + esc(e.message) + "</div>");
    })
    .finally(() => {
      checking = false;
      btnRefresh.classList.remove("busy");
      btnRefresh.textContent = oldText;
    });
}

initModal();
initSettings();

/* 检测按钮点击频率限制：1 秒内点击超过 2 次，弹出 75% 透明度提示，本次不执行检测 */
const _clickStamp = [];
let _clickWarnTs = 0;
function btnRefreshGuard() {
  const now = Date.now();
  _clickStamp.push(now);
  while (_clickStamp.length && _clickStamp[0] <= now - 1000) _clickStamp.shift();
  if (_clickStamp.length > 2) {
    if (now - _clickWarnTs > 1000) {
      _clickWarnTs = now;
      $("modalMask").classList.add("warn");
      openModal("温馨提示",
        '<div class="res-row ok" style="text-align:center;font-size:15px;">操作过于频繁，请稍后再试</div>');
    }
    return false;
  }
  return true;
}
btnRefresh.addEventListener("click", () => { if (btnRefreshGuard()) doCheck(); });
/* ========== 按钮震动反馈（静音） ========== */
(function () {
  var TAPSEL2 = 'button, a, .tab, .btn, .glass-btn, .sort-btn, .refresh-btn, select, [role="button"]';
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest(TAPSEL2) : null;
    if (!el) return;
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) {} }
  });
})();
