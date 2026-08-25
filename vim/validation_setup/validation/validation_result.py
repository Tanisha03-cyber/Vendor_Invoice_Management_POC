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

        validation_record = ValidationResult(
            InvoiceID=invoice_id,
            InvoiceNumber=invoice_number,
            ValidationType=result.get("stage"),
            ValidationStatus=result.get("status"),
            ValidationMessage=result.get("message"),
            ValidationDetails=result.get("details", {})
        )

        db.session.add(validation_record)

    db.session.commit()