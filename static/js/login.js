// Login page: staff choose a role, patients use the portal
const ROLES = [
  { role: "Admin", icon: "🛡️", color: "#a855f7", desc: "Full control, staff and activity log" },
  { role: "Doctor", icon: "🩺", color: "#00d4aa", desc: "Patients, appointments, prescriptions" },
  { role: "Nurse", icon: "💉", color: "#3b82f6", desc: "Admissions, wards and patient care" },
  { role: "Pharmacist", icon: "💊", color: "#f59e0b", desc: "Medicine stock and dispensing" },
  { role: "Receptionist", icon: "🗂️", color: "#ec4899", desc: "Front desk, appointments and billing" },
];

let chosenRole = null;
const $ = id => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Tabs
function showTab(tab) {
  const isStaff = tab === "staff";
  document.querySelectorAll(".seg button").forEach(b => b.classList.toggle("active", b.dataset.tab === (isStaff ? "staff" : "patient")));
  $("staff-roles").hidden = !isStaff || Boolean(chosenRole);
  $("staff-form").hidden = !isStaff || !chosenRole;
  $("patient-login").hidden = tab !== "patient";
  $("patient-register").hidden = tab !== "register";
  history.replaceState(null, "", tab === "staff" ? location.pathname : "#" + tab);
  const first = document.querySelector(".login-card form:not([hidden]) input");
  if (first && tab !== "staff") first.focus();
}

// Staff roles
function chooseRole(role) {
  chosenRole = ROLES.find(r => r.role === role) || null;
  $("staff-error").style.display = "none";
  if (chosenRole) {
    $("role-icon").textContent = chosenRole.icon;
    $("role-icon").style.background = chosenRole.color + "2e";
    $("role-title").textContent = `${chosenRole.role} sign in`;
    $("role-desc").textContent = chosenRole.desc;
    $("staff-btn").textContent = `Sign in as ${chosenRole.role}`;
  }
  showTab("staff");
  if (chosenRole) $("username").focus();
}

$("role-grid").innerHTML = ROLES.map(r => `
  <button type="button" class="role-tile" style="--tile:${r.color}" onclick="chooseRole('${r.role}')">
    <span class="role-icon">${r.icon}</span>
    <b>${esc(r.role)}</b>
    <small>${esc(r.desc)}</small>
  </button>`).join("");

function togglePassword(btn) {
  const input = btn.previousElementSibling;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.textContent = show ? "HIDE" : "SHOW";
}

// Sending forms
async function send(form, errorId, url, body, goTo) {
  const errorBox = $(errorId);
  const btn = form.querySelector("button[type=submit]");
  const label = btn.textContent;
  errorBox.style.display = "none";
  btn.disabled = true;
  btn.textContent = "Please wait…";
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Server error (${res.status})`);
    window.location.href = goTo;
  } catch (err) {
    errorBox.textContent = err.message === "Failed to fetch" ? "Cannot reach the server. Is python app.py running?" : err.message;
    errorBox.style.display = "block";
    btn.disabled = false;
    btn.textContent = label;
  }
}

const formData = form => Object.fromEntries(new FormData(form).entries());

$("staff-form").addEventListener("submit", e => {
  e.preventDefault();
  send(e.target, "staff-error", "/api/auth/login", { ...formData(e.target), role: chosenRole.role }, "/");
});

$("patient-login").addEventListener("submit", e => {
  e.preventDefault();
  send(e.target, "patient-error", "/api/portal/login", formData(e.target), "/portal");
});

$("patient-register").addEventListener("submit", e => {
  e.preventDefault();
  send(e.target, "register-error", "/api/portal/register", formData(e.target), "/portal#book");
});

// Theme
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  $("theme-btn").textContent = theme === "light" ? "🌙" : "☀️";
  try { localStorage.setItem("theme", theme); } catch (e) { }
}

function toggleTheme() {
  applyTheme(document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light");
}

applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
$("r_dob").max = new Date().toISOString().slice(0, 10);
showTab(["patient", "register"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "staff");
