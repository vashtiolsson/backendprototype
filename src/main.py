from src.transform.support_type import transform_support_type
from src.transform.amount import transform_amount
from src.transform.period import transform_period
from src.transform.status import transform_status
from src.transform.occupation import transform_occupation
from src.transform.person import transform_person

PERSON_ID = "20000421-1234"


def main() -> None:
    print(f"\n=== PIPELINE RESULT for {PERSON_ID} ===\n")

    person = transform_person(PERSON_ID)
    print(f"Person:       {person}")

    support_types = transform_support_type(PERSON_ID)
    print(f"SupportType:  {len(support_types)} record(s)")

    amounts = transform_amount(PERSON_ID)
    print(f"Amount:       {len(amounts)} record(s)")

    periods = transform_period(PERSON_ID)
    print(f"Period:       {len(periods)} record(s)")

    statuses = transform_status(PERSON_ID)
    print(f"Status:       {len(statuses)} record(s)")

    occupations = transform_occupation(PERSON_ID)
    print(f"Occupation:   {len(occupations)} record(s)")


if __name__ == "__main__":
    main()
