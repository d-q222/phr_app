BODY_SYSTEMS = [
    "General",
    "Cardiovascular",
    "Respiratory",
    "Gastrointestinal",
    "Neurologic",
    "Musculoskeletal",
    "Endocrine",
    "Renal/Urinary",
    "Dermatologic",
    "ENT",
    "Ophthalmologic",
    "Mental Health",
    "Reproductive",
    "Immune/Allergy",
    "Oncology",
    "Other",
]

MEDICATION_STATUSES = ["Active", "Paused", "Completed", "Stopped", "Unknown"]
LAB_FLAGS = ["Normal", "High", "Low", "Abnormal", "Critical", "Unknown"]
REMINDER_STATUSES = ["Upcoming", "Completed", "Dismissed", "Overdue"]
APPOINTMENT_STATUSES = ["Scheduled", "Completed", "Canceled", "Missed", "Needs Follow-Up"]
# Who reported a tracked condition. Deliberately one flat list mixing specialty, care setting and
# reporter: that is how a family answers "who told you this." "Self-reported" records provenance --
# what the user entered themselves -- without the app inferring or asserting anything clinical.
CONDITION_SOURCES = [
    "Primary Care",
    "Pediatrician",
    "Allergist / Immunologist",
    "Cardiologist",
    "Dermatologist",
    "Endocrinologist",
    "ENT (Otolaryngologist)",
    "Gastroenterologist",
    "Nephrologist",
    "Neurologist",
    "OB-GYN",
    "Oncologist",
    "Ophthalmologist",
    "Orthopedist",
    "Psychiatrist / Mental Health",
    "Pulmonologist",
    "Rheumatologist",
    "Dentist",
    "Urgent Care",
    "Emergency Department",
    "Hospital / Inpatient",
    "Nurse / Nurse Educator",
    "Registered Dietitian",
    "Physical Therapist",
    "Self-reported",
    "Other",
]

WEARABLE_METRIC_TYPES = [
    "Steps",
    "Heart Rate",
    "Sleep",
    "Weight",
    "Blood Pressure Systolic",
    "Blood Pressure Diastolic",
    "Oxygen Saturation",
    "Temperature",
    "Glucose",
    "Other",
]
