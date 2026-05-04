"""
Generate synthetic SSBTEK data for three Swedish authority systems.
 
Source responsibilities (per the SSBTEK v11 information specification):
 
  AF  (Public Employment Service)
      - Job-seeker registration status, category, scope, dates (Table 13)
      - Benefit type decision: type and scope only, NO amounts (Table 14)
      - Activity report submission status (Table 15)
 
  FK  (Social Insurance Agency)
      - Case record including benefit group code (Table 26)
      - Activity support case basics: measure type and program (Table 27)
      - Period benefit decision: gross amount, periodicity, scope (Table 38)
      - Payment record: gross + tax + net per payout (Tables 55/56)
 
  CSN (Board of Student Finance)
      - Applied period: dates, pace, loan flag (Table 16)
      - Study support case: support type and form (Table 19)
      - Approved period: week range, study pace, total amount (Table 20)
      - Approved amounts per type: grant (GRUNDB) and loan (GRUNDL) (Table 21)
      - Grant decision summary (derived from Table 20 context)
 
Citizen #0 is always Jane Doe with fixed demo values.
The remaining citizens are randomly generated background data.
"""
 
import csv
import random
from datetime import date, timedelta
from pathlib import Path
from faker import Faker
 
random.seed(42)
fake = Faker("sv_SE")
Faker.seed(42)
 
NUM_CITIZENS = 50
OUT = Path(__file__).parent.parent / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)
 
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def gen_personal_id(birthdate: date) -> str:
    """Swedish personal number format: YYYYMMDD-XXXX"""
    suffix = f"{random.randint(1000, 9999)}"
    return f"{birthdate.strftime('%Y%m%d')}-{suffix}"
 
 
def date_to_iso_week(d: date) -> str:
    """Convert a date to CSN's year-week format: '202617' = week 17 of 2026."""
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}{iso_week:02d}"
 
 
def random_period_2025() -> tuple[date, date]:
    """Random 3-6 month period in 2025."""
    start_month = random.choice([1, 4, 7, 9])
    duration_days = random.choice([90, 120, 180])
    start = date(2025, start_month, 1)
    end = start + timedelta(days=duration_days)
    return start, end
 
 
def random_period_2026() -> tuple[date, date]:
    """Random study period in 2026."""
    start = date(2026, random.choice([1, 4, 8]), random.randint(15, 28))
    end = start + timedelta(weeks=random.randint(10, 20))
    return start, end
 
 
# ── Citizens ──────────────────────────────────────────────────────────────────
 
def generate_citizens(n: int) -> list[dict]:
    """
    Citizen 0 is Jane Doe (fixed demo values).
    Jane is a part-time student who used to receive activity support:
    her AF/FK period ended 2025-12-31 and her CSN study period runs into 2026.
    The rest are randomly generated.
    """
    citizens = [{
        "personal_id": "20000421-1234",
        "name": "Jane Doe",
        "is_job_seeker": True,  # was registered at AF; now de-registered
        "is_student": True,
    }]
    for _ in range(n - 1):
        birthdate = fake.date_of_birth(minimum_age=18, maximum_age=65)
        citizens.append({
            "personal_id": gen_personal_id(birthdate),
            "name": fake.name(),
            "is_job_seeker": random.random() < 0.4,
            "is_student": random.random() < 0.3,
        })
    return citizens
 
 
# ── AF: Public Employment Service ─────────────────────────────────────────────
# AF knows ONLY about registration status, job-seeker category, scope, and
# whether the person has submitted activity reports.
# AF does NOT know benefit amounts — those are owned entirely by FK.
 
def af_job_seeker_status(citizens: list[dict]) -> list[dict]:
    """
    Table 13: Job-seeker registration record.
    Fields: personal_id, registered, category, scope_pct,
            registered_date, deregistered_date, unemployment_fund
    """
    rows = []
    for c in citizens:
        if not c["is_job_seeker"]:
            continue
 
        if c["name"] == "Jane Doe":
            rows.append({
                "personal_id": c["personal_id"],
                # Whether currently registered as job-seeker (boolean)
                "registered": "false",          # de-registered after support period ended
                # Job-seeker category mapped from SKAT code to plain text.
                # "Openly unemployed" covers SKAT codes 11, 96, 97, 98.
                "category": "Openly unemployed",
                # Scope of job-seeking in percent (full-time = 100)
                "scope_pct": 100,
                "registered_date": "2025-09-01",
                "deregistered_date": "2025-12-31",
                # Unemployment fund name is self-reported by the job-seeker and not verified by AF
                "unemployment_fund": "Academics Unemployment Fund",
            })
        else:
            start, end = random_period_2025()
            still_active = end > date.today()
            rows.append({
                "personal_id": c["personal_id"],
                "registered": "true" if still_active else "false",
                "category": random.choice([
                    "Openly unemployed",
                    "Other job-seeker category",
                ]),
                "scope_pct": random.choice([100, 75, 50]),
                "registered_date": start.isoformat(),
                "deregistered_date": "" if still_active else end.isoformat(),
                "unemployment_fund": random.choice([
                    "Academics Unemployment Fund",
                    "Trade Workers Unemployment Fund",
                    "Municipal Workers Unemployment Fund",
                    "IF Metal Unemployment Fund",
                    "",
                ]),
            })
    return rows
 
 
def af_benefit_type_decision(job_seeker_rows: list[dict]) -> list[dict]:
    """
    Table 14: Economic decision record.
    AF records ONLY the type of support and its scope and validity period.
    NO amounts — FK owns all financial figures.
    Fields: personal_id, benefit_type, scope_pct, decision_from, decision_to
    """
    rows = []
    for r in job_seeker_rows:
        rows.append({
            "personal_id": r["personal_id"],
            # Type of benefit decided (not the amount — that belongs to FK)
            "benefit_type": "Activity support",
            "scope_pct": r["scope_pct"],
            "decision_from": r["registered_date"],
            "decision_to": r["deregistered_date"] if r["deregistered_date"] else "",
        })
    return rows
 
 
def af_activity_report(job_seeker_rows: list[dict]) -> list[dict]:
    """
    Table 15: Activity report submission status, one row per calendar month.
    Status codes:
      200 = report submitted on time
      500 = person is not required to report in this period
      501 = report not submitted
      502 = technical error
    Fields: personal_id, report_month, status_code, latest_submission_date
    """
    rows = []
    for r in job_seeker_rows:
        pid = r["personal_id"]
        start = date.fromisoformat(r["registered_date"])
        end_str = r["deregistered_date"] or date.today().isoformat()
        end = date.fromisoformat(end_str)
 
        current = start.replace(day=1)
        while current <= end:
            if pid == "20000421-1234":
                # Jane submitted every report on time
                status_code = 200
                submission_date = (current + timedelta(days=random.randint(20, 27))).isoformat()
            else:
                status_code = random.choices(
                    [200, 500, 501], weights=[0.65, 0.20, 0.15]
                )[0]
                submission_date = (
                    (current + timedelta(days=random.randint(18, 28))).isoformat()
                    if status_code == 200
                    else ""
                )
            rows.append({
                "personal_id": pid,
                "report_month": current.strftime("%Y-%m"),
                "status_code": status_code,
                # Only populated when status_code == 200
                "latest_submission_date": submission_date,
            })
            # Advance one calendar month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    return rows
 
 
# ── FK: Social Insurance Agency ───────────────────────────────────────────────
# FK owns the case, the period benefit decision (with gross amount),
# and the actual payment (gross + tax withheld + net).
# FK does not derive amounts from AF — personal_id is the shared join key.
 
def fk_case(job_seeker_rows: list[dict]) -> list[dict]: #Ärende, 26
    """
    Table 26: Case record.
    Fields: personal_id, case_id, opened_date, active, rejected, benefit_group_code
    """
    rows = []
    for i, r in enumerate(job_seeker_rows):
        rows.append({
            "personal_id": r["personal_id"],
            "case_id": f"FK-AS-{2025_0000 + i:08d}"[-12:],
            "opened_date": r["registered_date"],
            # 1 = active, 0 = closed
            "active": "1" if not r["deregistered_date"] else "0",
            "rejected": "0",
            # FK:AS = Activity support (official FK benefit group code)
            "benefit_group_code": "FK:AS",
        })
    return rows
 
 
def fk_activity_support_details(case_rows: list[dict]) -> list[dict]: #Grunduppgifter aktivitetsstödsärende, 27
    """
    Table 27: Activity support case details.
    Records the specific programme measure the person is assigned to.
    Fields: personal_id, case_id, measure_code, measure_description
    """
    measure_options = [
        ("40",  "Work placement"),
        ("122", "Youth job guarantee"),
        ("123", "Job and development guarantee phase 1"),
        ("124", "Job and development guarantee phase 2"),
        ("130", "Rehabilitation programme"),
    ]
    rows = []
    for r in case_rows:
        if r["personal_id"] == "20000421-1234":
            code, description = ("123", "Job and development guarantee phase 1")
        else:
            code, description = random.choice(measure_options)
        rows.append({
            "personal_id": r["personal_id"],
            "case_id": r["case_id"],
            "measure_code": code,
            "measure_description": description,
        })
    return rows
 
 
def fk_period_benefit_decision(case_rows: list[dict], #Periodersättningsbeslut, 38
                                job_seeker_by_pid: dict) -> list[dict]:
    """
    Table 38: Period benefit decision.
    FK decides and records the gross benefit amount and payment frequency.
    Fields: personal_id, case_id, benefit_type, payment_frequency,
            payment_frequency_label, gross_amount_sek, coordinated_gross_amount_sek,
            scope_pct, decision_from, decision_to, waiting_period
    """
    rows = []
    for r in case_rows:
        pid = r["personal_id"]
        js = job_seeker_by_pid[pid]
        # Jane: 455 SEK/day x 80 days = 36 400 SEK gross total
        gross = 36400 if pid == "20000421-1234" else random.randint(18000, 55000)
        rows.append({
            "personal_id": pid,
            "case_id": r["case_id"],
            "benefit_type": "Activity support",
            # Payment frequency code: 1 = monthly
            "periodicity": 1,
            "periodicity_label": "Monthly",
            "gross_amount_sek": gross,
            # Coordinated gross: same as gross here (no concurrent benefit deduction)
            "coordinated_gross_amount_sek": gross,
            "scope_pct": js["scope_pct"],
            "decision_from": js["registered_date"],
            "decision_to": js["deregistered_date"] if js["deregistered_date"] else "",
            "waiting_period": "None",
        })
    return rows
 
 
def fk_payment(case_rows: list[dict], #Utbetalning,
               period_decision_by_pid: dict) -> list[dict]:
    """
    Tables 55/56: Payment record, one row per monthly payout.
    FK pays the benefit and records gross, tax withheld, and net.
    Fields: personal_id, case_id, payment_date, gross_sek, tax_withheld_sek,
            net_sek, benefit_type
    """
    rows = []
    for r in case_rows:
        pid = r["personal_id"]
        pd = period_decision_by_pid[pid]
        gross_total = pd["gross_amount_sek"]
 
        start = date.fromisoformat(pd["decision_from"])
        end_str = pd["decision_to"] or date.today().isoformat()
        end = date.fromisoformat(end_str)
        months = max(1, round((end - start).days / 30))
 
        monthly_gross = round(gross_total / months)
        monthly_tax = round(monthly_gross * 0.20)
        monthly_net = monthly_gross - monthly_tax
 
        # FK pays around the 25th of each month
        payout_date = start.replace(day=25)
        for _ in range(min(months, 12)):
            rows.append({
                "personal_id": pid,
                "case_id": r["case_id"],
                "payment_date": payout_date.isoformat(),
                "gross_sek": monthly_gross,
                "tax_withheld_sek": monthly_tax,
                "net_sek": monthly_net,
                "benefit_type": "Activity support",
            })
            if payout_date.month == 12:
                payout_date = payout_date.replace(year=payout_date.year + 1, month=1)
            else:
                payout_date = payout_date.replace(month=payout_date.month + 1)
    return rows
 
 
# ── CSN: Board of Student Finance ─────────────────────────────────────────────
# CSN owns everything about study support: application, case, approved period
# (counted in weeks), and approved amounts broken down by grant and loan.
 
def csn_applied_period(citizens: list[dict]) -> list[dict]:
    """
    Table 16: Applied period.
    Fields: personal_id, applied_from, applied_to, applied_scope_pct, loan_applied
    Jane is a part-time distance student at 50% pace.
    """
    rows = []
    for c in citizens:
        if not c["is_student"]:
            continue
        if c["name"] == "Jane Doe":
            rows.append({
                "personal_id": c["personal_id"],
                # CSN uses YYYYMMDD for application dates
                "applied_from": "20260413",
                "applied_to": "20260627",
                "applied_scope_pct": 50,
                # "J" = loan applied for, " " = no loan applied for
                "loan_applied": "J",
            })
        else:
            start, end = random_period_2026()
            rows.append({
                "personal_id": c["personal_id"],
                "applied_from": start.strftime("%Y%m%d"),
                "applied_to": end.strftime("%Y%m%d"),
                "applied_scope_pct": random.choice([100, 75, 50]),
                "loan_applied": random.choice(["J", " "]),
            })
    return rows
 
 
def csn_study_support_case(applied_rows: list[dict]) -> list[dict]:
    """
    Table 19: Study support case record.
    Fields: personal_id, support_type, support_form_code,
            support_form_description, case_status
    """
    rows = []
    for r in applied_rows:
        rows.append({
            "personal_id": r["personal_id"],
            "support_type": "student_grant",
            # GRUND = standard student finance for studies in Sweden (official CSN code)
            "support_form_code": "GRUND",
            "support_form_description": "Student finance for studies in Sweden",
            "case_status": "Initiated",
        })
    return rows
 
 
def csn_approved_period(applied_rows: list[dict]) -> list[dict]:
    """
    Table 20: Approved period.
    CSN counts approved time in WEEKS using YYYYWW format (e.g. 202617 = week 17 of 2026).
    Fields: personal_id, start_week, end_week, study_pace_pct, total_amount_sek
    Jane: weeks 202617-202627, 50% pace, total 18 689 SEK.
    """
    rows = []
    for r in applied_rows:
        pid = r["personal_id"]
        if pid == "20000421-1234":
            rows.append({
                "personal_id": pid,
                "start_week": "202617",
                "end_week": "202627",
                "study_pace_pct": 50,
                # Combined total of all amount types (grant + loan)
                "total_amount_sek": 18689,
            })
        else:
            start = date.fromisoformat(
                r["applied_from"][:4] + "-" +
                r["applied_from"][4:6] + "-" +
                r["applied_from"][6:8]
            )
            end = date.fromisoformat(
                r["applied_to"][:4] + "-" +
                r["applied_to"][4:6] + "-" +
                r["applied_to"][6:8]
            )
            weeks = max(1, (end - start).days // 7)
            rows.append({
                "personal_id": pid,
                "start_week": date_to_iso_week(start),
                "end_week": date_to_iso_week(end),
                "study_pace_pct": r["applied_scope_pct"],
                "total_amount_sek": random.randint(900, 2000) * weeks,
            })
    return rows
 
 
def csn_approved_amounts(approved_period_rows: list[dict]) -> list[dict]:
    """
    Table 21: Approved amounts, one row per amount type.
    GRUNDB and GRUNDL are official CSN codes and are kept as-is.
    Fields: personal_id, amount_type_code, amount_type_label,
            amount_per_week_sek, total_amount_sek
    Jane: GRUNDB 978 SEK/week x 11 weeks = 10 758 SEK
          GRUNDL 721 SEK/week x 11 weeks =  7 931 SEK
    """
    rows = []
    for r in approved_period_rows:
        pid = r["personal_id"]
        if pid == "20000421-1234":
            rows.append({
                "personal_id": pid,
                "amount_type_code": "GRUNDB",
                "amount_type_label": "Grant",
                "amount_per_week_sek": 978,
                "total_amount_sek": 10758,
            })
            rows.append({
                "personal_id": pid,
                "amount_type_code": "GRUNDL",
                "amount_type_label": "Loan",
                "amount_per_week_sek": 721,
                "total_amount_sek": 7931,
            })
        else:
            total = r["total_amount_sek"]
            # Typical split: ~60% grant, ~40% loan
            grant_total = round(total * 0.60)
            loan_total = total - grant_total
            try:
                sw = int(str(r["start_week"])[4:])
                ew = int(str(r["end_week"])[4:])
                sy = int(str(r["start_week"])[:4])
                ey = int(str(r["end_week"])[:4])
                weeks = max(1, (ey - sy) * 52 + (ew - sw))
            except Exception:
                weeks = 10
            rows.append({
                "personal_id": pid,
                "amount_type_code": "GRUNDB",
                "amount_type_label": "Grant",
                "amount_per_week_sek": round(grant_total / weeks),
                "total_amount_sek": grant_total,
            })
            rows.append({
                "personal_id": pid,
                "amount_type_code": "GRUNDL",
                "amount_type_label": "Loan",
                "amount_per_week_sek": round(loan_total / weeks),
                "total_amount_sek": loan_total,
            })
    return rows
 
 
def csn_grant_decision(approved_period_rows: list[dict]) -> list[dict]:
    """
    Grant decision summary (derived from Table 20 context).
    Fields: personal_id, decision_type, study_mode, scope_pct,
            period_start_week, period_end_week, grant_code, status
    """
    rows = []
    for r in approved_period_rows:
        pid = r["personal_id"]
        rows.append({
            "personal_id": pid,
            "decision_type": "Grant",
            "study_mode": "Distance" if pid == "20000421-1234" else random.choice(
                ["Distance", "On-campus", "Hybrid"]
            ),
            "scope_pct": r["study_pace_pct"],
            "period_start_week": r["start_week"],
            "period_end_week": r["end_week"],
            # Official CSN code for the grant component
            "grant_code": "GRUNDB",
            "status": "Initiated",
        })
    return rows
 
 
# ── Write CSVs ────────────────────────────────────────────────────────────────
 
def write_csv(filename: str, rows: list[dict]):
    if not rows:
        print(f"  ! {filename}: no rows, skipping")
        return
    path = OUT / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  + {filename}: {len(rows)} rows")
 
 
def main():
    print(f"Generating SSBTEK v11 synthetic data for {NUM_CITIZENS} citizens...\n")
 
    citizens = generate_citizens(NUM_CITIZENS)
 
    # ── AF ───────────────────────────────────────────────────────────────────
    print("AF (Public Employment Service) — registration, status, and activity reports only:")
    af_js = af_job_seeker_status(citizens)
    write_csv("af_job_seeker_status.csv", af_js)
 
    af_bd = af_benefit_type_decision(af_js)
    write_csv("af_benefit_type_decision.csv", af_bd)
 
    af_ar = af_activity_report(af_js)
    write_csv("af_activity_report.csv", af_ar)
 
    # ── FK ───────────────────────────────────────────────────────────────────
    print("\nFK (Social Insurance Agency) — case, decision, and payments (owns all amounts):")
    js_by_pid = {r["personal_id"]: r for r in af_js}
 
    fk_c = fk_case(af_js)
    write_csv("fk_case.csv", fk_c)
 
    fk_asd = fk_activity_support_details(fk_c)
    write_csv("fk_activity_support_details.csv", fk_asd)
 
    fk_pbd = fk_period_benefit_decision(fk_c, js_by_pid)
    write_csv("fk_period_benefit_decision.csv", fk_pbd)
 
    pbd_by_pid = {r["personal_id"]: r for r in fk_pbd}
    fk_p = fk_payment(fk_c, pbd_by_pid)
    write_csv("fk_payment.csv", fk_p)
 
    # ── CSN ──────────────────────────────────────────────────────────────────
    print("\nCSN (Board of Student Finance) — application, case, approved period and amounts:")
    csn_ap = csn_applied_period(citizens)
    write_csv("csn_applied_period.csv", csn_ap)
 
    csn_ssc = csn_study_support_case(csn_ap)
    write_csv("csn_study_support_case.csv", csn_ssc)
 
    csn_aprd = csn_approved_period(csn_ap)
    write_csv("csn_approved_period.csv", csn_aprd)
 
    csn_aa = csn_approved_amounts(csn_aprd)
    write_csv("csn_approved_amounts.csv", csn_aa)
 
    csn_gd = csn_grant_decision(csn_aprd)
    write_csv("csn_grant_decision.csv", csn_gd)
 
    print(f"\nAll files written to {OUT}/")
    print("\nSource ownership:")
    print("  AF  -> af_job_seeker_status, af_benefit_type_decision, af_activity_report")
    print("  FK  -> fk_case, fk_activity_support_details, fk_period_benefit_decision, fk_payment")
    print("  CSN -> csn_applied_period, csn_study_support_case, csn_approved_period, csn_approved_amounts, csn_grant_decision")
 
 
if __name__ == "__main__":
    main()