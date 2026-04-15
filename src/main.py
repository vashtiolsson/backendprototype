
from data.csn_record import CSN_RECORD
from logic.engine import register_org_data, run_pipeline


def main() -> None:
    category = "income"

    # register mock source data
    register_org_data("CSN", CSN_RECORD)

    # run pipeline
    result = run_pipeline(category)

    print("\n=== PIPELINE RESULT ===")
    print(f"Category: {category}")
    for concept, value in result.items():
        print(f"{concept}: {value}")


if __name__ == "__main__":
    main()