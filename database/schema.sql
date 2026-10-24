-- ============================================================
--  HOSPITAL MANAGEMENT SYSTEM - MySQL schema
--  Modules: Patients, Doctors & Staff, Appointments, Admissions,
--           Prescriptions, Billing & Payments, Pharmacy, Wards & Rooms,
--           Patient Portal, Activity Log
--
--  WARNING: running this file DELETES the database hospital_db
--  and creates it again with sample data.
--  Easiest way to run it:  flask init-db
-- ============================================================

DROP DATABASE IF EXISTS hospital_db;
CREATE DATABASE hospital_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE hospital_db;

-- ------------------------------------------------------------
-- 1. DEPARTMENTS
-- ------------------------------------------------------------
CREATE TABLE departments (
    dept_id       INT AUTO_INCREMENT PRIMARY KEY,
    dept_name     VARCHAR(100) NOT NULL,
    head_doctor_id INT,                      -- FK added after doctors table
    location      VARCHAR(100),
    phone         VARCHAR(20),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 2. WARDS & ROOMS
-- ------------------------------------------------------------
CREATE TABLE wards (
    ward_id      INT AUTO_INCREMENT PRIMARY KEY,
    ward_name    VARCHAR(100) NOT NULL,
    ward_type    ENUM('General','ICU','NICU','Surgery','Maternity','Pediatric','Isolation') NOT NULL,
    dept_id      INT,
    total_beds   INT NOT NULL DEFAULT 0,
    available_beds INT NOT NULL DEFAULT 0,
    floor_no     TINYINT,
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id) ON DELETE SET NULL
);

CREATE TABLE rooms (
    room_id      INT AUTO_INCREMENT PRIMARY KEY,
    room_number  VARCHAR(20) NOT NULL UNIQUE,
    ward_id      INT NOT NULL,
    room_type    ENUM('Single','Double','Suite','ICU','Emergency') NOT NULL,
    status       ENUM('Available','Occupied','Under Maintenance') DEFAULT 'Available',
    daily_rate   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    FOREIGN KEY (ward_id) REFERENCES wards(ward_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- 3. STAFF & DOCTORS
-- ------------------------------------------------------------
CREATE TABLE staff (
    staff_id      INT AUTO_INCREMENT PRIMARY KEY,
    first_name    VARCHAR(60) NOT NULL,
    last_name     VARCHAR(60) NOT NULL,
    role          ENUM('Doctor','Nurse','Pharmacist','Lab Technician','Admin','Receptionist','Support') NOT NULL,
    dept_id       INT,
    email         VARCHAR(120) UNIQUE NOT NULL,
    phone         VARCHAR(20),
    address       TEXT,
    gender        ENUM('Male','Female','Other'),
    dob           DATE,
    hire_date     DATE NOT NULL,
    salary        DECIMAL(12,2),
    status        ENUM('Active','Inactive','On Leave') DEFAULT 'Active',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id) ON DELETE SET NULL
);

CREATE TABLE doctors (
    doctor_id         INT AUTO_INCREMENT PRIMARY KEY,
    staff_id          INT NOT NULL UNIQUE,
    specialization    VARCHAR(100) NOT NULL,
    qualification     VARCHAR(200),
    license_number    VARCHAR(50) UNIQUE NOT NULL,
    consultation_fee  DECIMAL(10,2) DEFAULT 0.00,
    available_days    SET('Mon','Tue','Wed','Thu','Fri','Sat','Sun'),
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id) ON DELETE CASCADE
);

-- Back-fill the FK for department head
ALTER TABLE departments
    ADD CONSTRAINT fk_dept_head
    FOREIGN KEY (head_doctor_id) REFERENCES doctors(doctor_id) ON DELETE SET NULL;

-- ------------------------------------------------------------
-- 4. PATIENTS
-- ------------------------------------------------------------
CREATE TABLE patients (
    patient_id    INT AUTO_INCREMENT PRIMARY KEY,
    first_name    VARCHAR(60) NOT NULL,
    last_name     VARCHAR(60) NOT NULL,
    dob           DATE NOT NULL,
    gender        ENUM('Male','Female','Other') NOT NULL,
    blood_group   ENUM('A+','A-','B+','B-','AB+','AB-','O+','O-'),
    phone         VARCHAR(20) NOT NULL,
    email         VARCHAR(120),
    address       TEXT,
    emergency_contact_name  VARCHAR(120),
    emergency_contact_phone VARCHAR(20),
    medical_history         TEXT,
    allergies               TEXT,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Online patient portal logins (one per patient)
CREATE TABLE patient_accounts (
    account_id    INT AUTO_INCREMENT PRIMARY KEY,
    patient_id    INT NOT NULL UNIQUE,
    email         VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    failed_logins INT NOT NULL DEFAULT 0,
    locked_until  DATETIME,
    last_login    DATETIME,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);

CREATE TABLE patient_admissions (
    admission_id  INT AUTO_INCREMENT PRIMARY KEY,
    patient_id    INT NOT NULL,
    room_id       INT,
    admitted_by   INT,               -- doctor_id
    admission_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    discharge_date DATETIME,
    diagnosis     TEXT,
    status        ENUM('Admitted','Discharged','Transferred','Deceased') DEFAULT 'Admitted',
    notes         TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (room_id)    REFERENCES rooms(room_id) ON DELETE SET NULL,
    FOREIGN KEY (admitted_by) REFERENCES doctors(doctor_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 5. APPOINTMENTS
-- ------------------------------------------------------------
CREATE TABLE appointments (
    appointment_id   INT AUTO_INCREMENT PRIMARY KEY,
    patient_id       INT NOT NULL,
    doctor_id        INT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    reason           VARCHAR(255),
    status           ENUM('Scheduled','Completed','Cancelled','No-Show') DEFAULT 'Scheduled',
    booked_via       ENUM('Staff','Online') NOT NULL DEFAULT 'Staff',
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id)  REFERENCES doctors(doctor_id)  ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- 6. PHARMACY
-- ------------------------------------------------------------
CREATE TABLE medicines (
    medicine_id   INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(150) NOT NULL,
    generic_name  VARCHAR(150),
    category      VARCHAR(80),
    manufacturer  VARCHAR(120),
    unit          VARCHAR(30) DEFAULT 'Tablet',
    unit_price    DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    stock_qty     INT NOT NULL DEFAULT 0,
    reorder_level INT NOT NULL DEFAULT 10,
    expiry_date   DATE,
    requires_prescription BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prescriptions (
    prescription_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT NOT NULL,
    doctor_id       INT NOT NULL,
    appointment_id  INT,
    issued_date     DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes           TEXT,
    FOREIGN KEY (patient_id)     REFERENCES patients(patient_id)         ON DELETE CASCADE,
    FOREIGN KEY (doctor_id)      REFERENCES doctors(doctor_id)           ON DELETE CASCADE,
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE SET NULL
);

CREATE TABLE prescription_items (
    item_id         INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    medicine_id     INT NOT NULL,
    dosage          VARCHAR(80),
    frequency       VARCHAR(80),
    duration_days   INT,
    qty_prescribed  INT NOT NULL DEFAULT 1,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(prescription_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id)     REFERENCES medicines(medicine_id)         ON DELETE RESTRICT
);

CREATE TABLE pharmacy_dispensing (
    dispense_id     INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    medicine_id     INT NOT NULL,
    dispensed_by    INT,               -- staff_id of pharmacist
    qty_dispensed   INT NOT NULL,
    dispense_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(prescription_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id)     REFERENCES medicines(medicine_id)         ON DELETE RESTRICT,
    FOREIGN KEY (dispensed_by)    REFERENCES staff(staff_id)               ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 7. BILLING & PAYMENTS
-- ------------------------------------------------------------
CREATE TABLE bills (
    bill_id        INT AUTO_INCREMENT PRIMARY KEY,
    patient_id     INT NOT NULL,
    admission_id   INT,
    appointment_id INT,
    bill_date      DATETIME DEFAULT CURRENT_TIMESTAMP,
    due_date       DATE,
    subtotal       DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    discount       DECIMAL(10,2) DEFAULT 0.00,
    tax            DECIMAL(10,2) DEFAULT 0.00,
    total_amount   DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    paid_amount    DECIMAL(12,2) DEFAULT 0.00,
    balance        DECIMAL(12,2) GENERATED ALWAYS AS (total_amount - paid_amount) STORED,
    status         ENUM('Pending','Partial','Paid','Cancelled','Refunded') DEFAULT 'Pending',
    notes          TEXT,
    FOREIGN KEY (patient_id)     REFERENCES patients(patient_id)           ON DELETE CASCADE,
    FOREIGN KEY (admission_id)   REFERENCES patient_admissions(admission_id) ON DELETE SET NULL,
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id)   ON DELETE SET NULL
);

CREATE TABLE bill_items (
    item_id      INT AUTO_INCREMENT PRIMARY KEY,
    bill_id      INT NOT NULL,
    description  VARCHAR(255) NOT NULL,
    item_type    ENUM('Consultation','Room','Medicine','Lab','Surgery','Procedure','Other') NOT NULL,
    quantity     INT DEFAULT 1,
    unit_price   DECIMAL(10,2) NOT NULL,
    total_price  DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (bill_id) REFERENCES bills(bill_id) ON DELETE CASCADE
);

CREATE TABLE payments (
    payment_id     INT AUTO_INCREMENT PRIMARY KEY,
    bill_id        INT NOT NULL,
    amount         DECIMAL(12,2) NOT NULL,
    payment_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
    payment_method ENUM('Cash','Card','UPI','Net Banking','Insurance','Cheque') NOT NULL,
    transaction_ref VARCHAR(100),
    received_by    INT,               -- staff_id
    notes          TEXT,
    FOREIGN KEY (bill_id)       REFERENCES bills(bill_id)    ON DELETE CASCADE,
    FOREIGN KEY (received_by)   REFERENCES staff(staff_id)   ON DELETE SET NULL
);

CREATE TABLE insurance_claims (
    claim_id       INT AUTO_INCREMENT PRIMARY KEY,
    bill_id        INT NOT NULL,
    patient_id     INT NOT NULL,
    provider_name  VARCHAR(150) NOT NULL,
    policy_number  VARCHAR(100) NOT NULL,
    claim_amount   DECIMAL(12,2) NOT NULL,
    approved_amount DECIMAL(12,2),
    status         ENUM('Submitted','Under Review','Approved','Rejected','Paid') DEFAULT 'Submitted',
    submitted_date DATE,
    resolved_date  DATE,
    FOREIGN KEY (bill_id)    REFERENCES bills(bill_id)       ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- 8. AUDIT / SYSTEM LOGS
-- ------------------------------------------------------------
CREATE TABLE system_users (
    user_id      INT AUTO_INCREMENT PRIMARY KEY,
    staff_id     INT UNIQUE NOT NULL,
    username     VARCHAR(60) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role         ENUM('Admin','Doctor','Nurse','Pharmacist','Receptionist','Billing') NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    failed_logins INT NOT NULL DEFAULT 0,
    locked_until DATETIME,
    last_login   DATETIME,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id) ON DELETE CASCADE
);

-- Settings the admin can change from the Settings page
CREATE TABLE app_settings (
    setting_key   VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL
);

-- Who did what, and when (shown to admins as the Activity Log)
CREATE TABLE audit_log (
    log_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_type  ENUM('Staff','Patient','System') NOT NULL,
    actor_id    INT,
    actor_name  VARCHAR(150),
    actor_role  VARCHAR(40),
    action      VARCHAR(80) NOT NULL,
    details     VARCHAR(255),
    ip_address  VARCHAR(45),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_time (created_at)
);

-- ------------------------------------------------------------
-- USEFUL VIEWS
-- ------------------------------------------------------------

-- Patient overview with current admission
CREATE OR REPLACE VIEW vw_patient_overview AS
SELECT
    p.patient_id,
    CONCAT(p.first_name,' ',p.last_name) AS patient_name,
    p.dob, p.gender, p.blood_group, p.phone,
    a.admission_id, a.admission_date, a.status AS admission_status,
    r.room_number, w.ward_name,
    CONCAT(s.first_name,' ',s.last_name) AS attending_doctor
FROM patients p
LEFT JOIN patient_admissions a ON a.patient_id = p.patient_id AND a.status = 'Admitted'
LEFT JOIN rooms r              ON r.room_id    = a.room_id
LEFT JOIN wards w              ON w.ward_id    = r.ward_id
LEFT JOIN doctors doc          ON doc.doctor_id = a.admitted_by
LEFT JOIN staff s              ON s.staff_id    = doc.staff_id;

-- Doctor schedule
CREATE OR REPLACE VIEW vw_doctor_schedule AS
SELECT
    d.doctor_id,
    CONCAT(s.first_name,' ',s.last_name) AS doctor_name,
    d.specialization,
    d.consultation_fee,
    d.available_days,
    dep.dept_name,
    COUNT(ap.appointment_id) AS total_appointments_today
FROM doctors d
JOIN staff s         ON s.staff_id  = d.staff_id
LEFT JOIN departments dep ON dep.dept_id = s.dept_id
LEFT JOIN appointments ap ON ap.doctor_id = d.doctor_id
    AND ap.appointment_date = CURDATE()
    AND ap.status = 'Scheduled'
GROUP BY d.doctor_id, doctor_name, d.specialization, d.consultation_fee, d.available_days, dep.dept_name;

-- Outstanding bills
CREATE OR REPLACE VIEW vw_outstanding_bills AS
SELECT
    b.bill_id,
    CONCAT(p.first_name,' ',p.last_name) AS patient_name,
    b.bill_date, b.total_amount, b.paid_amount, b.balance, b.status
FROM bills b
JOIN patients p ON p.patient_id = b.patient_id
WHERE b.status IN ('Pending','Partial')
ORDER BY b.balance DESC;

-- Low stock medicines
CREATE OR REPLACE VIEW vw_low_stock_medicines AS
SELECT
    medicine_id, name, generic_name, category,
    stock_qty, reorder_level, expiry_date
FROM medicines
WHERE stock_qty <= reorder_level
ORDER BY stock_qty ASC;

-- ------------------------------------------------------------
-- SAMPLE SEED DATA
-- ------------------------------------------------------------

INSERT INTO departments (dept_name, location, phone) VALUES
('Cardiology',    'Block A, Floor 2', '0522-300-101'),
('Neurology',     'Block B, Floor 1', '0522-300-102'),
('Orthopedics',   'Block C, Floor 3', '0522-300-103'),
('Pediatrics',    'Block A, Floor 1', '0522-300-104'),
('General Medicine','Block D, Floor 1','0522-300-105'),
('Pharmacy',      'Ground Floor',     '0522-300-200');

INSERT INTO wards (ward_name, ward_type, dept_id, total_beds, available_beds, floor_no) VALUES
('Cardiac Ward',     'ICU',      1, 10, 4, 2),
('Neuro Ward',       'General',  2, 20, 12, 1),
('Ortho Ward',       'General',  3, 15, 9, 3),
('Pediatric Ward',   'Pediatric',4, 18, 10, 1),
('General Ward',     'General',  5, 30, 18, 1),
('Emergency',        'ICU',      5,  8,  3, 0);

INSERT INTO rooms (room_number, ward_id, room_type, status, daily_rate) VALUES
('A-101','1','ICU',      'Available', 5000.00),
('A-102','1','ICU',      'Occupied',  5000.00),
('B-201','2','Single',   'Available', 2500.00),
('B-202','2','Double',   'Available', 1800.00),
('C-301','3','Single',   'Occupied',  2200.00),
('D-101','4','Single',   'Available', 2000.00),
('E-101','5','Double',   'Available',  900.00),
('E-102','5','Suite',    'Available', 4500.00),
('ER-01', '6','Emergency','Occupied', 3500.00),
('A-103','1','ICU',      'Under Maintenance', 5000.00),
('C-302','3','Double',   'Available', 1500.00),
('D-102','4','Double',   'Available', 1600.00),
('ER-02', '6','Emergency','Available', 3500.00);

INSERT INTO staff (first_name,last_name,role,dept_id,email,phone,gender,dob,hire_date,salary) VALUES
('Arun',   'Sharma',   'Doctor',      1,'arun.sharma@hospital.com',   '9876543210','Male',  '1978-05-12','2010-06-01',150000),
('Priya',  'Mehta',    'Doctor',      2,'priya.mehta@hospital.com',   '9876543211','Female','1982-08-22','2012-03-15',140000),
('Rakesh', 'Verma',    'Doctor',      3,'rakesh.verma@hospital.com',  '9876543212','Male',  '1975-11-30','2008-01-10',160000),
('Sunita', 'Singh',    'Nurse',       1,'sunita.singh@hospital.com',  '9876543213','Female','1990-04-18','2015-07-01', 45000),
('Mohit',  'Jain',     'Pharmacist',  6,'mohit.jain@hospital.com',    '9876543214','Male',  '1988-02-14','2016-09-01', 50000),
('Kavita', 'Rao',      'Receptionist',5,'kavita.rao@hospital.com',    '9876543215','Female','1993-07-25','2019-01-15', 35000),
('Deepak', 'Gupta',    'Doctor',      4,'deepak.gupta@hospital.com',  '9876543216','Male',  '1980-09-07','2011-04-01',145000),
('Shashank','Mishra',  'Admin',       5,'shashank.mishra@hospital.com','9876543217','Male', NULL,        '2020-08-01', 60000);

INSERT INTO doctors (staff_id, specialization, qualification, license_number, consultation_fee, available_days) VALUES
(1,'Cardiology',   'MD, DM Cardiology',     'MCI-CARD-001', 800.00, 'Mon,Tue,Wed,Thu,Fri'),
(2,'Neurology',    'MD, DM Neurology',      'MCI-NEUR-002', 900.00, 'Mon,Wed,Fri'),
(3,'Orthopedics',  'MS Orthopedics',        'MCI-ORTH-003', 700.00, 'Tue,Thu,Sat'),
(7,'Pediatrics',   'MD Pediatrics, MRCP',   'MCI-PEDI-004', 600.00, 'Mon,Tue,Wed,Thu,Fri');

INSERT INTO patients (first_name,last_name,dob,gender,blood_group,phone,email,address,emergency_contact_name,emergency_contact_phone) VALUES
('Ramesh',  'Kumar',   '1965-03-10','Male',  'B+','9811111111','ramesh.k@email.com',  'Hazratganj, Lucknow','Suresh Kumar',   '9811111112'),
('Anita',   'Patel',   '1990-07-22','Female','A+','9822222222','anita.p@email.com',   'Aliganj, Lucknow','Rajesh Patel', '9822222223'),
('Vikas',   'Tiwari',  '1978-11-05','Male',  'O-','9833333333','vikas.t@email.com',   'Indira Nagar, Lucknow','Meena Tiwari',  '9833333334'),
('Shalini', 'Mishra',  '2001-01-15','Female','AB+','9844444444','shalini.m@email.com','Mahanagar, Lucknow',     'Sunil Mishra',  '9844444445'),
('Amit',    'Srivastava','1955-06-28','Male', 'A-','9855555555','amit.s@email.com',   'Alambagh, Lucknow',     'Rita Srivastava','9855555556');

INSERT INTO patients (first_name,last_name,dob,gender,blood_group,phone,email,address,emergency_contact_name,emergency_contact_phone,allergies,medical_history) VALUES
('Pooja',   'Saxena',  '1988-09-14','Female','O+','9866666666','pooja.s@email.com',  'Vikas Nagar, Lucknow','Arvind Saxena', '9866666667','Penicillin', NULL),
('Rahul',   'Yadav',   '1995-12-02','Male',  'B-','9877777777','rahul.y@email.com',  'Jankipuram, Lucknow',   'Sunita Yadav',  '9877777778', NULL, NULL),
('Meera',   'Pandey',  '1972-04-19','Female','A+','9888888888', NULL,                'Rajajipuram, Lucknow','Alok Pandey',  '9888888889', NULL, 'Type 2 diabetes, high blood pressure'),
('Arjun',   'Chauhan', '2015-08-30','Male',  'O+','9899999999', NULL,                'Chinhat, Lucknow',       'Kiran Chauhan', '9899999990','Peanuts', 'Asthma'),
('Fatima',  'Khan',    '1983-02-11','Female','AB-','9800000000','fatima.k@email.com','Aminabad, Lucknow', 'Imran Khan',    '9800000001', NULL, 'Migraine');

INSERT INTO patient_admissions (patient_id,room_id,admitted_by,admission_date,diagnosis,status) VALUES
(1,2,1,NOW() - INTERVAL 10 DAY,'Acute Myocardial Infarction','Admitted'),
(3,5,3,NOW() - INTERVAL 6 DAY, 'Fractured Femur','Admitted'),
(5,9,1,NOW() - INTERVAL 2 DAY, 'Chest Pain - Under Observation','Admitted');

INSERT INTO appointments (patient_id,doctor_id,appointment_date,appointment_time,reason,status) VALUES
(2,1,CURDATE(),                   '10:00:00','Routine cardiac checkup','Scheduled'),
(4,2,CURDATE(),                   '11:30:00','Recurring headaches','Scheduled'),
(2,3,CURDATE() + INTERVAL 1 DAY,  '09:00:00','Knee pain follow-up','Scheduled'),
(1,1,CURDATE() - INTERVAL 12 DAY, '10:00:00','Initial consultation','Completed'),
(3,3,CURDATE() - INTERVAL 8 DAY,  '09:30:00','Pre-surgery assessment','Completed'),
(6,2,CURDATE() - INTERVAL 20 DAY, '12:00:00','Dizziness','Completed'),
(7,4,CURDATE() - INTERVAL 5 DAY,  '16:00:00','Fever and cough','No-Show'),
(8,1,CURDATE() - INTERVAL 3 DAY,  '10:30:00','Blood pressure review','Completed'),
(9,4,CURDATE() + INTERVAL 2 DAY,  '11:00:00','Asthma follow-up','Scheduled'),
(10,2,CURDATE() - INTERVAL 15 DAY,'14:00:00','Migraine','Cancelled'),
(6,1,CURDATE(),                   '15:00:00','Palpitations','Scheduled');

-- One medicine is already expired and one expires soon on purpose,
-- so expiry warnings have something to show.
INSERT INTO medicines (name,generic_name,category,manufacturer,unit,unit_price,stock_qty,reorder_level,expiry_date) VALUES
('Aspirin 75mg',    'Aspirin',          'Antiplatelet','Sun Pharma',    'Tablet', 2.50, 500, 50, CURDATE() + INTERVAL 15 MONTH),
('Atorvastatin 20mg','Atorvastatin',    'Statin',      'Cipla',         'Tablet', 8.00, 300, 30, CURDATE() + INTERVAL 9 MONTH),
('Metformin 500mg', 'Metformin HCl',   'Antidiabetic','Dr. Reddys',    'Tablet', 3.50, 200, 25, CURDATE() - INTERVAL 7 DAY),
('Paracetamol 500mg','Paracetamol',    'Analgesic',   'GSK India',     'Tablet', 1.50, 800, 100,CURDATE() + INTERVAL 6 MONTH),
('Amoxicillin 500mg','Amoxicillin',    'Antibiotic',  'Mankind Pharma','Capsule',12.00,  15, 20, CURDATE() + INTERVAL 4 MONTH),
('Normal Saline 500ml','Sodium Chloride','IV Fluid',  'Baxter',        'Bottle',120.00, 60, 15, CURDATE() + INTERVAL 20 DAY),
('Omeprazole 20mg', 'Omeprazole',      'PPI',         'Torrent Pharma','Capsule',5.00, 400, 40, CURDATE() + INTERVAL 12 MONTH),
('Ceftriaxone 1g',  'Ceftriaxone',     'Antibiotic',  'Sun Pharma',    'Vial', 180.00,   8, 10, CURDATE() + INTERVAL 3 MONTH);

-- Ramesh's bill is past its due date on purpose (overdue example).
INSERT INTO bills (patient_id,admission_id,bill_date,due_date,subtotal,tax,total_amount,paid_amount,status) VALUES
(1,1,NOW() - INTERVAL 10 DAY,CURDATE() - INTERVAL 3 DAY,25000.00,0.00,25000.00,10000.00,'Partial'),
(3,2,NOW() - INTERVAL 6 DAY, CURDATE() + INTERVAL 1 DAY,18000.00,0.00,18000.00,18000.00,'Paid'),
(5,3,NOW() - INTERVAL 2 DAY, CURDATE() + INTERVAL 5 DAY,12000.00,0.00,12000.00,0.00,'Pending');

-- Older, fully paid OPD bills so the revenue chart has history.
INSERT INTO bills (patient_id,bill_date,due_date,subtotal,tax,total_amount,paid_amount,status) VALUES
(2, NOW() - INTERVAL 5 MONTH,               CURDATE() - INTERVAL 5 MONTH + INTERVAL 7 DAY, 3200.00,0.00, 3200.00, 3200.00,'Paid'),
(4, NOW() - INTERVAL 4 MONTH,               CURDATE() - INTERVAL 4 MONTH + INTERVAL 7 DAY, 5400.00,0.00, 5400.00, 5400.00,'Paid'),
(6, NOW() - INTERVAL 3 MONTH,               CURDATE() - INTERVAL 3 MONTH + INTERVAL 7 DAY,22000.00,0.00,22000.00,22000.00,'Paid'),
(8, NOW() - INTERVAL 2 MONTH,               CURDATE() - INTERVAL 2 MONTH + INTERVAL 7 DAY, 7600.00,0.00, 7600.00, 7600.00,'Paid'),
(7, NOW() - INTERVAL 1 MONTH,               CURDATE() - INTERVAL 1 MONTH + INTERVAL 7 DAY, 1800.00,0.00, 1800.00, 1800.00,'Paid'),
(10,NOW() - INTERVAL 1 MONTH - INTERVAL 5 DAY,CURDATE() - INTERVAL 1 MONTH + INTERVAL 2 DAY,9500.00,0.00, 9500.00, 9500.00,'Paid');

INSERT INTO bill_items (bill_id,description,item_type,quantity,unit_price,total_price) VALUES
(1,'ICU Room (4 days)','Room',4,5000.00,20000.00),
(1,'Cardiologist Consultation','Consultation',1,800.00,800.00),
(1,'ECG & Echo','Procedure',2,2100.00,4200.00),
(2,'Single Room (3 days)','Room',3,2200.00,6600.00),
(2,'Orthopaedic Consultation','Consultation',1,700.00,700.00),
(2,'Fracture Surgery','Surgery',1,10000.00,10000.00),
(3,'Emergency Room (2 days)','Room',2,3500.00,7000.00),
(3,'Cardiologist Consultation','Consultation',1,800.00,800.00),
(3,'Medicines & Supplies','Medicine',1,4200.00,4200.00),
(4,'Cardiologist Consultation','Consultation',1,800.00,800.00),
(4,'Lipid profile & blood tests','Lab',1,2400.00,2400.00),
(5,'Neurologist Consultation','Consultation',1,900.00,900.00),
(5,'MRI Brain','Lab',1,4500.00,4500.00),
(6,'Day-care procedure','Procedure',1,18000.00,18000.00),
(6,'Single Room (2 days)','Room',2,2000.00,4000.00),
(7,'Cardiologist Consultation','Consultation',1,800.00,800.00),
(7,'ECG & Echo','Procedure',2,2100.00,4200.00),
(7,'Blood tests','Lab',1,2600.00,2600.00),
(8,'General Consultation','Consultation',1,600.00,600.00),
(8,'Chest X-Ray','Lab',1,1200.00,1200.00),
(9,'Neurologist Consultation','Consultation',1,900.00,900.00),
(9,'EEG','Procedure',1,3600.00,3600.00),
(9,'Medicines & Supplies','Medicine',1,5000.00,5000.00);

INSERT INTO payments (bill_id,amount,payment_date,payment_method,transaction_ref,received_by) VALUES
(1,10000.00,NOW() - INTERVAL 9 DAY,'UPI','UPI-SAMPLE-001',6),
(2,18000.00,NOW(),'Card','CARD-SAMPLE-002',6),
(4, 3200.00,NOW() - INTERVAL 5 MONTH,'Card','CARD-SAMPLE-004',6),
(5, 5400.00,NOW() - INTERVAL 4 MONTH,'UPI','UPI-SAMPLE-005',6),
(6,22000.00,NOW() - INTERVAL 3 MONTH,'Insurance','INS-SAMPLE-006',6),
(7, 7600.00,NOW() - INTERVAL 2 MONTH,'Cash',NULL,6),
(8, 1800.00,NOW() - INTERVAL 1 MONTH,'UPI','UPI-SAMPLE-008',6),
(9, 9500.00,NOW() - INTERVAL 1 MONTH - INTERVAL 5 DAY,'Net Banking','NB-SAMPLE-009',6);

-- Prescriptions: the first one has been dispensed, the others are waiting.
INSERT INTO prescriptions (patient_id,doctor_id,appointment_id,issued_date,notes) VALUES
(1,1,4,   NOW() - INTERVAL 9 DAY,'After heart attack. Continue for one month.'),
(2,1,NULL,NOW() - INTERVAL 1 DAY,'Review after two weeks.'),
(3,3,5,   NOW() - INTERVAL 6 DAY,'Post-surgery pain and infection cover.');

INSERT INTO prescription_items (prescription_id,medicine_id,dosage,frequency,duration_days,qty_prescribed) VALUES
(1,1,'75mg', 'Once daily',        30,30),
(1,2,'20mg', 'At night',          30,30),
(2,4,'500mg','Twice daily',        5,10),
(2,7,'20mg', 'Before breakfast',  14,14),
(3,4,'500mg','Three times daily',  5,15),
(3,8,'1g',   'Once daily (IV)',    5, 5);

INSERT INTO pharmacy_dispensing (prescription_id,medicine_id,dispensed_by,qty_dispensed,dispense_date) VALUES
(1,1,5,30,NOW() - INTERVAL 9 DAY),
(1,2,5,30,NOW() - INTERVAL 9 DAY);

-- ------------------------------------------------------------
-- Ask for a password when signing in (1 = yes, 0 = name or email only).
-- The admin can switch this on the Settings page.
INSERT INTO app_settings (setting_key, setting_value) VALUES ('require_password', '1');

-- DEMO LOGINS (for trying the app only; change these for real use).
-- Staff sign in with their name, e.g. "Shashank Mishra" or just "Shashank":
--   Admin: Shashank Mishra / admin123      Doctor: Arun Sharma / doctor123
--   Nurse: Sunita Singh / nurse123          Pharmacist: Mohit Jain / pharma123
--   Receptionist: Kavita Rao / reception123
-- Passwords are stored as salted hashes, never as plain text.
-- ------------------------------------------------------------
INSERT INTO system_users (staff_id, username, password_hash, role) VALUES
(8,'shashank.mishra','pbkdf2:sha256:600000$xnuO5Up5yGTGvHRu$4697906dba48033519a7c4dc38af726f18588bf255d7c30aaee92930926451e5','Admin'),
(1,'arun.sharma',    'pbkdf2:sha256:600000$N7SUfRBjKBVgtIxS$e9eb8595cfe6030496d91913eff19501b1497f24a4f8c93d2f3fc27009484a5a','Doctor'),
(4,'sunita.singh',   'pbkdf2:sha256:600000$0pDoURDAZCcqVBFD$dc2f8e1ab438d68299f7ade309d02682a0f13a7af29e655e3d90abf0c3e40ba0','Nurse'),
(5,'mohit.jain',     'pbkdf2:sha256:600000$tnbyDgHSyaMg6aF9$5af3358050e256d518c006748a6ae6be62438845bdd63a0136bcc56402efd054','Pharmacist'),
(6,'kavita.rao',     'pbkdf2:sha256:600000$s1lXV87LvMLXOKDf$a5005845155fd4481e7edb0f68de1a2b4dd5b6823d639f9e5c8e58470552dcff','Receptionist');

-- Demo patient portal login:  anita.p@email.com / patient123
INSERT INTO patient_accounts (patient_id, email, password_hash) VALUES
(2,'anita.p@email.com','pbkdf2:sha256:600000$kAZ2C3PgCZqGmON6$4e211dcd20990edfe085f5f004c1edaffe9470329ae7e9c6f5346148ce01978a');

UPDATE appointments SET booked_via='Online' WHERE appointment_id IN (3, 9);

-- END OF SCHEMA
