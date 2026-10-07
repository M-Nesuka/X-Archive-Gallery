"""Stable X attachment identity, independent of ZIP root and image encoding."""
from pathlib import PurePosixPath


def attachment_identity(post_id, media_index, kind, source):
    # X keeps this filename when exporting the same attachment at a new size.
    # Do not match unrelated posts, attachment positions or video renditions.
    name = PurePosixPath(str(source).replace('\\', '/')).name
    return str(post_id), int(media_index), str(kind), name
