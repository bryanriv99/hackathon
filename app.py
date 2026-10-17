
import streamlit as st
import pandas as pd
import joblib
import numpy as np
import plotly.graph_objects as go
import os
import joblib

# Carga desde la raíz del proyecto
stuff_model = joblib.load('stuff_model.pkl')
# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL DE LA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Diablos Rojos Analytics | Plataforma Plus",
    page_icon="⚾",
    layout="wide"
)

st.markdown(
    """
    <style>
    :root {
        --page: #f7f8fa;
        --card: #ffffff;
        --ink: #18181b;
        --muted: #71717a;
        --line: #e4e7ec;
        --lime: #d2ff00;
        --blue: #2563eb;
    }
    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--page); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppViewContainer"] > .main {
        padding: 2rem 3rem 3rem;
    }
    .block-container { max-width: 1500px; }
    [data-testid="stSidebar"] {
        background: var(--card);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { padding: 1.4rem 1.1rem; }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--ink);
        font-weight: 700;
    }
    h1, h2, h3 {
        color: var(--ink) !important;
        letter-spacing: -0.035em;
    }
    h1 { font-size: clamp(1.8rem, 3vw, 2.7rem) !important; margin-bottom: .35rem !important; }
    h2 { font-size: 1.35rem !important; margin-top: 1.5rem !important; }
    h3 { font-size: 1.05rem !important; }
    p { color: var(--muted); }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p {
        color: #52525b !important;
        font-size: .82rem;
    }
    [data-baseweb="select"] > div,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextInput"] input {
        background: #fff !important;
        border: 1px solid var(--line) !important;
        border-radius: 9px !important;
        color: var(--ink) !important;
    }
    [data-testid="stSlider"] [data-baseweb="slider"] div[data-testid="stThumb"] {
        background: var(--ink);
    }
    [data-testid="stMetric"] {
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        box-shadow: 0 5px 18px rgba(24, 24, 27, .04);
    }
    [data-testid="stMetricLabel"] p {
        color: var(--muted) !important;
        font-size: .78rem;
        font-weight: 600;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink) !important;
        font-size: 1.75rem;
        font-weight: 750;
    }
    [data-testid="stMetricDelta"] { color: #4d6900 !important; }
    [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
        background: #fff;
    }
    [data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        background: #fff;
    }
    [data-testid="stAlert"] { border-radius: 12px; }
    hr { border-color: var(--line); }
    @media (max-width: 900px) {
        [data-testid="stAppViewContainer"] > .main { padding: 1.2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div style="display:flex;align-items:center;gap:.75rem;margin-bottom:.25rem">'
    '<div style="background:#d2ff00;border-radius:12px;padding:.5rem .65rem;font-size:1.35rem">⚾</div>'
    '<div><div style="font-size:.72rem;color:#71717a;text-transform:uppercase;letter-spacing:.12em;font-weight:700">Diablos Rojos · Analytics</div>'
    '<h1 style="margin:0">Plataforma de analítica de pitcheo</h1></div></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="margin:.35rem 0 1.4rem">Compara Stuff+, Location+ y Pitching+ con una proyección del efecto de altitud en CDMX.</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 1. CARGA DE ARTEFACTOS DESDE LA RAÍZ LOCAL
# ---------------------------------------------------------
@st.cache_resource
def load_artifacts():
    stuff_model = joblib.load('stuff_model.pkl')
    loc_model = joblib.load('location_model.pkl')
    pitching_model = joblib.load('pitching_model.pkl')
    
    df_scores = pd.read_parquet('dataset_scores_final.parquet')
    df_summary = pd.read_csv('resumen_pitchers_plus.csv') if os.path.exists('resumen_pitchers_plus.csv') else None
    
    return stuff_model, loc_model, pitching_model, df_scores, df_summary


def build_model_input(model, values):
    """Construye la entrada usando exactamente las variables del modelo."""
    feature_names = model.get_booster().feature_names
    missing_features = [name for name in feature_names if name not in values]
    if missing_features:
        raise ValueError(
            f"El modelo requiere variables que no fueron definidas: {missing_features}"
        )
    return pd.DataFrame([[values[name] for name in feature_names]], columns=feature_names)

try:
    stuff_model, loc_model, pitching_model, df_scores, df_summary = load_artifacts()
    st.sidebar.success("✅ Artefactos cargados correctamente")
except Exception as e:
    st.error(f"❌ Error al cargar artefactos: {e}")
    st.info("Asegúrate de ejecutar el script de procesamiento en esta misma carpeta para re-generar los archivos .pkl y .parquet.")
    st.stop()

# ---------------------------------------------------------
# 2. CONTROLES Y SLIDERS (SIDEBAR)
# ---------------------------------------------------------
st.sidebar.header("🎛️ Parámetros del Lanzamiento")

pitch_type = st.sidebar.selectbox("Tipo de Pitcheo", ['Fastball', 'Sinker', 'Slider', 'Changeup', 'Curveball'], index=0)

st.sidebar.subheader("Métricas Físicas (Release)")
rel_speed = st.sidebar.slider("Velocidad (RelSpeed - mph)", 70.0, 103.0, 93.5)
spin_rate = st.sidebar.slider("Tasa de Giro (SpinRate - rpm)", 1000, 3500, 2250)
ivb_input = st.sidebar.slider("Quiebre Vert. Inducido (IVB - pulg)", -20.0, 25.0, 15.0)
hb_input = st.sidebar.slider("Quiebre Horiz. (HB - pulg)", -25.0, 25.0, 5.0)
rel_height = st.sidebar.slider("Altura de Soltado (RelHeight - ft)", 4.0, 7.5, 5.8)
rel_side = st.sidebar.slider("Posición Lateral (RelSide - ft)", -4.0, 4.0, -1.5)
extension = st.sidebar.slider("Extensión (Extension - ft)", 4.5, 7.5, 6.2)

st.sidebar.subheader("Ubicación y Contexto")
zone = st.sidebar.selectbox("Zona de Impacto (Zone)", list(range(1, 14)), index=4)
balls = st.sidebar.selectbox("Bolas", [0, 1, 2, 3], index=0)
strikes = st.sidebar.selectbox("Strikes", [0, 1, 2], index=0)
pitcher_throws = st.sidebar.radio("Mano del Pitcher", ["R", "L"], index=0)
batter_side = st.sidebar.radio("Mano del Bateador", ["R", "L"], index=0)

p_throws_num = 1 if pitcher_throws == 'R' else 0
b_side_num = 1 if batter_side == 'R' else 0

velo_diff = 0.0 if pitch_type in ['Fastball', 'Sinker'] else -8.0
ivb_diff = 0.0 if pitch_type in ['Fastball', 'Sinker'] else -7.0
hb_diff = 0.0 if pitch_type in ['Fastball', 'Sinker'] else 6.0

# ---------------------------------------------------------
# 3. MÓDULO 1: SIMULADOR Y CÁLCULO DE SCORES PLUS
# ---------------------------------------------------------
st.subheader("📊 Simulador Lado a Lado: Efecto de Altitud en CDMX")
st.markdown("Demuestra el impacto de la menor densidad del aire en el **Estadio Alfredo Harp Helú (~2,240 msnm)** sobre la trayectoria y las métricas Plus.")

cdmx_ivb = ivb_input * 0.82
cdmx_hb = hb_input * 0.85

# --- 1. STUFF+ ---
input_sea_stuff = pd.DataFrame([[rel_speed, spin_rate, ivb_input, hb_input, rel_height, rel_side, extension]], 
                               columns=['RelSpeed', 'SpinRate', 'InducedVertBreak', 'HorzBreak', 'RelHeight', 'RelSide', 'Extension'])

input_cdmx_stuff = pd.DataFrame([[rel_speed, spin_rate, cdmx_ivb, cdmx_hb, rel_height, rel_side, extension]], 
                                columns=['RelSpeed', 'SpinRate', 'InducedVertBreak', 'HorzBreak', 'RelHeight', 'RelSide', 'Extension'])

pred_xrv_stuff_sea = stuff_model.predict(input_sea_stuff)[0]
pred_xrv_stuff_cdmx = stuff_model.predict(input_cdmx_stuff)[0]

mean_s = df_scores['xRV_Stuff_Pred'].mean() if 'xRV_Stuff_Pred' in df_scores.columns else 0.0
std_s = df_scores['xRV_Stuff_Pred'].std() if 'xRV_Stuff_Pred' in df_scores.columns else 0.1

stuff_sea = 100 - (((pred_xrv_stuff_sea - mean_s) / std_s) * 10)
stuff_cdmx = 100 - (((pred_xrv_stuff_cdmx - mean_s) / std_s) * 10)

# --- 2. LOCATION+ ---
context_values = {
    'Zone': zone,
    'Balls': balls,
    'Strikes': strikes,
    'PitcherThrows_Num': p_throws_num,
    'BatterSide_Num': b_side_num,
}
input_loc = build_model_input(loc_model, context_values)

pred_xrv_loc = loc_model.predict(input_loc)[0]
mean_l = df_scores['xRV_Location_Pred'].mean() if 'xRV_Location_Pred' in df_scores.columns else 0.0
std_l = df_scores['xRV_Location_Pred'].std() if 'xRV_Location_Pred' in df_scores.columns else 0.1
loc_score = 100 - (((pred_xrv_loc - mean_l) / std_l) * 10)

# --- 3. PITCHING+ ---
pitching_values = {
    'RelSpeed': rel_speed,
    'SpinRate': spin_rate,
    'InducedVertBreak': ivb_input,
    'HorzBreak': hb_input,
    'RelHeight': rel_height,
    'RelSide': rel_side,
    'Extension': extension,
    **context_values,
    'velo_diff_vs_fb': velo_diff,
    'ivb_diff_vs_fb': ivb_diff,
    'hb_diff_vs_fb': hb_diff,
}
input_pitching = build_model_input(pitching_model, pitching_values)

pred_xrv_pitching = pitching_model.predict(input_pitching)[0]
pitching_values_cdmx = {
    **pitching_values,
    'InducedVertBreak': cdmx_ivb,
    'HorzBreak': cdmx_hb,
}
input_pitching_cdmx = build_model_input(pitching_model, pitching_values_cdmx)
pred_xrv_pitching_cdmx = pitching_model.predict(input_pitching_cdmx)[0]
mean_p = df_scores['xRV_Pitching_Pred'].mean() if 'xRV_Pitching_Pred' in df_scores.columns else 0.0
std_p = df_scores['xRV_Pitching_Pred'].std() if 'xRV_Pitching_Pred' in df_scores.columns else 0.1
pitching_score = 100 - (((pred_xrv_pitching - mean_p) / std_p) * 10)
pitching_score_cdmx = 100 - (((pred_xrv_pitching_cdmx - mean_p) / std_p) * 10)

col_sea, col_cdmx = st.columns(2)

with col_sea:
    st.markdown("### 🌊 Nivel del Mar")
    st.metric("Stuff+", f"{stuff_sea:.1f}")
    st.metric("Location+", f"{loc_score:.1f}")
    st.metric("Pitching+", f"{pitching_score:.1f}")
    st.metric("IVB / HB Real", f"{ivb_input:.1f}\" / {hb_input:.1f}\"")

with col_cdmx:
    st.markdown("### 🏟️ CDMX (Estadio Alfredo Harp Helú)")
    delta_s = stuff_cdmx - stuff_sea
    st.metric("Stuff+ Proyectado CDMX", f"{stuff_cdmx:.1f}", delta=f"{delta_s:.1f} pts")
    st.metric("Location+", f"{loc_score:.1f}")
    st.metric(
        "Pitching+ Proyectado CDMX",
        f"{pitching_score_cdmx:.1f}",
        delta=f"{pitching_score_cdmx - pitching_score:.1f} pts",
    )
    st.metric("IVB / HB Mermado", f"{cdmx_ivb:.1f}\" / {cdmx_hb:.1f}\"", delta=f"{cdmx_ivb - ivb_input:.1f}\" IVB")

st.divider()

# ---------------------------------------------------------
# 4. MÓDULO 2: VISUALIZADOR DE MOVIMIENTO (MOVEMENT PLOT)
# ---------------------------------------------------------
st.subheader("🎯 Mapa de Movimiento Interactivo (Movement Plot)")

fig = go.Figure()

if 'HorzBreak' in df_scores.columns and 'InducedVertBreak' in df_scores.columns:
    fig.add_trace(go.Scatter(
        x=df_scores['HorzBreak'].head(1000),
        y=df_scores['InducedVertBreak'].head(1000),
        mode='markers',
        name='Muestra Liga LMB',
        marker=dict(size=5, color='gray', opacity=0.25)
    ))

fig.add_trace(go.Scatter(
    x=[hb_input], y=[ivb_input],
    mode='markers+text', name='Nivel del Mar',
    text=['🌊 Nivel del Mar'], textposition='top center',
    marker=dict(size=14, color='blue', symbol='circle')
))

fig.add_trace(go.Scatter(
    x=[cdmx_hb], y=[cdmx_ivb],
    mode='markers+text', name='CDMX (Harp Helú)',
    text=['🏟️ CDMX'], textposition='bottom center',
    marker=dict(size=14, color='red', symbol='diamond')
))

fig.update_layout(
    title=f"Dispersión de Quiebre — {pitch_type}",
    xaxis=dict(title="Horizontal Break (pulgadas)", range=[-30, 30], zeroline=True, zerolinewidth=2),
    yaxis=dict(title="Induced Vertical Break (pulgadas)", range=[-30, 30], zeroline=True, zerolinewidth=2),
    width=800, height=550, template="plotly_white"
)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------
# 5. MÓDULO 3: RANKING Y BUSCADOR DE LANZADORES
# ---------------------------------------------------------
st.subheader("🔍 Buscador de Lanzadores: Rendimiento por Lugar y Situación")

if df_scores is not None and len(df_scores) > 0:
    f_col1, f_col2 = st.columns(2)
    
    with f_col1:
        stadium_opts = ['Todos'] + list(df_scores['stadium'].dropna().unique()) if 'stadium' in df_scores.columns else ['Todos', 'CDMX (Harp Helú)', 'Nivel del Mar']
        sel_stadium = st.selectbox("🏟️ Lugar / Estadio:", stadium_opts)
        
    with f_col2:
        if 'Balls' in df_scores.columns and 'Strikes' in df_scores.columns:
            df_scores['Count_Str'] = df_scores['Balls'].astype(str) + '-' + df_scores['Strikes'].astype(str)
            count_opts = ['Todos'] + list(df_scores['Count_Str'].unique())
        else:
            count_opts = ['Todos', '0-0', '0-2', '3-2', '2-1']
        sel_count = st.selectbox("⚾ Conteo (Bolas - Strikes):", count_opts)
        
    df_filtered = df_scores.copy()
    
    if sel_stadium != 'Todos' and 'stadium' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['stadium'] == sel_stadium]
        
    if sel_count != 'Todos' and 'Count_Str' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['Count_Str'] == sel_count]
        
    pitcher_id_col = next((c for c in ['PitcherId', 'PitcherID', 'pitcher_id', 'PitchUID'] if c in df_filtered.columns), None)
    
    if pitcher_id_col and len(df_filtered) > 0:
        st.markdown(f"#### 🏆 Ranking de Pitchers ({len(df_filtered)} picheos analizados):")
        
        ranking = df_filtered.groupby(pitcher_id_col).agg(
            Lanzamientos=('RelSpeed', 'count'),
            Avg_Stuff_Plus=('Stuff+', 'mean') if 'Stuff+' in df_filtered.columns else ('RelSpeed', 'mean'),
            Avg_Location_Plus=('Location+', 'mean') if 'Location+' in df_filtered.columns else ('RelSpeed', 'mean'),
            Avg_Pitching_Plus=('Pitching+', 'mean') if 'Pitching+' in df_filtered.columns else ('RelSpeed', 'mean')
        ).reset_index()
        
        ranking = ranking.sort_values(by='Avg_Pitching_Plus', ascending=False).round(1)
        st.dataframe(ranking.head(15), use_container_width=True)
    else:
        st.warning("No se encontraron lanzamientos para los filtros seleccionados.")

st.divider()

# ---------------------------------------------------------
# 6. TABLA GENERAL DE PITCHERS
# ---------------------------------------------------------
if st.checkbox("Mostrar Resumen Agregado por Pitcher"):
    if df_summary is not None:
        st.dataframe(df_summary.sort_values(by='Avg_Pitching_Plus', ascending=False), use_container_width=True)

