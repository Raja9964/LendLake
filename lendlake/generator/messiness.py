"""Source-system noise: the kind of thing Silver has to clean up."""

import numpy as np
import pandas as pd

from lendlake.generator.reference import CITY_VARIANTS

DATE_FORMATS = ("%d/%m/%Y", "%d-%b-%Y", "%Y%m%d")


def _mask(df: pd.DataFrame, rng: np.random.Generator, rate: float) -> np.ndarray:
    return rng.random(len(df)) < rate


def duplicate_rows(df: pd.DataFrame, rng, rate: float) -> pd.DataFrame:
    dupes = df[_mask(df, rng, rate)]
    return pd.concat([df, dupes], ignore_index=True) if len(dupes) else df


def mixed_dates(df: pd.DataFrame, column: str, rng, rate: float) -> None:
    mask = _mask(df, rng, rate) & (df[column] != "")
    if not mask.any():
        return
    parsed = pd.to_datetime(df.loc[mask, column], format="%Y-%m-%d")
    formats = rng.choice(DATE_FORMATS, mask.sum())
    df.loc[mask, column] = [d.strftime(f) for d, f in zip(parsed, formats, strict=True)]


def sloppy_text(df: pd.DataFrame, column: str, rng, rate: float) -> None:
    mask = _mask(df, rng, rate)
    styles = rng.integers(0, 3, mask.sum())
    values = df.loc[mask, column].astype(str)
    df.loc[mask, column] = [
        v.lower() if s == 0 else f" {v} " if s == 1 else v.title() + " "
        for v, s in zip(values, styles, strict=True)
    ]


def indian_grouping(df: pd.DataFrame, column: str, rng, rate: float) -> None:
    def fmt(value: str) -> str:
        whole, _, frac = value.partition(".")
        if len(whole) <= 3:
            return value
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        return ",".join(groups + [tail]) + (f".{frac}" if frac else "")

    mask = _mask(df, rng, rate)
    df.loc[mask, column] = df.loc[mask, column].map(fmt)


def blank_out(df: pd.DataFrame, column: str, rng, rate: float) -> None:
    df.loc[_mask(df, rng, rate), column] = ""


def city_aliases(df: pd.DataFrame, rng, rate: float) -> None:
    mask = _mask(df, rng, rate) & df["city"].isin(list(CITY_VARIANTS))
    df.loc[mask, "city"] = [str(rng.choice(CITY_VARIANTS[c])) for c in df.loc[mask, "city"]]


def messy_mobile(df: pd.DataFrame, rng, rate: float) -> None:
    mask = _mask(df, rng, rate)
    styles = rng.integers(0, 3, mask.sum())
    df.loc[mask, "mobile"] = [
        f"+91-{m}" if s == 0 else f"0{m}" if s == 1 else f"{m[:5]} {m[5:]}"
        for m, s in zip(df.loc[mask, "mobile"], styles, strict=True)
    ]


def apply(table: str, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df
    if table == "customers":
        city_aliases(df, rng, 0.15)
        sloppy_text(df, "city", rng, 0.05)
        sloppy_text(df, "employment_type", rng, 0.1)
        sloppy_text(df, "gender", rng, 0.05)
        messy_mobile(df, rng, 0.2)
        mixed_dates(df, "date_of_birth", rng, 0.3)
        blank_out(df, "email", rng, 0.06)
        blank_out(df, "annual_income", rng, 0.04)
        mask = _mask(df, rng, 0.05)
        df.loc[mask, "pincode"] = df.loc[mask, "pincode"] + ".0"
        df = duplicate_rows(df, rng, 0.02)
    elif table == "loan_applications":
        sloppy_text(df, "branch_code", rng, 0.05)
        sloppy_text(df, "product_code", rng, 0.03)
        sloppy_text(df, "application_status", rng, 0.05)
        blank_out(df, "channel", rng, 0.04)
        mixed_dates(df, "application_date", rng, 0.15)
        df = duplicate_rows(df, rng, 0.01)
    elif table == "sanctions":
        indian_grouping(df, "sanctioned_amount", rng, 0.08)
        mask = _mask(df, rng, 0.05)
        df.loc[mask, "interest_rate"] = df.loc[mask, "interest_rate"] + "%"
        mixed_dates(df, "sanction_date", rng, 0.1)
    elif table == "disbursements":
        indian_grouping(df, "disbursed_amount", rng, 0.08)
        sloppy_text(df, "disbursement_mode", rng, 0.05)
        mixed_dates(df, "disbursement_date", rng, 0.1)
        df = duplicate_rows(df, rng, 0.01)
    elif table == "repayments":
        sloppy_text(df, "payment_status", rng, 0.06)
        sloppy_text(df, "payment_mode", rng, 0.06)
        mixed_dates(df, "payment_date", rng, 0.1)
        df = duplicate_rows(df, rng, 0.007)
    elif table == "branches":
        sloppy_text(df, "region", rng, 0.2)
    return df
