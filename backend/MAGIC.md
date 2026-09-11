# The Magic List (behaviors of the app that I once couldn't explain very well):
- TEXT dates / int booleans in the models.py (ORM layer) -> They are converted with the pydantic layer
- relationship() vs a bare foreign key in the db into model transfer. bare foregin keys only. relationships() may be used later to better suit SQLAlchemy
- DB path relative to cwd (breaks under Docker in W13)
- why did i need a backend.main in backend folder -> terminal calls need them.
- profile_password_* fields on people. An auth migration decision for W6
- Schema creation ownership post-strangler (Streamlit db.py vs SQLAlchemy create_all)
- now_iso duplicated from db.py (used in models to get proper time of creation and update); delete the old copy when Streamlit retires.
