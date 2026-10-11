const $ = (id) => document.getElementById(id);
const densityClass = (v) => (v || "LOW").toLowerCase();
function setText(id, value) { $(id).textContent = value ?? "—"; }
function setDensity(id, value) {
  const el = $(id); el.textContent = value || "LOW";
  el.className = "density-badge " + densityClass(value);
}
function setBar(id, count) {
  const el = $(id); el.style.width = Math.min(100, (Number(count) / 10) * 100) + "%";
  el.style.background = Number(count) >= 5 ? "var(--red)" : Number(count) >= 3 ? "var(--amber)" : "var(--green)";
}
function updateRoutes(routes) {
  const container = $("routes");
  if (!routes || !routes.length) {
    container.innerHTML = '<div class="route-item"><div class="route-copy"><b>No route available</b><small>Check the simulated road graph.</small></div></div>';
    setText("eta", "-- min"); return;
  }
  container.innerHTML = routes.map((r, i) => `
    <div class="route-item">
      <div class="route-rank">${i + 1}</div>
      <div class="route-copy"><b>${escapeHtml(r.name)}</b><small>${r.recommended ? "Recommended route" : "Alternative route"}</small></div>
      <div class="route-eta">${Number(r.eta_minutes).toFixed(1)} min<small>estimated</small></div>
    </div>`).join("");
  setText("eta", Number(routes[0].eta_minutes).toFixed(1) + " min");
  $("route-main").style.opacity = routes[0].nodes.includes("CENTRAL") ? "1" : ".25";
  $("route-alt").style.opacity = routes[0].nodes.includes("CENTRAL") ? ".35" : "1";
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function setLamps(activeLane) {
  ["a","b"].forEach(lane => {
    ["r","y","g"].forEach(color => {
      const el = $("lamp-" + lane + "-" + color);
      el.className = "";
    });
    const active = lane.toUpperCase() === activeLane;
    $(active ? "lamp-" + lane + "-g" : "lamp-" + lane + "-r").className = active ? "on-green" : "on-red";
  });
}
async function refresh() {
  try {
    const response = await fetch("/api/state", {cache:"no-store"});
    const s = await response.json();
    setText("total", s.vehicles_total);
    setText("congestion", s.congestion);
    $("congestion").style.color = s.congestion === "HIGH" ? "var(--red)" : s.congestion === "MEDIUM" ? "var(--amber)" : "var(--green)";
    setText("congestion-note", "Threshold: " + s.lane_a_count + " / " + s.lane_b_count + " per lane");
    setText("green-seconds", s.green_seconds);
    setText("signal-lane", "Lane " + s.signal_lane);
    setText("fps", s.fps);
    setText("camera-status", s.camera_status);
    setText("count-a", s.lane_a_count); setText("count-b", s.lane_b_count);
    setDensity("density-a", s.lane_a_density); setDensity("density-b", s.lane_b_density);
    setBar("bar-a", s.lane_a_count); setBar("bar-b", s.lane_b_count);
    setText("esp-status", s.esp32_status);
    setText("plan-a", "Suggested green " + (s.signal_lane === "A" ? s.green_seconds : 15) + " sec");
    setText("plan-b", "Suggested green " + (s.signal_lane === "B" ? s.green_seconds : 15) + " sec");
    setLamps(s.signal_lane);
    setText("updated", "Last update " + s.updated_at);
    updateRoutes(s.routes);
    if (s.error) setText("camera-status", s.camera_status + " · " + s.error);
    $("camera-placeholder").style.display = s.camera_status === "Live" ? "none" : "grid";
  } catch (e) {
    setText("camera-status", "Backend unavailable");
  }
}
function clock() { setText("clock", new Date().toLocaleTimeString()); }
refresh(); clock(); setInterval(refresh, 1000); setInterval(clock, 1000);
