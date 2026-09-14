"""WebSocket - 파이프라인 실시간 진행률"""
import asyncio, uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(tags=["WebSocket"])

@router.websocket("/ws/pipeline/{project_id}")
async def pipeline_ws(websocket: WebSocket, project_id: uuid.UUID):
    await websocket.accept()
    logger.info(f"[WS] 연결: {project_id}")
    last_progress = -1
    try:
        while True:
            from app.db.session import AsyncSessionLocal
            from app.db.models.project import Project, JobStatus
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(Project).where(Project.id == project_id))
                project = r.scalar_one_or_none()
            if not project:
                await websocket.send_json({"type": "error", "data": {"message": "프로젝트 없음"}})
                break
            if project.progress != last_progress:
                await websocket.send_json({"type": "progress", "data": {
                    "progress": project.progress, "step": project.current_step, "status": project.status}})
                last_progress = project.progress
            if project.status == JobStatus.SUCCESS:
                await websocket.send_json({"type": "completed", "data": {"project_id": str(project.id)}})
                break
            if project.status == JobStatus.FAILED:
                await websocket.send_json({"type": "error", "data": {"message": project.error_message or "오류"}})
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info(f"[WS] 종료: {project_id}")
    except Exception as e:
        logger.error(f"[WS] 오류: {e}")
        try:
            await websocket.send_json({"type": "error", "data": {"message": str(e)}})
        except Exception:
            pass
