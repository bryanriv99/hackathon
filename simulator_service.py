"""Stuff+, Location+ and Pitching+ prediction service for the web dashboard."""
import json
import math
import os
import shutil
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
REGISTRY = BASE / "model_registry"
PLOTS = BASE / "plots"
PITCH_TYPES = ["Four-Seam", "Sinker", "Cutter", "Changeup", "Slider", "Curveball", "Splitter"]
PITCH_LABELS = {
    "Four-Seam": "Recta de 4 costuras", "Sinker": "Sinker", "Cutter": "Cutter",
    "Changeup": "Cambio", "Slider": "Slider", "Curveball": "Curva", "Splitter": "Splitter",
}
ALTITUDES = ["Extreme Altitude (CDMX)", "Medium Altitude", "No Altitude"]


@lru_cache(maxsize=1)
def _models():
    return (
        joblib.load(REGISTRY / "stuff_model.pkl"),
        joblib.load(REGISTRY / "location_model.pkl"),
        joblib.load(REGISTRY / "pitching_model.pkl"),
        json.loads((REGISTRY / "scale_metadata.json").read_text(encoding="utf-8")),
    )


def _dataset_path():
    for name in ("dataset_scores_final_v2.parquet", "dataset_enriched.parquet"):
        path = BASE / name
        if path.exists():
            return path
    url = os.environ.get("DATASET_URL", "").strip()
    if url:
        cache_path = Path(tempfile.gettempdir()) / "diablos_dashboard_dataset.parquet"
        if not cache_path.exists():
            with urllib.request.urlopen(url, timeout=180) as response, cache_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        return cache_path
    return None


@lru_cache(maxsize=1)
def _dataset():
    path = _dataset_path()
    if path is None:
        return None
    return pd.read_parquet(path)


@lru_cache(maxsize=1)
def _explainers():
    import shap
    models = _models()[:3]
    metadata = _models()[3]
    keys = ("stuff", "location", "pitching")
    return {key: shap.TreeExplainer(model) for key, model in zip(keys, models)}, metadata


def _arsenal_reference():
    df = _dataset()
    if df is None:
        raise ValueError("Falta el dataset del proyecto. Coloca dataset_scores_final_v2.parquet junto a server.py o configura DATASET_URL.")
    source = df[df.get("AutoPitchType", pd.Series(index=df.index, dtype=str)).isin(["Four-Seam", "Sinker"])]
    refs = {}
    for key, candidates in {
        "speed": ("fb_avg_speed", "RelSpeed"),
        "ivb": ("fb_avg_ivb", "InducedVertBreak"),
        "hb": ("fb_avg_hb", "HorzBreak"),
    }.items():
        col = next((c for c in candidates if c in df.columns), None)
        values = pd.to_numeric(df[col], errors="coerce") if col else pd.Series(dtype=float)
        if col and col.startswith("fb_avg_") and {"pitcher_anon_id", "year"}.issubset(df.columns):
            values = values.loc[~df.duplicated(["pitcher_anon_id", "year"])]
        if col in {"RelSpeed", "InducedVertBreak", "HorzBreak"} and col in source.columns:
            values = pd.to_numeric(source[col], errors="coerce")
        refs[key] = float(values.replace([np.inf, -np.inf], np.nan).median()) if values.notna().any() else {"speed": 91.5, "ivb": 16.0, "hb": 5.0}[key]
    return refs


def _plus(raw, key, metadata):
    item = metadata[key]
    return round(float(np.clip(100 + 10 * (raw - item["mu"]) / item["sigma"], 60, 140)), 1)


def simulate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Los datos del lanzamiento no tienen un formato válido.")
    stuff_model, loc_model, pitching_model, meta = _models()
    pitch_type = payload.get("pitch_type", "Four-Seam")
    throws = payload.get("pitcher_throws", "Right")
    batter = payload.get("batter_side", "Right")
    if pitch_type not in PITCH_TYPES:
        raise ValueError("Selecciona un tipo de lanzamiento válido.")
    if throws not in ("Right", "Left") or batter not in ("Right", "Left"):
        raise ValueError("Selecciona una mano válida para el lanzador y el bateador.")

    bounds = {
        "rel_speed": (70, 103, "Velocidad"), "spin_rate": (1200, 3200, "Tasa de giro"),
        "spin_axis": (0, 360, "Eje de giro"), "ivb": (-20, 25, "Quiebre vertical"),
        "hb": (-25, 25, "Quiebre horizontal"), "extension": (4.5, 7.5, "Extensión"),
        "rel_height": (4, 7.5, "Altura de soltado"), "rel_side": (-4, 4, "Posición lateral"),
        "plate_loc_height": (0.5, 4.5, "Altura al plato"), "plate_loc_side": (-2, 2, "Lateral al plato"),
    }
    vals = {}
    for key, (lo, hi, label) in bounds.items():
        try:
            value = float(payload.get(key))
        except (TypeError, ValueError):
            raise ValueError(f"{label} debe ser numérico.")
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{label} debe estar entre {lo:g} y {hi:g}.")
        vals[key] = value
    def integer(key, lo, hi, label):
        value = payload.get(key, 0)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} debe ser un entero entre {lo} y {hi}.")
        if not number.is_integer() or not lo <= number <= hi:
            raise ValueError(f"{label} debe ser un entero entre {lo} y {hi}.")
        return int(number)

    balls = integer("balls", 0, 3, "Bolas")
    strikes = integer("strikes", 0, 2, "Strikes")
    speed, spin, axis = vals["rel_speed"], vals["spin_rate"], vals["spin_axis"]
    ivb, hb = vals["ivb"], vals["hb"]
    ext, rh, rs = vals["extension"], vals["rel_height"], vals["rel_side"]
    ph, ps = vals["plate_loc_height"], vals["plate_loc_side"]
    eff_distance = 60.5 - ext
    pitch_num = meta["pitch_type_map"].get(pitch_type, 8)
    pitcher_num = 1.0 if throws == "Right" else 0.0
    batter_num = 1.0 if batter == "Right" else 0.0
    in_zone = int(1.5 <= ph <= 3.5 and -0.83 <= ps <= 0.83)
    ref = _arsenal_reference()
    common = {
        "RelSpeed": speed, "SpinRate": spin, "SpinAxis": axis,
        "InducedVertBreak": ivb, "HorzBreak": hb, "VertBreak": ivb - 5.0,
        "EffectiveVelo": speed, "SpeedDrop": speed * 0.07, "RelHeight": rh,
        "RelSide": rs, "Extension": ext,
        "VertRelAngle": -6.0 + (rh - 5.8) * 2, "HorzRelAngle": rs * 0.5,
        "PlateLocHeight": ph, "PlateLocSide": ps, "in_strike_zone": in_zone,
        "Balls": balls, "Strikes": strikes, "AutoPitchType_Num": pitch_num,
        "PitcherThrows_Num": pitcher_num, "BatterSide_Num": batter_num,
        "velo_diff_vs_fb": speed - ref["speed"], "ivb_diff_vs_fb": ivb - ref["ivb"],
        "hb_diff_vs_fb": hb - ref["hb"], "effective_distance": eff_distance,
        "perceived_velo_factor": speed * 60.5 / eff_distance,
    }
    frame = pd.DataFrame([common])
    raw = {
        "stuff": float(stuff_model.predict(frame[meta["features"]["stuff"]])[0]),
        "location": float(loc_model.predict(frame[meta["features"]["location"]])[0]),
        "pitching": float(pitching_model.predict(frame[meta["features"]["pitching"]])[0]),
    }
    explanation = {}
    explanation_note = ""
    try:
        explainers, explain_meta = _explainers()
        labels = {
            "RelSpeed": "Velocidad", "SpinRate": "Tasa de giro", "SpinAxis": "Eje de giro",
            "InducedVertBreak": "Quiebre vertical", "HorzBreak": "Quiebre horizontal", "VertBreak": "Quiebre vertical total",
            "EffectiveVelo": "Velocidad efectiva", "SpeedDrop": "Pérdida de velocidad", "RelHeight": "Altura de soltado",
            "RelSide": "Lateral de soltado", "Extension": "Extensión", "VertRelAngle": "Ángulo vertical de soltado",
            "HorzRelAngle": "Ángulo lateral de soltado", "PlateLocHeight": "Altura al plato", "PlateLocSide": "Lateral al plato",
            "in_strike_zone": "Dentro de zona", "Balls": "Bolas", "Strikes": "Strikes",
            "AutoPitchType_Num": "Tipo de lanzamiento", "PitcherThrows_Num": "Mano del lanzador", "BatterSide_Num": "Mano del bateador",
            "velo_diff_vs_fb": "Velocidad vs. recta", "ivb_diff_vs_fb": "Quiebre vertical vs. recta",
            "hb_diff_vs_fb": "Quiebre horizontal vs. recta", "effective_distance": "Distancia efectiva",
            "perceived_velo_factor": "Velocidad percibida",
        }
        for key in ("stuff", "location", "pitching"):
            features = explain_meta["features"][key]
            values = explainers[key].shap_values(frame[features])
            values = np.asarray(values)
            if values.ndim == 3:
                values = values[0, :, 0]
            else:
                values = values.reshape(-1, len(features))[0]
            sigma = explain_meta[key]["sigma"]
            items = [{"feature": labels.get(name, name), "value": float(frame[name].iloc[0]),
                      "impact": float(values[i] * 10.0 / sigma)} for i, name in enumerate(features)]
            explanation[key] = sorted(items, key=lambda item: abs(item["impact"]), reverse=True)[:8]
    except Exception:
        explanation_note = "La explicación de contribuciones no está disponible en este entorno; los scores sí se calcularon."
    ranges = {}
    df = _dataset()
    if df is not None:
        for field, key in (("RelSpeed", "rel_speed"), ("SpinRate", "spin_rate"), ("InducedVertBreak", "ivb"),
                           ("HorzBreak", "hb"), ("RelHeight", "rel_height"), ("RelSide", "rel_side"),
                           ("Extension", "extension"), ("PlateLocHeight", "plate_loc_height"),
                           ("PlateLocSide", "plate_loc_side")):
            if field in df.columns:
                ranges[key] = [float(df[field].quantile(.01)), float(df[field].quantile(.99))]
    warnings = [
        {"field": key, "value": round(vals[key], 1), "min": round(pair[0], 1), "max": round(pair[1], 1)}
        for key, pair in ranges.items() if not pair[0] <= vals[key] <= pair[1]
    ]
    return {
        "pitch_type": pitch_type, "pitch_label": PITCH_LABELS[pitch_type],
        "scores": {key: _plus(value, key, meta) for key, value in raw.items()},
        "deltas": {key: round(_plus(value, key, meta) - 100, 1) for key, value in raw.items()},
        "explanations": explanation, "explanation_note": explanation_note,
        "in_zone": bool(in_zone), "perceived_velocity": round(speed * 60.5 / eff_distance, 1),
        "effective_distance": round(eff_distance, 1), "warnings": warnings,
        "movement": {"hb": hb, "ivb": ivb},
        "location": {"x": ps, "y": ph},
    }


def dashboard_data():
    validation_path = REGISTRY / "validation_metrics.json"
    altitude_path = PLOTS / "h1_altitude_differences.csv"
    stuff_altitude_path = PLOTS / "stuff_plus_by_altitude_type.csv"
    out = {"dataset_available": False, "validation": None, "altitude": [], "stuff_altitude": [], "top_pitchers": [], "distributions": {}, "movement": {}}
    if validation_path.exists():
        out["validation"] = json.loads(validation_path.read_text(encoding="utf-8"))
    if altitude_path.exists():
        out["altitude"] = pd.read_csv(altitude_path).replace({np.nan: None}).to_dict(orient="records")
    if stuff_altitude_path.exists():
        out["stuff_altitude"] = pd.read_csv(stuff_altitude_path).replace({np.nan: None}).to_dict(orient="records")
    df = _dataset()
    if df is None:
        return out
    out["dataset_available"] = True
    if {"AutoPitchType", "HorzBreak", "InducedVertBreak"}.issubset(df.columns):
        for pitch_type in ("Four-Seam", "Sinker", "Slider", "Changeup", "Curveball", "Cutter"):
            sample = df.loc[df.AutoPitchType == pitch_type, ["HorzBreak", "InducedVertBreak"]].dropna()
            if len(sample):
                sample = sample.sample(min(300, len(sample)), random_state=42)
                out["movement"][pitch_type] = {"hb": sample.HorzBreak.astype(float).tolist(), "ivb": sample.InducedVertBreak.astype(float).tolist()}
    if "pitcher_anon_id" in df.columns and "Stuff+" in df.columns:
        aggregations = {"n_pitches": ("RelSpeed", "count")} if "RelSpeed" in df.columns else {"n_pitches": ("Stuff+", "count")}
        for col in ("RelSpeed", "SpinRate", "Stuff+", "Location+", "Pitching+"):
            if col in df.columns:
                aggregations[f"avg_{col}"] = (col, "mean")
        pitchers = df.groupby("pitcher_anon_id").agg(**aggregations).reset_index()
        pitchers = pitchers[pitchers.n_pitches >= 100].sort_values("avg_Stuff+", ascending=False).head(30)
        out["top_pitchers"] = pitchers.replace({np.nan: None}).to_dict(orient="records")
    for col in ("Stuff+", "Location+", "Pitching+"):
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce").dropna().clip(60, 140)
            counts, edges = np.histogram(values, bins=40, range=(60, 140))
            out["distributions"][col] = {"x": [round(float((edges[i] + edges[i+1]) / 2), 1) for i in range(len(counts))], "y": counts.tolist()}
    out["raw_columns"] = [str(c) for c in df.columns[:40]]
    raw = json.loads(df.head(200).to_json(orient="records", date_format="iso"))
    out["raw_rows"] = raw
    return out


def metadata():
    _, _, _, meta = _models()
    return {
        "pitch_types": [{"key": key, "label": PITCH_LABELS[key]} for key in PITCH_TYPES],
        "pitch_type_map": meta["pitch_type_map"],
        "altitudes": ALTITUDES,
        "defaults": {"pitch_type": "Four-Seam", "pitcher_throws": "Right", "batter_side": "Right", "altitude": ALTITUDES[0],
                     "rel_speed": 93.5, "spin_rate": 2250, "spin_axis": 200, "ivb": 15, "hb": 5,
                     "extension": 6.2, "rel_height": 5.8, "rel_side": -1.5,
                     "plate_loc_height": 2.5, "plate_loc_side": 0, "balls": 0, "strikes": 0},
        "definitions": {
            "Stuff+": "Calidad de las características físicas del lanzamiento: velocidad, giro y movimiento.",
            "Location+": "Calidad de la ubicación considerando zona, conteo, tipo de lanzamiento y manos.",
            "Pitching+": "Evaluación integral que combina características físicas, ubicación y contexto.",
        },
    }

