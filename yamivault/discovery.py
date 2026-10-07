"""Local discovery using explicit metadata, manual flags and view history only."""
from .order import order_assets
import hashlib


def has_x_post_info(asset):
    return bool(asset.post_id) and not asset.asset_key.startswith('warning:')


def discovery_filter(assets,performance,views,favorite_hashes,*,exclude_favorites=False,
                     recent_cutoff=None,high_only=False,no1_only=False,high_unfav=False,post_info='',no_high_unfav=False,high_hashes=None):
    if no_high_unfav and high_hashes is None:
        high_hashes={a.annotation_key for a in assets if performance.get(a.performance_key,{}).get('high_count',0) or performance.get(a.performance_key,{}).get('top1_count',0)}
    def accept(a):
        record=performance.get(a.performance_key,{})
        if (exclude_favorites or high_unfav or no_high_unfav) and a.annotation_key in favorite_hashes:return False
        if no_high_unfav and (a.annotation_key in high_hashes or record.get('high_count',0) or record.get('top1_count',0)):return False
        if recent_cutoff is not None and views.get(a.annotation_key,{}).get('last_seen',float('-inf'))>=recent_cutoff:return False
        if (high_only or high_unfav) and not record.get('high_count',0):return False
        if no1_only and not record.get('top1_count',0):return False
        if post_info=='yes' and not has_x_post_info(a):return False
        if post_info=='unknown' and has_x_post_info(a):return False
        return True
    return [a for a in assets if accept(a)]


def discovery_order(assets,mode,normal_mode,seed,performance,views,grouped=False):
    if mode=='random' and grouped:
        # Draw image content uniformly, rather than rewarding reposted copies.
        return sorted(assets,key=lambda a:hashlib.sha256((str(seed)+'\0'+a.annotation_key+'\0'+a.kind).encode()).digest())
    if mode=='unseen':
        return sorted(assets,key=lambda a:(views.get(a.annotation_key,{}).get('last_seen',float('-inf')),
                    a.date.timestamp() if a.has_known_date else float('inf'),a.post_id,a.media_index,a.variant))
    mapping={'current':normal_mode,'random':'random','old':'oldest','strong':'performance'}
    return order_assets(assets,mapping.get(mode,normal_mode),seed,performance)
