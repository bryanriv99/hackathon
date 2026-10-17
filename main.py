# -*- coding: utf-8 -*-
"""
Script unificado de procesamiento, entrenamiento, validación y exportación
de artefactos para analítica de pitcheo (Stuff+, Location+, Pitching+).
"""

import os
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb

print("--- [1/6] Cargando el dataset crudo ---")
file_path = 'stuff_model_df.parquet'
if not os.path.exists(file_path):
    raise FileNotFoundError(f"No se encontró el archivo '{file_path}' en la carpeta actual.")

df = pd.read_parquet(file_path)
print(f"Dataset original cargado con éxito. Filas: {len(df)}, Columnas: {len(df.columns)}")

# 1. Definir variables y unificar ID de lanzador desde el inicio
variables_identificadores = ['PitcherId', 'PitcherID', 'pitcher_id', 'PitchUID', 'AutoPitchType', 'PitchType', 'pitch_type']
variables_fisicas = ['RelSpeed', 'SpinRate', 'InducedVertBreak', 'HorzBreak', 'RelHeight', 'RelSide', 'Extension']
variables_contexto = ['Zone', 'zone', 'Balls', 'Strikes', 'PitcherThrows', 'BatterSide', 'altitude_category', 'AltitudeCategory', 'stadium', 'Stadium']
variables_target = ['PitchCall', 'TaggedHitType', 'PlayResult', 'KorBB']

columnas_deseadas = list(dict.fromkeys(variables_identificadores + variables_fisicas + variables_contexto + variables_target))
columnas_existentes = [col for col in columnas_deseadas if col in df.columns]

df_limpio = df[columnas_existentes].copy()

# Detectar y estandarizar el ID del pitcher a 'PitcherId'
col_id_encontrado = next((c for c in ['PitcherId', 'PitcherID', 'pitcher_id', 'PitchUID'] if c in df_limpio.columns), None)
if col_id_encontrado and col_id_encontrado != 'PitcherId':
    df_limpio['PitcherId'] = df_limpio[col_id_encontrado]

# Estandarizar nombre de columna Zone
if 'zone' in df_limpio.columns and 'Zone' not in df_limpio.columns:
    df_limpio['Zone'] = df_limpio['zone']

# 2. Limpieza de anomalías de lectura de TrackMan
if 'RelSpeed' in df_limpio.columns:
    df_limpio = df_limpio[df_limpio['RelSpeed'] > 20]
if 'SpinRate' in df_limpio.columns:
    df_limpio = df_limpio[(df_limpio['SpinRate'] > 0) & (df_limpio['SpinRate'] < 4000)]

# Rellenar nulos físicos menores
for col_f in variables_fisicas:
    if col_f in df_limpio.columns:
        df_limpio[col_f] = df_limpio[col_f].fillna(df_limpio[col_f].median())

print(f"Filas tras limpieza y tratamiento de nulos: {len(df_limpio)}")

print("--- [2/6] Calculando Expected Run Value (xRV) - RE24 ---")
re_count_matrix = {
    '0-0': 0.481, '1-0': 0.538, '2-0': 0.632, '3-0': 0.741,
    '0-1': 0.413, '1-1': 0.467, '2-1': 0.552, '3-1': 0.671,
    '0-2': 0.328, '1-2': 0.373, '2-2': 0.443, '3-2': 0.563
}
rv_event_weights = {
    'Single': 0.46, 'Double': 0.77, 'Triple': 1.06, 'HomeRun': 1.40,
    'Walk': 0.33, 'HitByPitch': 0.35, 'Strikeout': -0.27, 'FieldOut': -0.25
}

balls_col = next((c for c in ['Balls', 'balls', 'count_balls'] if c in df_limpio.columns), None)
strikes_col = next((c for c in ['Strikes', 'strikes', 'count_strikes'] if c in df_limpio.columns), None)

if balls_col and strikes_col:
    df_limpio['count'] = df_limpio[balls_col].astype(str) + '-' + df_limpio[strikes_col].astype(str)
    df_limpio['re_start'] = df_limpio['count'].map(re_count_matrix).fillna(0.481)
else:
    df_limpio['re_start'] = 0.481

play_result_col = next((c for c in ['PlayResult', 'play_result', 'PitchCall'] if c in df_limpio.columns), None)
if play_result_col:
    df_limpio['event_rv'] = df_limpio[play_result_col].map(rv_event_weights).fillna(0.0)
    df_limpio['xRV'] = df_limpio['event_rv'] - df_limpio['re_start']
else:
    df_limpio['xRV'] = 0.0

print("--- [3/6] Ingeniería de Arsenal (Fastballs baseline) ---")
pitch_type_col = next((c for c in ['PitchType', 'AutoPitchType', 'pitch_type'] if c in df_limpio.columns), None)

if pitch_type_col and 'PitcherId' in df_limpio.columns:
    fastballs = df_limpio[df_limpio[pitch_type_col].isin(['Fastball', 'Sinker', 'Four-Seam', 'FA', 'SI', 'FF'])]
    if len(fastballs) > 0:
        fb_profile = fastballs.groupby('PitcherId')[['RelSpeed', 'InducedVertBreak', 'HorzBreak']].mean().reset_index()
        fb_profile.rename(columns={'RelSpeed': 'fb_avg_speed', 'InducedVertBreak': 'fb_avg_ivb', 'HorzBreak': 'fb_avg_hb'}, inplace=True)
        
        df_limpio = df_limpio.merge(fb_profile, on='PitcherId', how='left')
        df_limpio['fb_avg_speed'] = df_limpio['fb_avg_speed'].fillna(df_limpio['RelSpeed'])
        df_limpio['fb_avg_ivb'] = df_limpio['fb_avg_ivb'].fillna(df_limpio['InducedVertBreak'])
        df_limpio['fb_avg_hb'] = df_limpio['fb_avg_hb'].fillna(df_limpio['HorzBreak'])

        df_limpio['velo_diff_vs_fb'] = df_limpio['RelSpeed'] - df_limpio['fb_avg_speed']
        df_limpio['ivb_diff_vs_fb'] = df_limpio['InducedVertBreak'] - df_limpio['fb_avg_ivb']
        df_limpio['hb_diff_vs_fb'] = df_limpio['HorzBreak'] - df_limpio['fb_avg_hb']
    else:
        df_limpio['velo_diff_vs_fb'] = 0.0
        df_limpio['ivb_diff_vs_fb'] = 0.0
        df_limpio['hb_diff_vs_fb'] = 0.0

# Mapeo de lateralidad
if 'PitcherThrows' in df_limpio.columns:
    df_limpio['PitcherThrows_Num'] = df_limpio['PitcherThrows'].map({'R': 1, 'L': 0}).fillna(1)
else:
    df_limpio['PitcherThrows_Num'] = 1

if 'BatterSide' in df_limpio.columns:
    df_limpio['BatterSide_Num'] = df_limpio['BatterSide'].map({'R': 1, 'L': 0}).fillna(1)
else:
    df_limpio['BatterSide_Num'] = 1

print("--- [4/6] Entrenando Sub-modelo 1: Stuff+ ---")
features_stuff = ['RelSpeed', 'SpinRate', 'InducedVertBreak', 'HorzBreak', 'RelHeight', 'RelSide', 'Extension']
features_stuff_existentes = [c for c in features_stuff if c in df_limpio.columns]

df_stuff = df_limpio.dropna(subset=features_stuff_existentes + ['xRV']).copy()
stuff_model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=4, random_state=42, objective='reg:squarederror')
stuff_model.fit(df_stuff[features_stuff_existentes], df_stuff['xRV'])

df_stuff['xRV_Stuff_Pred'] = stuff_model.predict(df_stuff[features_stuff_existentes])
mean_s, std_s = df_stuff['xRV_Stuff_Pred'].mean(), df_stuff['xRV_Stuff_Pred'].std()
df_stuff['Stuff+'] = 100 - (((df_stuff['xRV_Stuff_Pred'] - mean_s) / std_s) * 10)

df_limpio['xRV_Stuff_Pred'] = df_stuff['xRV_Stuff_Pred']
df_limpio['Stuff+'] = df_stuff['Stuff+']

print("--- [5/6] Entrenando Sub-modelo 2: Location+ y 3: Pitching+ ---")
# SE INCLUYE EXPLÍCITAMENTE 'Zone'
features_loc = ['Zone', 'Balls', 'Strikes', 'PitcherThrows_Num', 'BatterSide_Num']
cols_loc_existentes = [c for c in features_loc if c in df_limpio.columns]

df_loc = df_limpio.dropna(subset=cols_loc_existentes + ['xRV']).copy()
loc_model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=4, random_state=42, objective='reg:squarederror')
loc_model.fit(df_loc[cols_loc_existentes], df_loc['xRV'])

df_loc['xRV_Location_Pred'] = loc_model.predict(df_loc[cols_loc_existentes])
mean_l, std_l = df_loc['xRV_Location_Pred'].mean(), df_loc['xRV_Location_Pred'].std()
df_loc['Location+'] = 100 - (((df_loc['xRV_Location_Pred'] - mean_l) / std_l) * 10)

df_limpio['xRV_Location_Pred'] = df_loc['xRV_Location_Pred']
df_limpio['Location+'] = df_loc['Location+']

# Pitching+ (Combinado)
features_pitching_base = features_stuff_existentes + ['Zone', 'Balls', 'Strikes', 'velo_diff_vs_fb', 'ivb_diff_vs_fb', 'hb_diff_vs_fb', 'PitcherThrows_Num', 'BatterSide_Num']
features_pitching = [c for c in features_pitching_base if c in df_limpio.columns]

df_pitching = df_limpio.dropna(subset=features_pitching + ['xRV']).copy()
pitching_model = xgb.XGBRegressor(n_estimators=150, learning_rate=0.08, max_depth=5, random_state=42, objective='reg:squarederror')
pitching_model.fit(df_pitching[features_pitching], df_pitching['xRV'])

df_pitching['xRV_Pitching_Pred'] = pitching_model.predict(df_pitching[features_pitching])
mean_p, std_p = df_pitching['xRV_Pitching_Pred'].mean(), df_pitching['xRV_Pitching_Pred'].std()
df_pitching['Pitching+'] = 100 - (((df_pitching['xRV_Pitching_Pred'] - mean_p) / std_p) * 10)

df_limpio['xRV_Pitching_Pred'] = df_pitching['xRV_Pitching_Pred']
df_limpio['Pitching+'] = df_pitching['Pitching+']

# Rellenar valores nulos faltantes
for col_plus in ['Stuff+', 'Location+', 'Pitching+']:
    if col_plus in df_limpio.columns:
        df_limpio[col_plus] = df_limpio[col_plus].fillna(100.0)

print("--- [6/6] Generando resumen por lanzador y guardando artefactos ---")
if 'PitcherId' in df_limpio.columns:
    df_pitcher_summary = df_limpio.groupby('PitcherId').agg(
        Total_Pitches=('RelSpeed', 'count'),
        Avg_Stuff_Plus=('Stuff+', 'mean'),
        Avg_Location_Plus=('Location+', 'mean'),
        Avg_Pitching_Plus=('Pitching+', 'mean')
    ).reset_index().round(1)

    df_pitcher_summary.to_csv('resumen_pitchers_plus.csv', index=False)

# Reemplazar artefactos guardados en disco local
joblib.dump(stuff_model, 'stuff_model.pkl')
joblib.dump(loc_model, 'location_model.pkl')
joblib.dump(pitching_model, 'pitching_model.pkl')
df_limpio.to_parquet('dataset_scores_final.parquet')

print("\n[Éxito] Nuevos modelos (.pkl) y archivos exportados correctamente.")