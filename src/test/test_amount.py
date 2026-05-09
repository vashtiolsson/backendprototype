from decimal import Decimal

from models.amount import MonetaryAmount, Frequency, ValueContext


amount = MonetaryAmount(
    value=Decimal("12500"),
    currency="SEK",
    frequency=Frequency.MONTH,
    context=ValueContext.GROSS,
    source_file="fk_payment.csv",
    source_field="gross_sek",
    source_record_id="row_1",
)

print(amount)

print(amount.model_dump())


class Frequency(str, Enum):
    """Mirrors :Frequency individuals in the ontology."""
    WEEK  = "Week"
    MONTH = "Month"
    TOTAL = "Total"

