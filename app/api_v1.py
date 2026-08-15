from fastapi import APIRouter
from .api_v1_session import router as session_router
from .api_v1_student import router as student_router
from .api_v1_lesson import router as lesson_router
from .api_v1_interactions import router as interactions_router
from .api_v1_learning import router as learning_router

router = APIRouter(prefix='/api/v1', tags=['api-v1'])
router.include_router(session_router)
router.include_router(student_router)
router.include_router(lesson_router)
router.include_router(interactions_router)
router.include_router(learning_router)
