"""Gallery ordering for the currently filtered collection."""
import hashlib


def order_assets(assets, mode='newest', seed='', performance=None):
    assets=list(assets)
    if mode in ('performance','no1'):
        performance=performance or {}
        def performance_key(asset):
            record=performance.get(asset.performance_key)
            has_data=record is not None
            high_count=(record or {}).get('high_count',0)
            top1_count=(record or {}).get('top1_count',0)
            timestamp=asset.date.timestamp() if asset.has_known_date else float('-inf')
            rank=(-top1_count,-high_count) if mode=='no1' else (-high_count,-top1_count)
            return (*rank,not has_data,-timestamp,
                    asset.post_id,asset.media_index,asset.variant)
        return sorted(assets,key=performance_key)
    if mode=='random':
        def random_key(asset):
            identity='\0'.join(map(str,asset.identity))
            rank=hashlib.sha256((str(seed)+'\0'+identity).encode('utf-8')).digest()
            return rank
        return sorted(assets,key=random_key)
    dated=[asset for asset in assets if asset.has_known_date]
    undated=[asset for asset in assets if not asset.has_known_date]
    def chronological_key(asset):
        date=asset.date
        timestamp=date.timestamp()
        return (-timestamp if mode=='newest' else timestamp, asset.post_id,
                asset.media_index, asset.variant)
    dated.sort(key=chronological_key)
    undated.sort(key=lambda a:(a.post_id,a.media_index,a.variant))
    return dated+undated
