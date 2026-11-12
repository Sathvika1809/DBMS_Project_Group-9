from decimal import Decimal
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from database import db_error_message, get_db_connection

router = APIRouter(prefix="/api/orders", tags=["Orders"])


class OrderCreateRequest(BaseModel):
    account_id: int
    instrument_id: int
    side: Literal["BUY", "SELL"]
    price: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2, description="Limit price")
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=4)


class CancelRequest(BaseModel):
    account_id: int


class ModifyRequest(BaseModel):
    account_id: int
    price: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=4)


@router.post("/", status_code=status.HTTP_201_CREATED)
@router.post("", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def place_and_match_order(order: OrderCreateRequest, unsafe: bool = False):
    proc = "match_and_settle_unsafe" if unsafe else "match_and_settle"
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO "ORDER" (account_id, instrument_id, side, price, qty)
                VALUES (%s, %s, %s, %s, %s) RETURNING order_id
                """,
                (order.account_id, order.instrument_id, order.side, order.price, order.qty),
            ).fetchone()
            order_id = row["order_id"]
            conn.execute(f"CALL {proc}(%s::INT)", (order_id,))
            result = conn.execute(
                'SELECT status, filled_qty FROM "ORDER" WHERE order_id = %s', (order_id,)
            ).fetchone()
            fills = conn.execute(
                "SELECT fill_seq, qty, price FROM ORDER_FILL WHERE order_id = %s ORDER BY fill_seq",
                (order_id,),
            ).fetchall()
        return {
            "order_id": order_id,
            "status": result["status"],
            "filled_qty": result["filled_qty"],
            "fills": fills,
            "mode": "unsafe" if unsafe else "safe",
        }
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=db_error_message(e))


@router.get("/")
@router.get("", include_in_schema=False)
def list_orders(account_id: int, limit: int = 50):
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT o.order_id, i.symbol, o.side, o.price, o.qty, o.filled_qty, o.status, o.created_at
              FROM "ORDER" o JOIN INSTRUMENT i ON i.instrument_id = o.instrument_id
             WHERE o.account_id = %s
             ORDER BY o.order_id DESC LIMIT %s
            """,
            (account_id, limit),
        ).fetchall()


@router.post("/{order_id}/modify")
def modify_order(order_id: int, body: ModifyRequest):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "CALL modify_order(%s::INT, %s::INT, %s::NUMERIC, %s::NUMERIC)",
                (order_id, body.account_id, body.price, body.qty),
            )
            result = conn.execute(
                'SELECT status, filled_qty, price, qty FROM "ORDER" WHERE order_id = %s',
                (order_id,),
            ).fetchone()
        return {"order_id": order_id, **result}
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=db_error_message(e))


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, body: CancelRequest):
    try:
        with get_db_connection() as conn:
            conn.execute("CALL cancel_order(%s::INT, %s::INT)", (order_id, body.account_id))
        return {"order_id": order_id, "status": "CANCELLED"}
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=db_error_message(e))