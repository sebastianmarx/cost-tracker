.PHONY: test lint build plan deploy deploy-infra deploy-frontend scrape-now dev

VENV := backend/.venv/bin

test:
	cd backend && ./.venv/bin/python -m pytest -q
	cd frontend && npm run check

lint:
	cd backend && ./.venv/bin/ruff check . && ./.venv/bin/ruff format --check .
	terraform -chdir=infra fmt -check -recursive

build:
	./scripts/build_lambda.sh
	cd frontend && npm run build

plan:
	./scripts/build_lambda.sh
	terraform -chdir=infra plan -var-file=envs/prod.tfvars

deploy:
	./scripts/deploy.sh

deploy-infra:
	./scripts/deploy.sh infra

deploy-frontend:
	./scripts/deploy.sh frontend

scrape-now:
	./scripts/scrape_now.sh

dev:
	cd frontend && npm run dev
