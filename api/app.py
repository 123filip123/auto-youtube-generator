"""FastAPI application factory.

Must be started from the repository root: every path in `utils.paths` is
relative to the current working directory by design, so the static mounts and
the pipeline both resolve against the CWD.

    uvicorn api.app:app --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routes import router
from api.runs import RunStore
from utils.paths import GENERATED_DATA_ROOT, OUTPUTS_ROOT, ensure_output_dirs

# The Vite dev server runs on a different origin during development.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

FRONTEND_DIST = Path("frontend/dist")


class SpaFiles(StaticFiles):
    """Static files that fall back to `index.html` for unknown paths.

    The frontend routes client-side, so `/archives` is not a file on disk.
    Plain `StaticFiles` would 404 it, breaking a refresh or a pasted deep
    link. The Vite dev server does this fallback for us; this is the
    equivalent for the production build.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app(*, client=None) -> FastAPI:
    """Build an app rooted at the current working directory.

    A factory rather than a module-level singleton so tests can `chdir` into a
    temp directory first and inject a fake OpenAI client.
    """
    ensure_output_dirs()
    GENERATED_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Auto YouTube Generator", version="1.0.0")
    app.state.run_store = RunStore(client=client)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    # Mounted after the router so /api always wins.
    app.mount("/media/outputs", StaticFiles(directory=OUTPUTS_ROOT), name="media-outputs")
    app.mount(
        "/media/generated_data",
        StaticFiles(directory=GENERATED_DATA_ROOT),
        name="media-archives",
    )

    # Optional: serve a production frontend build if one has been made.
    if FRONTEND_DIST.is_dir():
        app.mount("/", SpaFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
