.PHONY: help test lint compose-check build-v5 up-v5 down-v5 health

help:
	@echo "Available targets:"
	@echo "  test        - run v5.0 core tests"
	@echo "  lint        - lint v5.0 core with ruff"
	@echo "  compose-check - validate docker-compose-v5.yml syntax"
	@echo "  build-v5    - build v5.0 traffic-coordinator image"
	@echo "  up-v5       - start v5.0 stack in detached mode"
	@echo "  down-v5     - stop v5.0 stack"
	@echo "  health      - check traffic-coordinator health"

test:
	python -m pytest core/tests/ -q

lint:
	ruff check core/

compose-check:
	docker compose -f docker-compose-v5.yml config

build-v5:
	docker compose -f docker-compose-v5.yml build traffic-coordinator

up-v5:
	docker compose -f docker-compose-v5.yml up -d --build

down-v5:
	docker compose -f docker-compose-v5.yml down

health:
	@curl -s http://localhost:8000/health | python -m json.tool
