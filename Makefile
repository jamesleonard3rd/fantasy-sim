PYTHON ?= python
DB_DSN ?= $(DATABASE_URL)

.PHONY: db-init db-init-no-seed db-ping check

db-init:
	$(PYTHON) -m scripts.init_db --dsn "$(DB_DSN)"

db-init-no-seed:
	$(PYTHON) -m scripts.init_db --skip-seed --dsn "$(DB_DSN)"

db-ping:
	$(PYTHON) main.py ping --dsn "$(DB_DSN)"

# Basic pipeline hook: ensure database reachable
check: db-ping
