// Settings (admin only): password on/off, and every login account for staff and patients
pages.settings = { title: "Settings", load: loadSettings, perm: "settings.manage" };

let accountData = { staff: [], patients: [] };
const LOGIN_ROLE_FOR_JOB = { Doctor: "Doctor", Nurse: "Nurse", Pharmacist: "Pharmacist", Receptionist: "Receptionist", Admin: "Admin" };
const ACCOUNT_URL = { staff: "/settings/staff-accounts", patient: "/settings/patient-accounts" };

async function loadSettings() {
  hideError("settings-error");
  $("#staff-accounts").innerHTML = loadingRow(7);
  $("#patient-accounts").innerHTML = loadingRow(6);
  try {
    const [settings, accounts] = await Promise.all([api.get("/settings"), api.get("/settings/accounts")]);
    accountData = accounts;
    $("#require-password").checked = settings.require_password;
    explainPasswordSetting(settings.require_password);
    renderStaffAccounts();
    renderPatientAccounts();
  } catch (e) { showError("settings-error", e.message); }
}

function explainPasswordSetting(on) {
  $("#pw-explain").textContent = on
    ? "Staff type their name and password. Patients type their email and password."
    : "Staff only type their name and patients only their email. Anyone who knows a name can sign in, so keep this off only for demos or a closed network.";
  const missing = [...accountData.staff.filter(s => s.user_id), ...accountData.patients].filter(a => !a.has_password).length;
  $("#pw-warning").hidden = !(on && missing);
  $("#pw-warning").textContent = `${missing} account(s) have no password yet. They can't sign in until you set one below.`;
}

async function toggleRequirePassword(box) {
  try {
    await api.put("/settings", { require_password: box.checked });
    explainPasswordSetting(box.checked);
    showToast(box.checked ? "Passwords are now required to sign in." : "Passwords turned off: name only.");
  } catch (e) {
    box.checked = !box.checked;
    showToast(e.message, true);
  }
}

function passwordBadge(a) {
  return a.has_password ? html`<span class="badge badge-green">Set</span>` : html`<span class="badge badge-amber">Not set</span>`;
}

function accountBadge(a) {
  if (!a.is_active) return html`<span class="badge badge-red">Turned off</span>`;
  if (a.locked) return html`<span class="badge badge-amber">Locked</span>`;
  return html`<span class="badge badge-green">Active</span>`;
}

function accountButtons(kind, id, a) {
  return html`<div class="btn-row">
    <button class="btn btn-ghost btn-sm" onclick="openSetPassword('${kind}', ${id})">${a.has_password ? "Change password" : "Set password"}</button>
    <button class="btn btn-ghost btn-sm" onclick="setAccountActive('${kind}', ${id}, ${!a.is_active})">${a.is_active ? "Turn off" : "Turn on"}</button>
  </div>`;
}

function renderStaffAccounts() {
  $("#staff-accounts").innerHTML = html`${accountData.staff.map(s => s.user_id ? html`<tr>
      <td>${s.name}</td>
      <td>${s.job}</td>
      <td><span class="badge badge-blue">${s.login_role}</span></td>
      <td>${passwordBadge(s)}</td>
      <td>${accountBadge(s)}</td>
      <td class="td-mono" style="white-space:nowrap">${s.last_login ? formatDateTime(s.last_login) : "Never"}</td>
      <td>${accountButtons("staff", s.user_id, s)}</td>
    </tr>` : html`<tr>
      <td>${s.name}</td>
      <td>${s.job}</td>
      <td colspan="4" class="text-muted text-sm">No account: can't sign in</td>
      <td><button class="btn btn-primary btn-sm" onclick="openStaffAccountForm(${s.staff_id})">Create account</button></td>
    </tr>`)}`;
}

function renderPatientAccounts() {
  const list = accountData.patients;
  $("#patient-accounts").innerHTML = list.length ? html`${list.map(p => html`<tr>
      <td>${p.name}<div class="cell-sub">${code("P", p.patient_id)}</div></td>
      <td class="td-mono">${p.email}</td>
      <td>${passwordBadge(p)}</td>
      <td>${accountBadge(p)}</td>
      <td class="td-mono" style="white-space:nowrap">${p.last_login ? formatDateTime(p.last_login) : "Never"}</td>
      <td>${accountButtons("patient", p.account_id, p)}</td>
    </tr>`)}` : emptyRow(6, "No patient accounts yet");
}

const passwordField = (label = "Password") => ({
  name: "password", label, type: "password", full: true,
  hint: "At least 8 characters with letters and numbers. Can be left empty while passwords are switched off.",
});

// Create accounts
function openStaffAccountForm(staffId) {
  const s = accountData.staff.find(x => x.staff_id === staffId);
  if (!s) return;
  openModal({
    title: `Create Account for ${s.name}`,
    intro: `${s.name} will sign in by typing their name.`,
    submitLabel: "Create Account",
    body: formGrid([
      { name: "role", label: "Signs in as", type: "select", full: true, options: ["Admin", "Doctor", "Nurse", "Pharmacist", "Receptionist"],
        value: LOGIN_ROLE_FOR_JOB[s.job] || "Receptionist", hint: "Decides which pages they can open" },
      passwordField(),
    ]),
    onSubmit: async data => {
      await api.post(ACCOUNT_URL.staff, { ...data, staff_id: staffId });
      saved(`Account created for ${s.name}.`);
    },
  });
}

async function openPatientAccountForm(patientId) {
  let patients, accounts;
  try {
    [patients, accounts] = await Promise.all([api.get("/patients"), api.get("/settings/accounts")]);
  } catch (e) { showToast(e.message, true); return; }
  const hasAccount = new Set(accounts.patients.map(a => a.patient_id));
  const choices = patients.filter(p => !hasAccount.has(p.patient_id))
    .sort((a, b) => a.first_name.localeCompare(b.first_name));
  const preset = choices.find(p => p.patient_id === patientId);

  openModal({
    title: "Create Patient Account",
    intro: "Check the patient's ID first. They will sign in to the patient portal with this email.",
    submitLabel: "Create Account",
    body: formGrid([
      { name: "patient_id", label: "Patient", type: "select", required: true, full: true, placeholder: "Choose a patient…",
        options: choices.map(p => ({ value: p.patient_id, label: `${p.first_name} ${p.last_name} · ${code("P", p.patient_id)}` })), value: patientId },
      { name: "email", label: "Email (signs in with)", type: "email", required: true, full: true, value: preset?.email },
      passwordField(),
    ]),
    onOpen: form => {
      $("#f_patient_id", form).addEventListener("change", e => {
        const p = choices.find(x => String(x.patient_id) === e.target.value);
        $("#f_email", form).value = p?.email || "";
      });
    },
    onSubmit: async data => {
      await api.post(ACCOUNT_URL.patient, data);
      saved("Patient account created.");
    },
  });
}

// Change existing accounts
function findAccount(kind, id) {
  return kind === "staff"
    ? accountData.staff.find(s => s.user_id === id)
    : accountData.patients.find(p => p.account_id === id);
}

function openSetPassword(kind, id) {
  const a = findAccount(kind, id);
  if (!a) return;
  openModal({
    title: `Password for ${a.name}`,
    intro: "Setting a password also unlocks the account if it was locked after wrong attempts.",
    submitLabel: "Save Password",
    body: formGrid([
      { ...passwordField("New Password"), required: true, hint: "At least 8 characters, with letters and numbers" },
      { name: "confirm", label: "Repeat Password", type: "password", required: true, full: true },
    ]),
    onSubmit: async data => {
      if (data.password !== data.confirm) throw new Error("The two passwords are not the same.");
      await api.put(`${ACCOUNT_URL[kind]}/${id}`, { password: data.password });
      saved(`Password saved for ${a.name}.`);
    },
  });
}

async function setAccountActive(kind, id, active) {
  const a = findAccount(kind, id);
  try {
    await api.put(`${ACCOUNT_URL[kind]}/${id}`, { is_active: active });
    showToast(`${a.name}'s account is turned ${active ? "on" : "off"}.`);
    loadSettings();
  } catch (e) { showToast(e.message, true); }
}
