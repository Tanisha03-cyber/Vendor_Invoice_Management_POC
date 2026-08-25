from .stages import (
    InvoiceCompletenessCheck,
    OcrConfidenceValidation,
    VendorValidation,
    POMatching,
    TaxValidation,
    DuplicateDetection
)


class ValidationEngine:

    def __init__(self):

        self.stages = [
            InvoiceCompletenessCheck(),
            OcrConfidenceValidation(),
            VendorValidation(),
            POMatching(),
            TaxValidation(),
            DuplicateDetection()
        ]

    def validate_invoice(self, invoice, context=None):

        context = context or {}

        results = []

        for stage in self.stages:

            result = stage.validate(
                invoice,
                context
            )

            results.append(result)

        passed = sum(
            1 for result in results
            if result["status"] == "PASSED"
        )

        failed = sum(
            1 for result in results
            if result["status"] == "FAILED"
        )

        overall_status = (
            "PASSED"
            if failed == 0
            else "FAILED"
        )

        return {
            "invoice_number": invoice.get("invoice_number"),
            "overall_status": overall_status,
            "total_stages": len(results),
            "stages_passed": passed,
            "stages_failed": failed,
            "validation_results": results
        }

    def validate_invoices(self, invoices, context=None):

        reports = []

        for invoice in invoices:

            report = self.validate_invoice(
                invoice,
                context
            )

            reports.append(report)

        return reports