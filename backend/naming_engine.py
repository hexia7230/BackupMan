"""
naming_engine.py - Resolves naming templates for backup output files.

Supported placeholders:
  {name}        - Custom label from the naming template
  {date}        - Current date YYYY_MM_DD
  {datetime}    - Current datetime YYYY_MM_DD_HHmmss
  {year}        - 4-digit year
  {month}       - 2-digit month
  {day}         - 2-digit day
  {time}        - HHmmss
  {id}          - Random alphanumeric ID (7 chars by default)
  {seq}         - Sequential counter (passed in)
  {source_name} - Basename of the source path
  {ext}         - File extension (without dot)
"""
import random
import string
from datetime import datetime


def _random_id(length: int = 7) -> str:
    return ''.join(random.choices(string.digits, k=length))


def resolve(template: str, ext: str, context: dict) -> str:
    """
    Resolve a naming template string.

    :param template: Template string, e.g. '{name}_{date}_{id}.{ext}'
                     If empty/whitespace → use original source filename unchanged.
    :param ext:      File extension without leading dot, e.g. 'bak'.
                     If empty → no extension is added even if {ext} is in template.
    :param context:  dict with optional keys: name, seq, source_name
    :return: Resolved filename string
    """
    # ── Empty template → use original source name, no renaming ────────────────
    if not template or not template.strip():
        raw = context.get('source_name', 'source')
        # Do NOT sanitize — preserve the exact original name (including extension)
        return raw or 'source'

    # ── Normalize ext: user may now enter '.bak' or 'bak' ────────────────────
    ext = ext.lstrip('.') if ext else ''

    now = datetime.now()
    has_ext_placeholder = '{ext}' in template

    replacements = {
        'name':        context.get('name', 'backup'),
        'date':        now.strftime('%Y_%m_%d'),
        'datetime':    now.strftime('%Y_%m_%d_%H%M%S'),
        'year':        now.strftime('%Y'),
        'month':       now.strftime('%m'),
        'day':         now.strftime('%d'),
        'time':        now.strftime('%H%M%S'),
        'id':          _random_id(7),
        'seq':         str(context.get('seq', 1)).zfill(4),
        'source_name': context.get('source_name', 'source'),
        'ext':         ext,
    }

    result = template
    for key, value in replacements.items():
        result = result.replace('{' + key + '}', value)

    # ── If {ext} was used but ext is empty, strip the resulting trailing dot ──
    if has_ext_placeholder:
        if ext:
            # Extension was specified — ensure it's appended if not already
            if not result.endswith('.' + ext):
                result = result + '.' + ext
        else:
            # No extension specified — remove any trailing dot left over
            result = result.rstrip('.')
    # If no {ext} placeholder → do not touch the extension at all

    # ── Sanitize filename (remove chars unsafe for Windows/Linux paths) ────────
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.()[] ')
    result = ''.join(c if c in safe_chars else '_' for c in result)
    # Strip leading/trailing dots and spaces that could cause issues
    result = result.strip('. ')
    return result or 'backup'

