import pandas as pd


def normalize_ordered(records, sep="_"):
    """json_normalize, keeping original key order with nested keys expanded in place."""
    df = pd.json_normalize(records, sep=sep)
    top = list(dict.fromkeys(k for r in records for k in r))

    order, seen = [], set()
    for key in top:
        for col in df.columns:
            if col not in seen and (col == key or col.startswith(key + sep)):
                order.append(col)
                seen.add(col)
    order += [c for c in df.columns if c not in seen]
    return df[order]
