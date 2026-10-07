"""Small offline UI catalog. User content and database keys are never translated."""
from functools import lru_cache
_language='ja'

def language():return _language

def set_language_code(value):
    global _language
    _language=value if value in ('ja','en') else 'ja'
    tr.cache_clear()

@lru_cache(maxsize=1)
def _english():
    from .i18n_en import EN
    return EN

@lru_cache(maxsize=1024)
def tr(text):
    if _language!='en' or not isinstance(text,str):return text
    return _english().get(text,text)

def trf(template,*values):
    return tr(template).format(*values)

def performance_name(value):
    """Only call this for software-generated performance labels, not manual tags."""
    return tr(value)

def unknown_date(value):
    return tr(value) if value in ('不明','日付不明','期間不明','未記録','未収録') else value

def error_text(error):
    if language()=='ja':return str(error)
    from .diagnostics import friendly_error
    return friendly_error(error)

def preferred_language(directory):
    """Read one preference without creating a DB or performing migrations."""
    import json,sqlite3
    from pathlib import Path
    path=Path(directory).resolve()/'yami_vault.sqlite3'
    if not path.is_file():return 'ja'
    try:
        connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:row=connection.execute("SELECT value FROM settings WHERE key='ui_language'").fetchone()
        finally:connection.close()
        value=json.loads(row[0]) if row else 'ja'
        return value if value in ('ja','en') else 'ja'
    except (sqlite3.Error,ValueError,TypeError):return 'ja'

def software_message(value):
    """For app/worker messages only, never pass file names or user tags here."""
    result=tr(value)
    if language()=='en' and result==value and isinstance(value,str):
        import re
        if re.search('[ぁ-んァ-ン一-龯]',value):return error_text(ValueError(value))
    return result

def warning_reason(value):
    if language()!='en':return value
    result=tr(value)
    if result!=value:return result
    return software_message(value)
