# PHR api spec v1

## Enums
- status: "active" | "resolved" | "monitoring"
- body_system: "cardiac" | "respiratory" | "digestive" | "neurological"
  | "musculoskeletal" | "skin" | ...   ← must match body-map region ids
- sex: "male" | "female" | "other"
- flag: "low" | "medium" | "high"
- source: "cardiologist" | "primary doctor" | ...
## Patients:
### GET /patients
List all the patients.
Auth: required (registered user in family)
Query params: sex (optional, enum), relationship (optional, string)
Response 200: {"total": int, "items": [{"id": int, "name": str, "sex": str, "relationship": str, "date_of_birth": date, "emergency_contact": str|null, "notes": str|null, "profile_password_enabled": int, "profile_password_hash": str|null, "profile_password_hint": str|null, "created_at": date, "updated_at": date}]}
Errors: 401 (no/bad token), 404 (no patients), 422 (wrong query params)
### GET /patients/{patient_id}
List one patient info.
Auth: required (registered user in family)
Response 200: {"id": int, "name": str, "sex": str, "relationship": str, "date_of_birth": date, "emergency_contact": str|null, "notes": str|null, "profile_password_enabled": int, "profile_password_hash": str|null, "profile_password_hint": str|null, "created_at": date, "updated_at": date}
Errors: 401 (no/bad token), 404 (patient doesn't exist), 422 (wrong query params)
### POST /patients
Add a patient.
Auth: required (PHR admin)
Request: {"name": str, "sex": str, "relationship": str, "date_of_birth": date, "emergency_contact": str|null, "notes": str|null, "profile_password_enabled": int, "profile_password_hash": str|null, "profile_password_hint": str|null, "created_at": date, "updated_at": date}
Response 201: same + "id"
Errors: 403 (not admin) 401 (no/bad token), 422 (invalid body)
### PUT /patients/{patient_id}
Update patient info.
Auth: required (family member)
Request: { "name": str, "sex": str, "relationship": str, "date_of_birth": date, "emergency_contact": str|null, "notes": str|null, "profile_password_enabled": int, "profile_password_hash": str|null, "profile_password_hint": str|null, "created_at": date, "updated_at": date}
Response 200: same + "id"
Errors: 401, 403, 404, 422 (invalid body)
## Conditions:
### GET /patients/{patient_id}/conditions 
List tracked conditions for one patient. 
Auth: required (family member) 
Query params: body_system (optional, enum), limit (int, default 50), offset (int, default 0) 
Response 200: { "total": int, "items": [ { "id": int, "condition_name": str, "body_system": enum, "status": enum, "noted_date": date|null, "person_id": int, "source": enum|null, "notes": str|null, "created_at": date, "updated_at": date} ] } 
Errors: 401 (no/bad token), 404 (patient not found)
### POST /patients/{patient_id}/conditions 
Write tracked conditions for one patient. 
Auth: required (family member) 
Request: {"condition_name": str, "body_system": enum, "status": enum, "noted_date": date|null, "person_id": int, "source": enum|null, "notes": str|null, "created_at": date, "updated_at": date}

Response 201: same + "id"
Errors: 401 (no/bad token), 404 (patient not found), 422 (bad body)
### GET /patients/{patient_id}/conditions/{condition_id}
Get one condition
Auth: required (family member)
Response 200: {"id": int, "condition_name": str, "body_system": enum, "status": enum, "noted_date": date|null, "person_id": int, "source": enum|null, "notes": str|null, "created_at": date, "updated_at": date}
Errors: 401 (no/bad token), 404 (patient not found, condition not found)
### PUT /patients/{patient_id}/conditions/{condition_id}
Update one condition
Auth: required (family member)
Request: {"condition_name": str, "body_system": enum, "status": enum, "noted_date": date|null, "person_id": int, "source": enum|null, "notes": str|null, "created_at": date, "updated_at": date}
Response 200: same + "id"
Errors: 401 (no/bad token), 404 (patient not found, condition not found) 422 (bad body)

## Lab Results:
### GET /patients/{patient_id}/lab_results
Get one patient's lab results.
Auth: required (family member)
Query params: body_system (optional, enum), flag (optional, enum), limit (int, default 50), offset (int, default 0) 
Response 200: {"total": int, "items": [{"person_id": int, "test_name": str, "flag": enum, "lab_date": date, "result_value": str, "numeric_value": int, "unit": text, "reference_low": int, "reference_high": int, "notes": str, "created_at": date, "updated_at": date}]}
Errors: 401 (no/bad token), 404 (patient not found)
### POST /patients/{patient_id}/lab_results 
Write lab result for one patient. 
Auth: required (family member) 
Request: {"person_id": int, "test_name": str, "flag": enum, "lab_date": date, "result_value": str, "numeric_value": int, "unit": text, "reference_low": int, "reference_high": int, "notes": str, "created_at": date, "updated_at": date}
Response 201: same + "id"
Errors: 401 (no/bad token),404 (patient not found), 422 (bad body)
### GET /patients/{patient_id}/lab_results/{lab_id}
Get one lab
Auth: required (family member)
Response 200: {"id": int, "person_id": int, "test_name": str, "flag": enum, "lab_date": date, "result_value": str, "numeric_value": int, "unit": text, "reference_low": int, "reference_high": int, "notes": str, "created_at": date, "updated_at": date}
Errors: 401 (no/bad token), 404 (patient not found, lab result not found)
### PUT /patients/{patient_id}/lab_results/{lab_id}
Update one lab result
Auth: required (family member)
Request: {"person_id": int, "test_name": str, "flag": enum|null, "lab_date": date, "result_value": str, "numeric_value": int, "unit": str|null, "reference_low": int, "reference_high": int, "notes": str|null, "created_at": date, "updated_at": date}
Response 200: same + "id"}
Errors: 401 (no/bad token), 404 (patient not found, lab result not found) 422 (bad body)