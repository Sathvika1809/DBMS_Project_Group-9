from fastapi import APIRouter, HTTPException

from database import get_db_connection

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


@router.get("")
@router.get("/", include_in_schema=False)
def list_accounts():
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT a.account_id, u.name, a.account_type, a.cash_balance
              FROM ACCOUNT a JOIN "USER" u ON u.user_id = a.user_id
             ORDER BY a.account_id
            """
        ).fetchall()


@router.get("/{account_id}/portfolio")
def get_portfolio(account_id: int):
    """Cash, positions and unrealized P&L (reads portfolio_view)."""
    with get_db_connection() as conn:
        account = conn.execute(
            "SELECT account_id, user_id, cash_balance, account_type FROM ACCOUNT WHERE account_id = %s",
            (account_id,),
        ).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
        holdings = conn.execute(
            """
            SELECT instrument_id, symbol, instrument_type, quantity, avg_buy_price,
                   current_price, market_value, unrealized_pnl
              FROM portfolio_view WHERE account_id = %s ORDER BY symbol
            """,
            (account_id,),
        ).fetchall()
    market_value = sum(h["market_value"] for h in holdings)
    return {
        **account,
        "is_house": account["account_type"] == "HOUSE",
        "holdings": holdings,
        "market_value": market_value,
        "total_equity": account["cash_balance"] + market_value,
        "unrealized_pnl": sum(h["unrealized_pnl"] for h in holdings),
    }


@router.get("/{account_id}/ledger")
def get_ledger(account_id: int, limit: int = 50):
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT ledger_id, entry_type, amount, trade_id, instrument_id, value_date, created_at
              FROM CASH_LEDGER WHERE account_id = %s ORDER BY ledger_id DESC LIMIT %s
            """,
            (account_id, limit),
        ).fetchall()
