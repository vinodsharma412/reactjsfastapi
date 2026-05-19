from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, health, menu, scraping, email_action, stocks
from app.api.v1.endpoints.product_master import product_router, suggestion_router

api_router = APIRouter()
api_router.include_router(auth.router,            prefix="/auth",             tags=["Auth"])
api_router.include_router(users.router,           prefix="/users",            tags=["Users"])
api_router.include_router(menu.router,            prefix="/menus",            tags=["Menus"])
api_router.include_router(health.router,          prefix="/health",           tags=["Health"])
api_router.include_router(scraping.router,        prefix="/scraping",         tags=["Scraping"])
api_router.include_router(email_action.router,    prefix="/email",            tags=["Email"])
api_router.include_router(product_router,         prefix="/products",         tags=["Products"])
api_router.include_router(suggestion_router,      prefix="/word-suggestions", tags=["WordSuggestions"])
api_router.include_router(stocks.router,          prefix="/stocks",           tags=["Stocks"])
