from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from database import pool, get_db_connection
from routers import orders, portfolio

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    print("Database connection pool established.")
    yield
    pool.close()
    print("Database connection pool closed.")

app = FastAPI(
    title="Paper-Trading Exchange API",
    description="CS F212 Database Systems — Backend API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(orders.router)
app.include_router(portfolio.router)

@app.get("/")
def read_root():
    return {"message": "Paper-Trading Exchange Backend API is running."}

@app.get("/health")
def db_health_check():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM INSTRUMENT;")
                count = cur.fetchone()[0]
                return {
                    "status": "healthy",
                    "database": "connected",
                    "total_instruments": count
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")