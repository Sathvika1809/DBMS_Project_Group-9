import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import db_error_message, get_db_connection, pool
from routers import analytics, market_data, orders, portfolio,simulator

from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(
    title="Paper-Trading Exchange API",
    description="CS F212 Database Systems: thin API over PostgreSQL. The matching engine lives in the database.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router)
app.include_router(simulator.router)
app.include_router(portfolio.router)
app.include_router(market_data.router)
app.include_router(analytics.router)


@app.get("/")
def read_root():
    return {"message": "Paper-Trading Exchange Backend API is running."}


@app.get("/health")
def db_health_check():
    try:
        with get_db_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM INSTRUMENT").fetchone()
        return {"status": "healthy", "database": "connected", "total_instruments": row["n"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {db_error_message(e)}")
