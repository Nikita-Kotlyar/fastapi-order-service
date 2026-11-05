from fastapi import APIRouter

from app.api import auth_router, health, imports, issues, master_data, orders

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router.router)
api_router.include_router(orders.router)
api_router.include_router(issues.router)
api_router.include_router(master_data.router)
api_router.include_router(imports.router)
