(function ($) {
    "use strict";

    var META = null;
    var SIM_META = null;
    var DASHBOARD = null;
    var LAST_SIMULATION = null;
    var state = { requestId: 0, timer: null };

    function fmt1(v) {
        return (Math.round(v * 10) / 10).toFixed(1);
    }

    function pct1(v) {
        return fmt1(v) + "%";
    }

    function clamp(v, min, max) {
        return Math.max(min, Math.min(max, v));
    }

    function pitchLabel(key) {
        var types = (META && META.pitch_types) || (SIM_META && SIM_META.pitch_types) || [];
        for (var i = 0; i < types.length; i++) {
            if (types[i].key === key) return types[i].label;
        }
        return key;
    }

    function objectiveLabel(key) {
        for (var i = 0; i < META.objectives.length; i++) {
            if (META.objectives[i].key === key) return META.objectives[i].label;
        }
        return key;
    }

    function stuffBadge(v) {
        var cls = "badge-stuff-gray";
        if (v >= 110) cls = "badge-stuff-green";
        else if (v < 90) cls = "badge-stuff-red";
        return '<span class="badge stuff-badge ' + cls + '">' + fmt1(v) + '</span>';
    }

    function fillArsenalRowValues($tr, thrower) {
        var type = $tr.find(".arsenal-type").val();
        var d = META.defaults[thrower][type];
        $tr.find(".arsenal-speed").val(d.speed);
        $tr.find(".arsenal-ivb").val(d.ivb);
        $tr.find(".arsenal-hb").val(d.hb);
    }

    function buildArsenalRow(pitch) {
        var options = "";
        for (var i = 0; i < META.pitch_types.length; i++) {
            var pt = META.pitch_types[i];
            options += '<option value="' + pt.key + '"' + (pitch && pitch.pitch_type === pt.key ? " selected" : "") + ">" + pt.label + "</option>";
        }
        pitch = pitch || { pitch_type: null, speed: "", ivb: "", hb: "" };
        var $tr = $(
            '<tr>' +
            '<td><select class="form-control underlined arsenal-type">' + options + "</select></td>" +
            '<td><input type="number" step="0.1" min="60" max="105" class="form-control underlined arsenal-speed" value="' + (pitch.speed === null || pitch.speed === undefined ? "" : pitch.speed) + '"></td>' +
            '<td><input type="number" step="0.1" min="-25" max="30" class="form-control underlined arsenal-ivb" value="' + (pitch.ivb === null || pitch.ivb === undefined ? "" : pitch.ivb) + '"></td>' +
            '<td><input type="number" step="0.1" min="-25" max="25" class="form-control underlined arsenal-hb" value="' + (pitch.hb === null || pitch.hb === undefined ? "" : pitch.hb) + '"></td>' +
            '<td class="arsenal-stuff">--</td>' +
            '<td><button type="button" class="btn btn-default btn-sm arsenal-remove" title="Eliminar"><i class="fa fa-trash-o"></i></button></td>' +
            "</tr>"
        );
        $tr.find(".arsenal-type").on("change", function () {
            fillArsenalRowValues($tr, currentThrows());
            scheduleAnalyze();
        });
        $tr.find(".arsenal-speed, .arsenal-ivb, .arsenal-hb").on("input", scheduleAnalyze);
        $tr.find(".arsenal-remove").on("click", function () {
            if ($("#arsenal-table tbody tr").length <= 1) return;
            $tr.remove();
            refreshArsenalButtons();
            scheduleAnalyze();
        });
        return $tr;
    }

    function currentThrows() {
        return $('input[name="p-throws"]:checked').val() || "Right";
    }

    function refreshArsenalButtons() {
        var n = $("#arsenal-table tbody tr").length;
        $("#btn-add-pitch").prop("disabled", n >= 6);
        $("#arsenal-table tbody tr").each(function () {
            $(this).find(".arsenal-remove").prop("disabled", n <= 1);
        });
    }

    function setLeagueHints() {
        var L = META.league;
        $("#hint-k").text("Liga: " + pct1(L.k_pct * 100));
        $("#hint-bb").text("Liga: " + pct1(L.bb_pct * 100));
        $("#hint-gb").text("Liga: " + pct1(L.gb_pct * 100));
        $("#hint-fb").text("Liga: " + pct1(L.fb_pct * 100));
    }

    function initObjectiveButtons() {
        var icons = { auto: "fa-magic", flyball: "fa-arrow-up", groundball: "fa-arrow-down", strikeout: "fa-bolt" };
        var $group = $("#objective-group");
        $group.empty();
        for (var i = 0; i < META.objectives.length; i++) {
            var o = META.objectives[i];
            var btn = $('<button type="button" class="btn btn-oval objective-btn" data-key="' + o.key + '"><i class="fa ' + icons[o.key] + '"></i> ' + o.label + "</button>");
            btn.on("click", function () {
                $(".objective-btn").removeClass("btn-primary").addClass("btn-secondary");
                $(this).addClass("btn-primary").removeClass("btn-secondary");
                scheduleAnalyze();
                return false;
            });
            $group.append(btn);
        }
        $(".objective-btn[data-key='auto']").addClass("btn-primary").removeClass("btn-secondary");
    }

    function init() {
        var dp = META.default_pitcher;
        $("#p-name").val(dp.name);
        $('input[name="p-throws"][value="' + dp.throws + '"]').prop("checked", true);
        $("#p-era").val(dp.era);
        $("#p-whip").val(dp.whip);
        $("#p-k").val(dp.k_pct);
        $("#p-bb").val(dp.bb_pct);
        $("#p-gb").val(dp.gb_pct);
        $("#p-fb").val(dp.fb_pct);
        setLeagueHints();
        initObjectiveButtons();
        for (var i = 0; i < META.default_arsenal.length; i++) {
            var p = $.extend({}, META.default_arsenal[i]);
            $("#arsenal-table tbody").append(buildArsenalRow(p));
        }
        refreshArsenalButtons();
        analyzeNow();
    }

    function readPitcher() {
        return {
            name: $("#p-name").val() || "Lanzador",
            throws: currentThrows(),
            era: parseFloat($("#p-era").val()),
            whip: parseFloat($("#p-whip").val()),
            k_pct: parseFloat($("#p-k").val()),
            bb_pct: parseFloat($("#p-bb").val()),
            gb_pct: parseFloat($("#p-gb").val()),
            fb_pct: parseFloat($("#p-fb").val())
        };
    }

    function readArsenal() {
        var list = [];
        $("#arsenal-table tbody tr").each(function () {
            var $tr = $(this);
            list.push({
                pitch_type: $tr.find(".arsenal-type").val(),
                speed: parseFloat($tr.find(".arsenal-speed").val()),
                ivb: parseFloat($tr.find(".arsenal-ivb").val()),
                hb: parseFloat($tr.find(".arsenal-hb").val())
            });
        });
        return list;
    }

    function readSituation() {
        var out = { balls: 0, strikes: 0, outs: 0, on_first: false, on_second: false, on_third: false, batter_side: $('input[name="sit-batter"]:checked').val() || "Right", objective: "auto" };
        $(".sit-group button.btn-primary").each(function () {
            var key = $(this).attr("data-sit");
            out[key] = parseInt($(this).attr("data-value"), 10);
        });
        out.on_first = $("#base-1b").hasClass("active");
        out.on_second = $("#base-2b").hasClass("active");
        out.on_third = $("#base-3b").hasClass("active");
        var obj = $(".objective-btn.btn-primary").attr("data-key");
        if (obj) out.objective = obj;
        return out;
    }

    function setGroupError($group, hasError) {
        $group.toggleClass("has-error", !!hasError);
    }

    function validate(pitcher, arsenal) {
        var ok = true;
        setGroupError($("#p-era").closest(".form-group"), !(pitcher.era >= 0 && pitcher.era <= 20));
        setGroupError($("#p-whip").closest(".form-group"), !(pitcher.whip >= 0 && pitcher.whip <= 5));
        setGroupError($("#p-k").closest(".form-group"), !(pitcher.k_pct >= 0 && pitcher.k_pct <= 100));
        setGroupError($("#p-bb").closest(".form-group"), !(pitcher.bb_pct >= 0 && pitcher.bb_pct <= 100));
        setGroupError($("#p-gb").closest(".form-group"), !(pitcher.gb_pct >= 0 && pitcher.gb_pct <= 100));
        setGroupError($("#p-fb").closest(".form-group"), !(pitcher.fb_pct >= 0 && pitcher.fb_pct <= 100));
        $("#arsenal-table tbody tr").each(function () {
            var $r = $(this);
            var speed = parseFloat($r.find(".arsenal-speed").val());
            var ivb = parseFloat($r.find(".arsenal-ivb").val());
            var hb = parseFloat($r.find(".arsenal-hb").val());
            var bad = isNaN(speed) || speed < 60 || speed > 105 || isNaN(ivb) || ivb < -25 || ivb > 30 || isNaN(hb) || hb < -25 || hb > 25;
            setGroupError($r.find(".arsenal-speed").closest("td"), false);
            $r.find(".arsenal-speed").toggleClass("input-error", isNaN(speed) || speed < 60 || speed > 105);
            $r.find(".arsenal-ivb").toggleClass("input-error", isNaN(ivb) || ivb < -25 || ivb > 30);
            $r.find(".arsenal-hb").toggleClass("input-error", isNaN(hb) || hb < -25 || hb > 25);
            if (bad) ok = false;
        });
        if (isNaN(pitcher.era) || pitcher.era < 0 || pitcher.era > 20) ok = false;
        if (isNaN(pitcher.whip) || pitcher.whip < 0 || pitcher.whip > 5) ok = false;
        if (isNaN(pitcher.k_pct) || pitcher.k_pct < 0 || pitcher.k_pct > 100) ok = false;
        if (isNaN(pitcher.bb_pct) || pitcher.bb_pct < 0 || pitcher.bb_pct > 100) ok = false;
        if (isNaN(pitcher.gb_pct) || pitcher.gb_pct < 0 || pitcher.gb_pct > 100) ok = false;
        if (isNaN(pitcher.fb_pct) || pitcher.fb_pct < 0 || pitcher.fb_pct > 100) ok = false;
        return ok;
    }

    function showValidationError() {
        var message = "Revisa los campos marcados en rojo. Completa las estadísticas del lanzador y cada lanzamiento del arsenal dentro de los rangos indicados.";
        $("#rec-state").html('<div class="alert alert-warning rec-alert" role="alert">' + message + "</div>");
    }

    function buildPayload() {
        var pitcher = readPitcher();
        var arsenal = readArsenal();
        if (!validate(pitcher, arsenal)) {
            showValidationError();
            return null;
        }
        return { pitcher: pitcher, arsenal: arsenal, situation: readSituation() };
    }

    function scheduleAnalyze() {
        clearTimeout(state.timer);
        state.timer = setTimeout(analyzeNow, 350);
    }

    function analyzeNow() {
        if (!META) return;
        var payload = buildPayload();
        if (!payload) return;
        state.requestId++;
        var reqId = state.requestId;
        $("#rec-state").html('<i class="fa fa-spinner fa-spin fa-2x"></i><p class="form-hint">Analizando…</p>');
        $.ajax({
            url: "/api/analyze",
            method: "POST",
            contentType: "application/json",
            data: JSON.stringify(payload)
        })
            .done(function (res) {
                if (reqId !== state.requestId) return;
                render(res);
            })
            .fail(function (xhr) {
                if (reqId !== state.requestId) return;
                var msg = "No se pudo analizar.";
                if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
                $("#rec-state").html('<div class="alert alert-danger rec-alert" role="alert">' + msg + "</div>");
            });
    }

    function renderStats(res) {
        var stuff = res.summary.stuff_plus_avg || 0;
        $("#stat-stuff").text(fmt1(stuff));
        $("#bar-stuff").css("width", pctBar(clamp((stuff - 60) / 80, 0, 1) * 100));
        var pitcher = readPitcher();
        $("#stat-k").text(pct1(pitcher.k_pct));
        $("#bar-k").css("width", pctBar(relativeToLeague(pitcher.k_pct, META.league.k_pct)));
        $("#stat-gb").text(pct1(pitcher.gb_pct));
        $("#bar-gb").css("width", pctBar(relativeToLeague(pitcher.gb_pct, META.league.gb_pct)));
        $("#stat-fb").text(pct1(pitcher.fb_pct));
        $("#bar-fb").css("width", pctBar(relativeToLeague(pitcher.fb_pct, META.league.fb_pct)));
        $("#stat-era").text(fmt1(pitcher.era));
        $("#bar-era").css("width", pctBar(clamp((6 - pitcher.era) / 6, 0, 1) * 100));
        $("#stat-whip").text(fmt1(pitcher.whip));
        $("#bar-whip").css("width", pctBar(clamp((3 - pitcher.whip) / 3, 0, 1) * 100));
        $("#summary-pitcher-name").text(pitcher.name);
        $("#arsenal-table tbody tr").each(function (i) {
            var $r = $(this);
            var info = res.arsenal[i];
            if (info) {
                var warnings = (info.warnings && info.warnings.length) ? '<span class="stuff-warnings">' + info.warnings.join(" · ") + "</span>" : "";
                $r.find(".arsenal-stuff").html(stuffBadge(info.stuff_plus) + warnings);
            }
        });
    }

    function pctBar(v) {
        return clamp(v, 0, 100) + "%";
    }

    function relativeToLeague(valuePct, leagueFrac) {
        return valuePct / (2 * leagueFrac * 100) * 100;
    }

    function renderRecommendation(res) {
        var rec = res.recommendation;
        var obj = res.objective;
        var autoBadge = obj.auto ? ' <span class="badge badge-primary">Automático</span>' : "";
        var diff = (rec.probability - rec.league_probability) * 100;
        var diffCls = diff >= 0 ? "cmp-pos" : "cmp-neg";
        var diffSign = diff >= 0 ? "+" : "";
        var html =
            '<div class="rec-objective">' + obj.label + autoBadge + "</div>" +
            '<p class="title-description rec-reason">' + (obj.reason || "") + "</p>" +
            '<h2 class="rec-pitch">' + rec.label + "</h2>" +
            '<div class="row rec-metrics">' +
            '<div class="col-4"><div class="rec-metric-value">' + fmt1(rec.speed) + '</div><div class="rec-metric-name">Velocidad (mph)</div></div>' +
            '<div class="col-4"><div class="rec-metric-value">' + stuffBadge(rec.stuff_plus) + '</div><div class="rec-metric-name">Stuff+</div></div>' +
            '<div class="col-4"><div class="rec-metric-value"><i class="fa fa-map-marker"></i> ' + rec.location.zone_label + '</div><div class="rec-metric-name">Ubicación</div></div>' +
            "</div>" +
            '<div class="rec-prob"><span class="rec-prob-value">' + pct1(rec.probability * 100) + "</span>" +
            '<span class="rec-prob-label">' + rec.metric_label + "</span>" +
            '<span class="rec-cmp ' + diffCls + '">' + diffSign + fmt1(diff) + " pts vs liga</span></div>" +
            '<div class="progress"><div class="progress-bar" style="width: ' + pctBar(rec.probability * 100) + ';"></div></div>';
        $("#rec-state").html(html);
    }

    function renderZone(res) {
        var el = document.getElementById("zone-chart");
        if (!el) return;
        var rec = res.recommendation;
        var hm = res.heatmap;
        var textColor = "#4f5f6f";
        var data = [];
        if (hm && hm.x && hm.y && hm.z) {
            var zt = [];
            for (var iy = 0; iy < hm.z.length; iy++) {
                zt.push(hm.z[iy].map(function (v) { return Math.round(v * 1000) / 1000; }));
            }
            data.push({
                type: "heatmap",
                x: hm.x,
                y: hm.y,
                z: zt,
                colorscale: [[0, "rgba(255,255,255,0)"], [0.2, "#fde4e8"], [0.5, "#f5a6b3"], [0.75, "#dd4660"], [1, "#C41E3A"]],
                opacity: 0.55,
                zsmooth: "best",
                showscale: false,
                hovertemplate: "%{z:.0%}<extra></extra>",
                colorbar: { tickformat: ".0%" }
            });
        }
        var markerColor = rec.location.in_zone ? "#2ECC71" : "#E74C3C";
        var markerText = rec.label + " " + pct1(rec.probability * 100);
        data.push({
            type: "scatter",
            mode: "markers+text",
            x: [rec.location.x],
            y: [rec.location.y],
            marker: { size: 25, color: markerColor, line: { color: "#ffffff", width: 2 } },
            text: [rec.label],
            textposition: "top center",
            textfont: { size: 11, color: textColor },
            hovertemplate: "<b>" + rec.label + "</b><br>" + rec.metric_label + ": %{text}<extra></extra>",
            customdata: [[rec.label + " " + pct1(rec.probability * 100)]]
        });
        var layout = {
            title: { text: "Zona de Strike", font: { family: "Open Sans, sans-serif", size: 14, color: textColor } },
            xaxis: { title: "Lateral (pies)", range: [-2.5, 2.5], zeroline: false, showgrid: false },
            yaxis: { title: "Altura (pies)", range: [-0.5, 5.0], zeroline: false, showgrid: false },
            showlegend: false,
            height: 380,
            margin: { l: 45, r: 15, t: 45, b: 45 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Open Sans, sans-serif", color: textColor },
            annotations: [
                {
                    x: rec.location.x,
                    y: rec.location.y + 0.45,
                    text: markerText,
                    showarrow: false,
                    font: { family: "Open Sans, sans-serif", size: 10, color: textColor },
                    bgcolor: "rgba(255,255,255,0.8)"
                }
            ]
        };
        var shapes = [
            { type: "rect", xref: "x", yref: "y", x0: -0.83, x1: 0.83, y0: 1.5, y1: 3.5, line: { color: textColor, width: 2 } },
            { type: "path", xref: "x", yref: "y", path: "M -0.71 0.5 L 0.71 0.5 L 0.71 0.3 L 0 0 L -0.71 0.3 Z", line: { color: textColor, width: 1 }, fillcolor: "rgba(79,95,111,0.12)" }
        ];
        layout.shapes = shapes;        Plotly.react(el, data, layout, { displayModeBar: false, responsive: true });
        $("#zone-legend-pitch").text(rec.label);
    }

    function renderRanking(res) {
        var keys = ["flyball", "groundball", "strikeout"];
        var titles = { flyball: "Forzar elevado", groundball: "Forzar rola", strikeout: "Buscar ponche" };
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            var list = res.ranking[key] || [];
            var metric = res.metric_labels[key] || "";
            var $body = $("#rank-" + key);
            $body.empty();
            $("#desc-" + key).text(metric);
            for (var j = 0; j < list.length; j++) {
                var item = list[j];
                var row = $(
                    '<tr>' +
                    '<th scope="row">' + (j + 1) + "</th>" +
                    "<td>" + item.label + "</td>" +
                    '<td><i class="fa fa-map-marker"></i> ' + item.location.zone_label + "</td>" +
                    '<td><div class="rank-prob"><div class="progress"><div class="progress-bar" style="width: ' + pctBar(item.probability * 100) + ';"></div></div><span>' + pct1(item.probability * 100) + "</span></div></td>" +
                    "<td>" + stuffBadge(item.stuff_plus) + "</td>" +
                    "</tr>"
                );
                if (j === 0) row.addClass("rank-first");
                $body.append(row);
            }
        }
        var activeKey = res.objective.key;
        var $tab = $("#ranking a[data-key='" + activeKey + "']");
        if ($tab.length) $tab.tab("show");
    }

    function render(res) {
        renderStats(res);
        renderRecommendation(res);
        renderZone(res);
        renderRanking(res);
    }

    function wireEvents() {
        $("#btn-analyze").on("click", function () {
            clearTimeout(state.timer);
            analyzeNow();
            return false;
        });
        $("#btn-add-pitch").on("click", function () {
            if ($("#arsenal-table tbody tr").length >= 6) return;
            $("#arsenal-table tbody").append(buildArsenalRow(null));
            refreshArsenalButtons();
            scheduleAnalyze();
            return false;
        });
        $("#p-name").on("input", scheduleAnalyze);
        $("#p-era, #p-whip, #p-k, #p-bb, #p-gb, #p-fb").on("input", scheduleAnalyze);
        $('input[name="p-throws"]').on("change", function () {
            $("#arsenal-table tbody tr").each(function () {
                fillArsenalRowValues($(this), currentThrows());
            });
            scheduleAnalyze();
        });
        $(".sit-group button").on("click", function () {
            var $group = $(this).closest(".sit-group");
            var $btn = $(this);
            $group.find("button").removeClass("btn-primary").addClass("btn-secondary");
            $btn.addClass("btn-primary").removeClass("btn-secondary");
            scheduleAnalyze();
            return false;
        });
        $('input[name="sit-batter"]').on("change", scheduleAnalyze);
        $(".diamond-base").on("click", function () {
            $(this).toggleClass("active");
            scheduleAnalyze();
            return false;
        });
        $("#sidebar-collapse-btn").on("click", function (e) {
            e.preventDefault();
            $("#app").toggleClass("sidebar-open");
        });
        $("#sidebar-overlay").on("click", function () {
            $("#app").removeClass("sidebar-open");
        });
        $(".sidebar-menu a").on("click.smooth", function () {
            var target = $(this.hash || $(this).attr("href"));
            if (target.length) {
                $("html, body").animate({ scrollTop: target.offset().top - 100 }, 400);
                return false;
            }
        });
        var rT = null;
        $(window).on("resize", function () {
            clearTimeout(rT);
            rT = setTimeout(function () {
                var el = document.getElementById("zone-chart");
                if (el && window.Plotly) Plotly.Plots.resize(el);
            }, 150);
        });
    }

    function simPayload() {
        return {
            pitch_type: $("#sim-pitch-type").val(), pitcher_throws: $("#sim-throws").val(),
            batter_side: $("#sim-batter").val(),
            rel_speed: $("#sim-rel-speed").val(), spin_rate: $("#sim-spin-rate").val(),
            spin_axis: $("#sim-spin-axis").val(), ivb: $("#sim-ivb").val(), hb: $("#sim-hb").val(),
            extension: $("#sim-extension").val(), rel_height: $("#sim-rel-height").val(),
            rel_side: $("#sim-rel-side").val(), plate_loc_height: $("#sim-plate-height").val(),
            plate_loc_side: $("#sim-plate-side").val(), balls: $("#sim-balls").val(), strikes: $("#sim-strikes").val()
        };
    }

    function setSimDefaults() {
        var d = SIM_META.defaults;
        $("#sim-pitch-type").val(d.pitch_type);
        $("#sim-throws").val(d.pitcher_throws);
        $("#sim-batter").val(d.batter_side);
        $("#sim-rel-speed").val(d.rel_speed); $("#sim-spin-rate").val(d.spin_rate);
        $("#sim-spin-axis").val(d.spin_axis); $("#sim-ivb").val(d.ivb); $("#sim-hb").val(d.hb);
        $("#sim-extension").val(d.extension); $("#sim-rel-height").val(d.rel_height);
        $("#sim-rel-side").val(d.rel_side); $("#sim-plate-height").val(d.plate_loc_height);
        $("#sim-plate-side").val(d.plate_loc_side); $("#sim-balls").val(d.balls); $("#sim-strikes").val(d.strikes);
    }

    function renderSimCharts(res) {
        var movement = (DASHBOARD && DASHBOARD.movement) || {};
        var movementData = [];
        var colors = { "Four-Seam": "#C41E3A", Sinker: "#259b8d", Slider: "#e3a526", Changeup: "#5277b8", Curveball: "#8565b5", Cutter: "#da704e" };
        Object.keys(movement).forEach(function (key) {
            movementData.push({ type: "scatter", mode: "markers", name: pitchLabel(key), x: movement[key].hb, y: movement[key].ivb,
                marker: { size: 5, opacity: 0.25, color: colors[key] || "#8090a0" }, hovertemplate: pitchLabel(key) + "<br>HB %{x:.1f} · IVB %{y:.1f}<extra></extra>" });
        });
        movementData.push({ type: "scatter", mode: "markers+text", name: "Lanzamiento evaluado", x: [res.movement.hb], y: [res.movement.ivb],
            marker: { size: 16, color: "#C41E3A", symbol: "diamond", line: { width: 2, color: "white" } }, text: [res.pitch_label], textposition: "top center" });
        Plotly.react("sim-movement-chart", movementData, {
            title: { text: "Movimiento del lanzamiento", font: { size: 15 } }, xaxis: { title: "Quiebre horizontal (pulg)", range: [-25, 25], zeroline: true },
            yaxis: { title: "Quiebre vertical inducido (pulg)", range: [-25, 25], zeroline: true }, height: 360, margin: { l: 50, r: 20, t: 50, b: 55 },
            paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", legend: { orientation: "h", y: -0.25 }
        }, { responsive: true, displayModeBar: false });
        var color = res.in_zone ? "#2ECC71" : "#E74C3C";
        Plotly.react("sim-zone-chart", [{ type: "scatter", mode: "markers", x: [res.location.x], y: [res.location.y],
            marker: { size: 20, color: color, line: { color: "#fff", width: 2 } }, hovertemplate: "Ubicación: %{x:.2f}, %{y:.2f}<extra></extra>" }], {
            title: { text: "Ubicación y zona de strike", font: { size: 15 } }, xaxis: { title: "Lateral (pies)", range: [-2.5, 2.5], zeroline: false },
            yaxis: { title: "Altura (pies)", range: [-0.5, 5], zeroline: false }, height: 360, margin: { l: 50, r: 20, t: 50, b: 55 },
            shapes: [
                { type: "rect", x0: -0.83, x1: 0.83, y0: 1.5, y1: 3.5, line: { color: "#596675", width: 2 } },
                { type: "path", path: "M -0.71 0.5 L 0.71 0.5 L 0.71 0.3 L 0 0 L -0.71 0.3 Z", line: { color: "#596675", width: 1 }, fillcolor: "rgba(79,95,111,0.12)" }
            ], paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", showlegend: false
        }, { responsive: true, displayModeBar: false });
    }

    function renderSimExplanation(res) {
        var key = $("#sim-explanation-score").val() || "stuff";
        var items = (res.explanations && res.explanations[key]) || [];
        $("#sim-shap-note").text(res.explanation_note || "");
        if (!items.length) {
            Plotly.react("sim-shap-chart", [], { annotations: [{ text: "No hay desglose disponible para este cálculo.", showarrow: false }], xaxis: { visible: false }, yaxis: { visible: false }, height: 280 });
            return;
        }
        items.sort(function (a, b) { return Math.abs(a.impact) - Math.abs(b.impact); });
        Plotly.react("sim-shap-chart", [{ type: "bar", orientation: "h", y: items.map(function (item) { return item.feature; }),
            x: items.map(function (item) { return item.impact; }),
            marker: { color: items.map(function (item) { return item.impact >= 0 ? "#25866b" : "#c44b58"; }) },
            customdata: items.map(function (item) { return item.value; }),
            hovertemplate: "%{y}<br>Aporte: %{x:+.2f} puntos Plus<br>Valor del lanzamiento: %{customdata:.2f}<extra></extra>" }], {
            xaxis: { title: "Aporte estimado al score (puntos Plus)", zeroline: true, zerolinecolor: "#657487" },
            yaxis: { automargin: true }, height: 330, margin: { l: 145, r: 20, t: 15, b: 55 },
            paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)"
        }, { responsive: true, displayModeBar: false });
    }

    function runSimulation() {
        if (!SIM_META) return;
        $("#btn-simulate").prop("disabled", true);
        $("#sim-status").text("Calculando…");
        $.ajax({ url: "/api/simulator/analyze", method: "POST", contentType: "application/json", data: JSON.stringify(simPayload()) })
            .done(function (res) {
                LAST_SIMULATION = res;
                ["stuff", "location", "pitching"].forEach(function (key) {
                    $("#sim-score-" + key).text(fmt1(res.scores[key]));
                    var delta = res.deltas[key];
                    $("#sim-delta-" + key).text((delta > 0 ? "+" : "") + fmt1(delta) + " vs. referencia");
                    $("#sim-delta-" + key).toggleClass("positive", delta >= 0).toggleClass("negative", delta < 0);
                });
                var warnings = $("#sim-warnings").empty();
                if (res.warnings.length) {
                    warnings.prop("hidden", false).append($('<b>').text("Valores fuera del rango central observado en los datos:"));
                    var list = $("<ul>");
                    res.warnings.forEach(function (w) { list.append($('<li>').text(w.field + ": " + w.value + " (rango observado " + w.min + "–" + w.max + ")")); });
                    warnings.append(list);
                } else warnings.prop("hidden", true);
                $("#sim-explain-title").text(res.pitch_label + " · " + ($("#sim-throws").val() === "Right" ? "lanzador derecho" : "lanzador zurdo") + " · conteo " + $("#sim-balls").val() + "-" + $("#sim-strikes").val());
                $("#sim-explain-copy").text("Stuff+ resume la calidad física; Location+ evalúa la ubicación con el conteo; Pitching+ integra ambas. El lanzamiento " + (res.in_zone ? "cae dentro" : "queda fuera") + " de la zona marcada. Velocidad percibida estimada: " + res.perceived_velocity + " mph, con " + res.effective_distance + " pies de distancia efectiva.");
                renderSimCharts(res);
                renderSimExplanation(res);
                $("#sim-status").text("Métricas actualizadas");
            })
            .fail(function (xhr) {
                var msg = (xhr.responseJSON && xhr.responseJSON.error) || "No se pudo calcular. Revisa los valores ingresados.";
                $("#sim-status").text(msg);
            })
            .always(function () { $("#btn-simulate").prop("disabled", false); });
    }

    function renderValidation(validation) {
        if (!validation) return;
        function addRows(selector, data) {
            var body = $(selector).empty();
            Object.keys(data || {}).forEach(function (name) {
                var m = data[name];
                body.append($("<tr>").append($('<td>').text(name), $('<td>').text(Number(m.n).toLocaleString("es-MX")),
                    $('<td>').text(Number(m.rmse).toFixed(3)), $('<td>').text(Number(m.mae).toFixed(3)), $('<td>').text(Number(m.r2).toFixed(3))));
            });
        }
        addRows("#validation-pitcher", validation.pitcher_holdout);
        addRows("#validation-season", validation.season_holdout);
        var altitudeBody = $("#validation-altitude").empty();
        Object.keys(validation.altitude_holdout || {}).forEach(function (altitude) {
            Object.keys(validation.altitude_holdout[altitude]).forEach(function (model) {
                var m = validation.altitude_holdout[altitude][model];
                altitudeBody.append($("<tr>").append($('<td>').text(altitude), $('<td>').text(model), $('<td>').text(Number(m.n).toLocaleString("es-MX")),
                    $('<td>').text(Number(m.rmse).toFixed(3)), $('<td>').text(Number(m.mae).toFixed(3)), $('<td>').text(Number(m.r2).toFixed(3))));
            });
        });
    }

    function renderAltitude(data) {
        var rows = data.altitude || [];
        var detailBody = $("#altitude-table-body").empty();
        var metricNames = { InducedVertBreak: "Quiebre vertical (pulg)", HorzBreak: "Quiebre horizontal (pulg)", RelSpeed: "Velocidad (mph)" };
        rows.forEach(function (row) {
            var p = Number(row.p_value);
            detailBody.append($("<tr>").append($('<td>').text(pitchLabel(row.pitch_type)), $('<td>').text(metricNames[row.metric] || row.metric),
                $('<td>').text(Number(row.cdmx_mean).toFixed(2)), $('<td>').text(Number(row.noalt_mean).toFixed(2)),
                $('<td>').text((Number(row.delta) > 0 ? "+" : "") + Number(row.delta).toFixed(2)),
                $('<td>').text(p < .001 ? "< 0.001" : p.toFixed(3)),
                $('<td>').text(Number(row.n_cdmx).toLocaleString("es-MX") + " / " + Number(row.n_noalt).toLocaleString("es-MX"))));
        });
        var metrics = ["InducedVertBreak", "HorzBreak", "RelSpeed"];
        var labels = { InducedVertBreak: "Quiebre vertical (pulg)", HorzBreak: "Quiebre horizontal (pulg)", RelSpeed: "Velocidad (mph)" };
        var traces = metrics.map(function (metric) {
            var selected = rows.filter(function (r) { return r.metric === metric; });
            return { type: "bar", name: labels[metric], x: selected.map(function (r) { return pitchLabel(r.pitch_type); }),
                y: selected.map(function (r) { return r.delta; }), text: selected.map(function (r) { return (r.delta > 0 ? "+" : "") + Number(r.delta).toFixed(2); }),
                textposition: "outside", hovertemplate: "%{x}<br>Delta %{y:.2f}<extra>" + labels[metric] + "</extra>" };
        });
        Plotly.react("altitude-chart", traces, { barmode: "group", title: "Diferencia de medias: CDMX menos nivel del mar", xaxis: { title: "Tipo de lanzamiento" },
            yaxis: { title: "Diferencia" }, height: 450, margin: { l: 60, r: 25, t: 60, b: 100 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", legend: { orientation: "h", y: -0.3 } }, { responsive: true, displayModeBar: false });
        var significant = rows.filter(function (r) { return r.metric === "InducedVertBreak" && Number(r.p_value) < 0.05; }).sort(function (a,b) { return a.delta - b.delta; })[0];
        $("#altitude-summary").text(significant ? "En estos datos, " + pitchLabel(significant.pitch_type) + " muestra el mayor cambio de quiebre vertical entre los tipos listados: " + Number(significant.delta).toFixed(2) + " pulg (p < 0.05)." : "No hay datos suficientes para resumir las diferencias de altitud.");
        var plus = data.stuff_altitude || [];
        var cats = ["Extreme Altitude", "Medium Altitude", "No Altitude"];
        var pTraces = cats.map(function (cat) { return { type: "bar", name: cat === "Extreme Altitude" ? "Altitud extrema (CDMX)" : cat === "No Altitude" ? "Nivel del mar" : "Altitud media",
            x: plus.map(function (r) { return pitchLabel(r.AutoPitchType); }), y: plus.map(function (r) { return r[cat]; }) }; });
        Plotly.react("stuff-altitude-chart", pTraces, { barmode: "group", yaxis: { title: "Stuff+ promedio" }, height: 400, margin: { l: 55, r: 20, t: 25, b: 80 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", legend: { orientation: "h", y: -0.3 } }, { responsive: true, displayModeBar: false });
    }

    function renderExplorer(data) {
        var body = $("#top-pitchers-body").empty();
        (data.top_pitchers || []).forEach(function (p) {
            body.append($("<tr>").append($('<td>').text(p.pitcher_anon_id), $('<td>').text(Number(p.n_pitches).toLocaleString("es-MX")),
                $('<td>').text(Number(p["avg_Stuff+"]).toFixed(1)), $('<td>').text(p["avg_Location+"] == null ? "—" : Number(p["avg_Location+"]).toFixed(1)),
                $('<td>').text(p["avg_Pitching+"] == null ? "—" : Number(p["avg_Pitching+"]).toFixed(1)), $('<td>').text(p.avg_RelSpeed == null ? "—" : Number(p.avg_RelSpeed).toFixed(1))));
        });
        function renderDistribution() {
            var score = $("#explorer-score").val();
            var d = (data.distributions || {})[score];
            if (!d) return;
            Plotly.react("score-distribution-chart", [{ type: "bar", x: d.x, y: d.y, marker: { color: "#C41E3A" }, hovertemplate: score + ": %{x}<br>Lanzamientos: %{y}<extra></extra>" }], {
                xaxis: { title: score, range: [60, 140] }, yaxis: { title: "Número de lanzamientos" }, height: 350, margin: { l: 60, r: 20, t: 15, b: 50 },
                shapes: [{ type: "line", x0: 100, x1: 100, y0: 0, y1: 1, yref: "paper", line: { dash: "dash", color: "#333" } }],
                annotations: [{ x: 100, y: 1, yref: "paper", text: "Referencia 100", showarrow: false, yshift: 12 }], paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)"
            }, { responsive: true, displayModeBar: false });
        }
        renderDistribution(); $("#explorer-score").on("change", renderDistribution);
        if (data.raw_rows && data.raw_rows.length) {
            var columns = (data.raw_columns || Object.keys(data.raw_rows[0])).slice(0, 14);
            var head = $("#raw-data-head").empty().append($("<tr>"));
            columns.forEach(function (col) { head.find("tr").append($('<th>').text(col)); });
            var rawBody = $("#raw-data-body").empty();
            data.raw_rows.forEach(function (row) { var tr = $("<tr>"); columns.forEach(function (col) { tr.append($('<td>').text(row[col] == null ? "" : row[col])); }); rawBody.append(tr); });
        }
        if (!data.dataset_available) $("#explorer-notice").prop("hidden", false).html("<b>Dataset no disponible.</b><span>Para habilitar el explorador y los datos de movimiento, coloca dataset_scores_final_v2.parquet en la carpeta del proyecto o configura DATASET_URL en el servidor.</span>");
    }

    function initDashboard() {
        $.getJSON("/api/dashboard").done(function (data) {
            DASHBOARD = data;
            if (data.altitude && data.altitude.length) renderAltitude(data);
            renderValidation(data.validation);
            renderExplorer(data);
            if (SIM_META) runSimulation();
        }).fail(function () { $("#sim-status").text("No se pudieron cargar los paneles de datos adicionales."); });
    }

    function initSimulator() {
        $.getJSON("/api/simulator/meta").done(function (meta) {
            SIM_META = meta;
            meta.pitch_types.forEach(function (pitch) { $("#sim-pitch-type").append($('<option>').val(pitch.key).text(pitch.label)); });
            setSimDefaults();
            $("#btn-simulate").on("click", runSimulation);
            $("#btn-sim-reset").on("click", function () { setSimDefaults(); runSimulation(); });
            $("#sim-explanation-score").on("change", function () { if (LAST_SIMULATION) renderSimExplanation(LAST_SIMULATION); });
            $("#simulator").find("input, select").on("change", function () { $("#sim-status").text("Cambios pendientes · calcula para actualizar"); });
            runSimulation();
        }).fail(function () { $("#sim-status").text("No se pudo cargar la configuración de los modelos."); });
    }

    $(function () {
        wireEvents();
        initSimulator();
        initDashboard();
        $("#btn-toggle-raw").on("click", function () {
            var open = !$("#raw-data-wrap").prop("hidden");
            $("#raw-data-wrap").prop("hidden", open);
            $(this).attr("aria-expanded", String(!open)).text(open ? "Mostrar datos crudos" : "Ocultar datos crudos");
        });
        $(".sidebar-menu a").on("click", function () {
            var href = $(this).attr("href");
            $(".sidebar-menu li").removeClass("active");
            $(this).closest("li").addClass("active");
            if (href === "#recomendacion") $("html, body").animate({ scrollTop: $("#recomendacion").offset().top - 90 }, 350);
        });
        $.getJSON("/api/meta")
            .done(function (meta) {
                META = meta;
                init();
            })
            .fail(function () {
                $("#rec-state").html('<div class="alert alert-danger rec-alert" role="alert">No se pudo cargar la configuración (/api/meta).</div>');
            });
    });
})(jQuery);
