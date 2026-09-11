# What this is:
This is the backend skeleton of a migration of the Streamlit PHR app to a full stack. The backend is done in SQLAlchemy, FastAPI, but the current app still runs Streamlit. The data is still data/phr.db.

# State as of September 10:
## What exists:
- /health, GET /people, /people/count, GET /people/{id}, POST /people
- the People model, 
- temp-db test fixture with dependency_overrides. 
## What's not built: 
auth, pagination, other resources

# Run:
Run:
```
uv run uvicorn backend.main:app --reload
```
Then go to http://127.0.0.1:8000/docs

# Test:
To run tests, run
```
uv run pytest tests/test_api.py -v
```

The fixture isolates a DB by running a test engine within a function that is connected to a helper with a small seeded database from /tests/test_basic.py. The function has a line ```app.dependency_overrides[get_db] = override_get_db ``` that substitutes override_get_db, a session from the test engine, for all instances of get_db so that the tests are isolated. 

# Next:
Auth (argon2, JWT, ownership), pagination/errors, point one Streamlit page at the API.