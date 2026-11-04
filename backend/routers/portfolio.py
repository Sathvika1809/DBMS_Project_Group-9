from fastapi import APIRouter, HTTPException, status
from database import get_db_connection

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


@router.get("/{account_id}")
def get_user_portfolio(account_id: int):
    """Account cash balance, positions, and unrealized P&L (via portfolio_view)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id, user_id, cash_balance, account_type "
                    "FROM ACCOUNT WHERE account_id = %s;",
                    (account_id,),
                )
                account_row = cur.fetchone()
                if not account_row:
                    raise HTTPException(status_code=404, detail="Account not found.")

                cur.execute(
                    """
                    SELECT symbol, instrument_type, quantity, avg_buy_price,
                           current_price, unrealized_pnl
                    FROM portfolio_view
                    WHERE account_id = %s;
                    """,
                    (account_id,),
                )
                holdings = [
                    {
                        "symbol": r[0],
                        "instrument_type": r[1],
                        "quantity": float(r[2]),
                        "avg_buy_price": float(r[3]),
                        "current_price": float(r[4]),
                        "unrealized_pnl": float(r[5]),
                    }
                    for r in cur.fetchall()
                ]

                return {
                    "account_id": account_row[0],
                    "user_id": account_row[1],
                    "cash_balance": float(account_row[2]),
                    "account_type": account_row[3],
                    "is_house": account_row[3] == "HOUSE",
                    "holdings": holdings,
                }

    except HTTPException:
        raise  # keep the 404 instead of turning it into a 500
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch portfolio: {str(e)}",
        )