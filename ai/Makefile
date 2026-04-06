SERVICE_DIR := service

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "AI workspace commands (proxy to ai/service/Makefile)"
	@echo ""
	@echo "  make up-build   Build/start AI containers (auto GPU detect)"
	@echo "  make up         Start AI containers (auto GPU detect)"
	@echo "  make down       Stop AI containers"
	@echo "  make ps         Show AI container status"
	@echo "  make logs       Follow aiops-api logs"

.PHONY: up-build up down restart ps logs logs-tail health status shell clean clean-cache network-create preflight-port env
up-build up down restart ps logs logs-tail health status shell clean clean-cache network-create preflight-port env:
	@$(MAKE) -C $(SERVICE_DIR) $@
