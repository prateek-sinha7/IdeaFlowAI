PYTEST        := uv run pytest
DEFAULT_M     := -m "not e2e and not performance and not live"
OFFLINE_INT_M := -m "integration and not requires_postgres and not requires_postgres_populated_migration"
COV           := --cov=app --cov=agents --cov=tools --cov-branch --cov-report=term-missing

.PHONY: test test-all test-unit test-integration test-integration-pg test-property test-security \
        test-performance test-e2e test-cov test-agents test-app test-tools test-check test-lf

test:               ; $(PYTEST) $(DEFAULT_M)
test-all:           ; $(PYTEST)
test-unit:          ; $(PYTEST) tests/unit
test-integration:   ; $(PYTEST) $(OFFLINE_INT_M)
test-integration-pg:; PYTEST_DATABASE_URL=$(PG_URL) $(PYTEST) tests/integration
test-property:      ; $(PYTEST) tests/property
test-security:      ; $(PYTEST) tests/security
test-performance:   ; $(PYTEST) tests/performance
test-e2e:           ; RUN_LIVE_BEDROCK=1 $(PYTEST) tests/e2e
test-cov:           ; $(PYTEST) $(DEFAULT_M) $(COV) --cov-report=html
test-agents:        ; $(PYTEST) tests/unit/agents tests/integration/agents
test-app:           ; $(PYTEST) tests/unit/app tests/integration/app
test-tools:         ; $(PYTEST) tests/unit/tools tests/property/tools
test-lf:            ; $(PYTEST) --lf
test-check:
	$(PYTEST) --collect-only -q | tail -3
	$(PYTEST) --collect-only -q -m "not unit and not integration and not contract and not e2e and not performance and not security and not property and not smoke" | tail -1
	$(PYTEST) tests/unit -q -x -p no:cacheprovider