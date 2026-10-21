import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBClassifier

BASE = Path(__file__).resolve().parent
MODEL_DIR = BASE / "model_registry"
MODEL_DIR.mkdir(exist_ok=True)

FEATURES = ["AutoPitchType_Num", "RelSpeed", "InducedVertBreak", "HorzBreak",
            "velo_diff_vs_fb", "ivb_diff_vs_fb", "hb_diff_vs_fb",
            "PitcherThrows_Num", "BatterSide_Num", "PlateLocHeight", "PlateLocSide",
            "Balls", "Strikes"]
TYPES = ["Four-Seam", "Sinker", "Cutter", "Changeup", "Slider", "Curveball", "Splitter"]
TYPE_GROUPS = {
    "Four-Seam": ["Four-Seam", "OneSeamFastBall"],
    "Sinker": ["Sinker", "TwoSeamFastBall"],
    "Cutter": ["Cutter"],
    "Changeup": ["Changeup"],
    "Slider": ["Slider"],
    "Curveball": ["Curveball"],
    "Splitter": ["Splitter"],
}
GROUP_MAP = {g: t for t, gs in TYPE_GROUPS.items() for g in gs}


def make_model():
    return XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.08,
                         tree_method="hist", random_state=42)


def evaluate(Xy, y, key):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(gss.split(Xy, y, groups=Xy["pitcher_anon_id"]))
    model = make_model()
    model.fit(Xy.iloc[tr][FEATURES], y.iloc[tr])
    if y.iloc[te].nunique() > 1:
        proba = model.predict_proba(Xy.iloc[te][FEATURES])[:, 1]
        auc = float(roc_auc_score(y.iloc[te], proba))
    else:
        auc = float("nan")
    print(f"{key}: AUC validacion {auc:.4f} | tasa base {float(y.mean()):.4f} | n {len(Xy)}")
    return auc, float(y.mean()), int(len(Xy))


def main():
    df = pd.read_parquet(BASE / "dataset_scores_final_v2.parquet")
    for c in FEATURES + ["Angle", "SpinRate", "SpinAxis", "RelHeight", "RelSide",
                         "Extension", "VertRelAngle", "HorzRelAngle", "SpeedDrop",
                         "EffectiveVelo", "VertBreak"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["PitchCall"] = df["PitchCall"].astype(str)
    df["KorBB"] = df["KorBB"].astype(str)
    df["PitcherThrows"] = df["PitcherThrows"].astype(str)
    df["AutoPitchType"] = df["AutoPitchType"].astype(str)
    df["type_group"] = df["AutoPitchType"].map(GROUP_MAP)

    hb_sign = {}
    for hand in ("Right", "Left"):
        fb = df[(df["PitcherThrows"] == hand) & (df["type_group"] == "Four-Seam")]
        med = float(fb["HorzBreak"].median())
        hb_sign[hand] = 1.0 if med >= 0 else -1.0
    df["user_hb"] = df["HorzBreak"] * df["PitcherThrows"].map(hb_sign)
    print("hb_sign:", hb_sign)

    base = df[df["PitchCall"] != "Undefined"]
    base = base[base[FEATURES].notna().all(axis=1)]
    print("filas base (excluye PitchCall Undefined):", len(base))
    if len(base) > 400000:
        base = base.sample(400000, random_state=42)
        print("muestreo base a 400k")

    ip = df[(df["PitchCall"] == "InPlay") & df["Angle"].notna()]
    ip = ip[ip[FEATURES].notna().all(axis=1)]
    print("filas InPlay con Angle:", len(ip))
    if len(ip) > 400000:
        ip = ip.sample(400000, random_state=42)
        print("muestreo InPlay a 400k")

    datasets = {
        "csw": (base, (base["PitchCall"].isin(["StrikeCalled", "StrikeSwinging"])).astype(int)),
        "inplay": (base, (base["PitchCall"] == "InPlay").astype(int)),
        "groundball": (ip, (ip["Angle"] < 10).astype(int)),
        "flyball": (ip, (ip["Angle"] >= 25).astype(int)),
    }

    meta = {
        "features": FEATURES,
        "auc": {},
        "n": {},
        "league": {},
        "league_definitions": {
            "csw": "tasa de StrikeCalled o StrikeSwinging sobre lanzamientos validos (PitchCall != Undefined)",
            "inplay": "tasa de InPlay sobre lanzamientos validos (PitchCall != Undefined)",
            "gb_pct": "proporcion de Angle < 10 entre lanzamientos InPlay con Angle no nulo",
            "fb_pct": "proporcion de Angle >= 25 entre lanzamientos InPlay con Angle no nulo",
            "k_pct": "Strikeout sobre PA; PA = KorBB != Undefined o PitchCall == InPlay o PitchCall == HitByPitch",
            "bb_pct": "Walk sobre PA; misma definicion de PA que k_pct",
        },
    }

    models = {}
    for key, (Xy, y) in datasets.items():
        auc, rate, n = evaluate(Xy, y, key)
        meta["auc"][key] = auc
        meta["n"][key] = n
        meta["league"][key] = rate
        m = make_model()
        m.fit(Xy[FEATURES], y)
        models[key] = m

    fb_rows = df[df["PitchCall"] != "Undefined"]
    meta["league"]["csw"] = float(fb_rows["PitchCall"].isin(["StrikeCalled", "StrikeSwinging"]).mean())
    meta["league"]["inplay"] = float((fb_rows["PitchCall"] == "InPlay").mean())
    ip_full = df[(df["PitchCall"] == "InPlay") & df["Angle"].notna()]
    meta["league"]["gb_pct"] = float((ip_full["Angle"] < 10).mean())
    meta["league"]["fb_pct"] = float((ip_full["Angle"] >= 25).mean())
    pa = (df["KorBB"] != "Undefined") | (df["PitchCall"] == "InPlay") | (df["PitchCall"] == "HitByPitch")
    meta["league"]["k_pct"] = float((df.loc[pa, "KorBB"] == "Strikeout").mean())
    meta["league"]["bb_pct"] = float((df.loc[pa, "KorBB"] == "Walk").mean())

    defaults = {}
    for hand in ("Right", "Left"):
        h = df[df["PitcherThrows"] == hand]
        defaults[hand] = {}
        for t in TYPES:
            g = h[h["type_group"] == t]
            med = g[["RelSpeed", "InducedVertBreak", "user_hb"]].median()
            defaults[hand][t] = {
                "speed": float(med["RelSpeed"]),
                "ivb": float(med["InducedVertBreak"]),
                "hb": float(med["user_hb"]),
                "hidden": {
                    "SpinRate": float(g["SpinRate"].median()),
                    "SpinAxis": float(g["SpinAxis"].median()),
                    "RelHeight": float(g["RelHeight"].median()),
                    "RelSide": float(g["RelSide"].median()),
                    "Extension": float(g["Extension"].median()),
                    "VertRelAngle": float(g["VertRelAngle"].median()),
                    "HorzRelAngle": float(g["HorzRelAngle"].median()),
                    "SpeedDrop": float(g["SpeedDrop"].median()),
                    "diff_effective_velo": float((g["EffectiveVelo"] - g["RelSpeed"]).median()),
                    "diff_vert_break": float((g["VertBreak"] - g["InducedVertBreak"]).median()),
                },
            }

    ranges = {}
    for t in TYPES:
        g = df[df["type_group"] == t]
        ranges[t] = {
            "speed": [float(g["RelSpeed"].quantile(0.01)), float(g["RelSpeed"].quantile(0.99))],
            "ivb": [float(g["InducedVertBreak"].quantile(0.01)), float(g["InducedVertBreak"].quantile(0.99))],
            "hb": [float(g["user_hb"].quantile(0.01)), float(g["user_hb"].quantile(0.99))],
        }

    meta["defaults"] = defaults
    meta["ranges"] = ranges
    meta["hb_sign"] = hb_sign

    joblib.dump(models, MODEL_DIR / "situational_models.pkl")
    with open(MODEL_DIR / "situational_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("League:", {k: round(v, 4) for k, v in meta["league"].items()})
    print("Defaults hid.", {h: {t: defaults[h][t]["speed"] for t in TYPES} for h in ("Right", "Left")})
    print("Guardado en", MODEL_DIR / "situational_models.pkl", "y situational_meta.json")


if __name__ == "__main__":
    main()
