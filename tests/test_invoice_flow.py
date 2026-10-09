wimport main


def test_free_tier_gate_after_three_invoices():
    state = {"free_invoices_used": 3, "is_pro": False}
    assert not main.can_process_invoice(state)

    state["is_pro"] = True
    assert main.can_process_invoice(state)


def test_export_uses_first_line_item_only():
    invoice_data = {
        "line_items": [
            {"description": "First line", "quantity": 1, "unit_price": 25.0, "line_total": 25.0},
            {"description": "Second line", "quantity": 2, "unit_price": 30.0, "line_total": 60.0},
        ]
    }

    export_df = main.build_export_dataframe(invoice_data)

    assert list(export_df["description"]) == ["First line"]
    assert len(export_df) == 1
