import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.errors import AppError
from backend.routes.documents import router
from backend.routes.records import router as records_router

logger = logging.getLogger("vendorops")
app = FastAPI(title="VendorOps AI", version="0.1.0")
app.include_router(router)
app.include_router(records_router)


@app.exception_handler(AppError)
async def application_error(request: Request, error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status, content={"error": {"code": error.code, "message": error.message}}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "Required inputs are missing or invalid.",
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    # Exception messages may contain document text, so log only the type.
    logger.error("request_failed exception_type=%s", type(error).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "Processing failed. Please try again."}
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
