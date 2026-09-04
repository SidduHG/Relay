from fastapi import APIRouter
from relay_api.api.v1 import auth, jobs, projects, queues

router = APIRouter()
router.include_router(auth.router)
router.include_router(auth.api_keys_router)
router.include_router(projects.router)
router.include_router(jobs.router)
router.include_router(queues.router)
