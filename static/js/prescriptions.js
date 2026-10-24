// Prescriptions: doctors write them, the pharmacy dispenses them
pages.prescriptions = { title: "Prescriptions", load: loadPrescriptions, perm: "view.prescriptions" };

let rxFilter = "Pending";

function filterPrescriptions(value) {
  rxFilter = value;
  loadPrescriptions();
}

async function loadPrescriptions() {
  setChip("rx-chips", rxFilter);
  const tbody = $("#rx-tbody");
  tbody.innerHTML = loadingRow(7);
  hideError("rx-error");
  try {
    const data = await api.get(`/prescriptions${rxFilter ? "?status=" + rxFilter : ""}`);
    if (!data.length) { tbody.innerHTML = emptyRow(7, "No prescriptions found"); return; }
    tbody.innerHTML = html`${data.map(r => html`<tr>
      <td class="td-mono">${code("RX", r.prescription_id)}</td>
      <td class="clickable" onclick="viewPatient(${r.patient_id})">${r.patient_name}</td>
      <td>Dr. ${r.doctor_name}</td>
      <td class="td-mono">${formatDate(r.issued_date)}</td>
      <td>${r.medicines}</td>
      <td>${statusBadge(r.status)}</td>
      <td><div class="btn-row">
        <button class="btn btn-ghost btn-sm" onclick="viewPrescription(${r.prescription_id})">View</button>
        ${r.status === "Pending" ? html`<button class="btn btn-primary btn-sm" data-perm="prescriptions.dispense" onclick="dispensePrescription(${r.prescription_id})">Dispense</button>` : ""}
      </div></td>
    </tr>`)}`;
    applyPermissions(tbody);
  } catch (e) { showError("rx-error", "Failed to load prescriptions: " + e.message); tbody.innerHTML = ""; }
}

async function viewPrescription(id) {
  let r;
  try { r = await api.get(`/prescriptions/${id}`); } catch (e) { showToast(e.message, true); return; }
  const pending = r.status === "Pending";
  openModal({
    title: `Prescription ${code("RX", id)}`,
    wide: true,
    intro: `${r.patient_name} · prescribed by Dr. ${r.doctor_name} on ${formatDateTime(r.issued_date)}`,
    body: html`
      <div class="mini-table"><table>
        <thead><tr><th>Medicine</th><th>Dosage</th><th>How often</th><th>Days</th><th>Qty</th><th>Given</th><th>In stock</th></tr></thead>
        <tbody>${r.items.map(i => html`<tr>
          <td>${i.name}<div class="cell-sub">${i.unit}</div></td>
          <td>${i.dosage || "—"}</td><td>${i.frequency || "—"}</td><td>${i.duration_days || "—"}</td>
          <td class="td-mono">${i.qty_prescribed}</td>
          <td class="td-mono">${i.qty_dispensed}</td>
          <td class="td-mono" style="${i.stock_qty < i.qty_prescribed - i.qty_dispensed ? "color:var(--danger)" : ""}">${i.stock_qty}</td>
        </tr>`)}</tbody>
      </table></div>
      ${r.notes ? html`<div class="sub-title">Doctor's notes</div><div class="text-sm">${r.notes}</div>` : ""}
      <div style="margin-top:16px">${statusBadge(r.status)}</div>`,
    footer: html`
      <button type="button" class="btn btn-ghost" onclick="printPrescription(${id})">🖨 Print</button>
      ${pending ? html`<button type="button" class="btn btn-primary" data-perm="prescriptions.dispense" onclick="dispensePrescription(${id})">Dispense All</button>` : ""}`,
  });
}

async function dispensePrescription(id) {
  try {
    await api.post(`/prescriptions/${id}/dispense`);
    saved(`${code("RX", id)} dispensed. Stock updated.`);
  } catch (e) {
    if ($("#modal").classList.contains("open")) showError("modal-error", e.message);
    else showToast(e.message, true);
  }
}

function printPrescription(id) {
  printWindow(`Prescription ${code("RX", id)}`, async () => {
    const r = await api.get(`/prescriptions/${id}`);
    return html`
      ${printHeader("Prescription", code("RX", id), formatDateTime(r.issued_date))}
      <p><b>Patient:</b> ${r.patient_name}<br><b>Doctor:</b> Dr. ${r.doctor_name}</p>
      <table><tr><th>Medicine</th><th>Dosage</th><th>How often</th><th>Days</th><th class="r">Qty</th></tr>
        ${r.items.map(i => html`<tr><td>${i.name}</td><td>${i.dosage || ""}</td><td>${i.frequency || ""}</td><td>${i.duration_days || ""}</td><td class="r">${i.qty_prescribed}</td></tr>`)}
      </table>
      ${r.notes ? html`<p><b>Notes:</b> ${r.notes}</p>` : ""}
      <p class="muted" style="margin-top:48px">Doctor's signature: ______________________</p>`;
  });
}

// Write a prescription
let rxMedicines = [];

function rxItemRow() {
  return html`<tr>
    <td style="min-width:200px"><select data-col="medicine_id">
      <option value="">Choose…</option>
      ${rxMedicines.map(m => html`<option value="${m.medicine_id}">${m.name} (${m.stock_qty} in stock)</option>`)}
    </select></td>
    <td><input data-col="dosage" placeholder="500mg"></td>
    <td><input data-col="frequency" placeholder="Twice daily"></td>
    <td><input data-col="duration_days" type="number" min="1" placeholder="5"></td>
    <td><input data-col="qty_prescribed" type="number" min="1" placeholder="10"></td>
    <td><button type="button" class="icon-btn" title="Remove" onclick="removeItemRow(this)">✕</button></td>
  </tr>`;
}

function addItemRow(tbodyId, rowFn) {
  $("#" + tbodyId).insertAdjacentHTML("beforeend", rowFn());
}

function removeItemRow(btn) {
  const tbody = btn.closest("tbody");
  if (tbody.rows.length > 1) btn.closest("tr").remove();
  tbody.dispatchEvent(new Event("input", { bubbles: true }));
}

async function openPrescriptionForm(preset = {}) {
  let patients, doctors;
  try {
    [patients, doctors, rxMedicines] = await Promise.all([patientOptions(), doctorOptions(), api.get("/medicines")]);
  } catch (e) { showToast(e.message, true); return; }
  rxMedicines = rxMedicines.filter(m => !m.expiry_date || parseDate(m.expiry_date) >= parseDate(todayLocal()));

  const isDoctor = Boolean(state.user.doctor_id);
  openModal({
    title: "Write Prescription",
    wide: true,
    submitLabel: "Save Prescription",
    intro: isDoctor ? `Prescribing doctor: Dr. ${state.user.name}` : "",
    body: html`
      ${formGrid([
        { name: "patient_id", label: "Patient", type: "select", required: true, full: isDoctor, placeholder: "Choose a patient…", options: patients, value: preset.patient_id },
        ...(isDoctor ? [] : [{ name: "doctor_id", label: "Doctor", type: "select", required: true, placeholder: "Choose a doctor…", options: doctors.options }]),
      ])}
      <div class="sub-title">Medicines</div>
      <div class="table-wrap"><table class="items-table">
        <thead><tr><th>Medicine</th><th>Dosage</th><th>How often</th><th>Days</th><th>Qty</th><th></th></tr></thead>
        <tbody id="rx-items">${rxItemRow()}</tbody>
      </table></div>
      <button type="button" class="btn btn-ghost btn-sm" onclick="addItemRow('rx-items', rxItemRow)">+ Add medicine</button>
      <div style="margin-top:16px">${formGrid([{ name: "notes", label: "Notes for the patient / pharmacy", type: "textarea", full: true }])}</div>`,
    onSubmit: async data => {
      data.items = readItems($("#rx-items")).filter(i => i.medicine_id || i.qty_prescribed);
      const r = await api.post("/prescriptions", data);
      saved(`Prescription ${code("RX", r.prescription_id)} saved!`);
    },
  });
}
