FastAPI: integrates well with my existing python codebase. No need to rewrite a lot of code, so time is saved. 
- rejected:
	- Node/TypeScript
		- good bc unified, but would have to rewrite everything
		- could actually reconsider bc FHIR is rewriting anyway
	- Django + TRF
		- better for multi-user server-side model. not what this is

SQLAlchemy ORM: Schema currently triplicated. The declarative model of this helps collapse to one. Also, allows for delete cascade. Postgres compatible later

