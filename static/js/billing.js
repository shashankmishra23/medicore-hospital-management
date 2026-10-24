// Billing: bills, create bill, record payment, printable receipt
pages.billing = { title: "Billing & Payments", load: loadBilling, perm: "view.billing" };

let billFilter = "";
let billsById = {};

function filterBills(value) {
  billFilter = value;
  loadBilling();
}

async function loadBilling() {
  setChip("bill-chips", billFilter);
  const tbody = $("#billing-tbody");
  tbody.innerHTML = loadingRow(9);
  hideError("billing-error");
  try {
    const data = await api.get(`/bills${billFilter ? "?status=" + billFilter : ""}`);
    billsById = Object.fromEntries(data.map(b => [b.bill_id, b]));
    if (!data.length) { tbody.innerHTML = emptyRow(9, "No bills found"); return; }
    const today = parseDate(todayLocal());
    tbody.innerHTML = html`${data.map(b => {
      const overdue = b.due_date && parseDate(b.due_date) < today && ["Pending", "Partial"].includes(b.status);
      return html`<tr>
        <td class="td-mono">${code("B", b.bill_id)}</td>
        <td class="clickable" onclick="viewPatient(${b.patient_id})">${b.patient_name}</td>
        <td class="td-mono">${formatDate(b.bill_date)}</td>
        <td class="td-mono" style="${overdue ? "color:var(--danger)" : ""}">${formatDate(b.due_date)}${overdue ? html`<div class="cell-sub" style="color:var(--danger)">overdue</div>` : ""}</td>
        <td class="td-mono">${fmt(b.total_amount)}</td>
        <td class="td-mono text-accent">${fmt(b.paid_amount)}</td>
        <td class="td-mono" style="${b.balance > 0 ? "color:var(--danger)" : ""}">${fmt(b.balance)}</td>
        <td>${statusBadge(b.status)}</td>
        <td><div class="btn-row">
          ${["Pending", "Partial"].includes(b.status) ? html`<button class="btn btn-primary btn-sm" data-perm="billing.write" onclick="openPayment(${b.bill_id})">Pay</button>` : ""}
          <button class="btn btn-ghost btn-sm" onclick="openReceipt(${b.bill_id})">Receipt</button>
        </div></td>
      </tr>`;
    })}`;
    applyPermissions(tbody);
  } catch (e) { showError("billing-error", "Failed to load bills: " + e.message); tbody.innerHTML = ""; }
}

// Record a payment
function openPayment(billId) {
  const b = billsById[billId];
  if (!b) return;
  openModal({
    title: "Record Payment",
    submitLabel: "Record Payment",
    body: html`
      <div style="background:var(--surface2);border-radius:10px;padding:16px;margin-bottom:20px;">
        <div class="info-label">Patient · ${code("B", b.bill_id)}</div>
        <div style="font-weight:600;margin-bottom:8px;">${b.patient_name}</div>
        <div class="info-label">Outstanding Balance</div>
        <div style="font-family:var(--font-mono);font-size:1.4rem;color:var(--danger);">${fmt(b.balance)}</div>
      </div>
      ${formGrid([
        { name: "amount", label: "Amount (₹)", type: "number", required: true, min: 1, max: b.balance, step: "0.01", value: b.balance },
        { name: "payment_method", label: "Payment Method", type: "select", options: ["Cash", "Card", "UPI", "Net Banking", "Insurance", "Cheque"] },
        { name: "transaction_ref", label: "Transaction Reference", full: true, placeholder: "UTR / Transaction ID (optional)" },
        { name: "notes", label: "Notes", type: "textarea", full: true },
      ])}`,
    onSubmit: async data => {
      const r = await api.post("/payments", { ...data, bill_id: billId });
      saved(r.status === "Paid" ? "Payment recorded. Bill fully paid!" : "Payment recorded!");
    },
  });
}

// Create a bill
const ITEM_TYPES = ["Consultation", "Room", "Medicine", "Lab", "Surgery", "Procedure", "Other"];

function billItemRow() {
  return html`<tr>
    <td style="min-width:200px"><input data-col="description" placeholder="e.g. Blood test"></td>
    <td><select data-col="item_type">${ITEM_TYPES.map(t => html`<option>${t}</option>`)}</select></td>
    <td style="width:80px"><input data-col="quantity" type="number" min="1" value="1"></td>
    <td style="width:120px"><input data-col="unit_price" type="number" min="0" step="0.01" placeholder="0.00"></td>
    <td class="td-mono line-total" style="width:110px;text-align:right">₹0</td>
    <td><button type="button" class="icon-btn" title="Remove" onclick="removeItemRow(this)">✕</button></td>
  </tr>`;
}

// Live totals while typing (the server works them out again when saving)
function updateBillTotals(form) {
  let subtotal = 0;
  $$("#bill-items tr", form).forEach(tr => {
    const qty = Number($("[data-col=quantity]", tr).value) || 0;
    const price = Number($("[data-col=unit_price]", tr).value) || 0;
    $(".line-total", tr).textContent = fmt(qty * price);
    subtotal += qty * price;
  });
  const discount = Math.min(Number($("#f_discount", form).value) || 0, subtotal);
  const tax = (subtotal - discount) * (Number($("#f_tax_percent", form).value) || 0) / 100;
  $("#bill-totals", form).innerHTML = html`
    <div><span>Subtotal</span><span>${fmt(subtotal)}</span></div>
    <div><span>Discount</span><span>− ${fmt(discount)}</span></div>
    <div><span>Tax</span><span>${fmt(tax.toFixed(2))}</span></div>
    <div class="grand"><span>Total</span><span>${fmt((subtotal - discount + tax).toFixed(2))}</span></div>`;
}

async function openBillForm(preset = {}) {
  let patients;
  try { patients = await patientOptions(); } catch (e) { showToast(e.message, true); return; }
  openModal({
    title: "Create Bill",
    wide: true,
    submitLabel: "Create Bill",
    body: html`
      ${formGrid([
        { name: "patient_id", label: "Patient", type: "select", required: true, placeholder: "Choose a patient…", options: patients, value: preset.patient_id },
        { name: "due_date", label: "Due Date", type: "date", min: todayLocal(), value: todayLocal(7) },
      ])}
      <div class="sub-title">Charges</div>
      <div class="table-wrap"><table class="items-table">
        <thead><tr><th>Description</th><th>Type</th><th>Qty</th><th>Rate (₹)</th><th style="text-align:right">Amount</th><th></th></tr></thead>
        <tbody id="bill-items">${billItemRow()}</tbody>
      </table></div>
      <button type="button" class="btn btn-ghost btn-sm" onclick="addItemRow('bill-items', billItemRow)">+ Add line</button>
      <div style="margin-top:16px">${formGrid([
        { name: "discount", label: "Discount (₹)", type: "number", min: 0, value: 0 },
        { name: "tax_percent", label: "Tax (%)", type: "number", min: 0, step: "0.01", value: 0 },
        { name: "notes", label: "Notes", type: "textarea", full: true },
      ])}</div>
      <div class="totals-box" id="bill-totals"></div>`,
    onOpen: form => {
      form.addEventListener("input", () => updateBillTotals(form));
      updateBillTotals(form);
    },
    onSubmit: async data => {
      data.items = readItems($("#bill-items")).filter(i => i.description || Number(i.unit_price));
      const r = await api.post("/bills", data);
      saved(`Bill ${code("B", r.bill_id)} created for ${fmt(r.total_amount)}!`);
    },
  });
}
