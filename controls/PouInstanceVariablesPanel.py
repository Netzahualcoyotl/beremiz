#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz IDE
# Copyright (C) 2012: Laurent BESSARD
# Copyright (C) 2026: Edouard TISSERANT
#
# See COPYING file for copyrights details.

import re
import time
from collections import namedtuple

import wx
import wx.lib.agw.customtreectrl as CT
import wx.lib.buttons

from wx.lib.mixins import treemixin

from plcopen.types_enums import *
from plcopen.POUVariablesCollector import _VariablesTreeItemInfos

from util.BitmapLibrary import GetBitmap


ARRAY_WINDOW_SIZE = 100


# Sentinel var_class for array navigation pseudo-items
_ITEM_ARRAY_NAV = object()


_SCALAR_TYPES = frozenset({
    'BOOL', 'SINT', 'INT', 'DINT', 'LINT',
    'USINT', 'UINT', 'UDINT', 'ULINT',
    'BYTE', 'WORD', 'DWORD', 'LWORD',
    'REAL', 'LREAL',
    'STRING', 'WSTRING',
    'TIME', 'DATE', 'DT', 'TOD',
    'TIME_OF_DAY', 'DATE_AND_TIME',
})


class VariablesTreeModel(object):
    """Hierarchical model for POU variables, supporting struct/FB/array expansion."""

    def __init__(self, controller, parent_window, debug,
                 edit_image, debug_instance_image):
        self._controller = controller
        self._parent_window = parent_window
        self._debug = debug
        self._edit_image = edit_image
        self._debug_instance_image = debug_instance_image

        self._root_infos = None
        self._filtered_vars = []
        self._children_cache = {}
        self._array_offsets = {}

        self._filter = None
        self._filter_case_sensitive = False
        self._filter_whole_word = False

    def set_controller(self, controller):
        self._controller = controller

    def set_data(self, pou_infos):
        self._root_infos = pou_infos
        self._children_cache.clear()
        self._array_offsets.clear()
        self._apply_filter()

    def set_filter(self, text, case_sensitive, whole_word):
        self._filter = text if text else None
        self._filter_case_sensitive = case_sensitive
        self._filter_whole_word = whole_word
        self._apply_filter()

    def _apply_filter(self):
        if self._root_infos is None:
            self._filtered_vars = []
            return
        if not self._filter:
            self._filtered_vars = list(self._root_infos.variables)
            return
        result = []
        pattern = self._filter
        if not self._filter_case_sensitive:
            pattern = pattern.upper()
        for var_infos in self._root_infos.variables:
            varname = var_infos.name
            if not self._filter_case_sensitive:
                varname = varname.upper()
            if self._filter_whole_word:
                if pattern != varname:
                    continue
            else:
                if pattern not in varname:
                    continue
            result.append(var_infos)
        self._filtered_vars = result

    def get_infos(self, indices):
        """Resolve index tuple to _VariablesTreeItemInfos (or None for nav items)."""
        return self._resolve_indices(indices)

    def _resolve_indices(self, indices):
        """Walk the tree to resolve an index tuple to an infos object."""
        if not indices:
            return self._root_infos
        infos = self._root_infos
        for depth, idx in enumerate(indices):
            parent_key = indices[:depth]
            parent_infos = infos
            children = self._get_children_list(parent_infos, parent_key)
            if idx < 0 or idx >= len(children):
                return None
            infos = children[idx]
            if infos is None:
                return None
        return infos

    def get_children_count(self, indices):
        infos = self._resolve_indices(indices)
        if infos is None:
            return 0
        if not indices:
            return len(self._filtered_vars)
        children = self._get_children_list(infos, indices)
        return len(children)

    def get_item_text(self, indices):
        infos = self._resolve_indices(indices)
        if infos is None:
            return ""
        if infos.var_class is _ITEM_ARRAY_NAV:
            return infos.name
        if infos.type:
            return "%s (%s)" % (infos.name, infos.type)
        return infos.name

    def get_item_image(self, indices):
        infos = self._resolve_indices(indices)
        if infos is None or infos.var_class is _ITEM_ARRAY_NAV:
            return -1
        return self._parent_window.GetTreeImage(infos.var_class)

    def get_right_images(self, indices):
        infos = self._resolve_indices(indices)
        if infos is None or infos.var_class is _ITEM_ARRAY_NAV:
            return []
        right_images = []
        if infos.edit:
            right_images.append(self._edit_image)
        if self._debug and infos.debug and not self.might_have_children(indices):
            right_images.append(self._debug_instance_image)
        return right_images

    def _get_children_list(self, infos, parent_indices):
        """Get the list of children for a given item, with caching and lazy expansion."""
        if infos is None:
            return []

        if not parent_indices:
            return self._filtered_vars

        if infos.variables:
            return infos.variables

        return self._resolve_children(infos, parent_indices)

    def _resolve_children(self, infos, parent_indices):
        if not infos.type or infos.var_class is _ITEM_ARRAY_NAV:
            return []

        type_name = infos.type

        # Check if this is an inline array type like "ARRAY [0..9] OF INT"
        array_info = self._parse_array_type(type_name)
        if array_info is not None:
            return self._make_array_children(array_info, infos, parent_indices)

        # Check cache for named types
        if type_name in self._children_cache:
            cached = self._children_cache[type_name]
            if cached is not None:
                return cached
            # cached is None means named array — resolve with parent_indices
            return self._resolve_named_array(type_name, infos, parent_indices)

        children = self._resolve_type_children(type_name, infos, parent_indices)
        return children

    def _resolve_type_children(self, type_name, parent_infos, parent_indices):
        if self._controller is None:
            return []

        children = []

        # Try as data type (struct, array, etc.)
        try:
            dt_infos = self._controller.GetDataTypeInfos(
                "D::" + type_name, self._debug)
        except Exception:
            dt_infos = None

        if dt_infos is not None:
            dt_type = dt_infos.get("type")

            if dt_type == "Structure":
                for elem in dt_infos["elements"]:
                    elem_type = elem["Type"]
                    if isinstance(elem_type, tuple):
                        # array member: ("array", base_type, [(lo, hi), ...])
                        dims_str = "][".join(
                            "%s..%s" % (lo, hi) for lo, hi in elem_type[2])
                        elem_type_str = "ARRAY [%s] OF %s" % (
                            dims_str, elem_type[1])
                    else:
                        elem_type_str = elem_type
                    children.append(_VariablesTreeItemInfos(
                        elem["Name"], ITEM_VAR_LOCAL, elem_type_str,
                        False, parent_infos.debug, []))
                self._children_cache[type_name] = children
                return children

            if dt_type == "Array":
                # Named array type — mark cache as None so we resolve
                # per-instance with parent_indices for windowing
                self._children_cache[type_name] = None
                return self._resolve_named_array(
                    type_name, parent_infos, parent_indices)

            if dt_type in ("Directly", "Enumerated", "Subrange"):
                self._children_cache[type_name] = []
                return []

        # Try as POU (function block / program)
        try:
            pou_infos = self._controller.GetPouVariables(
                ComputePouName(type_name), self._debug)
        except Exception:
            pou_infos = None

        if pou_infos is not None:
            children = list(pou_infos.variables)

        self._children_cache[type_name] = children
        return children

    def _resolve_named_array(self, type_name, parent_infos, parent_indices):
        """Resolve a named array type into windowed children."""
        try:
            dt_infos = self._controller.GetDataTypeInfos(
                "D::" + type_name, self._debug)
        except Exception:
            return []
        if dt_infos is None or dt_infos.get("type") != "Array":
            return []
        raw_dims = dt_infos.get("dimensions", [])
        base_type = dt_infos.get("base_type", "")
        if not raw_dims or not base_type:
            return []
        dims = [(int(lo), int(hi)) for lo, hi in raw_dims]
        array_info = (dims, base_type)
        return self._make_array_children(
            array_info, parent_infos, parent_indices)

    def _parse_array_type(self, type_str):
        """Parse 'ARRAY [lo..hi] OF base' or 'ARRAY [lo..hi][lo..hi] OF base'.

        Returns ([(lower, upper), ...], base_type) or None.
        """
        m = re.match(
            r'^ARRAY\s*\[(.*?)\]\s*OF\s+(.+)$', type_str, re.IGNORECASE)
        if m is None:
            return None
        dims_str = m.group(1)
        base_type = m.group(2).strip()
        dims = []
        for dim_part in re.split(r'\]\s*\[', dims_str):
            dm = re.match(r'\s*(\d+)\s*\.\.\s*(\d+)\s*', dim_part)
            if dm is None:
                return None
            dims.append((int(dm.group(1)), int(dm.group(2))))
        return (dims, base_type)

    def _make_array_children(self, array_info, parent_infos, parent_indices):
        dims, base_type = array_info
        lower, upper = dims[0]
        total = upper - lower + 1

        if len(dims) > 1:
            # Multi-dimensional: child type is sub-array
            remaining_dims = dims[1:]
            dims_str = "][".join("%d..%d" % (lo, hi) for lo, hi in remaining_dims)
            child_type = "ARRAY [%s] OF %s" % (dims_str, base_type)
        else:
            child_type = base_type

        if total <= ARRAY_WINDOW_SIZE:
            children = []
            for i in range(lower, upper + 1):
                children.append(_VariablesTreeItemInfos(
                    "[%d]" % i, ITEM_VAR_LOCAL, child_type,
                    False, parent_infos.debug, []))
            return children

        # Windowed: use offset tracking
        offset = self._array_offsets.get(parent_indices, lower)
        offset = max(lower, min(offset, upper - ARRAY_WINDOW_SIZE + 1))
        self._array_offsets[parent_indices] = offset

        children = []

        if offset > lower:
            nav_label = "\u25C0 [%d..%d]" % (lower, offset - 1)
            children.append(_VariablesTreeItemInfos(
                nav_label, _ITEM_ARRAY_NAV, None, False, False, []))

        window_end = min(offset + ARRAY_WINDOW_SIZE, upper + 1)
        for i in range(offset, window_end):
            children.append(_VariablesTreeItemInfos(
                "[%d]" % i, ITEM_VAR_LOCAL, child_type,
                False, parent_infos.debug, []))

        if window_end <= upper:
            nav_label = "\u25B6 [%d..%d]" % (window_end, upper)
            children.append(_VariablesTreeItemInfos(
                nav_label, _ITEM_ARRAY_NAV, None, False, False, []))

        return children

    def _get_array_bounds(self, parent_indices):
        """Get (lower, upper) bounds of first dimension for array at parent_indices."""
        infos = self._resolve_indices(parent_indices)
        if infos is None or not infos.type:
            return None
        array_info = self._parse_array_type(infos.type)
        if array_info is None:
            # Try named array type
            return self._get_named_array_bounds(infos.type)
        dims, _base_type = array_info
        return dims[0]

    def _get_named_array_bounds(self, type_name):
        """Get (lower, upper) for a named array type."""
        if self._controller is None:
            return None
        try:
            dt_infos = self._controller.GetDataTypeInfos("D::" + type_name, self._debug)
        except Exception:
            return None
        if dt_infos is None or dt_infos.get("type") != "Array":
            return None
        raw_dims = dt_infos.get("dimensions", [])
        if not raw_dims:
            return None
        return (int(raw_dims[0][0]), int(raw_dims[0][1]))

    def shift_array_window(self, parent_indices, direction):
        """Shift array window by direction (+1 forward, -1 backward)."""
        bounds = self._get_array_bounds(parent_indices)
        if bounds is None:
            return False
        lower, upper = bounds
        total = upper - lower + 1
        if total <= ARRAY_WINDOW_SIZE:
            return False

        offset = self._array_offsets.get(parent_indices, lower)
        new_offset = offset + direction * ARRAY_WINDOW_SIZE
        new_offset = max(lower, min(new_offset, upper - ARRAY_WINDOW_SIZE + 1))
        if new_offset == offset:
            return False

        self._array_offsets[parent_indices] = new_offset
        return True

    def set_array_offset(self, parent_indices, new_offset):
        """Set array window to an arbitrary offset. Returns True if changed."""
        bounds = self._get_array_bounds(parent_indices)
        if bounds is None:
            return False
        lower, upper = bounds
        total = upper - lower + 1
        if total <= ARRAY_WINDOW_SIZE:
            return False

        new_offset = max(lower, min(new_offset, upper - ARRAY_WINDOW_SIZE + 1))
        old_offset = self._array_offsets.get(parent_indices, lower)
        if new_offset == old_offset:
            return False

        self._array_offsets[parent_indices] = new_offset
        return True

    def build_iec_path(self, indices, instance_path):
        """Build full IEC variable path from tree indices and instance path."""
        parts = [instance_path] if instance_path else []
        for depth in range(len(indices)):
            sub_indices = indices[:depth + 1]
            infos = self._resolve_indices(sub_indices)
            if infos is None or infos.var_class is _ITEM_ARRAY_NAV:
                return None
            name = infos.name
            if name.startswith("["):
                if parts:
                    parts[-1] = parts[-1] + name
                else:
                    parts.append(name)
            else:
                parts.append(name)
        return ".".join(parts)

    def might_have_children(self, indices):
        """Check whether item at indices could have children.

        Uses cache and lightweight GetDataTypeInfos to avoid expensive
        GetPouVariables XSLT calls for every item.
        """
        infos = self._resolve_indices(indices)
        if infos is None:
            return False
        if infos.variables:
            return True
        if not infos.type:
            return False
        # Inline array syntax always has children
        if infos.type.upper().startswith('ARRAY'):
            return True
        if infos.type.upper() in _SCALAR_TYPES:
            return False
        # Check if type was already resolved
        if infos.type in self._children_cache:
            cached = self._children_cache[infos.type]
            return cached is None or bool(cached)
        # For unknown named types, check if it's a simple derived type
        if self._controller is not None:
            try:
                dt_infos = self._controller.GetDataTypeInfos("D::" + infos.type, self._debug)
            except Exception:
                dt_infos = None
            if dt_infos is not None:
                dt_type = dt_infos.get("type")
                if dt_type in ("Directly", "Enumerated", "Subrange"):
                    self._children_cache[infos.type] = []
                    return False
                return True
            # GetDataTypeInfos doesn't search confnode/library types.
            # Check if it's a POU (function block / program) which has children.
            try:
                pou = self._controller.GetPou(infos.type, self._debug)
            except Exception:
                pou = None
            if pou is not None:
                return True
            # Not a known data type or POU — assume leaf
            self._children_cache[infos.type] = []
            return False
        return True

    def is_nav_item(self, indices):
        infos = self._resolve_indices(indices)
        return infos is not None and infos.var_class is _ITEM_ARRAY_NAV

    def get_nav_direction(self, indices):
        """Return -1 for backward nav, +1 for forward nav, 0 if not a nav item."""
        infos = self._resolve_indices(indices)
        if infos is None or infos.var_class is not _ITEM_ARRAY_NAV:
            return 0
        if infos.name.startswith("\u25C0"):
            return -1
        if infos.name.startswith("\u25B6"):
            return 1
        return 0


_ButtonCallbacks = namedtuple("ButtonCallbacks", ["leftdown", "dclick"])


class PouVariablesVirtualTree(treemixin.VirtualTree,
                              treemixin.ExpansionState,
                              CT.CustomTreeCtrl):

    def __init__(self, *args, **kwargs):
        self._model = kwargs.pop('model')
        kwargs['agwStyle'] = (CT.TR_HAS_BUTTONS |
                              CT.TR_MULTIPLE |
                              CT.TR_HAS_VARIABLE_ROW_HEIGHT |
                              CT.TR_HIDE_ROOT |
                              CT.TR_NO_LINES |
                              CT.TR_FULL_ROW_HIGHLIGHT |
                              getattr(CT, "TR_ALIGN_WINDOWS_RIGHT",
                                      CT.TR_ALIGN_WINDOWS))
        super(PouVariablesVirtualTree, self).__init__(*args, **kwargs)
        # self.SetIndent(0)
        # self.SetSpacing(5)
        self._right_images = {}

    def SetModel(self, model):
        self._model = model

    # --- VirtualTree callbacks ---

    def OnGetChildrenCount(self, indices):
        return self._model.get_children_count(indices)

    def OnGetItemText(self, indices):
        return self._model.get_item_text(indices)

    def OnGetItemImage(self, indices, which):
        if which in [wx.TreeItemIcon_Normal, wx.TreeItemIcon_Selected]:
            return self._model.get_item_image(indices)
        return -1

    # --- Deferred type resolution: avoid expensive OnGetChildrenCount ---

    def RefreshItemRecursively(self, item, itemIndex):
        """Override to use fast might_have_children for collapsed items.

        VirtualTree's default calls OnGetChildrenCount for every item
        (even collapsed) which triggers expensive XSLT for FB types.
        We defer full resolution until user actually expands the item.
        """
        if self.IsExpanded(item):
            # Expanded: need real children count for population
            hasChildren = bool(self.OnGetChildrenCount(itemIndex))
            item = self.DoRefreshItem(item, itemIndex, hasChildren)
            self.RefreshChildrenRecursively(item, itemIndex)
        else:
            # Collapsed: fast check only, no controller calls
            hasChildren = self._model.might_have_children(itemIndex)
            item = self.DoRefreshItem(item, itemIndex, hasChildren)
            if not hasChildren:
                # Clean up stale children from previously expanded state
                self.RefreshChildrenRecursively(item, itemIndex)
        self.SetItemHasChildren(item, hasChildren)

    # --- Item refresh: set right images and PyData ---

    def DoRefreshItem(self, item, indices, hasChildren):
        item = super(PouVariablesVirtualTree, self).DoRefreshItem(
            item, indices, hasChildren)
        self._right_images[item] = self._model.get_right_images(indices)
        self.SetPyData(item, self._model.get_infos(indices))
        return item

    def GetItemRightImages(self, item):
        return self._right_images.get(item, [])

    # --- Right-image rendering (from CustomTreeCtrlWithRightImage) ---

    def SetRightImageList(self, imageList):
        self._imageListRight = imageList

    def GetLineHeight(self, item):
        height = CT.CustomTreeCtrl.GetLineHeight(self, item)
        rightimages = self.GetItemRightImages(item)
        if len(rightimages) > 0:
            _r_image_w, r_image_h = self._imageListRight.GetSize(rightimages[0])
            return max(height, r_image_h + 8)
        return height

    def GetItemRightImagesBBox(self, item):
        rightimages = self.GetItemRightImages(item)
        if len(rightimages) > 0:
            w, _h = self.GetClientSize()
            total_h = self.GetLineHeight(item)
            r_image_w, r_image_h = self._imageListRight.GetSize(rightimages[0])

            bbox_width = (r_image_w + 4) * len(rightimages) + 4
            bbox_height = r_image_h + 8
            bbox_x = w - bbox_width
            bbox_y = item.GetY() + ((total_h > r_image_h) and [(total_h-r_image_h)//2] or [0])[0]

            return wx.Rect(bbox_x, bbox_y, bbox_width, bbox_height)

        return None

    def IsOverItemRightImage(self, item, point):
        rightimages = self.GetItemRightImages(item)
        if len(rightimages) > 0:
            point = self.CalcUnscrolledPosition(point)
            r_image_w, r_image_h = self._imageListRight.GetSize(rightimages[0])
            images_bbx = self.GetItemRightImagesBBox(item)

            rect = wx.Rect(images_bbx.x + 4, images_bbx.y + 4,
                           r_image_w, r_image_h)
            for r_image in rightimages:
                if rect.Contains(point):
                    return r_image
                rect.x += r_image_w + 4

            return None

    def PaintItem(self, item, dc, level, align):
        CT.CustomTreeCtrl.PaintItem(self, item, dc, level, align)

        rightimages = self.GetItemRightImages(item)
        if len(rightimages) > 0:
            images_bbx = self.GetItemRightImagesBBox(item)
            r_image_w, _r_image_h = self._imageListRight.GetSize(rightimages[0])

            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.SetPen(wx.TRANSPARENT_PEN)

            dc.DrawRectangle(images_bbx.x, images_bbx.y,
                             images_bbx.width, images_bbx.height)
            x_pos = images_bbx.x + 4
            for r_image in rightimages:
                self._imageListRight.Draw(
                    r_image, dc, x_pos, images_bbx.y + 4,
                    wx.IMAGELIST_DRAW_TRANSPARENT)
                x_pos += r_image_w + 4


class PouInstanceVariablesPanel(wx.Panel):

    def __init__(self, parent, window, controller, debug):
        wx.Panel.__init__(self, name='PouInstanceTreePanel',
                          parent=parent, pos=wx.Point(0, 0),
                          size=wx.Size(0, 0), style=wx.TAB_TRAVERSAL)

        self.ParentButton = wx.lib.buttons.GenBitmapButton(
            self, bitmap=GetBitmap("top"), size=wx.Size(28, 28), style=wx.NO_BORDER)
        self.ParentButton.SetToolTip(_("Parent instance"))
        self.Bind(wx.EVT_BUTTON, self.OnParentButtonClick,
                  self.ParentButton)

        self.InstanceChoice = wx.ComboBox(self, size=wx.Size(0, 0), style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.OnInstanceChoiceChanged,
                  self.InstanceChoice)

        self.DebugButton = wx.lib.buttons.GenBitmapButton(
            self, bitmap=GetBitmap("debug_instance"), size=wx.Size(28, 28), style=wx.NO_BORDER)
        self.DebugButton.SetToolTip(_("Debug instance"))
        self.Bind(wx.EVT_BUTTON, self.OnDebugButtonClick,
                  self.DebugButton)

        self.TreeRightImageList = wx.ImageList(24, 24)
        self.EditImage = self.TreeRightImageList.Add(GetBitmap("edit"))
        self.DebugInstanceImage = self.TreeRightImageList.Add(GetBitmap("debug_instance"))

        self.ParentWindow = window
        self.Controller = controller
        self.Debug = debug

        self._model = VariablesTreeModel(
            controller, window, debug,
            self.EditImage, self.DebugInstanceImage)

        self.VariablesList = PouVariablesVirtualTree(
            self,
            model=self._model,
            style=wx.SUNKEN_BORDER)
        self.VariablesList.SetRightImageList(self.TreeRightImageList)

        self.VariablesList.Bind(CT.EVT_TREE_ITEM_ACTIVATED,
                                self.OnVariablesListItemActivated)
        self.VariablesList.Bind(wx.EVT_LEFT_DOWN, self.OnVariablesListLeftDown)
        self.VariablesList.Bind(wx.EVT_LEFT_UP, self.OnVariablesListLeftUp)
        self.VariablesList.Bind(wx.EVT_KEY_DOWN, self.OnVariablesListKeyDown)

        self.ButtonCallBacks = {
            self.EditImage: _ButtonCallbacks(
                self.EditButtonCallback, None),
            self.DebugInstanceImage: _ButtonCallbacks(
                self.DebugButtonCallback, self.DebugButtonDClickCallback)}

        self.FilterCtrl = wx.SearchCtrl(self)
        self.FilterCtrl.ShowCancelButton(True)
        self.FilterCtrl.Bind(wx.EVT_TEXT, self.OnFilterUpdate)
        self.FilterCtrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.OnFilterCancel)

        searchMenu = wx.Menu()
        item = searchMenu.AppendCheckItem(-1, _("Match Case"))
        self.Bind(wx.EVT_MENU, self.OnSearchMenu, item)
        item = searchMenu.AppendCheckItem(-1, _("Whole Words"))
        self.Bind(wx.EVT_MENU, self.OnSearchMenu, item)
        self.FilterCtrl.SetMenu(searchMenu)

        if not self.Debug:
            self.DebugButton.Hide()

        buttons_sizer = wx.FlexGridSizer(cols=3, hgap=0, rows=1, vgap=0)
        buttons_sizer.Add(self.ParentButton)
        buttons_sizer.Add(self.InstanceChoice, flag=wx.GROW)
        buttons_sizer.Add(self.DebugButton)
        buttons_sizer.AddGrowableCol(1)
        buttons_sizer.AddGrowableRow(0)

        main_sizer = wx.FlexGridSizer(cols=1, hgap=0, rows=3, vgap=0)
        main_sizer.Add(buttons_sizer, flag=wx.GROW)
        main_sizer.Add(self.VariablesList, flag=wx.GROW)
        main_sizer.Add(self.FilterCtrl, flag=wx.GROW)
        main_sizer.AddGrowableCol(0)
        main_sizer.AddGrowableRow(1)

        self.SetSizer(main_sizer)

        self.PouTagName = None
        self.PouInfos = None
        self.PouInstance = None
        self._nav_click_info = None

    def SetTreeImageList(self, tree_image_list):
        self.VariablesList.SetImageList(tree_image_list)

    def SetController(self, controller):
        self.Controller = controller
        self._model.set_controller(controller)
        self.RefreshView()

    def SetPouType(self, tagname, pou_instance=None):
        if self.Controller is not None:
            if tagname == "Project":
                config_name = self.Controller.GetProjectMainConfigurationName()
                if config_name is not None:
                    tagname = ComputeConfigurationName(config_name)
            if pou_instance is not None:
                self.PouInstance = pou_instance

            if self.PouTagName != tagname:
                self.PouTagName = tagname
                self.RefreshView()
            else:
                self.RefreshInstanceChoice()
        else:
            self.RefreshView()

    def ResetView(self):
        self.Controller = None
        self._model.set_controller(None)

        self.PouTagName = None
        self.PouInfos = None
        self.PouInstance = None

        self.RefreshView()

    def OnSearchMenu(self, event):
        searchMenu = self.FilterCtrl.GetMenu().GetMenuItems()
        self._model.set_filter(
            self.FilterCtrl.GetValue(),
            searchMenu[0].IsChecked(),
            searchMenu[1].IsChecked())
        self._RefreshTree()

    def OnFilterUpdate(self, event):
        searchMenu = self.FilterCtrl.GetMenu().GetMenuItems()
        self._model.set_filter(
            self.FilterCtrl.GetValue(),
            searchMenu[0].IsChecked(),
            searchMenu[1].IsChecked())
        self._RefreshTree()
        event.Skip()

    def OnFilterCancel(self, event):
        self.FilterCtrl.SetValue('')
        event.Skip()

    def _RefreshTree(self):
        """Refresh tree widget from current model state."""
        self.Freeze()
        expansion = self.VariablesList.GetExpansionState()
        self.VariablesList.RefreshItems()
        self.VariablesList.SetExpansionState(expansion)
        self.Thaw()

    def RefreshView(self):
        self.Freeze()

        if self.Controller is not None and self.PouTagName is not None:
            if self.PouTagName.split('::')[0] in ['A', 'T']:
                self.PouInfos = self.Controller.GetPouVariables('P::%s' % self.PouTagName.split('::')[1], self.Debug)
            else:
                self.PouInfos = self.Controller.GetPouVariables(self.PouTagName, self.Debug)
            if None in self.Controller.GetEditedElementType(self.PouTagName, self.Debug) and self.PouInfos is not None:
                self.PouInfos.debug = False
        else:
            self.PouInfos = None

        self._model.set_data(self.PouInfos)

        expansion = self.VariablesList.GetExpansionState()
        self.VariablesList.RefreshItems()
        self.VariablesList.SetExpansionState(expansion)

        self.RefreshInstanceChoice()
        self.RefreshButtons()

        self.Thaw()

    def RefreshInstanceChoice(self):
        self.InstanceChoice.Clear()
        self.InstanceChoice.SetValue("")
        if self.Controller is not None and self.PouInfos is not None:
            instances = self.Controller.SearchPouInstances(self.PouTagName, self.Debug)
            for instance in instances:
                self.InstanceChoice.Append(instance)
            if len(instances) == 1:
                self.PouInstance = instances[0]
            if self.PouInfos.var_class in [ITEM_CONFIGURATION, ITEM_RESOURCE]:
                self.PouInstance = None
                self.InstanceChoice.SetSelection(0)
            elif self.PouInstance in instances:
                self.InstanceChoice.SetStringSelection(self.PouInstance)
            else:
                self.PouInstance = None
                self.InstanceChoice.SetValue(_("Select an instance"))

    def RefreshButtons(self):
        enabled = self.InstanceChoice.GetSelection() != -1
        if self.PouInfos is not None:
            self.ParentButton.Enable(enabled and self.PouInfos.var_class != ITEM_CONFIGURATION)
            self.DebugButton.Enable(enabled and self.PouInfos.debug and self.Debug)
        else:
            self.ParentButton.Enable(False)
            self.DebugButton.Enable(False)

    def EditButtonCallback(self, infos, item=None):
        var_class = infos.var_class
        if var_class == ITEM_RESOURCE:
            tagname = ComputeConfigurationResourceName(
                self.InstanceChoice.GetStringSelection(),
                infos.name)
        elif var_class == ITEM_TRANSITION:
            tagname = ComputePouTransitionName(
                self.PouTagName.split("::")[1],
                infos.name)
        elif var_class == ITEM_ACTION:
            tagname = ComputePouActionName(
                self.PouTagName.split("::")[1],
                infos.name)
        else:
            var_class = ITEM_POU
            tagname = ComputePouName(infos.type)
        self.ParentWindow.EditProjectElement(var_class, tagname)

    def _GetVarPath(self, item):
        """Build full IEC path for a tree item using model indices."""
        if self.InstanceChoice.GetSelection() == -1:
            return None
        instance_path = self.InstanceChoice.GetStringSelection()
        if self.PouTagName.split("::")[0] in ["A", "T"]:
            pos = instance_path.rfind('.')
            instance_path = instance_path[0:pos]
        indices = self.VariablesList.GetIndexOfItem(item)
        return self._model.build_iec_path(indices, instance_path)

    def _GetSelectedDebugItems(self):
        """Get all selected items that have the debug_instance_image button."""
        result = []
        for item in self.VariablesList.GetSelections():
            item_infos = self.VariablesList.GetItemData(item)
            if item_infos is None:
                continue
            if item_infos.var_class not in ITEMS_VARIABLE:
                continue
            if not item_infos.debug:
                continue
            if self.might_have_children(item):
                continue
            result.append(item)
        return result

    def DebugButtonCallback(self, infos, item=None):
        if self.InstanceChoice.GetSelection() != -1:
            var_class = infos.var_class
            if var_class in ITEMS_VARIABLE:
                # Add all selected debuggable leaf items
                selected = self._GetSelectedDebugItems()
                if item is not None and item not in selected:
                    selected = [item]
                if not selected:
                    selected = [item] if item is not None else []
                for sel_item in selected:
                    var_path = self._GetVarPath(sel_item)
                    if var_path is not None:
                        self.ParentWindow.AddDebugVariable(var_path, force=True)
            elif var_class == ITEM_TRANSITION:
                instance_path = self.InstanceChoice.GetStringSelection()
                if self.PouTagName.split("::")[0] in ["A", "T"]:
                    pos = instance_path.rfind('.')
                    instance_path = instance_path[0:pos]
                var_path = "%s.%s" % (instance_path, infos.name)
                self.ParentWindow.OpenDebugViewer(
                    var_class,
                    var_path,
                    ComputePouTransitionName(
                        self.PouTagName.split("::")[1],
                        infos.name))
            elif var_class == ITEM_ACTION:
                instance_path = self.InstanceChoice.GetStringSelection()
                if self.PouTagName.split("::")[0] in ["A", "T"]:
                    pos = instance_path.rfind('.')
                    instance_path = instance_path[0:pos]
                var_path = "%s.%s" % (instance_path, infos.name)
                self.ParentWindow.OpenDebugViewer(
                    var_class,
                    var_path,
                    ComputePouActionName(
                        self.PouTagName.split("::")[1],
                        infos.name))
            else:
                instance_path = self.InstanceChoice.GetStringSelection()
                var_path = "%s.%s" % (instance_path, infos.name)
                self.ParentWindow.OpenDebugViewer(
                    var_class,
                    var_path,
                    ComputePouName(infos.type))

    def DebugButtonDClickCallback(self, infos, item=None):
        if self.InstanceChoice.GetSelection() != -1:
            if infos.var_class in ITEMS_VARIABLE:
                selected = self._GetSelectedDebugItems()
                if item is not None and item not in selected:
                    selected = [item]
                if not selected:
                    selected = [item] if item is not None else []
                for sel_item in selected:
                    var_path = self._GetVarPath(sel_item)
                    if var_path is not None:
                        self.ParentWindow.AddDebugVariable(var_path, force=True, graph=True)

    def ShowInstanceChoicePopup(self):
        self.InstanceChoice.SetFocusFromKbd()
        self.InstanceChoice.Popup()

    def OnParentButtonClick(self, event):
        if self.InstanceChoice.GetSelection() != -1:
            parent_path = self.InstanceChoice.GetStringSelection().rsplit(".", 1)[0]
            tagname = self.Controller.GetPouInstanceTagName(parent_path, self.Debug)
            if tagname is not None:
                wx.CallAfter(self.SetPouType, tagname, parent_path)
                wx.CallAfter(self.ParentWindow.SelectProjectTreeItem, tagname)
        event.Skip()

    def OnInstanceChoiceChanged(self, event):
        self.RefreshButtons()
        event.Skip()

    def OnDebugButtonClick(self, event):
        if self.InstanceChoice.GetSelection() != -1:
            self.ParentWindow.OpenDebugViewer(
                self.PouInfos.var_class,
                self.InstanceChoice.GetStringSelection(),
                self.PouTagName)
        event.Skip()

    def OnVariablesListItemActivated(self, event):
        selected_item = event.GetItem()
        if selected_item is not None and selected_item.IsOk():
            item_infos = self.VariablesList.GetItemData(selected_item)
            if item_infos is None:
                event.Skip()
                return

            # Handle array navigation pseudo-items — shift window
            if item_infos.var_class is _ITEM_ARRAY_NAV:
                indices = self.VariablesList.GetIndexOfItem(selected_item)
                parent_indices = indices[:-1]
                direction = self._model.get_nav_direction(indices)
                if direction != 0 and self._model.shift_array_window(parent_indices, direction):
                    self._RefreshTree()
                event.Skip()
                return

            item_button = self.VariablesList.IsOverItemRightImage(
                selected_item, event.GetPoint())
            if item_button is not None:
                callback = self.ButtonCallBacks[item_button].dclick
                if callback is not None:
                    callback(item_infos, selected_item)

            elif item_infos.var_class not in ITEMS_VARIABLE:
                instance_path = self.InstanceChoice.GetStringSelection()
                if item_infos.var_class == ITEM_RESOURCE:
                    if instance_path != "":
                        tagname = ComputeConfigurationResourceName(
                            instance_path,
                            item_infos.name)
                    else:
                        tagname = None
                else:
                    parent_item = selected_item.GetParent()
                    parent_infos = self.VariablesList.GetItemData(parent_item)
                    if parent_infos is not None:
                        parent_type = parent_infos.type
                    else:
                        parent_type = self.PouTagName.split("::")[1] if self.PouTagName else ""
                    if item_infos.var_class == ITEM_ACTION:
                        tagname = ComputePouActionName(parent_type, item_infos.name)
                    elif item_infos.var_class == ITEM_TRANSITION:
                        tagname = ComputePouTransitionName(parent_type, item_infos.name)
                    else:
                        tagname = ComputePouName(item_infos.type)
                if tagname is not None:
                    if instance_path != "":
                        item_path = "%s.%s" % (instance_path, item_infos.name)
                    else:
                        item_path = None
                    # Defer rebuild and don't Skip(): default double-click
                    # expansion would otherwise fire on an item that
                    # RefreshItems is about to delete.
                    wx.CallAfter(self.SetPouType, tagname, item_path)
                    wx.CallAfter(
                        self.ParentWindow.SelectProjectTreeItem, tagname)
                    return
        event.Skip()

    def _ShowArrayOffsetDialog(self, indices):
        """Show dialog to jump to arbitrary array offset."""
        parent_indices = indices[:-1]
        bounds = self._model._get_array_bounds(parent_indices)
        if bounds is None:
            return
        lower, upper = bounds
        offset = self._model._array_offsets.get(parent_indices, lower)
        dlg = wx.NumberEntryDialog(
            self, _("Enter array index to navigate to"),
            _("Index:"), _("Array Navigation"),
            offset, lower, upper)
        if dlg.ShowModal() == wx.ID_OK:
            if self._model.set_array_offset(parent_indices, dlg.GetValue()):
                self._RefreshTree()
        dlg.Destroy()

    def OnVariablesListLeftUp(self, event):
        if self.InstanceChoice.GetSelection() == -1:
            wx.CallAfter(self.ShowInstanceChoicePopup)
            event.Skip(False)
            return

        nav_info = self._nav_click_info
        self._nav_click_info = None
        if nav_info is not None:
            item, was_selected, click_time = nav_info
            elapsed = time.monotonic() - click_time
            if was_selected or elapsed >= 1.0:
                indices = self.VariablesList.GetIndexOfItem(item)
                self._ShowArrayOffsetDialog(indices)
            return

    def OnVariablesListLeftDown(self, event):
        if self.InstanceChoice.GetSelection() == -1:
            event.Skip(False)
            return
        event.Skip()

        item, flags = self.VariablesList.HitTest(event.GetPosition())
        if item is not None:
            item_infos = self.VariablesList.GetItemData(item)
            if item_infos is not None:
                # Check right-image button click
                item_button = self.VariablesList.IsOverItemRightImage(
                    item, event.GetPosition())
                if item_button is not None:
                    callback = self.ButtonCallBacks[item_button].leftdown
                    if callback is not None:
                        callback(item_infos, item)
                    return

                # Array navigation — record click for long-press detection
                if item_infos.var_class is _ITEM_ARRAY_NAV:
                    was_selected = item in self.VariablesList.GetSelections()
                    self._nav_click_info = (item, was_selected, time.monotonic())
                    return

                # Single variable drag on label click
                if (flags & CT.TREE_HITTEST_ONITEMLABEL and
                        item_infos.var_class in ITEMS_VARIABLE and
                        not self.might_have_children(item)):
                    var_path = self._GetVarPath(item)
                    if var_path is not None:
                        self.ParentWindow.EnsureTabVisible(
                            self.ParentWindow.DebugVariablePanel)
                        data = wx.TextDataObject(str((var_path, "debug")))
                        dragSource = wx.DropSource(self.VariablesList)
                        dragSource.SetData(data)
                        dragSource.DoDragDrop()
                    return


    def might_have_children(self, item):
        """Check if a tree item might have children (for selection filtering)."""
        indices = self.VariablesList.GetIndexOfItem(item)
        return self._model.might_have_children(indices)

    def OnVariablesListKeyDown(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            if self.InstanceChoice.GetSelection() != -1:
                selected = self._GetSelectedDebugItems()
                for sel_item in selected:
                    var_path = self._GetVarPath(sel_item)
                    if var_path is not None:
                        self.ParentWindow.AddDebugVariable(var_path, force=True)
                if selected:
                    # recover focus for further selection
                    # debug panel keeps it otherwise.
                    wx.CallAfter(self.SetFocusFromKbd)
        elif keycode != wx.WXK_LEFT:
            event.Skip()
