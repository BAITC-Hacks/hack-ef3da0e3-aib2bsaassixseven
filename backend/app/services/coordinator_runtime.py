"""Discover persisted meetings and schedule one coordinator step at a time."""

import asyncio
import logging
from typing import Protocol
from uuid import UUID

from app.services.artifact_store import (
    ArtifactIntegrityError,
    LocalArtifactStore,
    MeetingNotFound,
    UnsafePath,
)
from app.services.coordinator import CoordinatorStorageError
from app.services.local_janitor import LocalJanitor

logger = logging.getLogger(__name__)


class CoordinatorStep(Protocol):
    async def process_once(self, owner_id: UUID, meeting_id: UUID) -> object: ...


class CoordinatorRuntime:
    def __init__(self, store: LocalArtifactStore, coordinator: CoordinatorStep) -> None:
        self.store = store
        self.coordinator = coordinator
        self.janitor = LocalJanitor(store)
        self._tick_lock = asyncio.Lock()

    async def run_forever(self, poll_interval: float) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.error("Coordinator scan failed; will retry")
            await asyncio.sleep(poll_interval)

    def _meeting_ids(self) -> list[tuple[UUID, UUID]]:
        users = self.store.root / "users"
        if not users.is_dir() or users.is_symlink():
            return []
        identities: list[tuple[UUID, UUID]] = []
        for owner_dir in users.iterdir():
            if not owner_dir.is_dir() or owner_dir.is_symlink():
                continue
            try:
                owner_id = UUID(owner_dir.name)
            except ValueError:
                continue
            meetings_dir = owner_dir / "meetings"
            if not meetings_dir.is_dir() or meetings_dir.is_symlink():
                continue
            for meeting_dir in meetings_dir.iterdir():
                if not meeting_dir.is_dir() or meeting_dir.is_symlink():
                    continue
                try:
                    meeting_id = UUID(meeting_dir.name)
                except ValueError:
                    continue
                identities.append((owner_id, meeting_id))
        return identities

    async def tick(self) -> None:
        async with self._tick_lock:
            with self.store.coordinator_lock() as acquired:
                if not acquired:
                    return
                self.janitor.sweep()
                for owner_id, meeting_id in self._meeting_ids():
                    try:
                        with self.store.lifecycle_lock(
                            owner_id, meeting_id, blocking=False
                        ) as acquired:
                            if not acquired:
                                continue
                            meeting = self.store.read_meeting(owner_id, meeting_id)
                            pending_failed_job = meeting.status == "failed" and any(
                                job.job_id is not None
                                and job.cleanup_status == "pending"
                                for job in self.store.read_record(
                                    owner_id, meeting_id
                                ).jobs
                            )
                            if (
                                meeting.status in {"queued", "processing"}
                                or (
                                    meeting.status in {"review_required", "approved"}
                                    and meeting.cleanup_status == "pending"
                                )
                                or pending_failed_job
                            ):
                                await self.coordinator.process_once(
                                    owner_id, meeting_id
                                )
                    except (
                        MeetingNotFound,
                        ArtifactIntegrityError,
                        UnsafePath,
                        OSError,
                        CoordinatorStorageError,
                    ):
                        continue
                    except Exception:
                        logger.error(
                            "Coordinator step failed for meeting %s", meeting_id
                        )
