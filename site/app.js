/* IPL Steals & Splurges: renders season_2026.json */
const TEAMS = {
  "Chennai Super Kings": { code: "CSK", color: "#E3B505" },
  "Delhi Capitals": { code: "DC", color: "#1F5BB5" },
  "Gujarat Titans": { code: "GT", color: "#1B2A4A" },
  "Kolkata Knight Riders": { code: "KKR", color: "#4B2A84" },
  "Lucknow Super Giants": { code: "LSG", color: "#2A9BD8" },
  "Mumbai Indians": { code: "MI", color: "#0B5CAD" },
  "Punjab Kings": { code: "PBKS", color: "#D7262E" },
  "Rajasthan Royals": { code: "RR", color: "#E2368B" },
  "Royal Challengers Bengaluru": { code: "RCB", color: "#B3121A" },
  "Sunrisers Hyderabad": { code: "SRH", color: "#F26722" },
};
const cr = v => (v >= 10 ? v.toFixed(1) : v.toFixed(2)).replace(/\.?0+$/, "") ;
const money = v => `₹${cr(v)} cr`;
const badge = t => `<span class="badge" style="background:${TEAMS[t]?.color || "#777"}">${TEAMS[t]?.code || t}</span>`;

if (window.SEASON_2026) init(window.SEASON_2026);
else fetch("data/season_2026.json").then(r => r.json()).then(init);

function init(data) {
  const players = data.players.map(p => ({ ...p, value: p.fair }));
  const regulars = players.filter(p => p.matches >= 5);
  document.getElementById("rate").textContent = `₹${data.rate_lakh_per_run} lakh per run`;

  // ---- headline stats ----
  const steal = [...regulars].sort((a, b) => a.gap - b.gap)[0];
  const splurge = [...regulars].sort((a, b) => b.gap - a.gap)[0];
  const bestTeam = data.teams[0];
  document.getElementById("stats").innerHTML = [
    [`₹${data.rate_lakh_per_run} lakh`, "what one run above a replacement player was worth in 2026"],
    [steal.name, `biggest steal: ${money(steal.value)} of value on a ${money(steal.salary)} deal`],
    [splurge.name, `biggest splurge: ${money(splurge.salary)} paid for a ${splurge.rar > 0 ? money(splurge.value) + " season" : "replacement-level season"}`],
    [TEAMS[bestTeam.team].code, `best value for money: ${bestTeam.value_per_cr.toFixed(1)} runs above replacement per crore spent`],
  ].map(([v, l]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  // ---- lists ----
  const li = (p, g) => `<li><div><div class="n">${p.name}${badge(p.team)}</div>
    <div class="s">Paid ${money(p.salary)} · ${p.rar > 0 ? "delivered " + money(p.value) : "replacement-level season"} · ${p.runs ? p.runs + " runs" : ""}${p.runs && p.wickets ? ", " : ""}${p.wickets ? p.wickets + " wkts" : ""}</div></div>
    <div class="g ${g > 0 ? "neg" : "pos"}">${g > 0 ? "−" : "+"}${money(Math.abs(g))}</div></li>`;
  document.getElementById("steals").innerHTML = [...regulars].sort((a, b) => a.gap - b.gap).slice(0, 10).map(p => li(p, p.gap)).join("");
  document.getElementById("splurges").innerHTML = [...regulars].sort((a, b) => b.gap - a.gap).slice(0, 10).map(p => li(p, p.gap)).join("");
  document.getElementById("teams").innerHTML = data.teams.map(t => `<li><div><div class="n">${t.team}${badge(t.team)}</div>
    <div class="s">Spent ${money(t.spend)} · ${t.rar.toFixed(0)} runs above replacement</div></div>
    <div class="g pos">${t.value_per_cr.toFixed(1)}<span class="s"> runs/cr</span></div></li>`).join("");
  document.getElementById("benched").innerHTML = data.benched.filter(b => b.salary >= 0.5)
    .map(b => `<li><span>${b.name}${badge(b.team)}</span><span class="s">${money(b.salary)}</span></li>`).join("");

  // ---- filters ----
  const teamSel = document.getElementById("team");
  Object.keys(TEAMS).forEach(t => teamSel.insertAdjacentHTML("beforeend", `<option>${t}</option>`));
  const roleSel = document.getElementById("role"), search = document.getElementById("search");
  const chart = drawChart(players);
  const update = () => chart.filter(teamSel.value, roleSel.value, search.value.trim().toLowerCase());
  [teamSel, roleSel].forEach(el => el.addEventListener("change", update));
  search.addEventListener("input", update);
  window.addEventListener("resize", () => { chart.redraw(); update(); });
}

function drawChart(players) {
  const host = document.getElementById("chart"), tip = document.getElementById("tip");
  let svg, dots, labels;
  const minV = 0.25, maxV = Math.max(100, d3.max(players, p => Math.max(p.value, p.salary)) * 1.1);

  const jitter = s => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 997; return (h / 997 - 0.5) * 14; };
  function redraw() {
    host.innerHTML = "";
    const W = host.clientWidth, H = Math.max(360, Math.min(560, W * 0.62));
    const m = { t: 16, r: 16, b: 48, l: 56 };
    const x = d3.scaleLog().domain([minV, 40]).range([m.l, W - m.r]).clamp(true);
    const y = d3.scaleLog().domain([minV, maxV]).range([H - m.b, m.t]).clamp(true);
    svg = d3.select(host).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const ticks = [0.3, 1, 3, 10, 30, 100];
    svg.append("g").attr("class", "grid").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(ticks.filter(t => t <= 40)).tickSize(-(H - m.t - m.b)).tickFormat(""));
    svg.append("g").attr("class", "grid").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(y).tickValues(ticks).tickSize(-(W - m.l - m.r)).tickFormat(""));
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(ticks.filter(t => t <= 40)).tickFormat(d => `₹${d}cr`));
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(y).tickValues(ticks).tickFormat(d => `₹${d}cr`));
    if (W >= 520) svg.append("text").attr("class", "axis-label").attr("x", W - m.r).attr("y", H - 10).attr("text-anchor", "end").text("Paid →");
    if (W >= 520) svg.append("text").attr("class", "axis-label").attr("x", m.l + 8).attr("y", m.t + 12).text("↑ Value delivered");
    else svg.append("text").attr("class", "axis-label").attr("x", m.l).attr("y", H - 10).text("↑ Value · Paid →");
    // fair value line: value = paid
    svg.append("line").attr("class", "fair-line").attr("x1", x(minV)).attr("y1", y(minV)).attr("x2", x(40)).attr("y2", y(40));
    svg.append("text").attr("class", "zone-label").attr("x", x(0.4)).attr("y", y(40)).attr("fill", "var(--steal)").text("STEALS");
    svg.append("text").attr("class", "zone-label").attr("x", x(14)).attr("y", y(0.45)).attr("fill", "var(--splurge)").text("SPLURGES");

    const r = d3.scaleSqrt().domain([1, 17]).range([3, 8]);
    dots = svg.append("g").selectAll("circle").data(players).join("circle")
      .attr("class", "dot").attr("cx", p => x(p.salary)).attr("cy", p => y(Math.max(p.value, minV)) + (p.rar <= 0 ? jitter(p.name) : 0))
      .attr("r", p => r(Math.max(1, p.matches)))
      .attr("fill", p => p.gap < 0 ? "var(--steal)" : "var(--splurge)").attr("fill-opacity", .78)
      .on("mouseenter touchstart", (ev, p) => show(ev, p)).on("mousemove", ev => move(ev)).on("mouseleave", () => tip.hidden = true);
    const nS = W >= 520 ? 4 : 2, nP = W >= 520 ? 2 : 1;
    const notable = new Set([...players].filter(p => p.matches >= 5).sort((a, b) => a.gap - b.gap).slice(0, nS)
      .concat([...players].filter(p => p.matches >= 5).sort((a, b) => b.gap - a.gap).slice(0, nP)).map(p => p.name));
    labels = svg.append("g").selectAll("text").data(players.filter(p => notable.has(p.name))).join("text")
      .attr("class", "label").attr("x", p => x(p.salary) + (p.gap > 0 ? -9 : 9)).attr("text-anchor", p => p.gap > 0 ? "end" : "start")
      .attr("y", p => y(Math.max(p.value, minV)) + (p.gap > 0 ? -12 : 4))
      .text(p => p.name.split(" ").slice(-1)[0]);
  }
  function show(ev, p) {
    const verdict = p.gap < 0 ? `<span style="color:#8fe0b9">Steal: +${money(-p.gap)}</span>` : `<span style="color:#ffb3bd">Splurge: −${money(p.gap)}</span>`;
    tip.innerHTML = `<b>${p.name}</b> · ${TEAMS[p.team]?.code || ""} · ${p.role}<br>
      <div class="row"><span>Paid</span><span>${money(p.salary)}</span></div>
      <div class="row"><span>Value delivered</span><span>${p.rar > 0 ? money(p.value) : "replacement level"}</span></div>
      <div class="row"><span>Matches</span><span>${p.matches}</span></div>
      <div class="row"><span>${p.runs} runs · ${p.wickets} wkts</span><span>${p.rar >= 0 ? "+" : ""}${p.rar} runs vs replacement</span></div>${verdict}`;
    tip.hidden = false; move(ev);
  }
  function move(ev) {
    const e = ev.touches ? ev.touches[0] : ev;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, e.clientX + 14) + "px";
    tip.style.top = Math.max(8, e.clientY - h - 12) + "px";
  }
  redraw();
  return {
    redraw,
    filter(team, role, q) {
      const ok = p => (!team || p.team === team) && (!role || p.role === role) && (!q || p.name.toLowerCase().includes(q));
      dots.classed("dim", p => !ok(p)).classed("hit", p => q && ok(p));
      labels.style("display", p => (team || role || q) && !ok(p) ? "none" : null);
    },
  };
}
