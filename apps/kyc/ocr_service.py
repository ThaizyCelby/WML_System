"""OCR + AI-assisted extraction of SA ID details from uploaded documents.

Strategy:
1. Convert PDF pages to images (for scanned PDFs) using pypdfium2 (pure Python).
2. Send the image(s) to Gemini with a structured prompt.
3. Fall back to Tesseract OCR if the AI path is unavailable.
"""
import base64
import io
import logging
import re
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('apps.kyc')


# ──────────────────────────────────────────────────────────────────────
# PDF → images helper (uses pypdfium2, works cross-platform)
# ──────────────────────────────────────────────────────────────────────
def _pdf_to_images(pdf_bytes: bytes, max_pages: int = 2, dpi: int = 200) -> list[bytes]:
    """Return a list of PNG image bytes, one per page."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 not installed; cannot convert PDF to images.")
        return []

    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    for i in range(min(len(pdf), max_pages)):
        page = pdf[i]
        bitmap = page.render(scale=dpi / 72)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format='PNG', optimize=True)
        images.append(buf.getvalue())
    pdf.close()
    return images


# ──────────────────────────────────────────────────────────────────────
# SA ID parsing (checksum-validated)
# ──────────────────────────────────────────────────────────────────────
def _validate_sa_id(id_number: str) -> bool:
    """Validate a South African 13-digit ID using the Luhn algorithm."""
    if not id_number or not re.fullmatch(r'\d{13}', id_number):
        return False
    digits = [int(d) for d in id_number]
    # Luhn: double every second digit from the right
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _parse_dob_from_sa_id(id_number: str) -> Optional[str]:
    """Extract YYMMDD → a date. Assumes 19XX or 20XX based on plausibility."""
    if not re.fullmatch(r'\d{13}', id_number):
        return None
    yy = int(id_number[0:2])
    mm = int(id_number[2:4])
    dd = int(id_number[4:6])
    # Guess century: current year 2026 → anyone with YY > 26 is 19xx
    current_yy = timezone.now().year % 100
    year = 1900 + yy if yy > current_yy else 2000 + yy
    try:
        from datetime import date
        return date(year, mm, dd).isoformat()
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────
# AI-based extraction using Gemini vision
# ──────────────────────────────────────────────────────────────────────
GEMINI_VISION_PROMPT = """You are a KYC document reader for a South African lender.
Analyse the attached image of an identity document (ID card, ID book, or passport).

Return ONLY a JSON object with these fields (use null if not visible):
{
  "document_type": "sa_id_card" | "sa_id_book" | "passport" | "unknown",
  "id_number": "13-digit number or passport number",
  "first_names": "...",
  "surname": "...",
  "date_of_birth": "YYYY-MM-DD",
  "gender": "M" | "F",
  "nationality": "...",
  "issue_date": "YYYY-MM-DD",
  "expiry_date": "YYYY-MM-DD",
  "confidence": 0.0 to 1.0
}

Rules:
- Do NOT invent values. If a field is not clearly visible, use null.
- The SA ID number is 13 digits. If you see a longer number that contains 13 contiguous digits, extract the 13-digit segment.
- Return raw JSON, no markdown fences, no explanation.
"""


def _extract_with_gemini_vision(image_bytes: bytes) -> Optional[dict]:
    """Send the image to Gemini and parse its JSON reply."""
    provider_cfg = settings.AI_PROVIDERS.get('gemini') or {}
    if not provider_cfg.get('enabled') or not provider_cfg.get('api_key'):
        logger.info("Gemini not configured; skipping AI vision extraction.")
        return None

    import requests
    api_key = provider_cfg['api_key']
    model = provider_cfg.get('model', 'gemini-2.5-flash')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [{
            "parts": [
                {"text": GEMINI_VISION_PROMPT},
                {"inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(image_bytes).decode('ascii'),
                }},
            ]
        }],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 800},
    }
    try:
        resp = requests.post(
            url, params={"key": api_key}, json=payload, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        # Strip markdown fences if present
        text = re.sub(r'^```(?:json)?|```$', '', text, flags=re.MULTILINE).strip()
        import json
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        logger.warning("Gemini vision extraction failed: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────────
# Tesseract fallback
# ──────────────────────────────────────────────────────────────────────
def _extract_with_tesseract(image_bytes: bytes) -> Optional[dict]:
    """Fallback OCR via pytesseract (if installed)."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.info("pytesseract or Pillow not installed; skipping OCR fallback.")
        return None

    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang='eng')
        # Try to find a 13-digit number
        id_matches = re.findall(r'\b\d{13}\b', text)
        result = {'confidence': 0.5, 'source': 'tesseract'}
        for cand in id_matches:
            if _validate_sa_id(cand):
                result['id_number'] = cand
                result['document_type'] = 'sa_id_card'
                break
        if 'id_number' not in result and id_matches:
            result['id_number'] = id_matches[0]
            result['document_type'] = 'sa_id_card'
        return result
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def extract_identity_from_bytes(file_bytes: bytes, mime_type: str) -> dict:
    """
    Main entry point. Returns a dict with extraction results.

    Keys:
        id_number, first_names, surname, date_of_birth, gender,
        nationality, issue_date, expiry_date, document_type,
        confidence, source, validated (bool)
    """
    result = {
        'id_number': None,
        'first_names': None,
        'surname': None,
        'date_of_birth': None,
        'gender': None,
        'nationality': None,
        'issue_date': None,
        'expiry_date': None,
        'document_type': 'unknown',
        'confidence': 0.0,
        'source': 'none',
        'validated': False,
    }

    # Get an image to send to vision models
    images = []
    if mime_type == 'application/pdf':
        images = _pdf_to_images(file_bytes)
    elif mime_type in ('image/jpeg', 'image/png'):
        images = [file_bytes]
    else:
        return result

    if not images:
        return result

    # Try AI vision first
    extracted = _extract_with_gemini_vision(images[0])

    # Fallback to Tesseract
    if not extracted or not extracted.get('id_number'):
        extracted = _extract_with_tesseract(images[0])

    if not extracted:
        return result

    # Normalize / validate
    id_number = extracted.get('id_number')
    if id_number:
        id_number = re.sub(r'[^\dA-Za-z]', '', str(id_number))

    if id_number and _validate_sa_id(id_number):
        result['validated'] = True
        if not extracted.get('date_of_birth'):
            dob = _parse_dob_from_sa_id(id_number)
            if dob:
                result['date_of_birth'] = dob

    result.update({
        'id_number': id_number,
        'first_names': extracted.get('first_names'),
        'surname': extracted.get('surname'),
        'date_of_birth': extracted.get('date_of_birth') or result['date_of_birth'],
        'gender': extracted.get('gender'),
        'nationality': extracted.get('nationality'),
        'issue_date': extracted.get('issue_date'),
        'expiry_date': extracted.get('expiry_date'),
        'document_type': extracted.get('document_type', 'unknown'),
        'confidence': float(extracted.get('confidence') or 0.0),
        'source': 'gemini' if extracted.get('document_type') else 'tesseract',
    })
    return result


def extract_identity_from_document(document) -> dict:
    """
    Extract identity info from a Document model instance.
    Downloads the file from storage and processes it.
    """
    from django.core.files.storage import default_storage

    if not document or not document.storage_key:
        return {}

    try:
        with default_storage.open(document.storage_key, 'rb') as f:
            file_bytes = f.read()
    except FileNotFoundError:
        logger.error("Document file not found: %s", document.storage_key)
        return {}

    return extract_identity_from_bytes(file_bytes, document.mime_type)