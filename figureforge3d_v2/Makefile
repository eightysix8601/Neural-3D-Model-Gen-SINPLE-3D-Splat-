.PHONY: up up-ai down build clean logs env reset-db health

up:
	docker compose up postgres redis minio backend celery_worker frontend nginx -d
	@echo "✅ FigureForge3D 시작!"
	@echo "   웹앱  → http://localhost:3000"
	@echo "   API   → http://localhost:8000/api/docs"

up-light:
	docker compose up pattern_bg colmap_worker -d
	@echo "✅ 경량 AI Workers 시작"

up-bg:    ; docker compose up bg_removal -d
up-sugar: ; docker compose up sugar_worker -d
up-gof:   ; docker compose up gof_worker -d
up-all:   ; docker compose up -d

build:
	docker compose build --no-cache backend frontend celery_worker

build-light:
	docker compose build pattern_bg colmap_worker

build-sugar: ; docker compose build --no-cache sugar_worker
build-gof:   ; docker compose build --no-cache gof_worker
build-bg:    ; docker compose build --no-cache bg_removal

down:  ; docker compose down
clean: ; docker compose down -v
env:   ; cp .env.example .env
logs:  ; docker compose logs -f

reset-db:
	docker compose exec postgres psql -U ff3d -d figureforge3d -c \
		"TRUNCATE projects, project_images, assets RESTART IDENTITY CASCADE;"

health:
	@echo "=== 헬스체크 ==="
	@curl -s http://localhost:8000/health  | python3 -m json.tool 2>/dev/null || echo "❌ Backend (8000)"
	@curl -s http://localhost:8010/health  | python3 -m json.tool 2>/dev/null || echo "❌ BG Removal (8010)"
	@curl -s http://localhost:8011/health  | python3 -m json.tool 2>/dev/null || echo "❌ Pattern BG (8011)"
	@curl -s http://localhost:8012/health  | python3 -m json.tool 2>/dev/null || echo "❌ COLMAP (8012)"
	@curl -s http://localhost:8013/health  | python3 -m json.tool 2>/dev/null || echo "❌ SuGaR (8013)"
	@curl -s http://localhost:8014/health  | python3 -m json.tool 2>/dev/null || echo "❌ GOF (8014)"
