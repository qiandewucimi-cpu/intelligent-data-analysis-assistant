"""Synthetic data + real subprocess execution; no model and no network."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from analyzer.executor import run_in_sandbox


def main():
    frame = pd.DataFrame({"region": ["A", "A", "B"], "sales": [10, 20, 5]})
    code = "result = df.groupby('region', as_index=False)['sales'].sum()"
    output = run_in_sandbox(code, frame)
    if not output.ok:
        raise RuntimeError(output.error)
    records = output.result_frame.to_dict(orient="records")
    assert records == [{"region": "A", "sales": 30}, {"region": "B", "sales": 5}], records
    rejected = run_in_sandbox("result = pd.read_csv('not-a-real-file.csv')", frame)
    assert not rejected.ok and rejected.kind == "rejected"
    print(json.dumps({"mode": "offline_fixed_code_no_llm", "input": frame.to_dict(orient="records"),
                      "code": code, "result": records, "file_read": rejected.kind}, ensure_ascii=False, indent=2))
    print("PASS: synthetic aggregation and file-read rejection")


if __name__ == "__main__":
    main()
