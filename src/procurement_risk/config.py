"""Dataset identifiers, column allowlists and paths.

Columns are kept by allowlist: anything not listed here is never written to disk.
"""

from pathlib import Path

SOCRATA_DOMAIN = "www.datos.gov.co"

CONTRACTS_ID = "jbjy-vk9h"
AMENDMENTS_ID = "cb9c-h8sn"
PROCESSES_ID = "p6dx-8zbt"

CONTRACT_COLUMNS: tuple[str, ...] = (
    "id_contrato",
    "proceso_de_compra",
    "referencia_del_contrato",
    "nombre_entidad",
    "nit_entidad",
    "codigo_entidad",
    "departamento",
    "ciudad",
    "orden",
    "sector",
    "rama",
    "entidad_centralizada",
    "estado_contrato",
    "codigo_de_categoria_principal",
    "descripcion_del_proceso",
    "objeto_del_contrato",
    "tipo_de_contrato",
    "modalidad_de_contratacion",
    "justificacion_modalidad_de",
    "fecha_de_firma",
    "fecha_de_inicio_del_contrato",
    "fecha_de_fin_del_contrato",
    "duraci_n_del_contrato",
    "el_contrato_puede_ser_prorrogado",
    "tipodocproveedor",
    "documento_proveedor",
    "proveedor_adjudicado",
    "codigo_proveedor",
    "es_grupo",
    "es_pyme",
    "habilita_pago_adelantado",
    "origen_de_los_recursos",
    "destino_gasto",
    "valor_del_contrato",
    "valor_de_pago_adelantado",
    "valor_facturado",
    "valor_pagado",
    "dias_adicionados",
    "espostconflicto",
    "liquidaci_n",
    "ultima_actualizacion",
    "urlproceso",
)

AMENDMENT_COLUMNS: tuple[str, ...] = (
    "identificador",
    "id_contrato",
    "tipo",
    "descripcion",
    "fecharegistro",
)

PROCESS_COLUMNS: tuple[str, ...] = (
    "id_del_proceso",
    "id_del_portafolio",
    "referencia_del_proceso",
    "nit_entidad",
    "modalidad_de_contratacion",
    "fecha_de_publicacion_del",
    "precio_base",
    "duracion",
    "unidad_de_duracion",
    "proveedores_invitados",
    "proveedores_que_manifestaron",
    "respuestas_al_procedimiento",
    "proveedores_unicos_con",
    "numero_de_lotes",
    "estado_del_procedimiento",
    "adjudicado",
    "valor_total_adjudicacion",
    "codigo_principal_de_categoria",
    "tipo_de_contrato",
    "subtipo_de_contrato",
)

SNAPSHOT_COLUMNS: tuple[str, ...] = (
    "id_contrato",
    "valor_del_contrato",
    "fecha_de_fin_del_contrato",
    "dias_adicionados",
    "estado_contrato",
    "ultima_actualizacion",
)

DATA_DIR = Path("data")

DISCLAIMER = (
    "Scores are statistical estimates for analysis, not allegations of wrongdoing. "
    "They estimate the chance that a contract will be amended, nothing more."
)
