"""Analíticas de uso para el administrador (HU-52). No incluye el texto privado suelto."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from chatbot.adapters.inbound.http.auth.guards import require_roles
from chatbot.application.analytics import ReadUsageAnalytics
from chatbot.application.ports.token_verifier import Role
from chatbot.domain.analytics import MAX_PERIOD_DAYS, UsageReport

_ADMIN = [Depends(require_roles(Role.ADMINISTRATOR))]


def _view(report: UsageReport) -> dict[str, object]:
    return {
        "conversationsStarted": report.conversations_started,
        "frequentQuestions": [
            {"text": item.text, "count": item.count} for item in report.frequent_questions
        ],
        "topics": [{"intent": item.intent, "count": item.count} for item in report.topics],
        "resolutionRate": report.resolution_rate,
        "averageResponseMs": report.average_response_ms,
        "satisfaction": report.satisfaction,
        "escalations": report.escalations,
        "keywords": [{"text": item.text, "count": item.count} for item in report.keywords],
        "trend": [
            {"date": point.day.isoformat(), "queries": point.queries, "resolved": point.resolved}
            for point in report.trend
        ],
    }


def analytics_router(reading: ReadUsageAnalytics) -> APIRouter:
    router = APIRouter(prefix="/admin/analytics", tags=["analytics"])

    @router.get("", dependencies=_ADMIN)
    async def read_analytics(
        start: Annotated[datetime, Query(alias="from")],
        end: Annotated[datetime, Query(alias="to")],
    ) -> dict[str, object]:
        if start.tzinfo is None or end.tzinfo is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El periodo debe llevar zona horaria.")
        if end < start:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El periodo termina antes de empezar.")
        if end - start > timedelta(days=MAX_PERIOD_DAYS):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "El periodo no puede pasar de 366 dias.",
            )
        report = await reading.execute(start.astimezone(UTC), end.astimezone(UTC))
        return _view(report)

    return router
