from vim_database.database import db
from vim_database.models import ValidationResult


def save_validation_results(invoice, validation_result):
    """
    Store validation results for one invoice in validation_result table.
    """

    invoice_id = invoice.InvoiceID
    invoice_number = validation_result.get("invoice_number")

    results = validation_result.get(
        "validation_results",
        []
    )

    ValidationResult.query.filter_by(
        InvoiceID=invoice_id
    ).delete()

    for result in results:

        # --------------------------------------------------
        # Stage Status
        # --------------------------------------------------
        #
        # For now, this is derived from the existing
        # validation status.
        #
        # Later we can update this directly from each
        # stage when the stage starts/completes/fails.
        # --------------------------------------------------

        validation_status = result.get("status")

        if validation_status == "FAILED":
            stage_status = "failed"

        else:
            stage_status = "completed"

        validation_record = ValidationResult(
            InvoiceID=invoice_id,
            InvoiceNumber=invoice_number,
            ValidationType=result.get("stage"),

            # Existing logic - UNCHANGED
            ValidationStatus=validation_status,
            ValidationMessage=result.get("message"),
            ValidationDetails=result.get("details", {}),

            # NEW COLUMN ONLY
            StageStatus=stage_status
        )

        db.session.add(validation_record)

    db.session.commit()