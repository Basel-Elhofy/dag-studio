/* Dynamic DAG Multi-Agent Studio — UI client */
"use strict";

// ------------------------------------------------------------------- state
const state = {
  runId: null,
  dag: null,
  agents: new Map(), // agentId -> {nodeId, persona, icon, color, status, logs: []}
  files: [],
  activeFile: null,
  timer: null,
  startedAt: null,
};

// ------------------------------------------------------------------- dom
const $ = (id) => document.getElementById(id);
const els = {
  input: $("query-input"),
  btnRun: $("btn-run"),
  btnCancel: $("btn-cancel"),
  badge: $("run-badge"),
  stats: $("stats"),
  statTime: $("stat-time"),
  statParallel: $("stat-parallel"),
  statPeak: $("stat-peak"),
  statArtifacts: $("stat-artifacts"),
  statTokens: $("stat-tokens"),
  svg: $("dag-svg"),
  dagEmpty: $("dag-empty"),
  agentsList: $("agents-list"),
  eventLog: $("event-log"),
  filesList: $("files-list"),
  fileView: $("file-view"),
  fileCode: $("file-view code"),
};

// ------------------------------------------------------------------- ws
let ws;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (m) => handleEvent(JSON.parse(m.data));
  ws.onclose = () => setTimeout(connect, 1500);
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// ---------------------------------------------------------------- helpers
function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

function setBadge(mode, text) {
  els.badge.className = `run-badge ${mode}`;
  els.badge.textContent = text;
}

function setRunningUI(running) {
  els.btnRun.classList.toggle("hidden", running);
  els.btnCancel.classList.toggle("hidden", !running);
  els.input.disabled = running;
  els.stats.classList.toggle("hidden", !running && !state.dag);
}

function startTimer() {
  state.startedAt = Date.now();
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    els.statTime.textContent = ((Date.now() - state.startedAt) / 1000).toFixed(1) + "s";
  }, 100);
}

function stopTimer() {
  clearInterval(state.timer);
  state.timer = null;
}

// ------------------------------------------------------------------- DAG
const NODE_W = 210, NODE_H = 64;

function renderDag() {
  if (!state.dag) return;
  const { nodes, layout } = state.dag;
  const svg = els.svg;

  // Compute bounds
  let maxX = 0, maxY = 0;
  for (const p of Object.values(layout)) {
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  }
  svg.setAttribute("width", maxX + NODE_W + 80);
  svg.setAttribute("height", maxY + NODE_H + 80);
  svg.innerHTML = `
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#263156"></path>
      </marker>
      <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#22d3ee"></path>
      </marker>
    </defs>`;

  // Edges first (under nodes)
  for (const node of Object.values(nodes)) {
    const from = layout[node.id];
    if (!from) continue;
    for (const dep of node.depends_on) {
      const to = layout[dep];
      if (!to) continue;
      const x1 = to.x + NODE_W, y1 = to.y + NODE_H / 2;
      const x2 = from.x, y2 = from.y + NODE_H / 2;
      const mx = (x1 + x2) / 2;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      const active = node.status === "running" || node.status === "completed";
      path.setAttribute("class", `edge${active ? " active" : ""}`);
      svg.appendChild(path);
    }
  }

  // Nodes
  for (const node of Object.values(nodes)) {
    const p = layout[node.id];
    if (!p) continue;
    const agent = state.agents.get(node.agent_id);
    const icon = agent?.icon || "🤖";
    const color = agent?.color || "#94a3b8";
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", `node ${node.status}`);
    g.setAttribute("transform", `translate(${p.x}, ${p.y})`);
    g.innerHTML = `
      <rect class="box" width="${NODE_W}" height="${NODE_H}" rx="10"></rect>
      <text class="n-icon" x="12" y="26">${icon}</text>
      <text class="n-title" x="38" y="24">${escapeXml(node.title)}</text>
      <text class="n-persona" x="38" y="40">${escapeXml(node.persona)}</text>
      <text class="n-status" x="12" y="56}" fill="${statusColor(node.status)}">${node.status.toUpperCase()}</text>
      <text class="n-persona" x="${NODE_W - 12}" y="56}" text-anchor="end">${node.artifacts.length} files</text>
    `;
    g.addEventListener("click", () => showNodeFiles(node));
    svg.appendChild(g);
  }

  els.dagEmpty.classList.add("hidden");
}

function statusColor(s) {
  return {
    pending: "#8b94b8", ready: "#fbbf24", running: "#22d3ee",
    completed: "#34d399", failed: "#f87171", skipped: "#8b94b8",
  }[s] || "#8b94b8";
}

function escapeXml(s) {
  return String(s).replace(/[<>&'"]/g, (c) =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[c]));
}

function showNodeFiles(node) {
  if (!node.artifacts.length) return;
  switchTab("files");
  openFile(node.artifacts[0]);
}

// ---------------------------------------------------------------- agents
function upsertAgent(evt) {
  const id = evt.agent;
  let a = state.agents.get(id);
  if (!a) {
    a = { nodeId: evt.node_id, persona: evt.persona, icon: "🤖", color: "#94a3b8", status: "idle", logs: [] };
    state.agents.set(id, a);
  }
  if (evt.persona_label) a.personaLabel = evt.persona_label;
  if (evt.icon) a.icon = evt.icon;
  if (evt.color) a.color = evt.color;
  renderAgents();
}

function renderAgents() {
  if (!state.agents.size) return;
  els.agentsList.innerHTML = "";
  for (const a of state.agents.values()) {
    const node = state.dag?.nodes[a.nodeId];
    const card = document.createElement("div");
    card.className = "agent-card";
    card.style.borderLeftColor = a.color;
    card.innerHTML = `
      <div class="a-icon">${a.icon}</div>
      <div class="a-body">
        <div class="a-title">${a.personaLabel || a.persona}</div>
        <div class="a-task">${node ? escapeXml(node.title) : ""}</div>
        <div class="a-status ${a.status}">${a.status}</div>
        <div class="a-log">${a.logs.map(escapeXml).join("\n")}</div>
      </div>`;
    els.agentsList.appendChild(card);
  }
}

function agentStatus(nodeId, status) {
  for (const a of state.agents.values()) {
    if (a.nodeId === nodeId) a.status = status;
  }
  renderAgents();
}

function agentLog(nodeId, text) {
  for (const a of state.agents.values()) {
    if (a.nodeId === nodeId) {
      a.logs.push(text);
      if (a.logs.length > 30) a.logs.shift();
    }
  }
  renderAgents();
}

// ---------------------------------------------------------------- events
function logEvent(evt) {
  const div = document.createElement("div");
  div.className = `ev ${evt.type.replaceAll(".", " ")}`;
  const label = evt.type.replaceAll(".", " · ").toUpperCase();
  let detail = "";
  if (evt.type === "agent.thinking") detail = evt.text;
  else if (evt.type === "agent.tool_call") detail = `${evt.tool}(${JSON.stringify(evt.args)})`;
  else if (evt.type === "agent.tool_result") detail = `${evt.tool} → ${evt.ok ? "ok" : "fail"} ${evt.detail || ""}`;
  else if (evt.type === "agent.completed") detail = evt.summary;
  else if (evt.type === "agent.failed") detail = evt.error;
  else if (evt.type === "artifact.created") detail = `${evt.path} (${evt.size} bytes)`;
  else if (evt.type === "run.started") detail = `${evt.node_count} nodes planned`;
  else if (evt.type === "run.finished") detail = `${evt.stats.artifacts} artifacts in ${evt.stats.elapsed}s`;
  else if (evt.type === "run.cancelled") detail = "run cancelled by user";
  else if (evt.type === "planner.finished") detail = `${evt.node_count} nodes, ${evt.edge_count} edges`;
  else if (evt.type === "planner.started") detail = `provider: ${evt.provider}`;
  else detail = evt.query || "";
  div.innerHTML = `<span class="t">${fmtTime(evt.ts)}</span><span class="badge">${label}</span> ${escapeXml(detail)}`;
  els.eventLog.appendChild(div);
  els.eventLog.scrollTop = els.eventLog.scrollHeight;
}

async function handleEvent(evt) {
  logEvent(evt);

  switch (evt.type) {
    case "planner.started":
      setBadge("planning", "planning");
      break;

    case "planner.finished":
      break;

    case "run.started":
      state.runId = evt.run_id;
      setBadge("running", "running");
      setRunningUI(true);
      startTimer();
      break;

    case "dag.status":
      state.dag = evt.dag;
      renderDag();
      break;

    case "dag.node_status": {
      if (state.dag?.nodes[evt.node_id]) {
        state.dag.nodes[evt.node_id].status = evt.status;
        renderDag();
      }
      agentStatus(evt.node_id, evt.status);
      break;
    }

    case "agent.started":
      upsertAgent(evt);
      agentStatus(evt.node_id, "running");
      break;

    case "agent.thinking":
      agentLog(evt.node_id, `💭 ${evt.text}`);
      break;

    case "agent.tool_call":
      agentLog(evt.node_id, `🔧 ${evt.tool} ${JSON.stringify(evt.args)}`);
      break;

    case "agent.tool_result":
      agentLog(evt.node_id, `   ✓ ${evt.tool} ${evt.detail || ""}`);
      break;

    case "agent.completed":
      agentStatus(evt.node_id, "completed");
      agentLog(evt.node_id, `✅ ${evt.summary}`);
      break;

    case "agent.failed":
      agentStatus(evt.node_id, "failed");
      agentLog(evt.node_id, `❌ ${evt.error}`);
      break;

    case "agent.cancelled":
      agentStatus(evt.node_id, "idle");
      break;

    case "artifact.created":
      state.files.push({ path: evt.path, size: evt.size });
      renderFiles();
      break;

    case "run.stats":
      els.statParallel.textContent = evt.active;
      els.statPeak.textContent = evt.stats.peak_parallel;
      els.statArtifacts.textContent = evt.stats.artifacts;
      els.statTokens.textContent = (evt.stats.tokens_in + evt.stats.tokens_out).toLocaleString();
      break;

    case "run.finished": {
      const failed = Object.values(state.dag?.nodes || {}).some((n) => n.status === "failed");
      setBadge(failed ? "failed" : "done", failed ? "failed" : "done");
      setRunningUI(false);
      stopTimer();
      if (evt.tree) {
        const div = document.createElement("div");
        div.className = "ev";
        div.innerHTML = `<span class="badge">WORKSPACE</span> <pre style="margin:4px 0 0;white-space:pre-wrap">${escapeXml(evt.tree)}</pre>`;
        els.eventLog.appendChild(div);
      }
      break;
    }

    case "run.cancelled":
      setBadge("idle", "cancelled");
      setRunningUI(false);
      stopTimer();
      break;
  }
}

// ------------------------------------------------------------------ files
function renderFiles() {
  if (!state.files.length) return;
  els.filesList.innerHTML = "";
  for (const f of state.files) {
    const item = document.createElement("div");
    item.className = `file-item${state.activeFile === f.path ? " active" : ""}`;
    item.innerHTML = `<span>${escapeXml(f.path)}</span><span class="size">${f.size}b</span>`;
    item.addEventListener("click", () => openFile(f.path));
    els.filesList.appendChild(item);
  }
}

async function openFile(path) {
  state.activeFile = path;
  renderFiles();
  try {
    const resp = await fetch(`/api/run/${state.runId}/file?path=${encodeURIComponent(path)}`);
    const data = await resp.json();
    els.fileCode.textContent = data.content;
    els.fileCode.removeAttribute("data-highlighted");
    hljs.highlightElement(els.fileCode);
    els.fileView.classList.remove("hidden");
  } catch (err) {
    els.fileCode.textContent = `Failed to load: ${err}`;
    els.fileView.classList.remove("hidden");
  }
}

// ------------------------------------------------------------------ tabs
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-pane").forEach((p) =>
    p.classList.toggle("active", p.id === `tab-${name}`));
}

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => switchTab(t.dataset.tab)));

// ------------------------------------------------------------------ run
async function startRun() {
  const query = els.input.value.trim();
  if (!query) return;
  // Reset UI state
  state.dag = null;
  state.agents.clear();
  state.files = [];
  state.activeFile = null;
  els.agentsList.innerHTML = `<p class="muted pad">Agents spawn here as the planner decomposes your query.</p>`;
  els.eventLog.innerHTML = "";
  els.filesList.innerHTML = `<p class="muted pad">Generated source files appear here.</p>`;
  els.fileView.classList.add("hidden");
  els.dagEmpty.classList.remove("hidden");
  els.svg.innerHTML = "";
  setBadge("planning", "planning");
  setRunningUI(true);
  startTimer();

  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      setBadge("idle", "error");
      setRunningUI(false);
      stopTimer();
      alert(data.error || "Failed to start run");
    }
  } catch (err) {
    setBadge("idle", "error");
    setRunningUI(false);
    stopTimer();
  }
}

function cancelRun() {
  if (state.runId) fetch(`/api/run/${state.runId}/cancel`, { method: "POST" });
}

els.btnRun.addEventListener("click", startRun);
els.btnCancel.addEventListener("click", cancelRun);
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") startRun();
});
document.querySelectorAll(".chip").forEach((c) =>
  c.addEventListener("click", () => {
    els.input.value = c.dataset.q;
    startRun();
  }));

// ------------------------------------------------------------------ init
connect();
setInterval(() => send({ type: "ping" }), 25000);
