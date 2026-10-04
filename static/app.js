// SnapVid 前端逻辑
let currentVideo = null;   // 当前解析结果
let currentOption = null;  // 当前选中清晰度
let currentUrl = "";
const FREE_MAX_HEIGHT = 720; // 免费档清晰度上限（占位逻辑，后续接账号体系）

function toast(msg, ms = 2600) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add("hidden"), ms);
}

function showVip() { document.getElementById("vipModal").classList.remove("hidden"); }
function hideVip() { document.getElementById("vipModal").classList.add("hidden"); }

function fmtDur(s) {
  if (!s) return "";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function extractUrl(text) {
  text = (text || "").trim();
  if (/^https?:\/\//.test(text)) return text.split(/\s/)[0];
  const m = text.match(/https?:\/\/[^\s，。；！？"'<>）)】\]]+/);
  return m ? m[0] : "";
}

async function doParse(url) {
  const input = document.getElementById("urlInput");
  const btn = document.getElementById("parseBtn");
  currentUrl = extractUrl(url || input.value);
  if (!currentUrl) { toast("未识别到链接，请粘贴包含 http(s):// 的视频地址或分享文案"); return; }
  if (currentUrl !== input.value.trim()) input.value = currentUrl; // 净化输入框
  btn.disabled = true; btn.textContent = "解析中…";
  document.getElementById("resultArea").classList.add("hidden");
  document.getElementById("playlistArea").classList.add("hidden");
  try {
    const resp = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "解析失败");
    if (data.type === "playlist") renderPlaylist(data);
    else renderVideo(data);
  } catch (e) {
    toast(e.message || "解析失败，请检查链接", 4000);
  } finally {
    btn.disabled = false; btn.textContent = "解析";
  }
}

function renderVideo(data) {
  currentVideo = data;
  const card = document.getElementById("videoCard");
  const isPlaylistEntry = !!data._entryUrl;
  if (data._entryUrl) currentUrl = data._entryUrl;

  card.innerHTML = `
    ${data.thumbnail ? `<img class="thumb" src="${data.thumbnail}" alt="封面" referrerpolicy="no-referrer">` : ""}
    <div class="meta">
      <h3>${escapeHtml(data.title)}</h3>
      <div class="info-line">
        ${data.platform ? `来源：${escapeHtml(data.platform)}` : ""}
        ${data.uploader ? ` · UP主：${escapeHtml(data.uploader)}` : ""}
        ${data.duration ? ` · 时长：${fmtDur(data.duration)}` : ""}
      </div>
      <div class="q-label">选择清晰度（>${FREE_MAX_HEIGHT}P 为 VIP 专属）</div>
      <div class="q-grid" id="qGrid"></div>
      <div class="dl-row">
        <button class="btn-primary" id="dlDirect" onclick="downloadDirect()">⚡ 直接下载</button>
        <button class="btn-ghost" id="dlRelay" onclick="downloadRelay()">🛡 中转下载（更稳定）</button>
      </div>
      <div class="q-label" style="margin-top:10px">直接下载走平台 CDN，速度快；失败时请用中转下载</div>
    </div>`;
  document.getElementById("resultArea").classList.remove("hidden");
  document.getElementById("progressArea").classList.add("hidden");

  const grid = document.getElementById("qGrid");
  data.options.forEach((opt, i) => {
    const b = document.createElement("button");
    b.className = "q-btn";
    const locked = opt.height > FREE_MAX_HEIGHT;
    b.innerHTML = `${opt.label}${locked ? '<em class="vip-badge">VIP</em>' : ""}` +
      (opt.size_mb ? `<span class="q-size">约 ${opt.size_mb}MB</span>` : "");
    if (i === 0) b.classList.add("active");
    b.onclick = () => {
      if (locked) { showVip(); return; }
      grid.querySelectorAll(".q-btn").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      currentOption = opt;
    };
    grid.appendChild(b);
  });
  // 默认选第一个非 VIP 档
  currentOption = data.options.find(o => o.height <= FREE_MAX_HEIGHT) || data.options[0];
  grid.querySelectorAll(".q-btn").forEach((x, i) => {
    x.classList.toggle("active", data.options[i] === currentOption);
  });
  document.getElementById("resultArea").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderPlaylist(data) {
  document.getElementById("playlistTitle").textContent = `${data.title}（共 ${data.count} 个视频）`;
  const grid = document.getElementById("playlistGrid");
  grid.innerHTML = "";
  data.entries.forEach(ent => {
    const c = document.createElement("div");
    c.className = "pl-card";
    c.innerHTML = `
      ${ent.thumbnail ? `<img src="${ent.thumbnail}" loading="lazy" referrerpolicy="no-referrer">` : ""}
      <div class="pl-body">
        <div class="pl-title">${escapeHtml(ent.title)}</div>
        ${ent.duration ? `<div class="pl-dur">${fmtDur(ent.duration)}</div>` : ""}
      </div>`;
    c.onclick = () => { if (ent.url) doParse(ent.url); };
    grid.appendChild(c);
  });
  document.getElementById("playlistArea").classList.remove("hidden");
  document.getElementById("playlistArea").scrollIntoView({ behavior: "smooth" });
  toast("批量下载为 VIP 功能，当前可逐个点击解析");
}

function downloadDirect() {
  if (!currentOption) return;
  if (!currentOption.direct_url) {
    toast("该清晰度无直链（音视频分离），请使用中转下载", 3500);
    return;
  }
  const a = document.createElement("a");
  a.href = currentOption.direct_url;
  a.download = (currentVideo.title || "video") + "." + (currentOption.ext || "mp4");
  a.target = "_blank";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast("已发起直接下载；若浏览器拦截或下载失败，请改用中转下载", 4000);
}

async function downloadRelay() {
  if (!currentOption) return;
  const btn = document.getElementById("dlRelay");
  btn.disabled = true;
  const area = document.getElementById("progressArea");
  const fill = document.getElementById("progressFill");
  const text = document.getElementById("progressText");
  const meta = document.getElementById("progressMeta");
  area.classList.remove("hidden");
  fill.style.width = "0%";
  text.textContent = "正在创建下载任务…";
  try {
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, selector: currentOption.selector, title: currentVideo.title }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "任务创建失败");
    const es = new EventSource(`/api/progress/${data.task_id}`);
    es.onmessage = (ev) => {
      const t = JSON.parse(ev.data);
      if (t.status === "downloading") {
        const pct = t.percent != null ? t.percent : 0;
        fill.style.width = pct + "%";
        text.textContent = `下载中 ${t.percent != null ? pct + "%" : ""}`;
        meta.textContent = [t.speed, t.eta && "剩余 " + t.eta].filter(Boolean).join(" · ");
      } else if (t.status === "merging" || t.status === "pending") {
        fill.style.width = "100%";
        text.textContent = "正在合并音视频…";
      } else if (t.status === "completed") {
        es.close();
        text.textContent = "✅ 完成，正在保存到你的设备…";
        meta.textContent = "";
        window.location.href = `/api/file/${data.task_id}`;
        setTimeout(() => { area.classList.add("hidden"); btn.disabled = false; }, 3000);
      } else if (t.status === "error") {
        es.close();
        text.textContent = "❌ 下载失败：" + (t.error || "未知错误");
        btn.disabled = false;
      }
    };
    es.onerror = () => { es.close(); text.textContent = "❌ 进度连接中断"; btn.disabled = false; };
  } catch (e) {
    text.textContent = "❌ " + e.message;
    btn.disabled = false;
  }
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// 回车解析
document.getElementById("urlInput").addEventListener("keydown", e => { if (e.key === "Enter") doParse(); });
// 自动读取剪贴板中的链接（部分浏览器支持）
window.addEventListener("load", async () => {
  try {
    const txt = await navigator.clipboard.readText();
    if (txt && /^https?:\/\//.test(txt.trim())) {
      document.getElementById("urlInput").value = txt.trim();
    }
  } catch (_) { /* 无权限则忽略 */ }
});
