// Core: shared helpers used by every page
const API = "/api";
const HOSPITAL = window.HOSPITAL || { name: "Hospital", address: "", phone: "" };  // set by the page template
const state = { user: null, perms: new Set(), page: null };
const pages = {};          // each page file adds itself: pages.patients = { title, load }

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// Server calls
async function apiFetch(url, opts = {}) {
  let res;
  try {
    res = await fetch(API + url, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...opts,
    });
  } catch (e) {
    // Only reaches here when the server can't be reached at all
    $("#api-error").style.display = "block";
    throw new Error("Cannot reach the server. Is python app.py running?");
  }
  $("#api-error").style.display = "none";
  if (res.status === 401) {
    window.location.href = window.LOGIN_URL || "/login";
    throw new Error("Please log in.");
  }
  if (!res.ok) {
    // Server answered with an error: show its real message, not raw JSON
    let msg = `Server error (${res.status})`;
    try { const body = await res.json(); if (body.error) msg = body.error; } catch (_) { }
    throw new Error(msg);
  }
  return res.json();
}

const api = {
  get: url => apiFetch(url),
  post: (url, body = {}) => apiFetch(url, { method: "POST", body: JSON.stringify(body) }),
  put: (url, body = {}) => apiFetch(url, { method: "PUT", body: JSON.stringify(body) }),
};

// Safe HTML
// Everything put inside html`...` is escaped, so a patient called
// <script>alert(1)</script> is shown as text instead of running.
class SafeHtml {
  constructor(s) { this.s = s; }
  toString() { return this.s; }
}
const raw = s => new SafeHtml(String(s));

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderValue(v) {
  if (v === null || v === undefined || v === false) return "";
  if (v instanceof SafeHtml) return v.s;
  if (Array.isArray(v)) return v.map(renderValue).join("");
  return esc(v);
}

function html(strings, ...values) {
  let out = strings[0];
  values.forEach((v, i) => { out += renderValue(v) + strings[i + 1]; });
  return new SafeHtml(out);
}

// Formatting
function todayLocal(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// "2026-01-31" is read as local midnight (not UTC), so the day never shifts
function parseDate(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return m ? new Date(+m[1], m[2] - 1, +m[3]) : new Date(s);
}

function formatDate(d) {
  const date = parseDate(d);
  if (!date) return "—";
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function formatDateTime(d) {
  const date = parseDate(d);
  if (!date) return "—";
  return date.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatTime(t) {
  if (!t) return "—";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

// ₹1,200 for whole amounts, ₹1,200.50 when there are paise
function fmt(n) {
  const x = Number(n || 0);
  return "₹" + x.toLocaleString("en-IN", { minimumFractionDigits: Number.isInteger(x) ? 0 : 2, maximumFractionDigits: 2 });
}

function calcAge(dob) {
  const b = parseDate(dob), t = new Date();
  let age = t.getFullYear() - b.getFullYear();
  if (t < new Date(t.getFullYear(), b.getMonth(), b.getDate())) age--;
  return age;
}

function initials(name) {
  return String(name || "?").split(" ").filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

function code(prefix, id) {
  return `${prefix}-${String(id).padStart(3, "0")}`;
}

function statusBadge(s) {
  const map = {
    "Admitted": "badge-amber", "Discharged": "badge-green", "OPD": "badge-teal", "Transferred": "badge-blue",
    "Scheduled": "badge-blue", "Completed": "badge-green", "Cancelled": "badge-red", "No-Show": "badge-red",
    "Paid": "badge-green", "Partial": "badge-amber", "Pending": "badge-red", "Refunded": "badge-purple",
    "Active": "badge-green", "Inactive": "badge-red", "On Leave": "badge-amber",
    "Available": "badge-green", "Occupied": "badge-red", "Under Maintenance": "badge-amber",
    "Dispensed": "badge-green", "In stock": "badge-green", "Low stock": "badge-red",
    "Expired": "badge-red", "Expires soon": "badge-amber",
  };
  return html`<span class="badge ${map[s] || "badge-teal"}">${s}</span>`;
}

function loadingRow(cols) {
  return html`<tr><td colspan="${cols}"><div class="loading"><div class="spinner"></div></div></td></tr>`;
}

function emptyRow(cols, msg) {
  return html`<tr><td colspan="${cols}"><div class="empty-state">${msg}</div></td></tr>`;
}

function showError(elId, msg) {
  const el = document.getElementById(elId);
  if (el) { el.textContent = msg; el.style.display = "block"; }
}

function hideError(elId) {
  const el = document.getElementById(elId);
  if (el) el.style.display = "none";
}

function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Permissions
function can(action) {
  return state.perms.has(action);
}

// Hide every element marked data-perm="..." that this user may not use
function applyPermissions(root = document) {
  $$("[data-perm]", root).forEach(el => { el.hidden = !can(el.dataset.perm); });
}

// Navigation
// A page may need a permission (pages.billing.perm = "view.billing"); the first page is the fallback
function showPage(id) {
  const allowed = Object.keys(pages).filter(p => !pages[p].perm || can(pages[p].perm));
  if (!allowed.includes(id)) id = allowed[0];
  state.page = id;
  $$(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + id));
  $$(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.page === id));
  $("#topbar-title").textContent = pages[id].title;
  document.title = `${pages[id].title} · ${HOSPITAL.name}`;
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  toggleNav(false);
  closeModal();
  pages[id].load();
}

function refreshPage() {
  if (state.page) pages[state.page].load();
  if (typeof loadAlerts === "function") loadAlerts();
}

// Header used on printed receipts and prescriptions
function printHeader(title, number, sub) {
  return html`
    <div class="top">
      <div><h1>${HOSPITAL.name}</h1><div class="muted">${HOSPITAL.address} · ${HOSPITAL.phone}</div><div class="muted"><b>${title}</b></div></div>
      <div class="r"><b>${number}</b><div class="muted">${sub}</div></div>
    </div>`;
}

// Chips (filter buttons): mark the clicked one active
function setChip(groupId, value) {
  $$(`#${groupId} .chip`).forEach(c => c.classList.toggle("active", c.dataset.value === value));
}

// Phone layout: slide the sidebar in and out
function toggleNav(open) {
  document.body.classList.toggle("nav-open", open ?? !document.body.classList.contains("nav-open"));
}

// Modal (one popup window, reused by every form)
// locked: the popup can't be closed until the form is saved (used for "set your own password")
function openModal({ title, body, wide = false, submitLabel = "Save", onSubmit, onOpen, intro, footer, locked = false }) {
  const box = $("#modal-box");
  state.modalLocked = locked;
  box.className = "modal" + (wide ? " wide" : "");
  box.innerHTML = html`
    <div class="modal-header">
      <div class="modal-title">${title}</div>
      ${locked ? "" : html`<button type="button" class="modal-close" onclick="closeModal()" aria-label="Close">✕</button>`}
    </div>
    <form id="modal-form" novalidate autocomplete="off">
      <div class="modal-body">
        <div id="modal-error" class="error-banner"></div>
        ${intro ? html`<div class="modal-intro">${intro}</div>` : ""}
        ${body}
      </div>
      ${onSubmit ? html`
        <div class="modal-footer">
          ${locked ? "" : html`<button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>`}
          <button type="submit" class="btn btn-primary" id="modal-submit">${submitLabel}</button>
        </div>` : footer ? html`<div class="modal-footer">${footer}</div>` : ""}
    </form>`;

  const form = $("#modal-form");
  form.onsubmit = async e => {
    e.preventDefault();
    if (!onSubmit) return;
    hideError("modal-error");
    const missing = $$("[required]", form)
      .filter(el => !el.closest("[hidden]") && !String(el.value).trim())
      .map(el => $(`label[for="${el.id}"]`, form)?.firstChild?.textContent || el.name);
    if (missing.length) {
      showError("modal-error", `Please fill in: ${missing.join(", ")}.`);
      return;
    }
    const btn = $("#modal-submit");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Saving…";
    try {
      await onSubmit(readForm(form), form);
    } catch (err) {
      showError("modal-error", err.message);
      box.scrollTop = 0;
    } finally {
      if (btn.isConnected) { btn.disabled = false; btn.textContent = label; }
    }
  };

  $("#modal").classList.add("open");
  applyPermissions(box);
  if (onOpen) onOpen(form);
  $("input:not([type=checkbox]):not([type=hidden]), select, textarea", form)?.focus();
}

function closeModal(force = false) {
  if (state.modalLocked && !force) return;
  state.modalLocked = false;
  $("#modal").classList.remove("open");
}

// Close after a successful save, say so, and refresh what is on screen
function saved(message) {
  closeModal();
  showToast(message);
  refreshPage();
}

// Form fields
// A field is described as { name, label, type, required, options, value, ... }
function field(f) {
  if (f.type === "section") {
    return html`<div class="form-section" ${f.group ? raw(`data-group="${esc(f.group)}"`) : ""}>${f.label}</div>`;
  }
  const id = "f_" + f.name;
  const opts = (f.options || []).map(o => (typeof o === "object" ? o : { value: o, label: o }));
  const val = f.value ?? "";
  const req = f.required ? raw("required") : "";
  let input;

  if (f.type === "select") {
    input = html`<select id="${id}" name="${f.name}" ${req}>
      ${f.placeholder !== undefined ? html`<option value="">${f.placeholder}</option>` : ""}
      ${opts.map(o => html`<option value="${o.value}" ${String(o.value) === String(val) ? raw("selected") : ""}>${o.label}</option>`)}
    </select>`;
  } else if (f.type === "textarea") {
    input = html`<textarea id="${id}" name="${f.name}" rows="${f.rows || 2}" placeholder="${f.placeholder || ""}" ${req}>${val}</textarea>`;
  } else if (f.type === "checks") {
    const chosen = new Set(Array.isArray(val) ? val : String(val).split(","));
    input = html`<div class="check-row" id="${id}">${opts.map(o => html`
      <label><input type="checkbox" name="${f.name}" value="${o.value}" data-multi="1" ${chosen.has(o.value) ? raw("checked") : ""}> ${o.label}</label>`)}
    </div>`;
  } else if (f.type === "checkbox") {
    input = html`<label class="check-inline"><input type="checkbox" id="${id}" name="${f.name}" ${val ? raw("checked") : ""}> ${f.text || ""}</label>`;
  } else {
    input = html`<input id="${id}" name="${f.name}" type="${f.type || "text"}" value="${val}"
      placeholder="${f.placeholder || ""}" ${req}
      ${f.min !== undefined ? raw(`min="${esc(f.min)}"`) : ""}
      ${f.max !== undefined ? raw(`max="${esc(f.max)}"`) : ""}
      ${f.step !== undefined ? raw(`step="${esc(f.step)}"`) : ""}>`;
  }

  return html`
    <div class="form-group ${f.full ? "full" : ""}" ${f.group ? raw(`data-group="${esc(f.group)}"`) : ""}>
      <label for="${id}">${f.label}${f.required ? html`<span class="required-mark">*</span>` : ""}</label>
      ${input}
      ${f.hint ? html`<div class="form-hint" id="${id}_hint">${f.hint}</div>` : ""}
    </div>`;
}

function formGrid(fields) {
  return html`<div class="form-grid">${fields.map(field)}</div>`;
}

// Read every named input in the form into a plain object
function readForm(root) {
  const data = {};
  $$("[name]", root).forEach(el => {
    if (el.closest("[hidden]")) return;
    if (el.type === "checkbox" && el.dataset.multi) {
      data[el.name] = data[el.name] || [];
      if (el.checked) data[el.name].push(el.value);
    } else if (el.type === "checkbox") {
      data[el.name] = el.checked;
    } else {
      data[el.name] = el.value.trim();
    }
  });
  return data;
}

// Show or hide the fields that belong to a group (e.g. doctor-only fields)
function showGroup(root, group, visible) {
  $$(`[data-group="${group}"]`, root).forEach(el => { el.hidden = !visible; });
}

// Rows of items inside a form (prescription medicines, bill lines).
// Inputs in a row use data-col="..." instead of name="...".
function readItems(tbody) {
  return $$("tr", tbody).map(tr => {
    const row = {};
    $$("[data-col]", tr).forEach(el => { row[el.dataset.col] = el.value.trim(); });
    return row;
  });
}

// Options for <select> lists, fetched fresh each time a form opens
async function patientOptions(filter = () => true) {
  const list = await api.get("/patients");
  return list.filter(filter)
    .sort((a, b) => a.first_name.localeCompare(b.first_name))
    .map(p => ({ value: p.patient_id, label: `${p.first_name} ${p.last_name} · ${code("P", p.patient_id)}` }));
}

async function doctorOptions() {
  const list = await api.get("/doctors");
  return {
    list,
    options: list.filter(d => d.status === "Active")
      .map(d => ({ value: d.doctor_id, label: `Dr. ${d.first_name} ${d.last_name} — ${d.specialization}` })),
  };
}

// Toast
function showToast(msg, isError = false) {
  const t = document.createElement("div");
  t.className = "toast" + (isError ? " error" : "");
  t.textContent = (isError ? "⚠ " : "✓ ") + msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), isError ? 4500 : 2800);
}

// Print window (receipts, prescriptions)
// The window must open right away (on the click), or pop-up blockers stop it.
async function printWindow(title, buildBody) {
  const w = window.open("", "_blank");
  if (!w) { showToast("Please allow pop-ups for this site to print.", true); return; }
  w.document.write("<p style='font-family:sans-serif'>Loading…</p>");
  try {
    const body = await buildBody();
    w.document.open();
    w.document.write(`<!DOCTYPE html><html><head><title>${esc(title)}</title>
<style>
  body{font-family:Arial,sans-serif;max-width:720px;margin:30px auto;padding:0 16px;color:#111}
  h1{margin:0;font-size:22px} .muted{color:#666;font-size:13px} .r{text-align:right}
  .top{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:12px;margin-bottom:16px}
  table{width:100%;border-collapse:collapse;margin:8px 0 20px;font-size:14px}
  th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}
  .totals td{border:none;padding:4px 8px} .big{font-weight:bold;font-size:16px}
  button{padding:8px 18px;font-size:14px;cursor:pointer}
  @media print{button{display:none}}
</style></head><body>${body}
<button onclick="window.print()">Print / Save as PDF</button>
</body></html>`);
    w.document.close();
  } catch (e) {
    w.document.body.innerHTML = "<p style='font-family:sans-serif;color:red'>Could not load: " + esc(e.message) + "</p>";
  }
}

// Receipt
// The patient portal passes its own address for the bill
function openReceipt(billId, url = `/bills/${billId}`) {
  const billNo = code("B", billId);
  printWindow(`Receipt ${billNo}`, async () => {
    const b = await api.get(url);
    return html`
      ${printHeader(b.status === "Paid" ? "Payment Receipt" : "Bill", billNo, `Bill date: ${formatDate(b.bill_date)} · ${b.status}`)}
      <p><b>Patient:</b> ${b.patient_name}<br><span class="muted">${b.phone}${b.address ? " · " + b.address : ""}</span></p>
      <h3>Charges</h3>
      <table><tr><th>Description</th><th>Type</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount</th></tr>
        ${b.items.map(i => html`<tr><td>${i.description}</td><td>${i.item_type}</td><td class="r">${i.quantity}</td><td class="r">${fmt(i.unit_price)}</td><td class="r">${fmt(i.total_price)}</td></tr>`)}
      </table>
      <table class="totals">
        <tr><td class="r">Subtotal</td><td class="r" style="width:140px">${fmt(b.subtotal)}</td></tr>
        <tr><td class="r">Discount</td><td class="r">${fmt(b.discount)}</td></tr>
        <tr><td class="r">Tax</td><td class="r">${fmt(b.tax)}</td></tr>
        <tr><td class="r big">Total</td><td class="r big">${fmt(b.total_amount)}</td></tr>
        <tr><td class="r">Paid</td><td class="r">${fmt(b.paid_amount)}</td></tr>
        <tr><td class="r big">Balance</td><td class="r big">${fmt(b.balance)}</td></tr>
      </table>
      <h3>Payments</h3>
      <table><tr><th>Date</th><th>Method</th><th>Reference</th><th>Received by</th><th class="r">Amount</th></tr>
        ${b.payments.length ? b.payments.map(p => html`<tr><td>${formatDate(p.payment_date)}</td><td>${p.payment_method}</td><td>${p.transaction_ref || "—"}</td><td>${p.received_by_name || "—"}</td><td class="r">${fmt(p.amount)}</td></tr>`)
          : html`<tr><td colspan="5">No payments yet</td></tr>`}
      </table>
      <p class="muted">This is a computer-generated document.</p>`;
  });
}

// Change password (staff and patients).
// firstTime: signed in with a one-time password, so they must pick their own before going on.
function openChangePassword(firstTime = false) {
  openModal({
    title: firstTime ? "Choose Your Own Password" : "Change Password",
    intro: firstTime ? "You signed in with a one-time password. Pick a password only you know to continue." : "",
    submitLabel: firstTime ? "Save and Continue" : "Change Password",
    locked: firstTime,
    body: formGrid([
      { name: "current_password", label: firstTime ? "One-time Password" : "Current Password", type: "password", required: true, full: true },
      { name: "new_password", label: "New Password", type: "password", required: true, full: true, hint: "At least 8 characters, with letters and numbers" },
      { name: "confirm_password", label: "Repeat New Password", type: "password", required: true, full: true },
    ]),
    onSubmit: async data => {
      if (data.new_password !== data.confirm_password) throw new Error("The two new passwords are not the same.");
      await api.post("/auth/change-password", data);
      if (firstTime) { location.reload(); return; }
      closeModal();
      showToast("Password changed!");
    },
  });
}

// Shows a one-time password once, so staff can hand it over
function showOneTimePassword(title, who, password, extra = "") {
  openModal({
    title,
    body: html`
      <div class="text-sm">Give this to ${who}. It is shown only once; they choose their own password when they first sign in.</div>
      ${extra}
      <div class="info-label" style="margin-top:16px">One-time password</div>
      <div class="temp-password">${password}</div>`,
    footer: html`<button type="button" class="btn btn-primary" onclick="closeModal()">Done</button>`,
  });
}

// Theme (light / dark)
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  // Show the mode you will switch TO
  const btn = $("#theme-btn");
  if (btn) btn.textContent = theme === "light" ? "🌙" : "☀️";
  try { localStorage.setItem("theme", theme); } catch (e) { }
  document.dispatchEvent(new Event("themechange"));
}

function toggleTheme() {
  const now = document.documentElement.getAttribute("data-theme");
  applyTheme(now === "light" ? "dark" : "light");
}

// Read a colour from the CSS variables (used by the charts)
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
