import json
import math
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
MODEL_DIR = BASE / "model_registry"

PITCH_LABELS = {
    "Four-Seam": "Recta 4 costuras",
    "Sinker": "Sinker / 2 costuras",
    "Cutter": "Cutter",
    "Changeup": "Cambio",
    "Slider": "Slider",
    "Curveball": "Curva",
    "Splitter": "Splitter",
}
SUPPORTED_TYPES = set(PITCH_LABELS)
OBJECTIVES = [
    {"key": "auto", "label": "Automático"},
    {"key": "flyball", "label": "Forzar elevado"},
    {"key": "groundball", "label": "Forzar rola"},
    {"key": "strikeout", "label": "Buscar ponche"},
]
METRIC_LABELS = {
    "strikeout": "Prob. de strike cantado o abanicado",
    "groundball": "Prob. de rola si hay contacto",
    "flyball": "Prob. de elevado si hay contacto",
}
OBJECTIVE_LEAGUE_KEY = {"strikeout": "csw", "groundball": "gb_pct", "flyball": "fb_pct"}
OBJECTIVE_REASON = {
    "flyball": "Objetivo: forzar un elevado.",
    "groundball": "Objetivo: forzar una rola.",
    "strikeout": "Objetivo: buscar el ponche.",
}
GRID_X = [-1.1, -0.55, 0.0, 0.55, 1.1]
GRID_Y = [1.2, 1.85, 2.5, 3.15, 3.8]
NX, NY = len(GRID_X), len(GRID_Y)


@lru_cache(maxsize=1)
def _stuff_model():
    return joblib.load(MODEL_DIR / "stuff_model.pkl")


@lru_cache(maxsize=1)
def _scale_meta():
    return json.loads((MODEL_DIR / "scale_metadata.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _sit_models():
    return joblib.load(MODEL_DIR / "situational_models.pkl")


@lru_cache(maxsize=1)
def _sit_meta():
    return json.loads((MODEL_DIR / "situational_meta.json").read_text(encoding="utf-8"))


def warm():
    _stuff_model()
    _scale_meta()
    _sit_models()
    _sit_meta()


def get_meta():
    meta = _sit_meta()
    league = meta["league"]
    pct = {k: round(float(league[k]) * 100, 1) for k in ("k_pct", "bb_pct", "gb_pct", "fb_pct")}
    defaults = {
        hand: {t: {k: round(float(meta["defaults"][hand][t][k]), 1) for k in ("speed", "ivb", "hb")}
               for t in PITCH_LABELS}
        for hand in ("Right", "Left")
    }
    ranges = {
        t: {k: [round(float(v[0]), 1), round(float(v[1]), 1)] for k, v in meta["ranges"][t].items()}
        for t in PITCH_LABELS
    }
    return {
        "pitch_types": [{"key": t, "label": PITCH_LABELS[t]} for t in PITCH_LABELS],
        "defaults": defaults,
        "ranges": ranges,
        "league": {k: float(league[k]) for k in ("k_pct", "bb_pct", "gb_pct", "fb_pct", "csw", "inplay")},
        "objectives": OBJECTIVES,
        "default_pitcher": {"name": "Lanzador Diablos", "throws": "Right", "era": 3.80, "whip": 1.25, **pct},
        "default_arsenal": [
            {"pitch_type": t, "speed": defaults["Right"][t]["speed"],
             "ivb": defaults["Right"][t]["ivb"], "hb": defaults["Right"][t]["hb"]}
            for t in ("Four-Seam", "Slider", "Changeup")
        ],
    }


def _float_any(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _int_in(v, lo, hi, label):
    f = _float_any(v)
    if f is None or f != int(f):
        raise ValueError(f"{label} debe ser un entero entre {lo} y {hi}.")
    iv = int(f)
    if not (lo <= iv <= hi):
        raise ValueError(f"{label} debe ser un entero entre {lo} y {hi}.")
    return iv


def _pct(v, label, league_fraction):
    if v is None:
        return float(league_fraction) * 100.0
    f = _float_any(v)
    if f is None:
        raise ValueError(f"{label} debe ser un número.")
    if not (0.0 <= f <= 100.0):
        raise ValueError(f"{label} debe estar entre 0 y 100.")
    return f


def _location(x, y, batter_side):
    height = "Arriba" if y >= 3.15 else ("Abajo" if y <= 1.85 else "Medio")
    if batter_side == "Right":
        lateral = "Adentro" if x < 0 else ("Centro" if x == 0 else "Afuera")
    else:
        lateral = "Adentro" if x > 0 else ("Centro" if x == 0 else "Afuera")
    in_zone = abs(x) <= 0.83 and 1.5 <= y <= 3.5
    label = f"{height} {lateral}"
    if not in_zone:
        label = f"{label} (fuera de zona)"
    return {"x": x, "y": y, "zone_label": label, "in_zone": bool(in_zone)}


def _logit(p):
    return np.log(p / (1.0 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _adjust(p, pitcher_rate, league_rate):
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    pr = np.clip(pitcher_rate, 0.01, 0.99)
    lr = np.clip(league_rate, 0.01, 0.99)
    return _sigmoid(_logit(p) + 0.5 * (_logit(pr) - _logit(lr)))


def analyze(payload):
    if not isinstance(payload, dict):
        raise ValueError("El cuerpo de la solicitud debe ser un objeto JSON.")
    pitcher = payload.get("pitcher")
    arsenal_in = payload.get("arsenal")
    situation = payload.get("situation")
    if not isinstance(pitcher, dict) or not isinstance(arsenal_in, list) or not isinstance(situation, dict):
        raise ValueError("Faltan campos obligatorios: pitcher, arsenal y situation.")

    throws = pitcher.get("throws")
    if throws not in ("Right", "Left"):
        raise ValueError("La mano del lanzador (throws) debe ser 'Right' o 'Left'.")
    batter_side = situation.get("batter_side")
    if batter_side not in ("Right", "Left"):
        raise ValueError("El lado del bateador (batter_side) debe ser 'Right' o 'Left'.")
    objective = situation.get("objective", "auto")
    if objective not in ("auto", "flyball", "groundball", "strikeout"):
        raise ValueError("El objetivo debe ser 'auto', 'flyball', 'groundball' o 'strikeout'.")

    balls = _int_in(situation.get("balls"), 0, 3, "balls (bolas)")
    strikes = _int_in(situation.get("strikes"), 0, 2, "strikes")
    outs = _int_in(situation.get("outs"), 0, 2, "outs")
    on_first = bool(situation.get("on_first", False))
    on_second = bool(situation.get("on_second", False))
    on_third = bool(situation.get("on_third", False))

    if not 1 <= len(arsenal_in) <= 6:
        raise ValueError("El arsenal debe contener entre 1 y 6 lanzamientos.")

    meta = _sit_meta()
    league = meta["league"]
    k_pct = _pct(pitcher.get("k_pct"), "k_pct", league["k_pct"])
    bb_pct = _pct(pitcher.get("bb_pct"), "bb_pct", league["bb_pct"])
    gb_pct = _pct(pitcher.get("gb_pct"), "gb_pct", league["gb_pct"])
    fb_pct = _pct(pitcher.get("fb_pct"), "fb_pct", league["fb_pct"])
    k_rate, bb_rate, gb_rate, fb_rate = k_pct / 100.0, bb_pct / 100.0, gb_pct / 100.0, fb_pct / 100.0

    sm = _scale_meta()
    sm_feats = sm["features"]["stuff"]
    sign = meta["hb_sign"][throws]
    pitcher_num = 1.0 if throws == "Right" else 0.0
    batter_num = 1.0 if batter_side == "Right" else 0.0

    arsenal = []
    for a in arsenal_in:
        if not isinstance(a, dict):
            raise ValueError("Cada lanzamiento del arsenal debe ser un objeto.")
        pt = a.get("pitch_type")
        if pt not in SUPPORTED_TYPES:
            raise ValueError(f"Tipo de lanzamiento no soportado: {pt}.")
        speed = _float_any(a.get("speed"))
        ivb = _float_any(a.get("ivb"))
        hb = _float_any(a.get("hb"))
        if speed is None or ivb is None or hb is None:
            raise ValueError(f"El lanzamiento {pt} requiere speed, ivb y hb numéricos.")
        arsenal.append({"pitch_type": pt, "label": PITCH_LABELS[pt],
                        "speed": speed, "ivb": ivb, "hb": hb, "hb_ds": hb * sign})

    ref = (next((c for c in arsenal if c["pitch_type"] == "Four-Seam"), None)
           or next((c for c in arsenal if c["pitch_type"] == "Sinker"), None))
    if ref is None:
        d = meta["defaults"][throws]["Four-Seam"]
        ref = {"speed": d["speed"], "ivb": d["ivb"], "hb_ds": d["hb"] * sign}
    else:
        ref = {"speed": ref["speed"], "ivb": ref["ivb"], "hb_ds": ref["hb_ds"]}

    stuff_model = _stuff_model()
    mu, sigma = sm["stuff"]["mu"], sm["stuff"]["sigma"]
    stuff_rows = []
    for a in arsenal:
        hidden = meta["defaults"][throws][a["pitch_type"]]["hidden"]
        stuff_rows.append({
            "RelSpeed": a["speed"], "SpinRate": hidden["SpinRate"], "SpinAxis": hidden["SpinAxis"],
            "InducedVertBreak": a["ivb"], "HorzBreak": a["hb_ds"],
            "VertBreak": a["ivb"] + hidden["diff_vert_break"],
            "EffectiveVelo": a["speed"] + hidden["diff_effective_velo"],
            "SpeedDrop": hidden["SpeedDrop"], "RelHeight": hidden["RelHeight"],
            "RelSide": hidden["RelSide"], "Extension": hidden["Extension"],
            "VertRelAngle": hidden["VertRelAngle"], "HorzRelAngle": hidden["HorzRelAngle"],
            "AutoPitchType_Num": sm["pitch_type_map"][a["pitch_type"]],
            "PitcherThrows_Num": pitcher_num, "BatterSide_Num": batter_num,
            "velo_diff_vs_fb": a["speed"] - ref["speed"],
            "ivb_diff_vs_fb": a["ivb"] - ref["ivb"],
            "hb_diff_vs_fb": a["hb_ds"] - ref["hb_ds"],
        })
    stuff_preds = stuff_model.predict(pd.DataFrame(stuff_rows)[sm_feats])
    stuff_plus = [float(np.clip(100 + 10 * (p - mu) / sigma, 60, 140)) for p in stuff_preds]

    warnings_list = []
    for i, a in enumerate(arsenal):
        rng = meta["ranges"][a["pitch_type"]]
        ws = []
        if not rng["speed"][0] <= a["speed"] <= rng["speed"][1]:
            ws.append(f"Velocidad {a['speed']:.1f} mph fuera del rango típico de {a['label']} "
                      f"({rng['speed'][0]:.1f}-{rng['speed'][1]:.1f}).")
        if not rng["ivb"][0] <= a["ivb"] <= rng["ivb"][1]:
            ws.append(f"Quiebre vertical {a['ivb']:.1f} in fuera del rango típico de {a['label']} "
                      f"({rng['ivb'][0]:.1f}-{rng['ivb'][1]:.1f}).")
        if not rng["hb"][0] <= a["hb"] <= rng["hb"][1]:
            ws.append(f"Quiebre horizontal {a['hb']:.1f} in fuera del rango típico de {a['label']} "
                      f"({rng['hb'][0]:.1f}-{rng['hb'][1]:.1f}).")
        warnings_list.append(ws)

    n_pitches = len(arsenal)
    n_cells = NY * NX
    pred_rows = []
    for a in arsenal:
        for y in GRID_Y:
            for x in GRID_X:
                pred_rows.append({
                    "AutoPitchType_Num": sm["pitch_type_map"][a["pitch_type"]],
                    "RelSpeed": a["speed"], "InducedVertBreak": a["ivb"], "HorzBreak": a["hb_ds"],
                    "velo_diff_vs_fb": a["speed"] - ref["speed"],
                    "ivb_diff_vs_fb": a["ivb"] - ref["ivb"],
                    "hb_diff_vs_fb": a["hb_ds"] - ref["hb_ds"],
                    "PitcherThrows_Num": pitcher_num, "BatterSide_Num": batter_num,
                    "PlateLocHeight": y, "PlateLocSide": x,
                    "Balls": balls, "Strikes": strikes,
                })
    grid_df = pd.DataFrame(pred_rows)[meta["features"]]
    sit = _sit_models()
    proba = {key: sit[key].predict_proba(grid_df)[:, 1].reshape(n_pitches, n_cells)
             for key in ("csw", "inplay", "groundball", "flyball")}

    csw_adj = _adjust(proba["csw"], k_rate, league["csw"])
    gb_adj = _adjust(proba["groundball"], gb_rate, league["gb_pct"])
    fb_adj = _adjust(proba["flyball"], fb_rate, league["fb_pct"])
    scores = {"strikeout": csw_adj, "groundball": gb_adj, "flyball": fb_adj}

    in_zone_flat = np.array([abs(x) <= 0.83 and 1.5 <= y <= 3.5
                             for y in GRID_Y for x in GRID_X], dtype=bool)
    used_inplay = proba["inplay"] >= 0.6 * league["inplay"]
    candidates = {}
    for key in ("strikeout", "groundball", "flyball"):
        if key in ("groundball", "flyball"):
            m = np.zeros_like(used_inplay, dtype=bool)
            for i in range(n_pitches):
                m[i] = used_inplay[i] if used_inplay[i].any() else True
        else:
            m = np.ones((n_pitches, n_cells), dtype=bool)
        candidates[key] = m
    if balls == 3 or (balls == 2 and bb_rate > league["bb_pct"] + 0.03):
        for key in candidates:
            candidates[key] &= in_zone_flat

    auto = objective == "auto"
    if auto:
        if strikes == 2:
            obj_key, reason = "strikeout", "Dos strikes: buscar el ponche."
        elif on_third and outs < 2:
            obj_key, reason = "strikeout", "Corredor en tercera con menos de 2 outs: evitar el contacto."
        elif on_first and outs < 2:
            obj_key, reason = "groundball", "Corredor en primera con menos de 2 outs: buscar doble play con rola."
        else:
            obj_key, reason = "groundball", "Sin presión en bases: la rola minimiza el daño (menos extrabases)."
    else:
        obj_key = objective
        reason = OBJECTIVE_REASON[obj_key]
    obj_label = {o["key"]: o["label"] for o in OBJECTIVES}[obj_key]

    masked = np.where(candidates[obj_key], scores[obj_key], -1.0)
    best_cell = np.argmax(masked, axis=1)
    best_val = masked[np.arange(n_pitches), best_cell]
    pitch_i = int(np.argmax(best_val))
    cell = int(best_cell[pitch_i])
    x = GRID_X[cell % NX]
    y = GRID_Y[cell // NX]

    recommendation = {
        "pitch_type": arsenal[pitch_i]["pitch_type"],
        "label": arsenal[pitch_i]["label"],
        "speed": round(arsenal[pitch_i]["speed"], 1),
        "location": _location(x, y, batter_side),
        "probability": round(float(best_val[pitch_i]), 4),
        "league_probability": round(float(league[OBJECTIVE_LEAGUE_KEY[obj_key]]), 4),
        "metric_label": METRIC_LABELS[obj_key],
        "stuff_plus": round(stuff_plus[pitch_i], 1),
    }

    ranking = {}
    for key in ("strikeout", "groundball", "flyball"):
        msk = np.where(candidates[key], scores[key], -1.0)
        bc = np.argmax(msk, axis=1)
        bv = msk[np.arange(n_pitches), bc]
        items = []
        for i in range(n_pitches):
            items.append({
                "pitch_type": arsenal[i]["pitch_type"],
                "label": arsenal[i]["label"],
                "probability": round(float(bv[i]), 4),
                "location": _location(GRID_X[bc[i] % NX], GRID_Y[bc[i] // NX], batter_side),
                "stuff_plus": round(stuff_plus[i], 1),
            })
        items.sort(key=lambda it: it["probability"], reverse=True)
        ranking[key] = items

    z = np.round(scores[obj_key][pitch_i].reshape(NY, NX), 4)
    heatmap = {
        "pitch_type": arsenal[pitch_i]["pitch_type"],
        "x": GRID_X,
        "y": GRID_Y,
        "z": z.astype(float).tolist(),
    }

    out_arsenal = []
    for i, a in enumerate(arsenal):
        out_arsenal.append({
            "pitch_type": a["pitch_type"], "label": a["label"],
            "speed": round(a["speed"], 1), "ivb": round(a["ivb"], 1), "hb": round(a["hb"], 1),
            "stuff_plus": round(stuff_plus[i], 1), "warnings": warnings_list[i],
        })

    runners = []
    if on_first:
        runners.append("1B")
    if on_second:
        runners.append("2B")
    if on_third:
        runners.append("3B")

    summary = {
        "count": f"{balls}-{strikes}",
        "outs": outs,
        "runners": ", ".join(runners) if runners else "Bases vacías",
        "stuff_plus_avg": round(float(np.mean(stuff_plus)), 1),
        "league": {k: round(float(league[k]), 4)
                   for k in ("k_pct", "bb_pct", "gb_pct", "fb_pct", "csw", "inplay")},
    }

    return {
        "objective": {"key": obj_key, "label": obj_label, "auto": auto, "reason": reason},
        "recommendation": recommendation,
        "ranking": ranking,
        "arsenal": out_arsenal,
        "summary": summary,
        "heatmap": heatmap,
        "metric_labels": METRIC_LABELS,
    }
