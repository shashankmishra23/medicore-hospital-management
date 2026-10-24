// Pharmacy: medicine stock, add medicine, restock
pages.pharmacy = { title: "Pharmacy", load: loadPharmacy, perm: "view.pharmacy" };

let pharmaFilter = "";
let medicinesById = {};
const searchMedicines = debounce(loadPharmacy);

function filterPharmacy(value) {
  pharmaFilter = value;
  loadPharmacy();
}

function medicineStatus(m) {
  const expiry = parseDate(m.expiry_date);
  const today = parseDate(todayLocal());
  if (expiry && expiry < today) return "Expired";
  if (m.stock_qty <= m.reorder_level) return "Low stock";
  if (expiry && expiry - today <= 30 * 86400000) return "Expires soon";
  return "In stock";
}

async function loadPharmacy() {
  setChip("pharma-chips", pharmaFilter);
  const tbody = $("#pharma-tbody");
  tbody.innerHTML = loadingRow(9);
  hideError("pharma-error");
  const q = $("#medicine-search").value;
  try {
    const url = pharmaFilter === "low" ? "/medicines?low_stock=true" : `/medicines?search=${encodeURIComponent(q)}`;
    const data = await api.get(url);
    medicinesById = Object.fromEntries(data.map(m => [m.medicine_id, m]));
    if (!data.length) { tbody.innerHTML = emptyRow(9, "No medicines found"); return; }
    tbody.innerHTML = html`${data.map(m => {
      const status = medicineStatus(m);
      return html`<tr>
        <td class="td-mono">${code("M", m.medicine_id)}</td>
        <td><strong>${m.name}</strong><div class="cell-sub">${m.generic_name || ""}${m.unit ? " · " + m.unit : ""}</div></td>
        <td>${m.category || "—"}</td>
        <td class="td-mono">${m.unit_price !== undefined ? fmt(m.unit_price) : "—"}</td>
        <td class="td-mono" style="${status === "Low stock" ? "color:var(--danger);font-weight:600" : ""}">${m.stock_qty}</td>
        <td class="td-mono">${m.reorder_level}</td>
        <td class="td-mono">${m.expiry_date ? parseDate(m.expiry_date).toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : "—"}</td>
        <td>${statusBadge(status)}</td>
        <td><button class="btn btn-ghost btn-sm" data-perm="medicines.write" onclick="openRestockForm(${m.medicine_id})">Restock</button></td>
      </tr>`;
    })}`;
    applyPermissions(tbody);
  } catch (e) { showError("pharma-error", "Failed to load medicines: " + e.message); tbody.innerHTML = ""; }
}

function openMedicineForm() {
  openModal({
    title: "Add Medicine",
    submitLabel: "Add Medicine",
    body: formGrid([
      { name: "name", label: "Brand Name", required: true, placeholder: "e.g. Crocin 500mg" },
      { name: "generic_name", label: "Generic Name", placeholder: "e.g. Paracetamol" },
      { name: "category", label: "Category", placeholder: "e.g. Analgesic" },
      { name: "manufacturer", label: "Manufacturer" },
      { name: "unit", label: "Unit", type: "select", options: ["Tablet", "Capsule", "Syrup", "Injection", "Vial", "Bottle", "Tube", "Other"], value: "Tablet" },
      { name: "unit_price", label: "Price per Unit (₹)", type: "number", required: true, min: 0, step: "0.01" },
      { name: "stock_qty", label: "Opening Stock", type: "number", required: true, min: 0, value: 0 },
      { name: "reorder_level", label: "Reorder Level", type: "number", min: 0, value: 10, hint: "Warn when stock falls to this number" },
      { name: "expiry_date", label: "Expiry Date", type: "date", min: todayLocal(1) },
      { name: "requires_prescription", label: "Prescription", type: "checkbox", value: true, text: "Needs a doctor's prescription" },
    ]),
    onSubmit: async data => {
      const r = await api.post("/medicines", data);
      saved(`${data.name} added as ${code("M", r.medicine_id)}!`);
    },
  });
}

function openRestockForm(id) {
  const m = medicinesById[id];
  if (!m) return;
  openModal({
    title: `Restock ${m.name}`,
    intro: `In stock now: ${m.stock_qty} ${m.unit || ""}. Reorder level: ${m.reorder_level}.`,
    submitLabel: "Add to Stock",
    body: formGrid([
      { name: "quantity", label: "Quantity Received", type: "number", required: true, min: 1 },
      { name: "expiry_date", label: "Expiry of New Batch", type: "date", min: todayLocal(1),
        hint: m.expiry_date ? `Leave empty to keep ${formatDate(m.expiry_date)}` : "" },
    ]),
    onSubmit: async data => {
      await api.put(`/medicines/${id}/restock`, data);
      saved(`${m.name} restocked!`);
    },
  });
}
