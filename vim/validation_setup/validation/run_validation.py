import json
from pathlib import Path

from vim.validation_setup.validation.validation_engine import ValidationEngine
from vim_database.models import Invoice

from vim.validation_setup.validation.validation_result import (
    save_validation_results
)


def run_validation():

    # --------------------------------------------------
    # Path to enriched.json
    # --------------------------------------------------

    enriched_file = Path(
        r"C:\Users\SPAR-PUNE-042\Downloads\VIM\output\enriched.json"
    )

    # --------------------------------------------------
    # Read enriched.json
    # --------------------------------------------------

    with open(enriched_file, "r", encoding="utf-8") as file:
        invoices = json.load(file)

    # --------------------------------------------------
    # Create validation engine
    # --------------------------------------------------

    engine = ValidationEngine()

    # --------------------------------------------------
    # Process every invoice
    # --------------------------------------------------

    for invoice_data in invoices:

        # Run validation
        result = engine.validate_invoice(
            invoice_data,
            context={}
        )

        # --------------------------------------------------
        # Get business invoice number
        # --------------------------------------------------

        invoice_number = result.get("invoice_number")

        # --------------------------------------------------
        # Find actual invoice record in database
        # --------------------------------------------------

        invoice = Invoice.query.filter_by(
            InvoiceNumber=invoice_number
        ).first()

        if not invoice:
            print(
                f"WARNING: Invoice not found in database: "
                f"{invoice_number}"
            )
            continue

        # --------------------------------------------------
        # Store validation results in DB
        # --------------------------------------------------

        save_validation_results(
            invoice,
            result
        )

    return True