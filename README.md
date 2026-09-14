# SnapAsset3D v2.1

> 다각도 사진 → 고정밀 3D 메쉬 + 단일 이미지 → 스마트 메시 (TripoSG/TripoSF)

Tripo 스타일의 공개 갤러리, 카테고리 분류, 좋아요, 개인 프로젝트 관리, JWT 인증을 포함한 풀스택 3D 생성 플랫폼.

## 두 가지 생성 모드

| 모드 | 입력 | 시간 | 백엔드 |
|---|---|---|---|
| **스마트 메시** | 이미지 1장 | 1~3분 | TripoSG + TripoSF |
| **고정밀** | 다각도 20~60장 / 360° 동영상 | 30~60분 | BiRefNet → COLMAP → SuGaR/GOF/NeRF |

## 파이프라인 (고정밀)
```
📷 다각도 사진 → 🎭 배경 분리(BiRefNet) → 📍 COLMAP → ✨ SuGaR/GOF/NeRF → 🎯 GLB+OBJ+PLY
```

## 파이프라인 (스마트 메시)
```
🖼 단일 이미지 → 🎭 BiRefNet (자동) → ⚡ TripoSG → (옵션) TripoSF → 🎯 GLB+OBJ
```

## 빠른 시작 (Windows + Docker Desktop)

```powershell
# 1) 환경 변수 준비
cp .env.example .env
# .env 의 JWT_SECRET_KEY 를 새 값으로 교체 (필수!)
#   PowerShell: -join ((1..32) | % { '{0:X2}' -f (Get-Random -Max 256) })

# 2) 기본 서비스 (DB / Storage / 백엔드 / 프론트)
docker compose build backend frontend celery_worker
docker compose up -d postgres redis minio backend celery_worker frontend nginx

# 3) 경량 워커
docker compose build pattern_bg colmap_worker
docker compose up -d pattern_bg colmap_worker

# 4) GPU 워커 (각각 ~30분 첫 빌드)
docker compose build bg_removal && docker compose up -d bg_removal
docker compose build sugar_worker && docker compose up -d sugar_worker
docker compose build gof_worker  && docker compose up -d gof_worker
docker compose build nerf_worker && docker compose up -d nerf_worker

# 5) 신규: TripoSG/TripoSF 워커 (첫 추론 시 HF 가중치 ~6GB 자동 다운로드)
docker compose build tripo_worker
docker compose up -d tripo_worker
```

브라우저: <http://localhost> (nginx) 또는 <http://localhost:3000> (vite dev)

### 가중치 미리 다운로드 (선택)

방화벽이 막힌 환경이면 빌드 직후 미리 받아두면 좋다.

```powershell
docker compose run --rm tripo_worker python -c "from huggingface_hub import snapshot_download; snapshot_download('VAST-AI/TripoSG', local_dir='/weights/triposg')"
docker compose run --rm tripo_worker python -c "from huggingface_hub import snapshot_download; snapshot_download('VAST-AI/TripoSF', local_dir='/weights/triposf')"
```

## 헬스 체크
```powershell
curl http://localhost:8000/health    # backend
curl http://localhost:8010/health    # bg_removal
curl http://localhost:8013/health    # sugar
curl http://localhost:8017/health    # tripo
```

## 신규 API (인증 / 갤러리)

- `POST /api/v1/auth/register` — 회원가입
- `POST /api/v1/auth/login` — 로그인 (JWT 발급)
- `GET  /api/v1/auth/me` — 현재 사용자
- `GET  /api/v1/gallery` — 공개 갤러리 (카테고리/정렬)
- `GET  /api/v1/gallery/categories` — 카테고리별 카운트
- `POST /api/v1/projects/{id}/like` — 좋아요 토글 (로그인 필요)
- `PATCH /api/v1/projects/{id}` — 공개/카테고리/이름 변경

## 보안 노트
- 비밀번호는 **bcrypt 12 rounds** 해시 저장. 평문은 로깅하지 않음.
- JWT 는 access-only, 만료 7일. `JWT_SECRET_KEY` 환경변수로 비밀 분리.
- 로그인 실패 메시지는 통합("이메일/사용자명 또는 비밀번호가 올바르지 않습니다") → 사용자 enumeration 방어.
- 비공개 프로젝트는 본인 또는 admin 외에는 GET 403.
- 좋아요는 (user_id, project_id) UNIQUE 제약으로 중복 차단.

## 권장 촬영 (고정밀)
- 수평 360°: 10도 간격 36장
- 위 45°: 30도 간격 12장
- 아래 45°: 30도 간격 12장
- 총 권장: 60장 (최소 20장)
- 흰 배경 또는 단색 배경

## VRAM 가이드
- BiRefNet ~2 GB
- SuGaR / GOF ~10~12 GB
- NeRF ~12~16 GB
- **TripoSG fp16 ~6 GB** (옵션 TripoSF 활성화 시 +4 GB)

## 트러블슈팅
- **TripoSG 가중치 다운로드 실패**: `docker compose logs tripo_worker` 에서 HF 토큰/네트워크 오류 확인.
- **TripoSG pip 설치 실패**: 워커는 diffusers `DiffusionPipeline.from_pretrained(trust_remote_code=True)` 로 폴백.
- **DB enum 오류**: `tripo` 값이 빠진 경우 백엔드 startup 시 자동 `ALTER TYPE ... ADD VALUE`.
- **CORS / WebSocket**: nginx 경유 (port 80) 권장. vite dev 는 `/api`, `/ws` 모두 proxy.
