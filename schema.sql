CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date_of_birth TEXT,
    sex TEXT,
    relationship TEXT,
    emergency_contact TEXT,
    notes TEXT,
    profile_password_enabled INTEGER DEFAULT 0,
    profile_password_hash TEXT,
    profile_password_hint TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allergies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    allergen TEXT NOT NULL,
    reaction TEXT,
    severity TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    dose TEXT,
    frequency TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'Active',
    reason TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS lab_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    test_name TEXT NOT NULL,
    result_value TEXT,
    numeric_value REAL,
    unit TEXT,
    reference_low REAL,
    reference_high REAL,
    flag TEXT,
    lab_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS health_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    entry_date TEXT NOT NULL,
    title TEXT NOT NULL,
    body_system TEXT,
    body_part TEXT,
    severity INTEGER,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    title TEXT NOT NULL,
    provider TEXT,
    location TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    reminder_type TEXT NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT DEFAULT 'Upcoming',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS wearable_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    timestamp TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);
CREATE INDEX IF NOT EXISTS idx_allergies_person_allergen ON allergies(person_id, allergen);
CREATE INDEX IF NOT EXISTS idx_medications_person_status_name ON medications(person_id, status, name);
CREATE INDEX IF NOT EXISTS idx_lab_results_person_date ON lab_results(person_id, lab_date);
CREATE INDEX IF NOT EXISTS idx_lab_results_person_test ON lab_results(person_id, test_name);
CREATE INDEX IF NOT EXISTS idx_health_entries_person_date ON health_entries(person_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_appointments_person_date ON appointments(person_id, appointment_date);
CREATE INDEX IF NOT EXISTS idx_reminders_person_due_status ON reminders(person_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_wearable_records_person_timestamp ON wearable_records(person_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_wearable_records_person_metric ON wearable_records(person_id, metric_type);
