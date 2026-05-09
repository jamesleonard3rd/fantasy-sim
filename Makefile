PYTHON ?= python
DB_DSN ?= $(DATABASE_URL)

.PHONY: db-init db-init-no-seed db-ping demo type-check check install

install:
	$(PYTHON) -m pip install -r requirements.txt

db-init:
	$(PYTHON) backend/scripts/init_db.py --dsn "$(DB_DSN)"

db-init-no-seed:
	$(PYTHON) backend/scripts/init_db.py --skip-seed --dsn "$(DB_DSN)"

db-ping:
	$(PYTHON) backend/main.py ping --dsn "$(DB_DSN)"

demo:
	$(PYTHON) backend/scripts/demo_generate.py

type-check:
	mypy --explicit-package-bases backend/src/ backend/main.py

check: db-ping type-check
