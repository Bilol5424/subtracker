"use strict";

const $ = (sel) => document.querySelector(sel);
const api = {
  async get(path) { return (await fetch(path)).json(); },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  },
  async del(path) { return (await fetch(path, { method: "DELETE" })).json(); },
};

function money(value, currency) {
  return `${value.toFixed(2)} ${currency}`;
}

function joinTotals(map) {
  const entries = Object.entries(map);
  if (entries.length === 0) return "0.00";
  return entries.map(([cur, val]) => money(val, cur)).join("  ·  ");
}

function daysLabel(d) {
  if (d === null || d === undefined) return "—";
  if (d === 0) return "today";
  if (d === 1) return "tomorrow";
  return `in ${d}d`;
}

async function refresh() {
  const [subs, summary] = await Promise.all([
    api.get("/api/subscriptions"),
    api.get("/api/summary"),
  ]);

  $("#monthly").textContent = joinTotals(summary.monthly_total);
  $("#yearly").textContent = joinTotals(summary.yearly_total);
  $("#count").textContent = summary.count;

  const next = summary.upcoming[0];
  $("#next").textContent = next ? `${next.name} · ${daysLabel(next.days_until)}` : "nothing soon";
  $("#next-card").classList.toggle("card--warn", !!(next && next.due_soon));

  const rows = $("#rows");
  if (subs.length === 0) {
    rows.innerHTML = `<tr><td colspan="6" class="empty">No subscriptions yet — add one or import a statement.</td></tr>`;
    return;
  }

  rows.innerHTML = subs
    .sort((a, b) => (a.days_until ?? 9999) - (b.days_until ?? 9999))
    .map((s) => `
      <tr class="${s.due_soon ? "due-soon" : ""}">
        <td><div class="service">${escapeHtml(s.name)}<small>${escapeHtml(s.category)}</small></div></td>
        <td><span class="pill">${s.cycle}</span></td>
        <td class="num">${money(s.amount, s.currency)}</td>
        <td class="num">${s.monthly_cost.toFixed(2)}</td>
        <td class="num ${s.due_soon ? "due" : ""}">${daysLabel(s.days_until)}</td>
        <td class="num"><button class="del" data-id="${s.id}" title="Delete">×</button></td>
      </tr>`)
    .join("");

  rows.querySelectorAll(".del").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api.del(`/api/subscriptions?id=${btn.dataset.id}`);
      refresh();
    })
  );
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- add form ----
$("#toggle-add").addEventListener("click", () => {
  const f = $("#add-form");
  f.hidden = !f.hidden;
});

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = Object.fromEntries(fd.entries());
  const res = await api.post("/api/subscriptions", payload);
  if (res.error) { alert("Could not add: " + res.error); return; }
  e.target.reset();
  e.target.querySelector('[name="currency"]').value = "USD";
  $("#add-form").hidden = true;
  refresh();
});

// ---- import ----
$("#csv-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { $("#csv").value = reader.result; };
  reader.readAsText(file);
});

$("#detect").addEventListener("click", async () => {
  const csv = $("#csv").value.trim();
  if (!csv) { alert("Paste or upload a CSV first."); return; }
  const currency = $("#import-currency").value || "USD";
  const candidates = await api.post("/api/import", { csv, currency });
  renderCandidates(candidates);
});

function confClass(c) { return c >= 0.7 ? "high" : c >= 0.45 ? "mid" : ""; }

function renderCandidates(list) {
  const box = $("#candidates");
  if (!Array.isArray(list) || list.length === 0) {
    box.innerHTML = `<p class="hint">No recurring charges detected. Make sure the CSV has date, description and amount columns.</p>`;
    return;
  }
  box.innerHTML = list
    .map((c, i) => `
      <div class="candidate" style="animation-delay:${i * 0.04}s">
        <div class="candidate__name">${escapeHtml(c.name)}
          <small>${c.cycle} · seen ${c.occurrences}× · next ${c.next_charge}</small>
        </div>
        <span class="conf ${confClass(c.confidence)}">${Math.round(c.confidence * 100)}%</span>
        <span class="candidate__amt">${money(c.amount, c.currency)}</span>
        <button data-i="${i}">Add</button>
      </div>`)
    .join("");

  box.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const c = list[btn.dataset.i];
      await api.post("/api/subscriptions", {
        name: c.name, amount: c.amount, currency: c.currency,
        cycle: c.cycle, next_charge: c.next_charge, category: "imported",
      });
      btn.textContent = "Added ✓";
      btn.disabled = true;
      refresh();
    })
  );
}

// ---- clock ----
function tick() {
  $("#clock").textContent = new Date().toLocaleDateString(undefined, {
    weekday: "short", year: "numeric", month: "short", day: "numeric",
  });
}
tick();
refresh();
