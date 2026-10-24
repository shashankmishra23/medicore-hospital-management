// Start-up: who is logged in, menus, first page

// Everything the "+ New" button can create, and who may create it
const NEW_ACTIONS = [
  { perm: "patients.write", icon: "👤", label: "New patient", run: () => openPatientForm() },
  { perm: "appointments.write", icon: "📅", label: "Book appointment", run: () => openAppointmentForm() },
  { perm: "admissions.write", icon: "🛏", label: "Admit patient", run: () => openAdmitForm() },
  { perm: "prescriptions.write", icon: "℞", label: "Write prescription", run: () => openPrescriptionForm() },
  { perm: "billing.write", icon: "₹", label: "Create bill", run: () => openBillForm() },
  { perm: "medicines.write", icon: "💊", label: "Add medicine", run: () => openMedicineForm() },
  { perm: "staff.write", icon: "⚕", label: "Add staff member", run: () => openStaffForm() },
];

function buildNewMenu() {
  const allowed = NEW_ACTIONS.filter(a => can(a.perm));
  $("#new-wrap").hidden = !allowed.length;
  $("#new-menu").innerHTML = html`${allowed.map(a => html`
    <button type="button" class="menu-item" onclick="runNewAction(${NEW_ACTIONS.indexOf(a)})"><span>${a.icon}</span>${a.label}</button>`)}`;
}

function toggleNewMenu(e) {
  e.stopPropagation();
  $("#new-menu").classList.toggle("open");
}

function runNewAction(i) {
  $("#new-menu").classList.remove("open");
  NEW_ACTIONS[i].run();
}

async function logout() {
  try { await api.post("/auth/logout"); } finally { window.location.href = "/login"; }
}
function setUser(me) {
  state.user = me;
  state.perms = new Set(me.permissions);
  $("#user-avatar").textContent = initials(me.name);
  $("#user-name").textContent = me.name;
  $("#user-role").textContent = me.role;
}

// Close pop-ups when clicking elsewhere or pressing Escape
document.addEventListener("click", e => {
  const panel = $("#notif-panel");
  if (panel && !panel.contains(e.target)) panel.classList.remove("open");
  $("#new-menu")?.classList.remove("open");
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal();
});
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id !== state.page) showPage(id);
});

(async function init() {
  applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
  $("#current-date").textContent =
    new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  try {
    setUser(await api.get("/auth/me"));
  } catch (e) {
    return; // not logged in: apiFetch already sent us to the login page
  }
  applyPermissions();
  buildNewMenu();
  showPage(location.hash.slice(1) || "dashboard");
  loadAlerts();
})();
