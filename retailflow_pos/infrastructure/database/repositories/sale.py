"""
RetailFlow POS - Sales Repository
Specialized queries for sales transactions, line items, and payments.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from infrastructure.database.models.sales import Payment, Sale, SaleLineItem
from infrastructure.database.repositories.base import SqlAlchemyRepository
from shared.pagination import PaginatedResult


class SaleRepository(SqlAlchemyRepository[Sale, int]):
    """Repository for sales transactions."""

    def __init__(self, session: Session):
        super().__init__(session, Sale)

    def generate_transaction_number(self) -> str:
        """Generate a unique sequential transaction number (TXN-YYYYMMDD-XXXX)."""
        today_str = datetime.now().strftime("%Y%m%d")
        prefix = f"TXN-{today_str}-"

        last_sale = (
            self._session.query(Sale)
            .filter(Sale.transaction_number.like(f"{prefix}%"))
            .order_by(Sale.id.desc())
            .first()
        )

        if not last_sale:
            sequence = 1
        else:
            try:
                sequence = int(last_sale.transaction_number.split("-")[-1]) + 1
            except (ValueError, IndexError):
                sequence = 1

        return f"{prefix}{sequence:04d}"

    def get_by_transaction_number(self, txn_number: str) -> Sale | None:
        return (
            self._session.query(Sale)
            .options(
                joinedload(Sale.items),
                joinedload(Sale.payments),
                joinedload(Sale.cashier),
            )
            .filter(Sale.transaction_number == txn_number)
            .first()
        )

    def get_with_details(self, sale_id: int) -> Sale | None:
        return (
            self._session.query(Sale)
            .options(
                joinedload(Sale.items),
                joinedload(Sale.payments),
                joinedload(Sale.cashier),
            )
            .filter(Sale.id == sale_id)
            .first()
        )

    def search(
        self,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResult[Sale]:
        query = self._session.query(Sale)

        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Sale.transaction_number.ilike(like),
                    Sale.payment_method.ilike(like),
                )
            )

        if status:
            query = query.filter(Sale.status == status)

        total = query.count()
        items = (
            query.order_by(Sale.created_at.desc())
            .options(
                joinedload(Sale.items),
                joinedload(Sale.payments),
                joinedload(Sale.cashier),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return PaginatedResult(items=items, total=total, page=page, page_size=page_size)

    def get_today_sales_summary(self) -> tuple[Decimal, int]:
        """Return (total_revenue, transaction_count) for today's completed sales."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = (
            self._session.query(
                func.coalesce(func.sum(Sale.total_amount), 0),
                func.count(Sale.id),
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= today_start,
            )
            .first()
        )

        if result:
            total_rev, count = result
            return Decimal(str(total_rev)), count
        return Decimal("0.00"), 0

    def get_top_selling_products(self, limit: int = 5) -> list[tuple[str, int, Decimal]]:
        """Return top selling products by quantity sold: [(product_name, total_qty, total_revenue), ...]."""
        results = (
            self._session.query(
                SaleLineItem.product_name,
                func.sum(SaleLineItem.quantity).label("total_qty"),
                func.sum(SaleLineItem.subtotal).label("total_rev"),
            )
            .join(Sale, Sale.id == SaleLineItem.sale_id)
            .filter(Sale.status == "COMPLETED")
            .group_by(SaleLineItem.product_name)
            .order_by(func.sum(SaleLineItem.quantity).desc())
            .limit(limit)
            .all()
        )
        return [(r[0], int(r[1]), Decimal(str(r[2]))) for r in results]

    def get_recent_sales(self, limit: int = 5) -> list[Sale]:
        """Return the most recent completed sales."""
        return (
            self._session.query(Sale)
            .options(
                joinedload(Sale.items),
                joinedload(Sale.payments),
            )
            .filter(Sale.status == "COMPLETED")
            .order_by(Sale.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_revenue_trend(self, days: int = 7) -> list[tuple[str, Decimal]]:
        """Return daily revenue for the last N days: [("YYYY-MM-DD", total_rev), ...], including zero days."""
        from datetime import timedelta
        
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days - 1)
        start_date_bound = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        sales = (
            self._session.query(Sale.created_at, Sale.total_amount)
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= start_date_bound
            )
            .all()
        )
        
        # Initialize dictionary with all days set to 0
        trend = {}
        for i in range(days):
            d = (start_date_bound + timedelta(days=i)).strftime("%Y-%m-%d")
            trend[d] = Decimal("0.00")
            
        for created_at, amount in sales:
            if created_at:
                day_str = created_at.strftime("%Y-%m-%d")
                if day_str in trend:
                    trend[day_str] += Decimal(str(amount))
                    
        return sorted([(k, v) for k, v in trend.items()])

    def get_payment_method_breakdown(self) -> list[tuple[str, Decimal]]:
        """Return today's revenue breakdown by payment method: [("CASH", rev), ...]."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        results = (
            self._session.query(
                Sale.payment_method,
                func.sum(Sale.total_amount)
            )
            .filter(
                Sale.status == "COMPLETED",
                Sale.created_at >= today_start
            )
            .group_by(Sale.payment_method)
            .all()
        )
        
        return [(r[0], Decimal(str(r[1] or "0.00"))) for r in results]
