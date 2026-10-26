"""Group headings and selectable tag children for the management workspace."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem


class TagItem(QTreeWidgetItem):
    def data(self,*args):return super().data(0,args[0]) if len(args)==1 else super().data(*args)
    def setData(self,*args):return super().setData(0,*args) if len(args)==2 else super().setData(*args)
    def text(self,column=0):return super().text(column)
    def setText(self,*args):return super().setText(0,args[0]) if len(args)==1 else super().setText(*args)
    def setIcon(self,*args):return super().setIcon(0,args[0]) if len(args)==1 else super().setIcon(*args)
    def setToolTip(self,*args):return super().setToolTip(0,args[0]) if len(args)==1 else super().setToolTip(*args)
    def isHidden(self):
        parent=self.parent()
        return super().isHidden() or bool(parent and (parent.isHidden() or not parent.isExpanded()))


class TagTree(QTreeWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.tags=[];self.groups={}
        self.setHeaderHidden(True);self.setColumnCount(1)
        self.setIndentation(18);self.setUniformRowHeights(True)
        self.itemCollapsed.connect(self.clear_collapsed_selection)

    def clear(self):
        super().clear();self.tags=[];self.groups={}

    def add_group(self,key,name,expanded=True):
        item=TagItem([name]);item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font=item.font(0);font.setBold(True);item.setFont(0,font)
        self.addTopLevelItem(item);self.groups[key]=item;item.setExpanded(expanded)
        return item

    def add_tag(self,group,item):
        self.groups[group].addChild(item);self.tags.append(item)

    def count(self):return len(self.tags)
    def item(self,index):return self.tags[index]
    def setCurrentRow(self,index):self.setCurrentItem(self.tags[index] if index>=0 else None)
    def expand_group(self,key):
        if key in self.groups:self.groups[key].setExpanded(True)

    def clear_collapsed_selection(self,parent):
        for index in range(parent.childCount()):parent.child(index).setSelected(False)
