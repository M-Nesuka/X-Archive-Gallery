"""Optional light appearance; media and user-selected tag colors stay unchanged."""
import re
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from .style import STYLE

LIGHT_COLORS = {
    '#0b0b0e':'#fafbfc', '#101013':'#f1f3f6', '#131016':'#f4f5f8',
    '#151419':'#ffffff', '#17141c':'#f1f3f6', '#17161c':'#e9edf2',
    '#1b1821':'#ffffff', '#100d15':'#ffffff', '#111014':'#edf0f4',
    '#201e25':'#e9edf2', '#201c26':'#edf0f4', '#211c29':'#edf0f4',
    '#211f25':'#eef0f3', '#211d29':'#edf0f5', '#211e27':'#edf0f5',
    '#25212c':'#ffffff', '#242129':'#e5e8ef', '#342c40':'#dce1ea',
    '#2b2437':'#e5e1f0', '#3a304a':'#d9d1e9', '#2d2637':'#e5e1ef',
    '#2a2433':'#ffffff', '#29232f':'#e5e8ef', '#25272b':'#e5eced',
    '#253330':'#dbece7', '#3c3645':'#d9e4f5', '#4b3b5d':'#d5e0f0',
    '#463552':'#e2e7f0', '#514263':'#cbdcf4', '#39313f':'#cbd1dc',
    '#3b3344':'#d8dee7', '#332d3c':'#d5dce6', '#4b4455':'#b6bfcc',
    '#4b4354':'#c0c8d3', '#2a2630':'#dfe5ed',
    '#eeebf4':'#252b38', '#eeeaf5':'#252b38',
    '#e2dfe8':'#323747', '#efedf3':'#252b38', '#ffffff':'#252b38', '#fff':'#252b38',
    '#b9b2c3':'#596476', '#bcb5c7':'#556174', '#c7c0cf':'#596476',
    '#bfb6cc':'#616c7f', '#bfb5ca':'#616c7f', '#c8c1d2':'#526176',
    '#c5bdce':'#526176', '#b3b9bf':'#596779', '#b5a4c8':'#665879',
    '#b9aa80':'#81620e', '#dfcfef':'#514666', '#e5d4ff':'#54416e',
    '#e6d8f5':'#594674', '#c1abed':'#705494',
    '#f5edff':'#3c3450', '#a8bdb7':'#3f675c', '#d5e3df':'#315b50',
    '#c8dfd7':'#315b50', '#96909f':'#6e7787', '#93849f':'#6f607c',
    '#928a9c':'#6a7383', '#9c95a5':'#6a7383', '#8f879a':'#6a7383',
    '#a29baa':'#677386', '#a59bae':'#677386', '#76707f':'#657184',
    '#777180':'#657184', '#5c5664':'#9ba3b1', '#827b8d':'#939dab',
}


def is_white():
    app=QApplication.instance()
    return bool(app and app.property('xag_white'))


def theme_color(value):
    return LIGHT_COLORS.get(value.lower(),value) if is_white() else value


def theme_css(value,white=None):
    if white is None:white=is_white()
    if not white:return value
    result=re.sub(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b',
                  lambda m:LIGHT_COLORS.get(m[0].lower(),m[0]),value)
    return result.replace('rgba(18,16,22,232)','rgba(255,255,255,240)')


class AppearanceMixin:
    def set_white_mode(self,enabled):
        self.white_mode=bool(enabled)
        self.store.set('white_mode',self.white_mode)
        self.apply_appearance()

    def apply_appearance(self):
        app=QApplication.instance();app.setProperty('xag_white',self.white_mode)
        stylesheet=theme_css(STYLE,self.white_mode)
        app.setStyleSheet(stylesheet);self.setStyleSheet(stylesheet)
        # Rebuild from the base style rather than carrying light-only roles into dark mode.
        palette=QPalette(app.style().standardPalette())
        roles={'Window':'#0b0b0e','WindowText':'#eeebf4','Base':'#17141c',
            'AlternateBase':'#201c26','Text':'#eeebf4','Button':'#211c29',
            'ButtonText':'#eeebf4','Highlight':'#4b3b5d','HighlightedText':'#eeebf4',
            'PlaceholderText':'#96909f','ToolTipBase':'#2a2433','ToolTipText':'#eeebf4',
            'Link':'#c1abed','LinkVisited':'#b5a4c8',
            'Light':'#eeebf4','Midlight':'#b9b2c3','Mid':'#96909f',
            'Dark':'#39313f','Shadow':'#0b0b0e','BrightText':'#eeebf4'}
        for name,value in roles.items():
            palette.setColor(getattr(QPalette.ColorRole,name),QColor(theme_color(value)))
        app.setPalette(palette)
        if hasattr(self,'white_mode_action'):
            self.white_mode_action.blockSignals(True)
            self.white_mode_action.setChecked(self.white_mode)
            self.white_mode_action.blockSignals(False)
        if hasattr(self,'import_panel'):
            self.import_panel.refresh_appearance()
        if hasattr(self,'performance_tags'):self.update_manual_details()
        self.update()
        if hasattr(self,'gallery'):self.gallery.viewport().update()
        for name in ('preview','large'):
            if hasattr(self,name):getattr(self,name).update()
