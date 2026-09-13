const $ = (id) => document.getElementById(id);
let sessionId = localStorage.getItem("kicad-ai-session") || "";
let eventCount = 0;
let running = false;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
}

function normalizeArtifactPath(path) {
  const value = String(path).replaceAll("\\", "/");
  const marker = "/workspace/";
  const index = (/^[A-Za-z]:\//.test(value) || value.startsWith("/")) ? value.toLowerCase().indexOf(marker) : -1;
  return index >= 0 ? value.slice(index + marker.length) : value.replace(/^workspace\//i, "");
}

function setRunState(label, active = false) {
  $("run-state").textContent = label;
  $("run-state").classList.toggle("is-running", active);
}

function addLog(event) {
  const log = $("log");
  if (log.querySelector(".empty-state")) log.innerHTML = "";
  eventCount += 1;
  $("event-count").textContent = `${eventCount} event${eventCount === 1 ? "" : "s"}`;
  const row = document.createElement("div");
  row.className = `log-entry ${event.type}`;
  const time = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  const data = event.data && Object.keys(event.data).length ? `<pre>${escapeHtml(JSON.stringify(event.data, null, 2))}</pre>` : "";
  row.innerHTML = `<span class="time">${time}</span><span class="kind">${event.type.replace("_", " ").toUpperCase()}</span><p>${escapeHtml(event.message)}</p>${data}`;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  setRunState(event.type === "done" ? "Complete" : event.type.replace("_", " "), event.type !== "done");
}

function addArtifact(item) {
  item.path = normalizeArtifactPath(item.path);
  const list = $("artifact-list");
  if (list.querySelector(".empty-state")) list.innerHTML = "";
  const row = document.createElement("div");
  row.className = "artifact";
  const href = `/api/download/${item.path.split("/").map(encodeURIComponent).join("/")}`;
  row.innerHTML = `<span class="artifact-name">${escapeHtml(item.name)}</span><a href="${href}" target="_blank" rel="noopener">DOWNLOAD ↗</a>`;
  list.appendChild(row);
  $("artifact-count").textContent = `${list.children.length} file${list.children.length === 1 ? "" : "s"}`;
}

async function loadModels() {
  const models = await fetch("/api/models").then((response) => {
    if (!response.ok) throw new Error("Model catalog unavailable");
    return response.json();
  });
  if (!models.length) throw new Error("No models are configured");
  $("model").innerHTML = models.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.id)} · ${escapeHtml(model.provider || "Omniroute")}</option>`).join("");
  const preferred = models.find((model) => model.id.toLowerCase() === "auto/nemotron") || models.find((model) => /nemotron/i.test(model.id));
  if (preferred) $("model").value = preferred.id;
}

async function refreshSession() {
  if (!sessionId) return;
  const response = await fetch(`/api/session/${encodeURIComponent(sessionId)}`);
  if (!response.ok) return;
  const info = await response.json();
  $("session").textContent = `Session / ${info.session_id}`;
  $("current-project").textContent = info.project || "—";
  $("kicad-status").textContent = info.kicad.status === "ok" ? "Mock / ready" : "Not connected";
  $("footprints").textContent = info.kicad.footprints || 0;
  $("tracks").textContent = info.kicad.tracks || 0;
  $("nets").textContent = info.kicad.nets || 0;
  const artifactResponse = await fetch(`/api/artifacts?session_id=${encodeURIComponent(sessionId)}`);
  if (artifactResponse.ok) {
    const payload = await artifactResponse.json();
    $("artifact-list").innerHTML = "";
    if (!payload.artifacts.length) $("artifact-list").innerHTML = `<div class="empty-state py-8"><div class="empty-icon">□</div><div class="font-medium text-[#b4beb5]">No artifacts yet</div><div class="mt-1 text-[#68756b]">Generated files will be indexed here.</div></div>`;
    payload.artifacts.forEach(addArtifact);
  }

}

async function loadProjects() {
  const response = await fetch("/api/projects");
  if (!response.ok) return;
  const payload = await response.json();
  $("recent-project").innerHTML = payload.projects.length
    ? payload.projects.map((project) => `<option value="${escapeHtml(project.path)}">${escapeHtml(project.name)}</option>`).join("")
    : `<option value="">No projects indexed</option>`;
}

async function run() {
  const button = $("run");
  const stopButton = $("stop");
  button.disabled = true;
  stopButton.disabled = false;
  running = true;
  eventCount = 0;
  $("event-count").textContent = "0 events";
  $("log").innerHTML = `<div class="empty-state"><div class="empty-icon animate-pulse">◌</div><div class="font-medium text-[#b4beb5]">Agent is warming up</div><div class="mt-1 text-[#68756b]">Opening the execution channel...</div></div>`;
  $("artifact-list").innerHTML = `<div class="empty-state py-8"><div class="empty-icon animate-pulse">◌</div><div class="font-medium text-[#b4beb5]">Collecting outputs</div></div>`;
  setRunState("Running", true);
  const payload = {goal: $("goal").value, model: $("model").value, temperature: Number($("temperature").value), session_id: sessionId || null, project_name: $("project").value || null};
  try {
    const response = await fetch("/api/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    if (!response.ok) throw new Error(await response.text());
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop();
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.session_id) {
          sessionId = event.session_id;
          localStorage.setItem("kicad-ai-session", sessionId);
          $("session").textContent = `Session / ${sessionId}`;
          continue;
        }
        addLog(event);
        if (event.type === "artifact") ["symbol_file", "footprint_file", "evidence_file"].filter((key) => event.data[key]).forEach((key) => addArtifact({name: event.data[key].split(/[\\/]/).pop(), path: event.data[key]}));
      }
    }
    await refreshSession();
  } catch (error) {
    addLog({type: "error", message: error.message || "Agent run failed", data: {}});
    setRunState("Error");
  } finally {
    button.disabled = false;
    stopButton.disabled = true;
    running = false;
  }
}

loadModels().catch((error) => {
  $("model").innerHTML = `<option value="">Model catalog unavailable</option>`;
  addLog({type:"error", message: error.message, data:{}});
});
loadProjects();
$("run").addEventListener("click", run);
$("stop").addEventListener("click", async () => {
  if (sessionId && running) await fetch(`/api/stop/${encodeURIComponent(sessionId)}`, {method: "POST"});
});
$("save-project").addEventListener("click", async () => {
  if (sessionId) await fetch("/api/projects/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({session_id: sessionId})});
});
$("close-project").addEventListener("click", async () => {
  if (sessionId) {
    await fetch("/api/projects/close", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({session_id: sessionId})});
    await refreshSession();
  }
});
$("open-project").addEventListener("click", async () => {
  const projectPath = $("recent-project").value;
  if (!sessionId || !projectPath) return;
  await fetch("/api/projects/open", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({session_id: sessionId, project_path: projectPath})});
  await refreshSession();
});
document.querySelectorAll(".quick-action").forEach((button) => {
  button.addEventListener("click", () => {
    $("goal").value = button.dataset.goal;
    $("goal").focus();
  });
});
$("goal").addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") run(); });
