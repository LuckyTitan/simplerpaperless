import enum
from typing import Literal
from typing import Self
from typing import TypeAlias
from typing import TypedDict



class ProgressStatusOptions(enum.StrEnum):
    STARTED = "STARTED"
    WORKING = "WORKING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PermissionsData(TypedDict, total=False):
    """Permission fields included in status messages for access control."""

    owner_id: int | None
    users_can_view: list[int]
    groups_can_view: list[int]


class ProgressUpdateData(TypedDict):
    filename: str | None
    task_id: str | None
    current_progress: int
    max_progress: int
    status: str
    message: str
    document_id: int | None
    owner_id: int | None
    users_can_view: list[int]
    groups_can_view: list[int]


class StatusUpdatePayload(TypedDict):
    type: Literal["status_update"]
    data: ProgressUpdateData


class DocumentsDeletedData(TypedDict):
    documents: list[int]


class DocumentsDeletedPayload(TypedDict):
    type: Literal["documents_deleted"]
    data: DocumentsDeletedData


class DocumentUpdatedData(TypedDict):
    document_id: int
    modified: str
    owner_id: int | None
    users_can_view: list[int]
    groups_can_view: list[int]


class DocumentUpdatedPayload(TypedDict):
    type: Literal["document_updated"]
    data: DocumentUpdatedData


WebsocketPayload: TypeAlias = (
    StatusUpdatePayload | DocumentsDeletedPayload | DocumentUpdatedPayload
)


class BaseStatusManager:
    """
    Live push updates (websockets) were removed together with Redis. The UI polls
    the API instead, so sending a status is a no-op that keeps the call sites intact.
    """

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        pass

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send(self, payload: WebsocketPayload) -> None:
        pass


class ProgressManager(BaseStatusManager):
    def __init__(self, filename: str | None = None, task_id: str | None = None) -> None:
        super().__init__()
        self.filename = filename
        self.task_id = task_id

    def send_progress(
        self,
        status: ProgressStatusOptions,
        message: str,
        current_progress: int,
        max_progress: int,
        *,
        document_id: int | None = None,
        owner_id: int | None = None,
        users_can_view: list[int] | None = None,
        groups_can_view: list[int] | None = None,
    ) -> None:
        data: ProgressUpdateData = {
            "filename": self.filename,
            "task_id": self.task_id,
            "current_progress": current_progress,
            "max_progress": max_progress,
            "status": status,
            "message": message,
            "document_id": document_id,
            "owner_id": owner_id,
            "users_can_view": users_can_view or [],
            "groups_can_view": groups_can_view or [],
        }
        payload: StatusUpdatePayload = {"type": "status_update", "data": data}
        self.send(payload)


class DocumentsStatusManager(BaseStatusManager):
    def send_documents_deleted(self, documents: list[int]) -> None:
        payload: DocumentsDeletedPayload = {
            "type": "documents_deleted",
            "data": {
                "documents": documents,
            },
        }
        self.send(payload)

    def send_document_updated(
        self,
        *,
        document_id: int,
        modified: str,
        owner_id: int | None = None,
        users_can_view: list[int] | None = None,
        groups_can_view: list[int] | None = None,
    ) -> None:
        payload: DocumentUpdatedPayload = {
            "type": "document_updated",
            "data": {
                "document_id": document_id,
                "modified": modified,
                "owner_id": owner_id,
                "users_can_view": users_can_view or [],
                "groups_can_view": groups_can_view or [],
            },
        }
        self.send(payload)
