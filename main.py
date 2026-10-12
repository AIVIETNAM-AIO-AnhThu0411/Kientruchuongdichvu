import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from auth import LoginLimiter
from database import Settings, build_engine, check_schema, get_db, load_settings
from routers import auth, users


def create_app(settings: Settings | None = None, engine: Engine | None = None, check_on_start: bool = True) -> FastAPI:
    config = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_engine = engine if engine is not None else build_engine(config)
        app.state.engine = active_engine
        app.state.session_factory = sessionmaker(active_engine, expire_on_commit=False)
        try:
            if check_on_start:
                check_schema(active_engine)
            yield
        finally:
            if engine is None:
                active_engine.dispose()

    app = FastAPI(title='Auth/User Service — Quản lý trọ', version='2.0.1', lifespan=lifespan)
    app.state.settings = config
    app.state.login_limiter = LoginLimiter(config.login_limit)
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins), allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Không phản chiếu password/input hay exception context trong JSON lỗi.
        details = [{'loc': item['loc'], 'msg': item['msg'], 'type': item['type']} for item in error.errors()]
        return JSONResponse(status_code=422, content={'detail': details})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, error: SQLAlchemyError):
        # Không ghi SQL parameters vì có thể chứa password hash hoặc token digest.
        logging.getLogger('auth_service').error('Lỗi database: %s', type(error).__name__)
        return JSONResponse(status_code=503, content={'detail': 'Không xử lý được database. Kiểm tra cấu hình hoặc liên hệ quản trị.'})

    @app.get('/health', tags=['Kiểm tra kết nối'])
    def health(db: Session = Depends(get_db)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok', 'database': 'connected'}

    @app.get('/', include_in_schema=False)
    def home():
        return RedirectResponse('/ui/')

    app.include_router(auth.router)
    app.include_router(users.router)
    app.mount('/ui', StaticFiles(directory=Path(__file__).resolve().parent / 'static', html=True), name='ui')
    return app


app = create_app()
