import base64
import io
import json
from pathlib import Path

from groq import Groq
from PIL import Image, ImageEnhance

from vim.extraction import config
from vim.extraction.parser.core import parse_single_file
from vim.extraction.schema import empty_record, SCHEMA_DESCRIPTION_FOR_PROMPT, CONFIDENCE_KEYS
from vim.extraction.validator import validate_record

_groq_client = None


def _get_groq_client():
    global _groq_client
    config.validate()
    if _groq_client is None:
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client

_EXTRACTION_PROMPT = f"""
This is the content of a business invoice or bill. It may be presented to
you as an image, or as text/markdown that was already extracted from a
PDF, DOCX, PPTX, or HTML file.

Extract its data into EXACTLY this JSON schema — same keys every time,
regardless of vendor or source format:

{SCHEMA_DESCRIPTION_FOR_PROMPT}

Rules:
- Use the exact key names above. Do not rename, add, or remove header keys.
- If a header field is not present on the document, use null (not "unknown",
  not an empty string).
- Normalize all dates to "YYYY-MM-DD".
- Normalize all money values to plain numbers (no "$", no commas, no
  currency symbols). A credit/payment should be negative.
- "line_items" is for the itemized charge/usage table on the invoice.
- "extra_fields" is a flat object for everything else printed on the document.
- Do not invent or infer anything not visible on the document.
- For EVERY extracted field, include a confidence score from 0 to 100 in
  "field_confidence" (header fields), "line_items_confidence" (parallel to
  line_items, same length and keys), and "extra_fields_confidence" (parallel
  to extra_fields). Use null confidence when the field value is null.
  High confidence (90-100) = clearly visible and unambiguous; lower scores =
  partial, inferred, or unclear text.
- Return ONLY the JSON object. No markdown fences, no explanation.
""".strip()


def _vendor_match_prompt(registered_vendors: list[str]) -> str:
    vendor_list = json.dumps(registered_vendors, ensure_ascii=False)
    return f"""
You are reading a business invoice or bill.

Identify which company ISSUED this invoice (letterhead, logo, remit-to, or
"Invoice from" block). That is the vendor. Do NOT pick the bill-to customer,
ship-to address, or company being billed unless it is also the issuer.

Choose at most ONE name from this registered vendor list:
{vendor_list}

Return ONLY JSON:
{{"vendor_name": "exact name copied from the list above, or null if none match"}}

Rules:
- vendor_name must be copied exactly from the list, or null.
- Do not invent names outside the list.
""".strip()


def _load_raw_text(file_path: str) -> tuple[str | None, str | None]:
    """Parse document text via LlamaParse. Returns (raw_text, error)."""
    path = Path(file_path)
    try:
        docs = parse_single_file(str(path), verbose=False)
        raw_text = "\n\n".join(d.text or "" for d in docs)
        if not raw_text.strip():
            return None, "no text extracted from source document"
        return raw_text, None
    except Exception as e:
        return None, str(e)


def detect_vendor_name(
    file_path: str,
    registered_vendors: list[str] | None = None,
) -> tuple[str | None, str | None, str | None]:
    """
    Identify a registered issuing vendor from a document before full extraction.
    Returns (vendor_name, raw_text, error).
    """
    from vim.extraction.vendors import registered_vendor_names

    if registered_vendors is None:
        registered_vendors = registered_vendor_names()

    if not registered_vendors:
        return None, None, "no registered vendors in system — add vendors under Admin → Vendors"

    raw_text, error = _load_raw_text(file_path)
    if error:
        return None, None, error

    path = Path(file_path)
    try:
        response = _get_groq_client().chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f"{_vendor_match_prompt(registered_vendors)}\n\n"
                    f"--- DOCUMENT TEXT ({path.name}) ---\n{raw_text}"
                ),
            }],
            temperature=0.0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        payload = json.loads(_strip_fences(response.choices[0].message.content))
        vendor_name = payload.get("vendor_name")
        if vendor_name in (None, "", "null"):
            return None, raw_text, (
                "no registered vendor found on this invoice — "
                "register the issuing vendor under Admin → Vendors, then re-upload"
            )
        return str(vendor_name).strip(), raw_text, None
    except Exception as e:
        return None, raw_text, str(e)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


def _finalize(raw_content: str) -> dict:
    raw = _strip_fences(raw_content)
    result = json.loads(raw)
    base = empty_record()
    for key in CONFIDENCE_KEYS:
        if key in result:
            base[key] = result.pop(key)
    base.update(result)
    return base


def parse_image_direct(file_path: str) -> dict:
    try:
        img = Image.open(file_path)

        if hasattr(img, "n_frames") and img.n_frames > 1:
            img.seek(0)

        img = img.convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(1.8)

        w, h = img.size
        if w > 1600 or h > 1600:
            scale = min(1600 / w, 1600 / h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        response = _get_groq_client().chat.completions.create(
            model=config.GROQ_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": _EXTRACTION_PROMPT,
                    }
                ]
            }],
            temperature=0.1,
            max_tokens=4000,
        )

        return _finalize(response.choices[0].message.content)

    except Exception as e:
        record = empty_record()
        record["_extraction_error"] = str(e)
        return record


def parse_text_direct(raw_text: str, source_label: str = "") -> dict:
    try:
        if not raw_text.strip():
            raise ValueError("no text extracted from source document")

        response = _get_groq_client().chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f"{_EXTRACTION_PROMPT}\n\n"
                    f"--- DOCUMENT TEXT ({source_label}) ---\n{raw_text}"
                ),
            }],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        return _finalize(response.choices[0].message.content)

    except Exception as e:
        record = empty_record()
        record["_extraction_error"] = str(e)
        return record


def _extract_via_text(file_path: str, raw_text: str | None = None) -> dict:
    """LlamaParse → Groq text model. Works for PDFs, images, and other docs."""
    path = Path(file_path)
    if raw_text is None:
        raw_text, error = _load_raw_text(str(path))
        if error:
            record = empty_record()
            record["_extraction_error"] = error
            return record

    record = parse_text_direct(raw_text, source_label=path.name)
    record["raw_text"] = raw_text
    return record


def extract_from_file(file_path: str, raw_text: str | None = None) -> dict:
    """Run the full extraction + validation pipeline on a single file."""
    path = Path(file_path)
    ext = path.suffix.lower()

    # Try Groq Vision for images only when a vision model is configured and available.
    # Most Groq accounts only have text models — fall back to LlamaParse + text.
    if raw_text is None and ext in config.IMAGE_EXTENSIONS and config.GROQ_VISION_MODEL:
        record = parse_image_direct(str(path))
        if not record.get("_extraction_error") and record.get("total_due") is not None:
            pass  # vision succeeded
        else:
            record = _extract_via_text(str(path))
    else:
        record = _extract_via_text(str(path), raw_text=raw_text)

    record, issues = validate_record(record)
    record["file_name"] = path.name
    record["file_path"] = str(path)
    if issues:
        record["_validation_issues"] = issues

    return record
