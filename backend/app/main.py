import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.api.routes.meetings import MeetingApiError
from app.core.config import get_settings
from app.services.artifact_store import LocalArtifactStore
from app.services.coordinator import MeetingCoordinator
from app.services.coordinator_runtime import CoordinatorRuntime
from app.services.gpu_client import GPUClient


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        if settings.gpu_api_url is None and settings.gpu_api_token is None:
            yield
            return
        if settings.gpu_api_url is None or settings.gpu_api_token is None:
            raise RuntimeError(
                "GPU_API_URL and GPU_API_TOKEN must be configured together"
            )
        store = LocalArtifactStore(settings.data_root)
        async with GPUClient(
            settings.gpu_api_url,
            settings.gpu_api_token.get_secret_value(),
            timeout=settings.gpu_api_timeout_seconds,
        ) as gpu:
            runtime = CoordinatorRuntime(store, MeetingCoordinator(store, gpu))
            application.state.coordinator_runtime = runtime
            task = asyncio.create_task(
                runtime.run_forever(settings.coordinator_poll_seconds)
            )
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    application = FastAPI(title=settings.app_name, lifespan=lifespan)

    @application.exception_handler(MeetingApiError)
    async def meeting_error_handler(
        _request: Request, error: MeetingApiError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail, "code": error.code},
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
