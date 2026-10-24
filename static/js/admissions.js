// Admissions: admit to a room, discharge (with automatic bill)
pages.admissions = { title: "Admissions", load: loadAdmissions, perm: "view.admissions" };

let admFilter = "Admitted";
let admissionsById = {};

function filterAdmissions(value) {
  admFilter = value;
  loadAdmissions();
}

async function loadAdmissions() {
  setChip("adm-chips", admFilter);
  const tbody = $("#adm-tbody");
  tbody.innerHTML = loadingRow(8);
  hideError("adm-error");
  try {
    const data = await api.get(`/admissions${admFilter ? "?status=" + admFilter : ""}`);
    admissionsById = Object.fromEntries(data.map(a => [a.admission_id, a]));
    if (!data.length) { tbody.innerHTML = emptyRow(8, "No admissions found"); return; }
    tbody.innerHTML = html`${data.map(a => html`<tr>
      <td class="td-mono">${code("AD", a.admission_id)}</td>
      <td class="clickable" onclick="viewPatient(${a.patient_id})">${a.patient_name}<div class="cell-sub">${calcAge(a.dob)} · ${a.gender}</div></td>
      <td>${a.room_number || "—"}<div class="cell-sub">${a.ward_name || ""}</div></td>
      <td>${a.doctor_name ? "Dr. " + a.doctor_name : "—"}</td>
      <td class="td-mono">${formatDate(a.admission_date)}${a.discharge_date ? html`<div class="cell-sub">→ ${formatDate(a.discharge_date)}</div>` : ""}</td>
      <td class="td-mono">${a.days}</td>
      <td>${a.diagnosis || "—"}</td>
      <td>${a.status === "Admitted"
        ? html`<button class="btn btn-ghost btn-sm" data-perm="admissions.write" onclick="openDischargeForm(${a.admission_id})">Discharge</button>`
        : statusBadge(a.status)}</td>
    </tr>`)}`;
    applyPermissions(tbody);
  } catch (e) { showError("adm-error", "Failed to load admissions: " + e.message); tbody.innerHTML = ""; }
}

async function openAdmitForm(preset = {}) {
  let patients, doctors, rooms;
  try {
    [patients, doctors, rooms] = await Promise.all([
      patientOptions(p => p.admission_status !== "Admitted"),
      doctorOptions(),
      api.get("/rooms?status=Available"),
    ]);
  } catch (e) { showToast(e.message, true); return; }

  const roomOptions = rooms
    .filter(r => r.available_beds > 0)
    .map(r => ({ value: r.room_id, label: `${r.room_number} · ${r.ward_name} (${r.room_type}) · ${fmt(r.daily_rate)}/day` }));

  openModal({
    title: "Admit Patient",
    submitLabel: "Admit",
    intro: roomOptions.length ? "" : "⚠ There are no free rooms right now.",
    body: formGrid([
      { name: "patient_id", label: "Patient", type: "select", required: true, full: true, placeholder: "Choose a patient…", options: patients, value: preset.patient_id },
      { name: "doctor_id", label: "Doctor in Charge", type: "select", required: true, full: true, placeholder: "Choose a doctor…", options: doctors.options, value: state.user.doctor_id },
      { name: "room_id", label: "Room", type: "select", required: true, full: true, placeholder: "Choose a free room…", options: roomOptions },
      { name: "diagnosis", label: "Diagnosis", required: true, full: true, placeholder: "e.g. Fractured femur" },
      { name: "notes", label: "Notes", type: "textarea", full: true },
    ]),
    onSubmit: async data => {
      await api.post("/admissions", data);
      saved("Patient admitted!");
    },
  });
}

function openDischargeForm(id) {
  const a = admissionsById[id];
  if (!a) return;
  openModal({
    title: `Discharge ${a.patient_name}`,
    intro: `Room ${a.room_number || "—"} · admitted ${formatDate(a.admission_date)} · ${a.days} day(s).`,
    submitLabel: "Discharge",
    body: formGrid([
      { name: "notes", label: "Discharge Notes", type: "textarea", full: true, rows: 3, placeholder: "Condition at discharge, follow-up advice…" },
      { name: "create_bill", label: "Billing", type: "checkbox", full: true, value: true,
        text: "Create the bill now (room days, doctor's fee and medicines given during the stay)" },
    ]),
    onSubmit: async data => {
      const r = await api.post(`/admissions/${id}/discharge`, data);
      saved(r.bill_id ? `Discharged. Bill ${code("B", r.bill_id)} created.` : "Patient discharged.");
    },
  });
}
