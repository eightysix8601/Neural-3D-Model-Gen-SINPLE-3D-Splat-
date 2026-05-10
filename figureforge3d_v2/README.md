# FigureForge3D v2

> 다각도 사진 → 3D 메쉬 자동 생성 (Zero123++ 제거, 직접 촬영 방식)

## 파이프라인
```
📷 다각도 사진 (최소 20장, 권장 60장)
  ↓ ff3d_bg_removal:8010  (BiRefNet, torch 2.0+cu118)
🎭 배경 분리
  ↓ ff3d_pattern_bg:8011  (CPU only)
📐 패턴 배경 합성
  ↓ ff3d_colmap:8012      (CPU only)
📍 COLMAP 포즈 추정
  ↓
[SuGaR ff3d_sugar:8013] 또는 [GOF ff3d_gof:8014]
  ↓
🎯 GLB + OBJ + PLY 출력
```

## 권장 촬영 방법
- 수평 360°: 10도 간격 36장
- 위 45°: 30도 간격 12장  
- 아래 45°: 30도 간격 12장
- 총 권장: 60장 (최소 20장)
- 흰 배경 또는 단색 배경 사용

## 빠른 시작
```powershell
cp .env.example .env

# 기본 서비스 (5분)
docker compose build backend frontend celery_worker
docker compose up postgres redis minio backend celery_worker frontend nginx -d

# 경량 AI Workers (5분)
docker compose build pattern_bg colmap_worker
docker compose up pattern_bg colmap_worker -d

# GPU Workers (각 ~30분)
docker compose build bg_removal && docker compose up bg_removal -d
docker compose build sugar_worker && docker compose up sugar_worker -d
```

## 헬스체크
```powershell
make health
```
