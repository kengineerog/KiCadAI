const $ = (id) => document.getElementById(id);
let sessionId = localStorage.getItem("kicad-ai-session") || "";

function addLog(event) {
  const log = $("log");
  if (log.querySelector(".empty-log")) log.innerHTML = "";
  const row = document.createElement("div");
  row.className = `log-entry ${event.type}`;
  const time = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  const data = event.data && Object.keys(event.data).length ? `<pre>${escapeHtml(JSON.stringify(event.data, null, 2))}</pre>` : "";
  row.innerHTML = `<span class="time">${time}</span><span class="kind">${event.type.toUpperCase()}</span><p>${escapeHtml(event.message)}</p>${data}`;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  $("run-state").textContent = event.type === "done" ? "COMPLETE" : event.type.toUpperCase();
}
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c])); }
function addArtifact(item) {
  item.path = normalizeArtifactPath(item.path);
  const list = $("artifact-list");
  if (list.querySelector(".empty-log")) list.innerHTML = "";
  const row = document.createElement("div");
  row.className = "artifact";
  row.innerHTML = `<span class="artifact-name">${escapeHtml(item.name)}</span><a href="/api/download/${encodeURIComponent(item.path).replaceAll("%2F","/").replaceAll("%5C","/")}" target="_blank">OPEN ↗</a>`;
  list.appendChild(row);
  $("artifact-count").textContent = `${list.children.length} FILES`;
}
function normalizeArtifactPath(path) {
  const value = String(path).replaceAll("\\", "/");
  const marker = "/workspace/";
  const index = (/^[A-Za-z]:\//.test(value) || value.startsWith("/")) ? value.toLowerCase().indexOf(marker) : -1;
  return index >= 0 ? value.slice(index + marker.length) : value.replace(/^workspace\//i, "");
}
async function loadModels() {
  const models = await fetch("/api/models").then((r) => r.json());
  $("model").innerHTML = models.map((m) => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.label)} · ${escapeHtml(m.provider)}</option>`).join("");
}
async function refreshSession() {
  if (!sessionId) return;
  const response = await fetch(`/api/session/${sessionId}`);
  if (!response.ok) return;
  const info = await response.json();
  $("session").textContent = `SESSION // ${info.session_id}`;
  $("current-project").textContent = info.project || "—";
  $("kicad-status").textContent = info.kicad.status === "ok" ? "MOCK / READY" : "NOT CONNECTED";
  $("footprints").textContent = info.kicad.footprints || 0;
  $("tracks").textContent = info.kicad.tracks || 0;
  $("nets").textContent = info.kicad.nets || 0;
  const artifactResponse = await fetch(`/api/artifacts?session_id=${encodeURIComponent(sessionId)}`);
  if (artifactResponse.ok) {
    const payload = await artifactResponse.json();
    $("artifact-list").innerHTML = "";
    payload.artifacts.forEach(addArtifact);
  }
}
async function run() {
  const button = $("run");
  button.disabled = true; $("run-state").textContent = "RUNNING"; $("log").innerHTML = "";
  const payload = {goal: $("goal").value, model: $("model").value, temperature: Number($("temperature").value), session_id: sessionId || null, project_name: $("project").value || null};
  const response = await fetch("/api/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  if (!response.ok) { addLog({type:"error",message:await response.text(),data:{}}); button.disabled = false; return; }
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  while (true) {
    const {value, done} = await reader.read(); if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const chunks = buffer.split("\n\n"); buffer = chunks.pop();
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((x) => x.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6));
      if (event.session_id) { sessionId = event.session_id; localStorage.setItem("kicad-ai-session", sessionId); $("session").textContent = `SESSION // ${sessionId}`; continue; }
      addLog(event);
      if (event.type === "artifact") ["symbol_file","footprint_file","evidence_file"].filter((key) => event.data[key]).forEach((key) => addArtifact({name:event.data[key].split(/[\\/]/).pop(),path:event.data[key]}));
    }
  }
  await refreshSession(); button.disabled = false;
}
loadModels().catch((error) => addLog({type:"error",message:"Model catalog unavailable",data:{error:String(error)}}));
$("run").addEventListener("click", run);
$("goal").addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") run(); });
