"""Deterministically generates the synthetic sales dataset used by the eval set.

Same seed -> same data, so golden answers computed at eval time stay comparable
across runs and machines.  The data deliberately carries realistic quirks the
cleaning pipeline must handle: a duplicate-block (40 exact copies), missing
values (约 2% 数量、约 1.2% 城市) and text-form dates that only become real
datetimes after the shell's default cleaning.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

N_ROWS = 5000
N_DUPLICATES = 40
SEED = 42

_REGION_CITIES: dict[str, list[str]] = {
    "华东": ["上海", "杭州", "南京"],
    "华北": ["北京", "天津"],
    "华南": ["广州", "深圳"],
    "西南": ["成都", "重庆"],
    "东北": ["沈阳", "大连"],
}
_CATEGORIES = ["办公用品", "数码配件", "家居生活"]
_SALESPEOPLE = ["张伟", "李娜", "王强", "刘敏", "陈静", "杨帆", "赵磊", "黄霞", "周涛", "吴倩", "徐鹏", "孙丽"]


def generate_sample_frame() -> pd.DataFrame:
    """Builds the synthetic dataset (deterministic under SEED)."""

    rng = np.random.default_rng(SEED)
    regions = rng.choice(list(_REGION_CITIES), size=N_ROWS, p=[0.32, 0.24, 0.20, 0.14, 0.10])
    cities = np.array([rng.choice(_REGION_CITIES[region]) for region in regions])
    categories = rng.choice(_CATEGORIES, size=N_ROWS, p=[0.40, 0.35, 0.25])
    salespeople = rng.choice(_SALESPEOPLE, size=N_ROWS)
    customer_types = rng.choice(["新客", "老客"], size=N_ROWS, p=[0.45, 0.55])

    dates = (
        pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 181, size=N_ROWS), unit="D")
    ).strftime("%Y-%m-%d")

    unit_price = np.round(rng.uniform(20, 3000, size=N_ROWS), 2)
    quantity = rng.integers(1, 21, size=N_ROWS).astype("float64")
    quantity[rng.random(N_ROWS) < 0.02] = np.nan
    discount = np.round(rng.uniform(0, 0.3, size=N_ROWS), 4)
    discount[rng.random(N_ROWS) < 0.10] = 0.0
    amount = np.round(unit_price * quantity, 2)

    frame = pd.DataFrame(
        {
            "订单编号": [f"SO-2025-{index:05d}" for index in range(N_ROWS)],
            "日期": dates,
            "地区": regions,
            "城市": cities,
            "品类": categories,
            "销售员": salespeople,
            "客户类型": customer_types,
            "单价": unit_price,
            "数量": quantity,
            "销售额": amount,
            "折扣率": discount,
        }
    )

    missing_city_index = rng.choice(N_ROWS, size=60, replace=False)
    frame.loc[missing_city_index, "城市"] = np.nan

    duplicates = frame.iloc[rng.choice(N_ROWS, size=N_DUPLICATES, replace=False)]
    frame = pd.concat([frame, duplicates], ignore_index=True)
    return frame.iloc[rng.permutation(len(frame))].reset_index(drop=True)


def ensure_sample_csv(path: Path | None = None) -> Path:
    """Returns the sample CSV path, generating the file when missing."""

    target = path or (Path(__file__).resolve().parent / "sales_sample.csv")
    if not target.exists():
        generate_sample_frame().to_csv(target, index=False, encoding="utf-8-sig")
    return target


def main() -> None:
    out = ensure_sample_csv()
    frame = generate_sample_frame()
    print(f"wrote {out} ({len(frame)} rows, duplicated rows: {int(frame.duplicated().sum())})")


if __name__ == "__main__":
    main()
