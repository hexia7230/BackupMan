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
    :param ext:      File extension without leading dot, e.g. 'bak'
    :param context:  dict with optional keys: name, seq, source_name
    :return: Resolved filename string
    """
    now = datetime.now()

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

    # Ensure the extension is appended if not already
    if not result.endswith('.' + ext):
        result = result + '.' + ext

    # Sanitize filename (remove unsafe characters)
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.()[] ')
    result = ''.join(c if c in safe_chars else '_' for c in result)
    return result
