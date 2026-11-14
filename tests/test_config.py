from procurement_risk import config

FORBIDDEN = {
    "nombre_representante_legal", "identificaci_n_representante_legal",
    "g_nero_representante_legal", "nombre_del_banco", "tipo_de_cuenta",
    "n_mero_de_cuenta", "nombre_supervisor", "n_mero_de_documento_supervisor",
    "nombre_ordenador_del_gasto", "n_mero_de_documento_ordenador_del_gasto",
    "nombre_ordenador_de_pago", "n_mero_de_documento_ordenador_de_pago",
    "direcci_n_de_ejecuci_n_del_contrato", "nombre_del_adjudicador",
    "nombre_del_proveedor", "nit_del_proveedor_adjudicado", "codigoproveedor",
}


def test_allowlists_exclude_personal_columns():
    for cols in (config.CONTRACT_COLUMNS, config.PROCESS_COLUMNS,
                 config.AMENDMENT_COLUMNS, config.SNAPSHOT_COLUMNS):
        assert FORBIDDEN.isdisjoint(cols)


def test_snapshot_columns_are_subset_of_contract_columns():
    assert set(config.SNAPSHOT_COLUMNS) <= set(config.CONTRACT_COLUMNS)
