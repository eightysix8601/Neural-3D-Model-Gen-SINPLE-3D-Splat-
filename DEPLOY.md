# 로컬 배포 가이드 (Windows + Docker Desktop, NVIDIA GPU 1대)

## 0. 사전 준비

- Docker Desktop 4.30+ (WSL2 백엔드 권장)
- NVIDIA GPU + NVIDIA Container Toolkit (Docker Desktop on Windows 는 WSL2 nvidia-smi 가 동작해야 함)
- 디스크 여유: 빌드 캐시 + 가중치 합쳐 **~60 GB** 권장

## 1. 환경 변수

```powershell
cd C:\Project\figureforge3d_v2
cp .env.example .env
notepad .env
```

**필수 변경**:
- `JWT_SECRET_KEY` — 64자 이상 랜덤 문자열. PowerShell:
  ```powershell
  -join ((1..48) | ForEach-Object { [char]((48..57)+(65..90)+(97..122) | Get-Random) })
  ```
- `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD` — 변경 권장

## 2. 빌드 순서 (분리 빌드로 첫 트래픽 30분~3시간)

### 2-1. 인프라 + 백엔드 (~5분)
```powershell
docker compose build backend frontend celery_worker
docker compose up -d postgres redis minio
docker compose up -d backend celery_worker frontend nginx
```

서비스 확인:
```powershell
curl http://localhost:8000/health
# {"status":"ok",...}
```

DB 마이그레이션은 백엔드 startup 시 `create_all` + enum 패치로 자동.

### 2-2. 경량 워커 (~5분)
```powershell
docker compose build pattern_bg colmap_worker
docker compose up -d pattern_bg colmap_worker
```

### 2-3. GPU 워커 — 한 번에 하나씩 (디스크 캐시 효율)
```powershell
docker compose build bg_removal && docker compose up -d bg_removal
docker compose build sugar_worker && docker compose up -d sugar_worker
docker compose build gof_worker  && docker compose up -d gof_worker
docker compose build nerf_worker && docker compose up -d nerf_worker
```

### 2-4. ⭐ TripoSG/TripoSF 워커 (신규)
```powershell
docker compose build tripo_worker
docker compose up -d tripo_worker

# 첫 호출 시 가중치 자동 다운로드 (~6GB). 미리 받아두려면:
docker compose run --rm tripo_worker python -c `
  "from huggingface_hub import snapshot_download; `
   snapshot_download('VAST-AI/TripoSG', local_dir='/weights/triposg')"
```

## 3. 동작 확인

| 항목 | 방법 |
|---|---|
| 메인 갤러리 | http://localhost |
| 로그인 페이지 | http://localhost/login |
| API 문서 | http://localhost/api/docs |
| MinIO 콘솔 | http://localhost:9001 (계정: `.env` 의 MINIO_ROOT_*) |
| TripoSG 헬스 | `curl http://localhost:8017/health` |

테스트 흐름:
1. 회원가입 → 로그인
2. "스마트 메시 생성" → 이미지 1장 업로드 → 1~3분 후 GLB
3. 내 프로젝트에서 "공개" 토글 → 갤러리에 등장
4. 좋아요 / 다운로드 확인

## 4. 로그 확인

```powershell
docker compose logs -f backend
docker compose logs -f tripo_worker
docker compose logs -f celery_worker
```

## 5. 흔한 문제

### `tripo_worker` 가 OOM 으로 죽을 때
같은 GPU에 SuGaR/NeRF 가 모델을 잡고 있을 가능성. 다음을 시도:
```powershell
docker compose stop sugar_worker gof_worker nerf_worker
# 스마트 메시 테스트가 끝나면 다시 start
```

`TripoSG` 는 fp16 로 약 6GB 만 쓰므로 다른 GPU 워커를 잠시 내리면 안전.

### 가중치 다운로드 실패
- 사내 프록시: `HTTPS_PROXY` 를 `tripo_worker` env 에 추가
- HF rate limit: `HF_TOKEN` 발급 후 env 에 추가
- 수동 받기: 호스트에서 받아 `model_weights` 볼륨에 복사
  ```powershell
  docker run --rm -v figureforge3d_v2_model_weights:/weights `
    python:3.10 pip install huggingface_hub && `
    python -c "..."
  ```

### Tripo 패키지 설치 실패
Dockerfile 의 `pip install git+...` 가 실패해도 워커는 diffusers `trust_remote_code` 폴백을 사용한다. 컨테이너 로그에 `[WARN] TripoSG pip install 실패 → diffusers 폴백 사용` 이 보이면 정상.

### DB 마이그레이션
- 기존 DB 가 있던 경우 `ModelType` enum 에 `tripo` 가 없을 수 있음 → backend startup 에서 `ALTER TYPE ... ADD VALUE IF NOT EXISTS 'TRIPO'` 자동 실행.
- `users`, `likes` 등 새 테이블은 `create_all` (development) 또는 alembic 으로 생성. 운영 환경은 alembic 사용 권장:
  ```powershell
  docker compose exec backend alembic revision --autogenerate -m "users + likes + project cols"
  docker compose exec backend alembic upgrade head
  ```

## 6. 정지 / 재시작

```powershell
docker compose stop tripo_worker            # 단일 워커 정지
docker compose down                          # 전체 정지 (볼륨 유지)
docker compose down -v                       # ⚠️ DB / 가중치 / MinIO 데이터 삭제
```
