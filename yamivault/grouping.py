"""Reversible display grouping, never deletion or catalog mutation.

Filter attachments before grouping so older posts and filenames remain searchable.
Only identical file hashes with the same media kind share a tile. Near matches,
different encodings, and different resolutions remain separate.
"""
from collections import defaultdict


def content_key(asset):
    return asset.annotation_key, asset.kind


def group_index(assets):
    groups=defaultdict(list)
    for asset in assets:
        groups[content_key(asset)].append(asset)
    return dict(groups)


def representatives(assets):
    """Preserve catalog sort order: use the first matching attachment per group."""
    return [members[0] for members in group_index(assets).values()]


def representative_for(asset, visible, grouped):
    if not asset:
        return None
    if grouped:
        key=content_key(asset)
        return next((a for a in visible if content_key(a)==key),None)
    return next((a for a in visible if a.identity==asset.identity),None)
