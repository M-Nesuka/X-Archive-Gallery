"""Small, readable manual-tag palette, separate from purple/gold performance tags."""
PALETTE = {
    'teal': ('ティール', '#203f40', '#d2eeea'),
    'blue': ('ブルー', '#243e59', '#d8eaff'),
    'green': ('グリーン', '#314834', '#def0d8'),
    'coral': ('コーラル', '#5b3630', '#ffe1d7'),
    'slate': ('グレー', '#3a414b', '#e5e9ef'),
    'mint': ('ミント', '#89d6bd', '#123e32'),
    'sky': ('スカイ', '#85c6ed', '#163951'),
    'lime': ('ライム', '#b6d987', '#2d421c'),
    'salmon': ('サーモン', '#efa69a', '#502b25'),
    'silver': ('シルバー', '#b8c4cf', '#29343e'),
    'rose': ('ローズ', '#ffc1d5', '#69283f'),
    'cherry': ('チェリー', '#ff8fab', '#5d1834'),
    'peach': ('ピーチ', '#ffd1ae', '#62361e'),
    'apricot': ('アプリコット', '#ffb879', '#60300d'),
    'tangerine': ('オレンジ', '#ff994f', '#542708'),
    'lemon': ('レモン', '#f9ed8a', '#514817'),
    'cream': ('クリーム', '#fff2cd', '#594c2d'),
    'pistachio': ('ピスタチオ', '#dfefae', '#3e501e'),
    'spring': ('若草', '#a9eb83', '#2b4719'),
    'apple': ('アップル', '#78dba5', '#164c30'),
    'aqua': ('アクア', '#8de5e0', '#164d4b'),
    'turquoise': ('ターコイズ', '#52cfce', '#124548'),
    'ice': ('アイスブルー', '#c4ebff', '#244d64'),
    'cornflower': ('コーンフラワー', '#a2bdf7', '#283c70'),
    'periwinkle': ('ペリウィンクル', '#c1cdfd', '#3b4274'),
    'sand': ('サンド', '#e9d2b1', '#55412b'),
    'cocoa': ('ココア', '#d5b09c', '#4f3427'),
    'blush': ('桜', '#ffe1e8', '#673844'),
    'paper': ('ホワイト', '#f7f8fa', '#3d4552'),
    'graphite': ('グラファイト', '#586373', '#f3f6fa'),
}
DEFAULT_COLOR = 'teal'


def tag_colors(key):
    return PALETTE.get(key, PALETTE[DEFAULT_COLOR])[1:]
