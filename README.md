# Dashboard Stuff+ | Diablos Rojos del Mexico

Dashboard de Streamlit para explorar y simular métricas Stuff+, Location+ y Pitching+, con modelos entrenados, análisis SHAP y comparaciones por altitud.

## Requisitos

- Python 3.10 o superior
- Git

## Ejecución local en Windows

Desde la carpeta del proyecto, crea y activa un entorno virtual e instala las dependencias:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

La app busca primero `dataset_scores_final_v2.parquet` y luego `dataset_enriched.parquet` en la raíz del proyecto. Esos archivos grandes no se guardan en Git. Descarga `dataset_scores_final_v2.parquet` desde el [release de datos](https://github.com/Dustin2603/Id-Hackathon/releases/download/dashboard-data-v1/dataset_scores_final_v2.parquet) y colócalo junto a `app.py`. Después inicia el dashboard:

```powershell
streamlit run app.py
```

## Streamlit Community Cloud

Configura la app para usar el repositorio `Dustin2603/Id-Hackathon` y la rama `deploy/streamlit-app`, con `app.py` como archivo principal. En **Settings > Secrets**, agrega la URL del asset del release:

```toml
DATASET_URL = "https://github.com/Dustin2603/Id-Hackathon/releases/download/dashboard-data-v1/dataset_scores_final_v2.parquet"
```

La app descarga el dataset al iniciar cuando no encuentra uno local. No agregues `secrets.toml`, archivos `.env` ni datasets al commit.

## Actualizar el repositorio colaborativo

Trabaja sobre la rama de despliegue y trae primero los cambios recientes para no sobrescribir trabajo de otros colaboradores:

```powershell
git switch deploy/streamlit-app
git pull --ff-only origin deploy/streamlit-app
git status
```

Después de revisar los cambios, agrega solo los archivos que quieras actualizar y súbelos a esa rama:

```powershell
git add README.md app.py requirements.txt model_registry/ plots/ analyze_shap.py build_features.py train_models.py
git diff --cached
git commit -m "Actualiza dashboard de Streamlit"
git push origin deploy/streamlit-app
```

No uses `git add .` para esta actualización: evita incluir por accidente datos locales o secretos. Si el equipo integra cambios mediante pull request, crea uno de `deploy/streamlit-app` hacia `main` después del push.

## Datos y artefactos

- Los Parquet y datos fuente están excluidos por `.gitignore`; el Parquet requerido por la app se distribuye mediante el release `dashboard-data-v1`.
- Los modelos `.pkl`, metadatos JSON y archivos de análisis versionados en `model_registry/` y `plots/` son necesarios para el dashboard.
- No subas `.venv/`, `.venv-*/`, `.streamlit/secrets.toml` ni credenciales.