// Patients: list, search, full patient file, add / edit
pages.patients = { title: "Patients", load: loadPatients, perm: "view.patients" };

const searchPatients = debounce(loadPatients);

async function loadPatients() {
  const q = $("#patient-search").value;
  const tbody = $("#patients-tbody");
  tbody.innerHTML = loadingRow(8);
  hideError("patients-error");
  try {
    const data = await api.get(`/patients?search=${encodeURIComponent(q)}`);
    if (!data.length) { tbody.innerHTML = emptyRow(8, "No patients found"); return; }
    tbody.innerHTML = html`${data.map(p => {
      const name = `${p.first_name} ${p.last_name}`;
      const ward = p.ward_name ? `${p.ward_name}${p.room_number ? " · " + p.room_number : ""}` : "—";
      return html`<tr class="clickable" onclick="viewPatient(${p.patient_id})">
        <td class="td-mono">${code("P", p.patient_id)}</td>
        <td><div class="flex items-center" style="gap:10px"><div class="avatar">${initials(name)}</div>${name}</div></td>
        <td>${calcAge(p.dob)} · ${p.gender}</td>
        <td><span class="badge badge-blue">${p.blood_group || "—"}</span></td>
        <td class="td-mono">${p.phone}</td>
        <td>${statusBadge(p.admission_status || "OPD")}</td>
        <td>${ward}</td>
        <td><button class="btn btn-ghost btn-sm">View</button></td>
      </tr>`;
    })}`;
  } catch (e) { showError("patients-error", "Failed to load patients: " + e.message); tbody.innerHTML = ""; }
}

// Patient file
function info(label, value) {
  return html`<div><div class="info-label">${label}</div><div class="info-value">${value || "—"}</div></div>`;
}

function miniTable(headers, rows, emptyMsg) {
  if (!rows.length) return html`<div class="text-muted text-sm">${emptyMsg}</div>`;
  return html`<div class="mini-table"><table>
    <thead><tr>${headers.map(h => html`<th>${h}</th>`)}</tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

async function viewPatient(id) {
  let p;
  try { p = await api.get(`/patients/${id}`); } catch (e) { showToast(e.message, true); return; }
  const name = `${p.first_name} ${p.last_name}`;
  const current = p.admissions.find(a => a.status === "Admitted");

  const body = html`
    <div class="detail-head">
      <div class="avatar">${initials(name)}</div>
      <div>
        <div class="detail-name">${name}</div>
        <div class="cell-sub">${code("P", p.patient_id)} · registered ${formatDate(p.registered_at)}</div>
      </div>
      <div class="btn-row" style="margin-left:auto">
        <button type="button" class="btn btn-ghost btn-sm" data-perm="patients.write" onclick="openPatientForm(${id})">✎ Edit</button>
        <button type="button" class="btn btn-ghost btn-sm" data-perm="appointments.write" onclick="openAppointmentForm({patient_id:${id}})">📅 Book</button>
        ${current ? "" : html`<button type="button" class="btn btn-ghost btn-sm" data-perm="admissions.write" onclick="openAdmitForm({patient_id:${id}})">🛏 Admit</button>`}
        <button type="button" class="btn btn-ghost btn-sm" data-perm="prescriptions.write" onclick="openPrescriptionForm({patient_id:${id}})">℞ Prescribe</button>
      </div>
    </div>

    ${p.allergies ? html`<div class="note-box">⚠ <b>Allergies:</b> ${p.allergies}</div>` : ""}

    <div class="info-grid">
      ${info("Age", `${calcAge(p.dob)} years (${formatDate(p.dob)})`)}
      ${info("Gender", p.gender)}
      ${info("Blood group", p.blood_group)}
      ${info("Phone", p.phone)}
      ${info("Email", p.email)}
      ${info("Address", p.address)}
      ${info("Emergency contact", p.emergency_contact_name && `${p.emergency_contact_name} (${p.emergency_contact_phone || "no phone"})`)}
      ${info("Current status", current ? `Admitted · ${current.ward_name || ""} ${current.room_number || ""}` : "Outpatient")}
    </div>
    ${p.medical_history ? html`<div class="sub-title">Medical history</div><div class="text-sm">${p.medical_history}</div>` : ""}

    <div class="sub-title">Appointments</div>
    ${miniTable(["Date", "Doctor", "Reason", "Status"], p.appointments.map(a => html`<tr>
      <td class="td-mono">${formatDate(a.appointment_date)} · ${formatTime(a.appointment_time)}</td>
      <td>Dr. ${a.doctor_name}</td><td>${a.reason || "—"}</td><td>${statusBadge(a.status)}</td></tr>`), "No appointments yet.")}

    <div class="sub-title">Admissions</div>
    ${miniTable(["Admitted", "Discharged", "Room", "Diagnosis", "Status"], p.admissions.map(a => html`<tr>
      <td class="td-mono">${formatDate(a.admission_date)}</td><td class="td-mono">${formatDate(a.discharge_date)}</td>
      <td>${a.room_number || "—"}</td><td>${a.diagnosis || "—"}</td><td>${statusBadge(a.status)}</td></tr>`), "Never admitted.")}

    ${p.prescriptions === null ? "" : html`
      <div class="sub-title">Prescriptions</div>
      ${miniTable(["No.", "Date", "Doctor", "Medicines"], p.prescriptions.map(r => html`<tr class="clickable" onclick="viewPrescription(${r.prescription_id})">
        <td class="td-mono">${code("RX", r.prescription_id)}</td><td class="td-mono">${formatDate(r.issued_date)}</td>
        <td>Dr. ${r.doctor_name}</td><td>${r.medicines || "—"}</td></tr>`), "No prescriptions yet.")}`}

    ${p.bills === null ? "" : html`
      <div class="sub-title">Bills</div>
      ${miniTable(["Bill", "Date", "Total", "Balance", "Status"], p.bills.map(b => html`<tr class="clickable" onclick="openReceipt(${b.bill_id})">
        <td class="td-mono">${code("B", b.bill_id)}</td><td class="td-mono">${formatDate(b.bill_date)}</td>
        <td class="td-mono">${fmt(b.total_amount)}</td><td class="td-mono">${fmt(b.balance)}</td><td>${statusBadge(b.status)}</td></tr>`), "No bills yet.")}`}

    <div class="sub-title">Online patient portal</div>
    ${p.portal_email
      ? html`<div class="text-sm">✓ Active · signs in as <span class="text-mono">${p.portal_email}</span></div>`
      : html`<div class="text-sm text-muted">No portal account yet.
          <button type="button" class="btn btn-ghost btn-sm" data-perm="patients.write" onclick="openPortalAccess(${id})">🌐 Give portal access</button></div>`}
  `;
  openModal({ title: "Patient File", wide: true, body });
}

// Portal access for an existing patient
// Done at the desk after checking ID; a one-time password is shown to hand over.
async function openPortalAccess(id) {
  let p;
  try { p = await api.get(`/patients/${id}`); } catch (e) { showToast(e.message, true); return; }
  openModal({
    title: "Give Portal Access",
    intro: `${p.first_name} ${p.last_name} will be able to book appointments and see their prescriptions and bills online. Check their ID first.`,
    submitLabel: "Create Login",
    body: formGrid([{ name: "email", label: "Patient's Email", type: "email", required: true, full: true, value: p.email }]),
    onSubmit: async data => {
      const r = await api.post(`/patients/${id}/portal-access`, data);
      openModal({
        title: "Portal Access Created",
        body: html`
          <div class="text-sm">Give these details to ${p.first_name}. The password is shown only once.</div>
          <div class="info-grid" style="margin-top:16px">${info("Website", `${location.origin}/login#patient`)}${info("Email", r.email)}</div>
          <div class="info-label">One-time password</div>
          <div class="temp-password">${r.temporary_password}</div>
          <div class="form-hint">Ask them to change it after signing in (Profile → Change password).</div>`,
        footer: html`<button type="button" class="btn btn-primary" onclick="closeModal()">Done</button>`,
      });
      refreshPage();
    },
  });
}

// Add / edit
async function openPatientForm(id) {
  let p = {};
  if (id) {
    try { p = await api.get(`/patients/${id}`); } catch (e) { showToast(e.message, true); return; }
  }
  openModal({
    title: id ? "Edit Patient" : "Add New Patient",
    submitLabel: id ? "Save Changes" : "Save Patient",
    body: formGrid([
      { name: "first_name", label: "First Name", required: true, value: p.first_name },
      { name: "last_name", label: "Last Name", required: true, value: p.last_name },
      { name: "dob", label: "Date of Birth", type: "date", required: true, value: p.dob, max: todayLocal() },
      { name: "gender", label: "Gender", type: "select", required: true, options: ["Male", "Female", "Other"], value: p.gender },
      { name: "blood_group", label: "Blood Group", type: "select", placeholder: "Unknown", options: ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], value: p.blood_group },
      { name: "phone", label: "Phone", type: "tel", required: true, placeholder: "10-digit number", value: p.phone },
      { name: "email", label: "Email", type: "email", full: true, placeholder: "email@example.com", value: p.email },
      { name: "address", label: "Address", type: "textarea", full: true, placeholder: "Full address", value: p.address },
      { name: "emergency_contact_name", label: "Emergency Contact Name", value: p.emergency_contact_name },
      { name: "emergency_contact_phone", label: "Emergency Contact Phone", type: "tel", value: p.emergency_contact_phone },
      { name: "allergies", label: "Known Allergies", full: true, placeholder: "e.g. Penicillin", value: p.allergies },
      { name: "medical_history", label: "Medical History", type: "textarea", full: true, placeholder: "Past illnesses, surgeries, long-term conditions", value: p.medical_history },
    ]),
    onSubmit: async data => {
      if (id) {
        await api.put(`/patients/${id}`, data);
        saved("Patient updated!");
      } else {
        const r = await api.post("/patients", data);
        saved(`Patient ${code("P", r.patient_id)} added!`);
      }
    },
  });
}
