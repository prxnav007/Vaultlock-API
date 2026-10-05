import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import analytics, dashboard, health, merchants, payments
from app.core.config import settings
from app.db.session import engine
from ml.inference import ChurnModel, ModelContractError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # Fail fast, without echoing the driver error (it carries the host
        # and user).
        raise RuntimeError(
            "Startup failed: could not connect to PostgreSQL. "
            "Check that the database is running and that the POSTGRES_* "
            "settings are correct."
        ) from None

    # Load the trained model once, here. Training is an offline concern and must
    # never happen in the request path.
    app.state.churn_model = None
    try:
        app.state.churn_model = ChurnModel.load(
            settings.MODEL_PATH, settings.MODEL_METADATA_PATH
        )
        metadata = app.state.churn_model.metadata
        logger.info(
            "loaded churn model %s with %d features, threshold %.2f",
            metadata.model_version,
            len(metadata.feature_names),
            metadata.classification_threshold,
        )
    except ModelContractError as exc:
        if settings.REQUIRE_MODEL:
            raise RuntimeError(
                f"Startup failed: {exc}. Run the offline pipeline "
                "(scripts/run_pipeline.sh), or set REQUIRE_MODEL=false to run "
                "without the churn-risk endpoint."
            ) from None
        logger.warning("churn model unavailable, /churn-risk will return 503: %s", exc)

    yield

    app.state.churn_model = None
    await engine.dispose()


app = FastAPI(title="vault-api", lifespan=lifespan)
app.include_router(health.router)
app.include_router(merchants.router)
app.include_router(payments.router)
app.include_router(analytics.router)
app.include_router(dashboard.router)
