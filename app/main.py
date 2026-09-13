from fastapi import FastAPI
from app.routes import router as order_router

app = FastAPI()

# 注册订单相关的路由
app.include_router(order_router, prefix="/orders", tags=["Orders"])