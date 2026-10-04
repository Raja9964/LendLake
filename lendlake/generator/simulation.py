"""Month-by-month simulation of a retail lending book.

Every month gets its own RNG stream derived from (seed, year, month), so the
events for a given month never depend on how far ahead we simulate.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from lendlake.dates import add_months, month_end
from lendlake.generator import reference as ref

LATE_FEE_RATE = 0.02
BOUNCE_CHARGE = 500.0
BASE_APPLICATIONS = 400


@dataclass
class Installment:
    number: int
    due_date: date
    amount: float
    remaining: float
    bounces: int = 0


@dataclass
class Loan:
    loan_id: str
    branch_code: str
    region: str
    risk: float
    nach: bool
    emi: float
    last_emi: float
    tenure: int
    first_due: date
    next_installment: int = 1
    unpaid: list[Installment] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return self.next_installment > self.tenure and not self.unpaid

    def due_date(self, number: int) -> date:
        return add_months(self.first_due, number - 1)


def amortization(principal: float, annual_rate: float, tenure: int) -> list[tuple]:
    """Reducing-balance schedule in paise to avoid float drift."""
    r = annual_rate / 1200
    growth = (1 + r) ** tenure
    emi = math.ceil(principal * r * growth / (growth - 1)) * 100
    balance = round(principal * 100)
    rows = []
    for n in range(1, tenure + 1):
        interest = round(balance * r)
        principal_part = balance if n == tenure else min(emi - interest, balance)
        rows.append((n, balance, principal_part + interest, principal_part, interest))
        balance -= principal_part
    return rows


def _paise(value: int) -> str:
    return f"{value / 100:.2f}"


def _ts(day: date, rng: np.random.Generator) -> datetime:
    return datetime(day.year, day.month, day.day) + timedelta(
        hours=int(rng.integers(9, 19)), minutes=int(rng.integers(0, 60))
    )


class LendingSimulator:
    def __init__(self, seed: int, scale: float, start_month: date):
        self.seed = seed
        self.scale = scale
        self.start_month = start_month
        self.customers: dict[str, dict] = {}
        self.loans: list[Loan] = []
        self.rows: dict[str, list[dict]] = defaultdict(list)
        self.seq: dict[str, int] = defaultdict(int)
        self.emit_from = start_month
        self.until = start_month

    def run(self, until: date, emit_from: date) -> dict[str, list[dict]]:
        if until < self.start_month or emit_from < self.start_month:
            raise ValueError(f"history starts at {self.start_month:%Y-%m}")
        self.until, self.emit_from = until, emit_from
        month = self.start_month
        while month <= until:
            rng = np.random.default_rng([self.seed, month.year, month.month])
            self._update_customers(rng, month)
            self._originate(rng, month)
            self._service_loans(rng, month)
            month = add_months(month, 1)
        return self.rows

    def _next_id(self, kind: str) -> int:
        self.seq[kind] += 1
        return self.seq[kind]

    def _emit(self, table: str, row: dict, when: date) -> None:
        arrival = when.replace(day=1)
        if self.emit_from <= arrival <= self.until:
            row["_arrival"] = arrival
            self.rows[table].append(row)

    def _new_customer(self, rng, product: ref.Product, branch: ref.Branch, created: datetime) -> dict:
        female = rng.random() < 0.42
        first = str(rng.choice(ref.FEMALE_NAMES if female else ref.MALE_NAMES))
        last = str(rng.choice(ref.LAST_NAMES))
        city = branch.city if rng.random() < 0.9 else str(rng.choice(list(ref.CITY_PINCODES)))
        state = next((b.state for b in ref.BRANCHES if b.city == city), branch.state)
        employment = "SELF_EMPLOYED" if product.code == "PL_SE" or rng.random() < 0.2 else "SALARIED"
        letters = "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), 3))
        customer_id = f"CIF{self._next_id('customer'):08d}"
        return {
            "customer_id": customer_id,
            "first_name": first,
            "last_name": last,
            "gender": "F" if female else "M",
            "date_of_birth": (created.date() - timedelta(days=int(rng.integers(23 * 365, 58 * 365)))).isoformat(),
            "mobile": str(int(rng.integers(6_000_000_000, 9_999_999_999))),
            "email": f"{first}.{last}{int(rng.integers(1, 999))}@{rng.choice(ref.EMAIL_DOMAINS)}".lower().replace("'", ""),
            "pan": f"{letters}P{last[0].upper()}{int(rng.integers(1000, 9999))}{rng.choice(list('ABCDEFGHJKLMNPRSTUVWXYZ'))}",
            "city": city,
            "state": state,
            "pincode": str(ref.CITY_PINCODES[city] + int(rng.integers(0, 90))),
            "employment_type": employment,
            "annual_income": f"{round(float(rng.lognormal(math.log(900_000), 0.5)), -3):.2f}",
            "credit_score": "",
            "kyc_status": "VERIFIED" if rng.random() < 0.94 else "PENDING",
            "created_at": created.isoformat(sep=" "),
            "updated_at": created.isoformat(sep=" "),
        }

    def _update_customers(self, rng, month: date) -> None:
        existing = [c for c in self.customers.values() if c["created_at"] < month.isoformat()]
        if not existing:
            return
        picks = rng.random(len(existing)) < 0.02
        for customer, picked in zip(existing, picks, strict=True):
            if not picked:
                continue
            change = rng.choice(["relocation", "income", "kyc", "employment"])
            if change == "relocation":
                city = str(rng.choice(list(ref.CITY_PINCODES)))
                customer["city"] = city
                customer["state"] = next(b.state for b in ref.BRANCHES if b.city == city)
                customer["pincode"] = str(ref.CITY_PINCODES[city] + int(rng.integers(0, 90)))
            elif change == "income":
                income = float(customer["annual_income"]) * rng.uniform(1.05, 1.3)
                customer["annual_income"] = f"{round(income, -3):.2f}"
            elif change == "kyc":
                customer["kyc_status"] = "REKYC_DUE" if customer["kyc_status"] == "VERIFIED" else "VERIFIED"
            else:
                customer["employment_type"] = (
                    "SALARIED" if customer["employment_type"] == "SELF_EMPLOYED" else "SELF_EMPLOYED"
                )
            day = month + timedelta(days=int(rng.integers(0, month_end(month).day)))
            customer["updated_at"] = _ts(day, rng).isoformat(sep=" ")
            self._emit("customers", dict(customer), day)

    def _originate(self, rng, month: date) -> None:
        index = (month.year - self.start_month.year) * 12 + month.month - self.start_month.month
        festive = 1.35 if month.month in (10, 11) else 1.15 if month.month == 3 else 1.0
        expected = BASE_APPLICATIONS * self.scale * festive * (1 + 0.015 * index)
        branches = [b for b in ref.BRANCHES if b.opened_on <= month_end(month)]
        weights = np.array([b.weight for b in branches])
        shares = np.array([p.share for p in ref.PRODUCTS])
        days_in_month = month_end(month).day
        returning = list(self.customers)  # repeat borrowers come from earlier months only

        for _ in range(int(rng.poisson(expected))):
            branch = branches[rng.choice(len(branches), p=weights / weights.sum())]
            product = ref.PRODUCTS[rng.choice(len(ref.PRODUCTS), p=shares / shares.sum())]
            applied = _ts(month + timedelta(days=int(rng.integers(0, days_in_month))), rng)

            if returning and rng.random() < 0.06:
                customer = self.customers[returning[rng.integers(len(returning))]]
            else:
                customer = self._new_customer(rng, product, branch, applied - timedelta(minutes=20))
                score = int(np.clip(rng.normal(718, 62), 420, 890))
                customer["credit_score"] = "" if rng.random() < 0.04 else str(score)
                self.customers[customer["customer_id"]] = customer
                self._emit("customers", dict(customer), applied.date())
            score = int(customer["credit_score"] or 680)

            amount = float(np.clip(rng.lognormal(math.log(product.median_amount), product.sigma),
                                   product.min_amount, product.max_amount))
            amount = round(amount, -4 if product.code.startswith("HL") else -3)
            tenure = int(rng.choice(product.tenures))
            app_id = f"APP{month:%y%m}{self._next_id('application'):06d}"
            is_home = product.code.startswith("HL")
            decided = applied + timedelta(days=int(rng.integers(3, 18) if is_home else rng.integers(1, 6)))

            approve_p = 0.93 / (1 + math.exp(-(score - 640) / 32))
            draw = rng.random()
            if draw < 0.03:
                status, reason = "WITHDRAWN", ""
            elif draw < 0.03 + approve_p:
                status, reason = "APPROVED", ""
            else:
                status, reason = "REJECTED", str(rng.choice(ref.REJECTION_REASONS))

            application = {
                "application_id": app_id,
                "customer_id": customer["customer_id"],
                "branch_code": branch.code,
                "product_code": product.code,
                "application_date": applied.date().isoformat(),
                "requested_amount": f"{amount:.2f}",
                "requested_tenure_months": tenure,
                "channel": str(rng.choice(["BRANCH", "DSA", "DIGITAL"], p=[0.5, 0.3, 0.2])),
                "application_status": status,
                "decision_date": decided.date().isoformat(),
                "rejection_reason": reason,
                "updated_at": decided.isoformat(sep=" "),
            }
            if decided.month != applied.month:
                pending = {**application, "application_status": "PENDING", "decision_date": "",
                           "rejection_reason": "", "updated_at": applied.isoformat(sep=" ")}
                self._emit("loan_applications", pending, applied.date())
            self._emit("loan_applications", application, decided.date())

            if status == "APPROVED":
                self._sanction_and_disburse(rng, application, product, branch, score, decided, index)

    def _sanction_and_disburse(self, rng, application, product, branch, score, decided, index) -> None:
        requested = float(application["requested_amount"])
        sanctioned = requested if rng.random() < 0.6 else round(requested * rng.uniform(0.8, 1.0), -3)
        rate = product.base_rate + max(0.0, (760 - score) / 100) * 1.4 + rng.normal(0, 0.2)
        rate = round(float(np.clip(rate, product.base_rate, product.max_rate)), 2)
        tenure = int(application["requested_tenure_months"])
        schedule = amortization(sanctioned, rate, tenure)
        loan_id = f"LN{self._next_id('loan'):09d}"
        sanction_date = decided.date()
        self._emit("sanctions", {
            "sanction_id": f"SAN{self.seq['loan']:09d}",
            "application_id": application["application_id"],
            "loan_id": loan_id,
            "sanction_date": sanction_date.isoformat(),
            "sanctioned_amount": f"{sanctioned:.2f}",
            "interest_rate": f"{rate:.2f}",
            "tenure_months": tenure,
            "emi_amount": _paise(schedule[0][2]),
        }, sanction_date)

        if rng.random() > 0.93:
            return  # sanctioned but never drawn down
        is_home = product.code.startswith("HL")
        disbursed_on = sanction_date + timedelta(days=int(rng.integers(5, 30) if is_home else rng.integers(0, 4)))
        fee_rate = 0.004 if is_home else rng.uniform(0.015, 0.025)
        self._emit("disbursements", {
            "disbursement_id": f"DSB{self.seq['loan']:09d}",
            "loan_id": loan_id,
            "disbursement_date": disbursed_on.isoformat(),
            "disbursed_amount": f"{sanctioned:.2f}",
            "processing_fee": f"{min(sanctioned * fee_rate, 25_000):.2f}",
            "disbursement_mode": str(rng.choice(["RTGS", "CHEQUE"] if is_home else ["NEFT", "IMPS"])),
            "bank_reference": f"UTR{int(rng.integers(10**11, 10**12 - 1))}",
        }, disbursed_on)

        first_due = add_months(disbursed_on.replace(day=int(rng.choice([5, 10, 15]))), 1)
        for n, opening, emi, principal, interest in schedule:
            self._emit("emi_schedule", {
                "loan_id": loan_id,
                "installment_no": n,
                "due_date": add_months(first_due, n - 1).isoformat(),
                "opening_principal": _paise(opening),
                "emi_amount": _paise(emi),
                "principal_component": _paise(principal),
                "interest_component": _paise(interest),
                "closing_principal": _paise(opening - principal),
            }, disbursed_on)

        # Festive-season cohorts were underwritten a little looser.
        vintage = 1.3 if disbursed_on.month in (10, 11) else 1.0
        base_risk = 1 / (1 + math.exp((score - 650) / 45))
        risk = float(np.clip(base_risk * product.risk_factor * vintage + rng.normal(0, 0.03), 0.01, 0.95))
        self.loans.append(Loan(
            loan_id=loan_id, branch_code=branch.code, region=branch.region, risk=risk,
            nach=rng.random() < (0.95 if is_home else 0.85), emi=schedule[0][2] / 100,
            last_emi=schedule[-1][2] / 100, tenure=tenure, first_due=first_due,
        ))

    def _pay(self, loan: Loan, inst: Installment, paid_on: date, amount: float, mode: str,
             rng, settle: bool) -> None:
        penalty = 0.0
        if settle:
            late_fee = round(inst.amount * LATE_FEE_RATE, 2) if paid_on > inst.due_date else 0.0
            penalty = late_fee + inst.bounces * BOUNCE_CHARGE
        row = {
            "payment_id": f"PAY{paid_on:%y%m}{self._next_id('payment'):07d}",
            "loan_id": loan.loan_id,
            "installment_no": inst.number,
            "payment_date": paid_on.isoformat(),
            "amount_paid": f"{amount + penalty:.2f}",
            "penalty_paid": f"{penalty:.2f}",
            "payment_mode": mode,
            "payment_status": "SUCCESS",
            "bounce_reason": "",
        }
        inst.remaining = round(inst.remaining - amount, 2)
        late = paid_on.day >= 26 and rng.random() < 0.15
        self._emit("repayments", row, add_months(paid_on, 1) if late else paid_on)

    def _bounce(self, loan: Loan, inst: Installment, rng) -> None:
        inst.bounces += 1
        self._emit("repayments", {
            "payment_id": f"PAY{inst.due_date:%y%m}{self._next_id('payment'):07d}",
            "loan_id": loan.loan_id,
            "installment_no": inst.number,
            "payment_date": inst.due_date.isoformat(),
            "amount_paid": f"{inst.amount:.2f}",
            "penalty_paid": "0.00",
            "payment_mode": "NACH",
            "payment_status": "BOUNCED",
            "bounce_reason": str(rng.choice(ref.BOUNCE_REASONS)),
        }, inst.due_date)

    def _service_loans(self, rng, month: date) -> None:
        last_day = month_end(month)
        still_open = []
        for loan in self.loans:
            current = None
            arrears = len(loan.unpaid)
            if loan.next_installment <= loan.tenure and loan.due_date(loan.next_installment) <= last_day:
                n = loan.next_installment
                amount = loan.last_emi if n == loan.tenure else loan.emi
                current = Installment(n, loan.due_date(n), amount, amount)
                loan.unpaid.append(current)
                loan.next_installment += 1
            if not loan.unpaid:
                if not loan.closed:
                    still_open.append(loan)
                continue

            u = rng.random(4)
            after_due = current.due_date if current else month
            collected_on = min(after_due + timedelta(days=int(rng.integers(2, 14))), last_day)
            worked = arrears > 0

            if arrears == 0:
                if loan.nach and u[0] < 0.015 + 0.25 * loan.risk:
                    self._bounce(loan, current, rng)
                    worked = True
                    if u[1] < 0.85 - 0.5 * loan.risk:
                        self._pay(loan, current, collected_on, current.remaining,
                                  str(rng.choice(["UPI", "NEFT", "CASH"])), rng, settle=True)
                elif loan.nach:
                    self._pay(loan, current, current.due_date, current.remaining, "NACH", rng, settle=True)
                elif u[0] < 0.01 + 0.15 * loan.risk:
                    worked = True
                else:
                    paid_on = current.due_date if u[1] > 0.12 else collected_on
                    self._pay(loan, current, paid_on, current.remaining,
                              str(rng.choice(["UPI", "NEFT", "CHEQUE"])), rng, settle=True)
            else:
                if loan.nach and current and u[0] < 0.85:
                    self._bounce(loan, current, rng)
                cure = {1: 0.35, 2: 0.22, 3: 0.12}.get(arrears, 0.04) * (1 - 0.6 * loan.risk)
                pay_one = 0.30 if arrears <= 3 else 0.15
                mode = str(rng.choice(["CASH", "UPI", "NEFT"]))
                if u[1] < cure:
                    for inst in list(loan.unpaid):
                        self._pay(loan, inst, collected_on, inst.remaining, mode, rng, settle=True)
                elif u[1] < cure + pay_one:
                    oldest = loan.unpaid[0]
                    self._pay(loan, oldest, collected_on, oldest.remaining, mode, rng, settle=True)
                elif u[1] < cure + pay_one + 0.08:
                    oldest = loan.unpaid[0]
                    part = round(oldest.remaining * rng.uniform(0.3, 0.8), -2)
                    if 0 < part < oldest.remaining:
                        self._pay(loan, oldest, collected_on, part, mode, rng, settle=False)

            loan.unpaid = [i for i in loan.unpaid if i.remaining > 0.005]
            if worked:
                self._collections(rng, loan, month, arrears, collected_on)
            if not loan.closed:
                still_open.append(loan)
        self.loans = still_open

    def _collections(self, rng, loan: Loan, month: date, arrears: int, paid_on: date) -> None:
        last_day = month_end(month)
        actions = ["SMS"] + ["CALL"] * int(rng.integers(1, 3 + arrears))
        if arrears >= 2:
            actions += ["FIELD_VISIT"] * int(rng.integers(1, 3))
        if arrears >= 4 and rng.random() < 0.3:
            actions.append("LEGAL_NOTICE")
        outcomes = ["NO_ANSWER", "CALL_BACK", "PTP", "REFUSED_TO_PAY", "NOT_CONTACTABLE"]
        for action in actions:
            day = month + timedelta(days=int(rng.integers(0, last_day.day)))
            when = _ts(day, rng)
            outcome = str(rng.choice(outcomes, p=[0.35, 0.2, 0.25, 0.1, 0.1]))
            if action in ("SMS", "LEGAL_NOTICE"):
                outcome = "DELIVERED"
            ptp = None
            if outcome == "PTP":
                ptp = {"date": (day + timedelta(days=int(rng.integers(2, 10)))).isoformat(),
                       "amount": round(loan.emi, 2)}
            # field app syncs in UTC, the dialer logs local time
            stamp = (when - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ") \
                if action == "FIELD_VISIT" else when.isoformat(sep=" ")
            row = {
                "activity_id": f"COL{month:%y%m}{self._next_id('activity'):07d}",
                "loan_id": loan.loan_id,
                "activity_ts": stamp,
                "activity_type": action,
                "outcome": outcome,
                "agent": {"agent_id": f"AG{int(rng.integers(100, 140))}",
                          "team": f"{'FIELD' if action == 'FIELD_VISIT' else 'TELE'}-{loan.region.upper()}"},
                "ptp": ptp,
            }
            late = day.day >= 24 and rng.random() < 0.1
            self._emit("collection_activities", row, add_months(day, 1) if late else day)
