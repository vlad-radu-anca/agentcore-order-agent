INFRA := infra
TF    := terraform -chdir=$(INFRA)
VENV  := .venv
# Use the project virtualenv when it exists, so it doesn't need activating.
# CI has no virtualenv and uses the tools on PATH.
BIN   := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/,)

.PHONY: help venv lint fmt test validate check seed ingest chat

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

venv: ## Create .venv with the development dependencies
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements-dev.txt

lint: ## Ruff lint and format check
	$(BIN)ruff check .
	$(BIN)ruff format --check .

fmt: ## Format Python and Terraform
	$(BIN)ruff format .
	$(BIN)ruff check --fix .
	terraform fmt -recursive

test: ## Unit tests with coverage
	$(BIN)pytest

validate: ## terraform fmt and validate, no AWS credentials needed
	terraform fmt -check -recursive
	$(TF) init -backend=false -input=false
	$(TF) validate

check: lint test validate ## Everything CI runs, apart from tflint and trivy

# The targets below need a deployed stack and AWS credentials.

seed: ## Load sample orders and inventory
	$(BIN)python scripts/seed.py \
		--orders-table "$$($(TF) output -raw orders_table)" \
		--inventory-table "$$($(TF) output -raw inventory_table)"

ingest: ## Index the policy documents into the knowledge base
	aws bedrock-agent start-ingestion-job \
		--knowledge-base-id "$$($(TF) output -raw knowledge_base_id)" \
		--data-source-id "$$($(TF) output -raw data_source_id)"

chat: ## Talk to the agent
	$(BIN)python scripts/chat.py --harness-arn "$$($(TF) output -raw harness_arn)"
