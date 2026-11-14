from datetime import date

from procurement_risk.audit.report import decide, render_report


def results(hidden_share=0.1, sample_precision=None, with_add=1.0, without_add=1.0,
            moved=0.2, coverage=0.9):
    return {
        "as_of": date(2026, 11, 14),
        "sample_precision": sample_precision,
        "label_rates": [{"year": 2021, "n_contracts": 10, "value_addition_rate": 0.03,
                         "extension_rate": 0.15}],
        "hidden": {"explicit": 90, "hidden_matches": 10, "hidden_share": hidden_share,
                   "hidden_contracts": 5, "sample": ["ADICION EN VALOR"]},
        "value_vs_award": {"join_rate": 0.8, "median_ratio_with_addition": with_add,
                           "median_ratio_without_addition": without_add,
                           "n_with_addition": 5, "n_without_addition": 50},
        "end_date": {"n": 10, "share_end_date_moved": moved,
                     "share_duration_unparseable": 0.0},
        "closure": [{"estado_contrato": "terminado", "n": 5,
                     "share_end_before_as_of_minus_180d": 0.95},
                    {"estado_contrato": "En ejecución", "n": 5,
                     "share_end_before_as_of_minus_180d": 0.2}],
        "bidders": {"join_rate": 0.8, "unique_bidders_coverage": coverage,
                    "responses_coverage": 0.9, "single_bidder_share": 0.4},
    }


def test_render_report_contains_decisions():
    r = results(hidden_share=0.1)
    assert "Primary target: has_value_addition" in render_report(r, decide(r))
    r = results(hidden_share=0.5, sample_precision=0.5)
    assert "Primary target: has_time_extension" in render_report(r, decide(r))


def test_text_recovered_label_when_precise():
    d = decide(results(hidden_share=0.5, sample_precision=0.9))
    assert d["primary_target"] == "has_value_addition_text_recovered"


def test_missing_precision_blocks_decision():
    d = decide(results(hidden_share=0.5, sample_precision=None))
    assert d["primary_target"] == "pending_manual_check"


def test_amended_value_is_excluded():
    d = decide(results(with_add=1.3, without_add=1.0))
    assert d["valor_del_contrato"] == "excluded"
    assert d["features"]["valor_del_contrato"][0] == "excluded"
    assert d["features"]["valor_total_adjudicacion"][0] == "allowed"


def test_moved_end_date_excluded_and_bidders_allowed():
    d = decide(results(moved=0.9, coverage=0.9))
    assert d["features"]["fecha_de_fin_del_contrato"][0] == "excluded"
    assert d["features"]["proveedores_unicos_con"][0] == "allowed"
    assert d["closed_states"] == ["terminado"]
    assert decide(results(coverage=0.5))["features"]["proveedores_unicos_con"][0] == "excluded"


def test_whitelist_lists_every_column():
    from procurement_risk import config
    d = decide(results())
    assert set(config.CONTRACT_COLUMNS) | set(config.PROCESS_COLUMNS) <= set(d["features"])
    assert d["features"]["dias_adicionados"][0] == "excluded"


def test_audit_cli_writes_report(tmp_path):
    import pyarrow.parquet as pq

    from procurement_risk import __main__ as cli
    from procurement_risk import config
    from procurement_risk.parsing import to_arrow

    for name, cols, rows in (
        ("contracts", (*config.CONTRACT_COLUMNS, "supplier_is_natural_person"),
         [{"id_contrato": "1", "fecha_de_firma": "2021-01-01T00:00:00"}]),
        ("amendments", config.AMENDMENT_COLUMNS, []),
        ("processes", config.PROCESS_COLUMNS, []),
    ):
        (tmp_path / name).mkdir()
        pq.write_table(to_arrow(rows, cols), tmp_path / name / "part-00000.parquet")
    out = tmp_path / "audit.md"
    cli.main(["audit", "--raw", str(tmp_path), "--out", str(out), "--as-of", "2026-11-14"])
    assert "Primary target: has_value_addition" in out.read_text(encoding="utf-8")


def test_report_never_publishes_amendment_text():
    r = results()
    r["hidden"]["sample"] = ["ADICION EN VALOR CONTRATISTA JUAN PEREZ C.C. 1.234.567"]
    text = render_report(r, decide(r))
    assert "JUAN PEREZ" not in text
    assert "1.234.567" not in text


def test_audit_cli_writes_sample_outside_report(tmp_path):
    import pyarrow.parquet as pq

    from procurement_risk import __main__ as cli
    from procurement_risk import config
    from procurement_risk.parsing import to_arrow

    for name, cols, rows in (
        ("contracts", (*config.CONTRACT_COLUMNS, "supplier_is_natural_person"),
         [{"id_contrato": "1", "fecha_de_firma": "2021-01-01T00:00:00"}]),
        ("amendments", config.AMENDMENT_COLUMNS,
         [{"identificador": "h", "id_contrato": "1", "tipo": "Modificacion General",
           "descripcion": "ADICION EN VALOR A FAVOR DE JUAN PEREZ"}]),
        ("processes", config.PROCESS_COLUMNS, []),
    ):
        (tmp_path / name).mkdir()
        pq.write_table(to_arrow(rows, cols), tmp_path / name / "part-00000.parquet")
    out, sample = tmp_path / "audit.md", tmp_path / "private" / "sample.txt"
    cli.main(["audit", "--raw", str(tmp_path), "--out", str(out), "--as-of", "2026-11-14",
              "--sample-out", str(sample)])
    assert "JUAN PEREZ" not in out.read_text(encoding="utf-8")
    assert "JUAN PEREZ" in sample.read_text(encoding="utf-8")
