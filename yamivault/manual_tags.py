"""Manual image tags and explicit AND search, independent of Analytics tags."""
import re
import unicodedata


def normalize_tag(name):
    name = ' '.join(unicodedata.normalize('NFKC', name).strip().lstrip('#').split())
    if not name or len(name) > 80 or '"' in name or '#' in name:
        raise ValueError('タグは1〜80文字で入力してください。# と " は名前に使えません。')
    return name


def filter_manual_tags(assets, query, selected, definitions, mapping, aliases=None):
    required = set(selected)
    aliases=aliases or {}
    keys = {name.casefold(): ident for ident,name in definitions.items()}
    for ident,terms in aliases.items():
        for term in terms:keys.setdefault(term.casefold(),ident)
    search_names={ident:' '.join([name]+list(aliases.get(ident,[]))) for ident,name in definitions.items()}
    missing = False
    pattern = r'#(?:"([^"]+)"|(\S+))'
    for match in re.finditer(pattern, query):
        name = unicodedata.normalize('NFKC', match.group(1) or match.group(2)).casefold()
        ident = keys.get(name)
        if ident:
            required.add(ident)
        else:
            missing = True
    text = re.sub(pattern, '', query).strip().casefold()
    if missing:
        return []
    return [a for a in assets if required <= mapping.get(a.annotation_key,set())
            and (not text or text in (' '.join([a.post_id,a.filename] + [search_names[i] for i in mapping.get(a.annotation_key,set()) if i in search_names])).casefold())]
