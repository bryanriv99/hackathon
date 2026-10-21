import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from jinja2 import TemplateNotFound

from pitch_service import analyze, get_meta, warm
from simulator_service import dashboard_data, metadata as get_simulator_meta, simulate

BASE = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE / "web" / "templates"),
    static_folder=str(BASE / "web" / "static"),
    static_url_path="/static",
)

warm()


@app.get("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return ("Frontend no disponible: falta web/templates/index.html. "
                "El backend /api/meta y /api/analyze ya están funcionando.", 200)


@app.get("/api/meta")
def api_meta():
    return jsonify(get_meta())


@app.get("/api/simulator/meta")
def api_simulator_meta():
    return jsonify(get_simulator_meta())


@app.post("/api/simulator/analyze")
def api_simulator_analyze():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Los datos del lanzamiento deben enviarse en formato JSON."}), 400
    try:
        return jsonify(simulate(data))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(dashboard_data())


@app.get("/plots/<path:filename>")
def plot_asset(filename):
    return send_from_directory(BASE / "plots", filename)


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Cuerpo JSON inválido."}), 400
    try:
        return jsonify(analyze(data))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
