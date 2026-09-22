from fastapi import APIRouter

from app.api.routes.me import router as me_router

api_router = APIRouter()
api_router.include_router(me_router)

