"""Turn audit metrics into decisions (spec sections 4, 5.1, 10, 11) and a Markdown report."""

from __future__ import annotations

from typing import Any

HIDDEN_SHARE_LIMIT = 0.30
SAMPLE_PRECISION_MIN = 0.8
GRACE_DAYS = 180
CLOSED_STATE_SHARE = 0.9
COVERAGE_MIN = 0.7

Decision = tuple[str, str]  # ("allowed" | "excluded", reason)

_FIXED: dict[str, Decision] = {
    # contracts
    "id_contrato": ("excluded", "identifier"),
    "proceso_de_compra": ("excluded", "join key to processes"),
    "referencia_del_contrato": ("excluded", "identifier"),
    "nombre_entidad": ("excluded", "redundant with entity codes"),
    "nit_entidad": ("allowed", "entity key, only for point-in-time history features"),
    "codigo_entidad": ("allowed", "entity key, only for point-in-time history features"),
    "departamento": ("allowed", "known at signing"),
    "ciudad": ("allowed", "known at signing"),
    "orden": ("allowed", "known at signing"),
    "sector": ("allowed", "known at signing"),
    "rama": ("allowed", "known at signing"),
    "entidad_centralizada": ("allowed", "known at signing"),
    "estado_contrato": ("excluded", "post-signing state"),
    "codigo_de_categoria_principal": ("allowed", "UNSPSC category, known at signing"),
    "descripcion_del_proceso": ("allowed", "text known at signing"),
    "objeto_del_contrato": ("allowed", "text known at signing"),
    "tipo_de_contrato": ("allowed", "known at signing"),
    "modalidad_de_contratacion": ("allowed", "known at signing"),
    "justificacion_modalidad_de": ("allowed", "known at signing"),
    "fecha_de_firma": ("allowed", "signing date: calendar features and split key"),
    "fecha_de_inicio_del_contrato": ("allowed", "planned start, known at signing"),
    "fecha_de_fin_del_contrato": ("excluded", "may be moved by extensions (spec 5.1)"),
    "el_contrato_puede_ser_prorrogado": ("allowed", "contract clause, known at signing"),
    "tipodocproveedor": ("allowed", "supplier type (natural person flag)"),
    "documento_proveedor": ("allowed", "supplier key, only for point-in-time history"),
    "codigo_proveedor": ("allowed", "supplier key, only for point-in-time history"),
    "proveedor_adjudicado": ("excluded", "supplier name"),
    "es_grupo": ("allowed", "known at signing"),
    "es_pyme": ("allowed", "known at signing"),
    "habilita_pago_adelantado": ("allowed", "known at signing"),
    "origen_de_los_recursos": ("allowed", "known at signing"),
    "destino_gasto": ("allowed", "known at signing"),
    "valor_de_pago_adelantado": ("allowed", "agreed at signing"),
    "valor_facturado": ("excluded", "post-signing execution (spec 5.1)"),
    "valor_pagado": ("excluded", "post-signing execution (spec 5.1)"),
    "dias_adicionados": ("excluded", "label source (spec 5.1)"),
    "espostconflicto": ("allowed", "known at signing"),
    "liquidaci_n": ("excluded", "post-signing state (spec 5.1)"),
    "ultima_actualizacion": ("excluded", "post-signing metadata (spec 5.1)"),
    "urlproceso": ("excluded", "link, not a feature"),
    "supplier_is_natural_person": ("allowed", "derived from document type"),
    # processes
    "id_del_proceso": ("excluded", "identifier"),
    "id_del_portafolio": ("excluded", "join key"),
    "referencia_del_proceso": ("excluded", "identifier"),
    "fecha_de_publicacion_del": ("allowed", "publication date, before signing"),
    "precio_base": ("allowed", "budget published before award"),
    "duracion": ("allowed", "planned duration in the tender"),
    "unidad_de_duracion": ("allowed", "unit of planned duration"),
    "proveedores_invitados": ("allowed", "tender stage, before signing"),
    "proveedores_que_manifestaron": ("allowed", "tender stage, before signing"),
    "numero_de_lotes": ("allowed", "tender structure"),
    "estado_del_procedimiento": ("excluded", "current state, can change after signing"),
    "adjudicado": ("excluded", "constant for signed contracts"),
    "valor_total_adjudicacion": ("allowed", "awarded value, known at signing"),
    "codigo_principal_de_categoria": ("allowed", "tender category"),
    "subtipo_de_contrato": ("allowed", "known at signing"),
}


def decide(results: dict[str, Any]) -> dict[str, Any]:
    hidden = results["hidden"]
    precision = results.get("sample_precision")
    if hidden["hidden_share"] <= HIDDEN_SHARE_LIMIT:
        target = "has_value_addition"
        target_reason = (
            f"hidden share {hidden['hidden_share']:.1%} <= {HIDDEN_SHARE_LIMIT:.0%}: "
            "explicit 'Adicion en el valor' amendments are a reliable label"
        )
    elif precision is None:
        target = "pending_manual_check"
        target_reason = "hidden share above limit; manual precision check of the sample missing"
    elif precision >= SAMPLE_PRECISION_MIN:
        target = "has_value_addition_text_recovered"
        target_reason = (
            f"hidden share {hidden['hidden_share']:.1%} > {HIDDEN_SHARE_LIMIT:.0%} and text "
            f"matcher precision {precision:.0%} >= {SAMPLE_PRECISION_MIN:.0%}: label = explicit "
            "OR text-matched amendments"
        )
    else:
        target = "has_time_extension"
        target_reason = (
            f"hidden share {hidden['hidden_share']:.1%} > {HIDDEN_SHARE_LIMIT:.0%} and text "
            f"matcher precision {precision:.0%} < {SAMPLE_PRECISION_MIN:.0%}: value-addition "
            "label unusable, time extension promoted (spec 11)"
        )

    features: dict[str, Decision] = dict(_FIXED)

    vva = results["value_vs_award"]
    with_add, without_add = vva["median_ratio_with_addition"], vva["median_ratio_without_addition"]
    amended = (
        with_add is not None and without_add is not None
        and with_add > 1.05 and 0.95 <= without_add <= 1.05
    )
    if amended:
        valor = "excluded"
        features["valor_del_contrato"] = (
            "excluded",
            f"amended value (median ratio to award {with_add:.2f} with additions vs "
            f"{without_add:.2f} without); use valor_total_adjudicacion or precio_base",
        )
    else:
        valor = "allowed"
        features["valor_del_contrato"] = ("allowed", "no evidence it includes additions")

    moved = results["end_date"]["share_end_date_moved"]
    if moved is not None and moved > 0.5:
        features["duraci_n_del_contrato"] = (
            "allowed",
            f"end date moved in {moved:.0%} of extended contracts while this field did not: "
            "original duration",
        )
    else:
        features["duraci_n_del_contrato"] = (
            "excluded", "cannot show it is the original duration; use processes.duracion"
        )

    bidders = results["bidders"]
    for col, key in (("proveedores_unicos_con", "unique_bidders_coverage"),
                     ("respuestas_al_procedimiento", "responses_coverage")):
        cov = bidders.get(key) or 0.0
        features[col] = (
            ("allowed", f"coverage {cov:.0%} among joined contracts")
            if cov >= COVERAGE_MIN
            else ("excluded", f"coverage {cov:.0%} < {COVERAGE_MIN:.0%}")
        )

    closed_states = [
        r["estado_contrato"] for r in results["closure"]
        if r["estado_contrato"] is not None
        and r["share_end_before_as_of_minus_180d"] >= CLOSED_STATE_SHARE
    ]
    return {
        "primary_target": target,
        "primary_target_reason": target_reason,
        "valor_del_contrato": valor,
        "closed_states": closed_states,
        "grace_days": GRACE_DAYS,
        "features": features,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _num(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def render_report(results: dict[str, Any], decisions: dict[str, Any]) -> str:
    h, vva, ed, b = (results[k] for k in ("hidden", "value_vs_award", "end_date", "bidders"))
    lines = [
        "# Phase 0 Data Audit",
        "",
        f"As of {results['as_of'].isoformat()}. Generated by "
        "`python -m procurement_risk audit`; numbers come from the audit sample in `data/raw`.",
        "",
        "## Decisions",
        "",
        f"- **Primary target: {decisions['primary_target']}** — "
        f"{decisions['primary_target_reason']}.",
        "- **Secondary target:** has_time_extension (`dias_adicionados > 0`).",
        f"- **`valor_del_contrato`:** {decisions['valor_del_contrato']}.",
        "- **Closed contract:** state in "
        f"{', '.join(f'`{s}`' for s in decisions['closed_states']) or '(none)'}, or end date at "
        f"least {decisions['grace_days']} days before the as-of date. Only closed contracts are "
        "labelled and used for training/evaluation.",
        "",
        "## Label rates by signing year",
        "",
        "| Year | Contracts | Value addition | Time extension |",
        "|---|---:|---:|---:|",
    ]
    for r in results["label_rates"]:
        lines.append(f"| {r['year']} | {r['n_contracts']:,} | {_pct(r['value_addition_rate'])} "
                     f"| {_pct(r['extension_rate'])} |")
    lines += [
        "",
        "## Q3. Value additions hidden under other amendment types",
        "",
        f"- Explicit `Adicion en el valor` amendments: {h['explicit']:,}",
        f"- `Modificacion General` / `No definido` amendments whose text describes a value "
        f"addition: {h['hidden_matches']:,} (share of all value additions: "
        f"{_pct(h['hidden_share'])})",
        f"- Contracts whose only evidence of a value addition is text: "
        f"{h.get('hidden_contracts', 0):,}",
        f"- Manual precision of the text matcher on the sample: "
        f"{_pct(results.get('sample_precision'))}",
        "",
        "## Q1. Is `valor_del_contrato` the original or the amended value?",
        "",
        f"- Contracts joined to their process: {_pct(vva['join_rate'])}",
        f"- Median `valor_del_contrato / valor_total_adjudicacion`: "
        f"{_num(vva['median_ratio_with_addition'])} with value additions "
        f"(n={vva.get('n_with_addition', 0):,}), {_num(vva['median_ratio_without_addition'])} "
        f"without (n={vva.get('n_without_addition', 0):,})",
        "",
        "## Q2. Do end dates move after extensions?",
        "",
        f"- Contracts with added days: {ed['n']:,}",
        f"- Share whose start-to-end span exceeds the stated duration by the added days: "
        f"{_pct(ed['share_end_date_moved'])}",
        f"- Share with an unparseable duration: {_pct(ed['share_duration_unparseable'])}",
        "",
        "## Q4. Contract states",
        "",
        f"| State | Contracts | End date > {GRACE_DAYS} days before as-of |",
        "|---|---:|---:|",
    ]
    for r in results["closure"]:
        lines.append(f"| {r['estado_contrato']} | {r['n']:,} | "
                     f"{_pct(r['share_end_before_as_of_minus_180d'])} |")
    lines += [
        "",
        "## Q5. Bidder information from SECOP II Procesos",
        "",
        f"- Join rate: {_pct(b['join_rate'])}",
        f"- `proveedores_unicos_con` coverage: {_pct(b['unique_bidders_coverage'])}",
        f"- `respuestas_al_procedimiento` coverage: {_pct(b['responses_coverage'])}",
        f"- Single-bidder share (where known): {_pct(b['single_bidder_share'])}",
        "",
        "## Feature whitelist",
        "",
        "| Column | Decision | Reason |",
        "|---|---|---|",
    ]
    for col, (verdict, reason) in decisions["features"].items():
        lines.append(f"| `{col}` | {verdict} | {reason} |")
    lines += ["", "## Text-matcher sample (for the manual precision check)", ""]
    lines += [f"{i}. {s}" for i, s in enumerate(h["sample"], 1)]
    return "\n".join(lines) + "\n"
