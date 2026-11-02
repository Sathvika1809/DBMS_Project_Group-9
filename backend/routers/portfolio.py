from fastapi import APIRouter, HTTPException, status
from database import get_db_connection

# MAKE SURE THIS EXACT VARIABLE NAME IS DEFINED
router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

@router.get("/{account_id}")
def get_user_portfolio(account_id: int):
    """
    Fetches account cash balance, positions, and current P&L.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id, user_id, cash_balance, is_house FROM ACCOUNT WHERE account_id = %s;",
                    (account_id,)
                )
                account_row = cur.fetchone()
                
                if not account_row:
                    raise HTTPException(status_code=404, detail="Account not found.")
                
                holdings_query = """
                    SELECT 
                        symbol, 
                        instrument_type, 
                        quantity, 
                        avg_buy_price, 
                        current_price, 
                        unrealized_pnl
                    FROM portfolio_view 
                    WHERE account_id = %s;
                """
                cur.execute(holdings_query, (account_id,))
                holdings_rows = cur.fetchall()
                
                holdings = []
                for row in holdings_rows:
                    holdings.append({
                        "symbol": row[0],
                        "instrument_type": row[1],
                        "quantity": float(row[2]),
                        "avg_buy_price": float(row[3]),
                        "current_price": float(row[4]),
                        "unrealized_pnl": float(row[5])
                    })
                
                return {
                    "account_id": account_row[0],
                    "user_id": account_row[1],
                    "cash_balance": float(account_row[2]),
                    "is_house": account_row[3],
                    "holdings": holdings
                }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch portfolio: {str(e)}"
        )