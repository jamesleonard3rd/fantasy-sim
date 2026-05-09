PYTHON ?= python
DB_DSN ?= $(DATABASE_URL)

.PHONY: install db-init db-init-no-seed db-ping demo \
        sim-status sim-seed sim-once sim-forever \
        type-check test check

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

db-init:
	$(PYTHON) backend/scripts/init_db.py --dsn "$(DB_DSN)"

db-init-no-seed:
	$(PYTHON) backend/scripts/init_db.py --skip-seed --dsn "$(DB_DSN)"

db-ping:
	$(PYTHON) backend/main.py ping --dsn "$(DB_DSN)"

demo:
	$(PYTHON) backend/scripts/demo_generate.py

# ---- background simulation ----
# All sim commands go through the script shim so they work from a fresh shell
# without setting PYTHONPATH.

sim-status:
	$(PYTHON) backend/scripts/sim.py status

sim-seed:
	$(PYTHON) backend/scripts/sim.py seed-regions

sim-once:
	@if [ -z "$(REGION)" ]; then echo "usage: make sim-once REGION=<id>"; exit 1; fi
	$(PYTHON) backend/scripts/sim.py once --region-id $(REGION)

sim-forever:
	$(PYTHON) backend/scripts/sim.py forever

type-check:
	mypy --explicit-package-bases backend/src/ backend/main.py

test:
	$(PYTHON) -m pytest tests/ -v

check: db-ping type-check test
