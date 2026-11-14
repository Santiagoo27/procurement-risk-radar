"""Colombia (SECOP II) adapter: raw tables -> OCDS-inspired canonical tables.

Expects a connection from `audit.metrics.open_audit_db` (views `contracts`, `amendments`,
`processes`, temp table `process_one`, UDF `looks_like_value_addition`).

`current_end_at` and `added_days` are post-signing values: they exist only to build labels
and the closure rule, never as features.
"""

from __future__ import annotations

import duckdb

from procurement_risk.audit.metrics import HIDDEN_TYPES, VALUE_ADDITION

MAX_DURATION_DAYS = 3650  # longer planned durations are data-entry errors -> null

_UNIT_DAYS = """
    CASE
        WHEN u LIKE 'dia%' THEN 1.0
        WHEN u LIKE 'semana%' THEN 7.0
        WHEN u LIKE 'mes%' THEN 30.0
        WHEN u LIKE 'ano%' THEN 365.0
        WHEN u LIKE 'hora%' THEN 1.0 / 24
    END
"""


def build_canonical(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE canonical_contracts AS
        WITH p AS (
            SELECT *, strip_accents(lower(trim(unidad_de_duracion))) AS u FROM process_one
        )
        SELECT
            c.id_contrato AS contract_id,
            c.proceso_de_compra AS tender_id,
            c.codigo_entidad AS buyer_id,
            c.departamento AS buyer_department,
            c.ciudad AS buyer_city,
            c.orden AS buyer_order,
            c.sector AS buyer_sector,
            c.rama AS buyer_branch,
            c.entidad_centralizada AS buyer_centralized,
            c.modalidad_de_contratacion AS procurement_method,
            c.tipo_de_contrato AS contract_type,
            c.codigo_de_categoria_principal AS category_code,
            nullif(regexp_extract(c.codigo_de_categoria_principal, '(\\d{{2}})', 1), '')
                AS category_segment,
            c.origen_de_los_recursos AS funding_source,
            c.fecha_de_firma AS signed_at,
            c.fecha_de_inicio_del_contrato AS planned_start_at,
            c.fecha_de_fin_del_contrato AS current_end_at,
            coalesce(p.valor_total_adjudicacion, p.precio_base) AS award_value,
            p.precio_base AS tender_budget,
            CASE WHEN p.duracion > 0 AND p.duracion * ({_UNIT_DAYS}) <= {MAX_DURATION_DAYS}
                 THEN p.duracion * ({_UNIT_DAYS}) END AS planned_duration_days,
            p.fecha_de_publicacion_del AS tender_published_at,
            p.proveedores_unicos_con AS n_bidders,
            p.respuestas_al_procedimiento AS n_responses,
            p.proveedores_invitados AS n_invited,
            p.numero_de_lotes AS n_lots,
            c.codigo_proveedor AS supplier_key,
            c.supplier_is_natural_person,
            c.es_pyme AS supplier_is_sme,
            c.es_grupo AS supplier_is_group,
            c.habilita_pago_adelantado AS advance_payment_enabled,
            c.el_contrato_puede_ser_prorrogado AS extendable_clause,
            c.dias_adicionados AS added_days,
            p.id_del_portafolio IS NOT NULL AS process_found
        FROM contracts c
        LEFT JOIN p ON c.proceso_de_compra = p.id_del_portafolio
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE canonical_amendments AS
        SELECT
            identificador AS amendment_id,
            id_contrato AS contract_id,
            CASE
                WHEN tipo = '{VALUE_ADDITION}' THEN 'value_addition'
                WHEN tipo IN {HIDDEN_TYPES}
                     AND (descripcion ILIKE '%adic%' OR descripcion ILIKE '%mayor valor%')
                     AND looks_like_value_addition(descripcion) THEN 'value_addition_text'
                WHEN tipo = 'Extension' THEN 'extension'
                ELSE 'other'
            END AS kind,
            fecharegistro AS recorded_at
        FROM amendments
        WHERE id_contrato IN (SELECT id_contrato FROM contracts)
    """)
