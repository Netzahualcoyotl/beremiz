#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import math
import csv
from time import time as gettime
from types import TupleType
from numpy import array, matrix, argmin, argmax
from numpy.linalg import norm

import wx
import wx.lib.buttons

from graphics.DebugDataConsumer import DebugDataConsumer
from editors.DebugViewer import DebugViewer, REFRESH_PERIOD
from editors.EditorPanel import EditorPanel
from util.BitmapLibrary import GetBitmap

FRAME_BORDER = (10, 10)
AXIS_LABELS = ["X", "Y", "Z"]
AXIS_SIZE_FACTOR = 0.25 
ARROW_SIZE = 5.
ARROW_POINTS = array([
    [ARROW_SIZE, 0.], 
    [-ARROW_SIZE, -ARROW_SIZE],
    [-ARROW_SIZE, ARROW_SIZE]])
CIRCLE_RADIUS = 3
SQUARE_SIZE = (10, 10)
MAX_LINKAGE = 6

#def DrawArrow(dc, point, axis):
#    dc.DrawPolygon(
#        map(lambda x:
#                map(round, array(
#                    matrix([[axis[0], -axis[1]],
#                            [axis[1], axis[0]]]) * 
#                    x.reshape([2, 1])).reshape([1, 2])[0]),
#            ARROW_POINTS), point[0], point[1])
def DrawArrow(dc, point, axis):
    transformed_points = []
    for x in ARROW_POINTS:
        # Rotar y escalar el punto
        vec = array([[axis[0], -axis[1]],
                     [axis[1],  axis[0]]]) @ x.reshape((2, 1))
        vec = vec.reshape((2,))
        transformed_points.append([round(v) for v in vec])
    
    dc.DrawPolygon(transformed_points, point[0], point[1])


if wx.Platform == '__WXMSW__':
    faces = { 'times': 'Times New Roman',
              'mono' : 'Courier New',
              'helv' : 'Arial',
              'other': 'Comic Sans MS',
              'size' : 10,
             }
else:
    faces = { 'times': 'Times',
              'mono' : 'Courier',
              'helv' : 'Helvetica',
              'other': 'new century schoolbook',
              'size' : 12,
             }


try:
    import matplotlib
    matplotlib.use('WX')
    import matplotlib.pyplot
    from matplotlib.backends.backend_wx import FigureCanvasWx as FigureCanvas
    from mpl_toolkits.mplot3d import Axes3D
    USE_MPL = True
except:
    USE_MPL = False

class KinematicProjection(wx.Panel):
    
    def __init__(self, parent, landmark, window):
        wx.Panel.__init__(self, parent, style=wx.SIMPLE_BORDER)
        self.SetBackgroundColour(wx.WHITE)
        self.SetFont(wx.Font(
            faces["size"], 
            wx.SWISS, 
            wx.NORMAL, 
            wx.NORMAL, 
            faceName = faces["mono"])
        )
        
        self.ParentWindow = window
        self.Landmark = landmark
        self.Projection = matrix(zip(*landmark))
        self.KinematicChain = None
        self.ToolCentrePointEnvelop = None
        self.ScreenCenter = None
        self.Zoom = None
        
        nul_axis = 0
        for num, axis in enumerate(landmark):
            if axis[0] == 0 and axis[1] == 0:
                nul_axis += 1
        
        if nul_axis > 0:
            self.MouseOldPos = None
            self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
            self.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleUp)
            self.Bind(wx.EVT_MOTION, self.OnMotion)
        
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        
        self.RefreshClientScale()

    def RefreshClientScale(self):
        client_size = self.GetClientSize()
        
        self.ClientCenter = array(
            [float(client_size[0]) / 2.,
             float(client_size[1]) / 2.,
             0.]) 
        
        self.ClientScale = array(
            [min(float(client_size[0] - FRAME_BORDER[0] * 2) * 0.75,
                 float(client_size[1] - FRAME_BORDER[1] * 2) * 0.75)] * 3)
        
        self.AxisSize = min(
            float((client_size[0] - FRAME_BORDER[0] * 2)) * AXIS_SIZE_FACTOR,
            float((client_size[1] - FRAME_BORDER[1] * 2)) * AXIS_SIZE_FACTOR)
        
        
    def SetKinematicChain(self, chain, envelop, center, zoom):
        self.KinematicChain = chain
        self.ScreenCenter = center
        self.ToolCentrePointEnvelop = envelop
        self.Zoom = zoom
        self.Refresh()
        
    def SetScreenCenter(self, center):
        self.ScreenCenter = center
        self.Refresh()
        
    def SetZoom(self, zoom):
        self.Zoom = zoom
        self.Refresh()

    def OnMiddleDown(self, event):
        mouse_pos = event.GetPosition()
        self.MouseOldPos = array([mouse_pos[0], mouse_pos[1], 0.])
        event.Skip()
        
    def OnMiddleUp(self, event):
        self.MouseOldPos = None
        event.Skip()
        
    def OnMotion(self, event):
        if self.MouseOldPos is not None and event.MiddleIsDown():
            mouse_pos = event.GetPosition()
            new_pos = array([mouse_pos[0], mouse_pos[1], 0.])
            self.ParentWindow.SetScreenCenter(
                self.ScreenCenter + 
                array(self.Projection.I *
                      ((self.MouseOldPos - new_pos) / self.ClientScale).reshape([3, 1])
                ).reshape([1, 3])[0] / self.Zoom)
            self.MouseOldPos = new_pos
            
        event.Skip()
    
    def OnMouseWheel(self, event):
        rotation = event.GetWheelRotation() / event.GetWheelDelta()
        self.ParentWindow.ChangeZoom(rotation)
        event.Skip()
    
    def OnSize(self, event):
        self.RefreshClientScale()
        self.Refresh()
        event.Skip()
    
    def GetProjectedPoints(self, points):
        return array([
                map(round, 
                    array((self.Projection * (
                        (point - self.ScreenCenter) * self.Zoom
                    ).reshape([3, 1])).reshape([1, 3]))[0] * 
                    self.ClientScale + self.ClientCenter)
                for point in points])
    
    def OnPaint(self, event):
        client_size = self.GetClientSize()
        
        bitmap = wx.EmptyBitmap(*client_size)
        dc = wx.MemoryDC(bitmap)
        dc.Clear()
        
        # Draw kinematic chain informations
        if (self.KinematicChain is not None and 
            self.ScreenCenter is not None and self.Zoom is not None):
            
            dc.SetPen(wx.Pen(wx.RED))
            
            # Draw Tool Centre Point Envelop
            for points in self.ToolCentrePointEnvelop[0]:
                dc.DrawLines([point[:2] for point in 
                              self.GetProjectedPoints(points)])
            
            for point in self.GetProjectedPoints(self.ToolCentrePointEnvelop[1]):
                dc.DrawPoint(point[0], point[1])
            
            # Draw linkage movement and limits
            dc.SetBrush(wx.Brush(wx.NamedColour("orange")))
            
            for point, infos in self.KinematicChain:
                if infos is not None:
                    
                    if infos[2] is not None:    
                        dc.SetPen(wx.Pen(wx.NamedColour("orange")))
                        
                        for decoration in infos[2]:
                            dc.DrawLines([point[:2] for point in 
                                          self.GetProjectedPoints(decoration)])
                    
                    dc.SetPen(wx.Pen(wx.NamedColour("orange"), 3))
                    
                    move_points = self.GetProjectedPoints(infos[1])
                    
                    dc.DrawLines([point[:2] for point in move_points])
                    
                    axis = move_points[-1][:2] - move_points[-2][:2]
                    norm_axis = norm(axis)
                    if norm_axis != 0.:
                        normalized_axis = axis / norm_axis
                        DrawArrow(dc, move_points[-1][:2], normalized_axis)
            
            # Draw Kinematic Chain
            points = self.GetProjectedPoints(
                [point for point, infos in self.KinematicChain])
            
            dc.SetPen(wx.Pen(wx.BLUE))
            
            dc.DrawLines([point[:2] for point in points])
            
            linkages = []
            linkage_idx = 1
            for idx, (point, infos) in enumerate(self.KinematicChain):
                if infos is not None:
                    linkages.append((linkage_idx, points[idx], infos))
                    linkage_idx += 1
                elif idx == 0:
                    linkages.append((0, points[idx], None))
                elif idx == len(self.KinematicChain) - 1:
                    linkages.append((-1, points[idx], None))
            
            # Draw Linkages tooltips    
            #linkages.sort(lambda x, y: cmp(x[1][2], y[1][2]))
            linkages.sort(key=lambda x: x[1][2])
            for idx, point, infos in linkages:
                if idx == 0:
                    dc.SetPen(wx.Pen(wx.BLUE))
                    dc.SetBrush(wx.Brush(wx.BLUE))
                    dc.DrawRectangle(
                        point[0] - SQUARE_SIZE[0] / 2, 
                        point[1] - SQUARE_SIZE[1] / 2, 
                        SQUARE_SIZE[0], SQUARE_SIZE[1])
                elif idx == -1:
                    dc.SetPen(wx.Pen(wx.RED))
                    dc.SetBrush(wx.Brush(wx.RED))
                    dc.DrawCircle(point[0], point[1], CIRCLE_RADIUS)
                else:
                    idx_width, idx_height = dc.GetTextExtent(str(idx))
                    square_width, square_height = idx_width, idx_height
                    
                    icon = GetBitmap(LINKAGE_BITMAPS.get(infos[0]))
                    if icon is not None:
                        square_width += icon.GetWidth()
                        square_height = max(square_height, icon.GetHeight())
                
                    dc.SetPen(wx.Pen(wx.BLUE))
                    dc.SetBrush(wx.Brush(wx.BLUE))
                    dc.DrawCircle(point[0], point[1], CIRCLE_RADIUS)
                    dc.DrawLine(point[0], point[1], point[0] + 10, point[1] + 10)
                    
                    dc.SetBrush(wx.Brush(wx.WHITE))
                    dc.DrawRectangle(point[0] + 10, point[1] + 10, square_width + 4, square_height + 4)
                    dc.DrawText(str(idx), point[0] + 12, point[1] + 12)
                    if icon is not None:
                        dc.DrawBitmap(icon, point[0] + 12 + idx_width, point[1] + 12)
                
        # Draw Axis
        dc.SetPen(wx.BLACK_PEN)
        dc.SetBrush(wx.BLACK_BRUSH)
        dc.SetFont(self.GetFont())
        
        p0 = array([FRAME_BORDER[0], client_size[1] - FRAME_BORDER[1]])
        for num, axis in enumerate(self.Landmark):
            if axis[0] != 0 or axis[1] != 0:
                p1 = array([round(p0[0] + self.AxisSize * axis[0]),
                            round(p0[1] + self.AxisSize * axis[1])])
                dc.DrawLine(p0[0], p0[1], p1[0], p1[1])
                
                normalized_axis = axis / norm(axis)
                DrawArrow(dc, p1, normalized_axis)
                
                label = AXIS_LABELS[num]
                w, h = self.GetTextExtent(label)
                dc.DrawText(label, 
                    round(p0[0] + self.AxisSize * axis[0] + ARROW_SIZE * 2 * normalized_axis[0]) - float(w) / 2., 
                    round(p0[1] + self.AxisSize * axis[1] + ARROW_SIZE * 2 * normalized_axis[1]) - float(h) / 2.)
            
        wx.BufferedPaintDC(self, bitmap)
        event.Skip()


class FoldPanelCaption(wx.lib.buttons.GenBitmapTextToggleButton):
    
    def GetBackgroundBrush(self, dc):
        colBg = self.GetBackgroundColour()
        brush = wx.Brush(colBg, wx.SOLID)
        if self.style & wx.BORDER_NONE:
            myAttr = self.GetDefaultAttributes()
            parAttr = self.GetParent().GetDefaultAttributes()
            myDef = colBg == myAttr.colBg
            parDef = self.GetParent().GetBackgroundColour() == parAttr.colBg
            if myDef and parDef:
                if wx.Platform == "__WXMAC__":
                    brush.MacSetTheme(1) # 1 == kThemeBrushDialogBackgroundActive
                elif wx.Platform == "__WXMSW__":
                    if self.DoEraseBackground(dc):
                        brush = None
            elif myDef and not parDef:
                colBg = self.GetParent().GetBackgroundColour()
                brush = wx.Brush(colBg, wx.SOLID)
        return brush
    
    def DrawLabel(self, dc, width, height, dx=0, dy=0):
        bmp = self.bmpLabel
        if bmp is not None:     # if the bitmap is used
            if self.bmpDisabled and not self.IsEnabled():
                bmp = self.bmpDisabled
            if self.bmpFocus and self.hasFocus:
                bmp = self.bmpFocus
            if self.bmpSelected and not self.up:
                bmp = self.bmpSelected
            bw,bh = bmp.GetWidth(), bmp.GetHeight()
            hasMask = bmp.GetMask() is not None
        else:
            bw = bh = 0     # no bitmap -> size is zero
        
        dc.SetFont(self.GetFont())
        if self.IsEnabled():
            dc.SetTextForeground(self.GetForegroundColour())
        else:
            dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))

        label = self.GetLabel()
        tw, th = dc.GetTextExtent(label)        # size of text
        
        if bmp is not None:
            dc.DrawBitmap(bmp, width - bw - 2, (height-bh)/2, hasMask) # draw bitmap if available
        
        dc.DrawText(label, 2, (height-th)/2)      # draw the text

        dc.SetPen(wx.Pen(self.GetForegroundColour()))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangle(0, 0, width, height)

class LinkagePositionVariableDropTarget(wx.TextDropTarget):
    
    def __init__(self, parent):
        wx.TextDropTarget.__init__(self)
        self.ParentWindow = parent
    
    def OnDropText(self, x, y, data):
        message = None
        try:
            values = eval(data)
        except:
            message = _("Invalid value \"%s\" for debug variable")%data
            values = None
        if not isinstance(values, TupleType):
            message = _("Invalid value \"%s\" for debug variable")%data
            values = None
        if values is not None and values[1] == "debug":
            wx.CallAfter(self.ParentWindow.SetLinkagePositionVariablePath, values[0])
        if message is not None:
            wx.CallAfter(self.ShowMessage, message)
            
    def ShowMessage(self, message):
        dialog = wx.MessageDialog(self.ParentWindow.ParentWindow, message, _("Error"), wx.OK|wx.ICON_ERROR)
        dialog.ShowModal()
        dialog.Destroy()


LANDMARK_VALUES = ["Tx", "Ty", "Tz", "Rx", "Ry", "Rz"]
LINKAGE_TYPES = [
    ("r", _("Revolute around Z")), 
    ("p", _("Prismatic along X"))
]
LINKAGE_BITMAPS = {
    "r": "revolute",
    "p": "prismatic",
} 
LINKAGE_LIMITS = {
    "r": (0., 360.),
    "p": (0., 1000.),
}

class LinkageParamsPanel(wx.BoxSizer, DebugDataConsumer):
    
    def __init__(self, parent, num, window):
        wx.BoxSizer.__init__(self, wx.VERTICAL)
        DebugDataConsumer.__init__(self)
        
        self.FoldButton = FoldPanelCaption(parent, 
              label=_(u"Linkage n°%d") % num, 
              bitmap=GetBitmap("CollapsedIconData"), 
              size=wx.Size(-1, 20), style=wx.NO_BORDER|wx.ALIGN_LEFT)
        self.FoldButton.SetBitmapSelected(GetBitmap("ExpandedIconData"))
        self.FoldButton.SetToggle(False)
        self.FoldButton.Bind(wx.EVT_BUTTON, self.OnFoldButtonClick)
        
        self.AddWindow(self.FoldButton, flag=wx.GROW)
        
        self.ParamsPanel = wx.Panel(parent, style=wx.TAB_TRAVERSAL)
        self.AddWindow(self.ParamsPanel, flag=wx.GROW)
        
        paramspanel_sizer = wx.BoxSizer(wx.VERTICAL)
        
        landmark_staticbox = wx.StaticBox(self.ParamsPanel, 
              label=_("Coordinate system"))
        landmark_sizer = wx.StaticBoxSizer(landmark_staticbox, wx.VERTICAL)
        paramspanel_sizer.AddSizer(landmark_sizer, border=5, flag=wx.ALL|wx.GROW)
        
        landmarkcoords_sizer = wx.FlexGridSizer(cols=3, hgap=5, rows=4, vgap=5)
        for i in xrange(3):
            landmarkcoords_sizer.AddGrowableCol(i)
        landmark_sizer.AddSizer(landmarkcoords_sizer, border=5, 
              flag=wx.GROW|wx.ALL)
        for line in [[("Tx", _("Tx:")), 
                      ("Ty", _("Ty:")),
                      ("Tz", _("Tz:"))], 
                     [("Rx", _("Rx:")), 
                      ("Ry", _("Ry:")),
                      ("Rz", _("Rz:"))]]:
            for name, label in line:
                st = wx.StaticText(self.ParamsPanel, label=label)
                landmarkcoords_sizer.AddWindow(st, flag=wx.ALIGN_CENTER)
            for name, label in line:
                textctrl = wx.TextCtrl(self.ParamsPanel, 
                      style=wx.TE_PROCESS_ENTER|wx.ALIGN_RIGHT)
                callback = self.GetLandmarkChangedFunction(name, textctrl)
                textctrl.Bind(wx.EVT_TEXT_ENTER, callback)
                textctrl.Bind(wx.EVT_KILL_FOCUS, callback)
                setattr(self, name, textctrl)
                landmarkcoords_sizer.AddWindow(textctrl, flag=wx.GROW)
        
        linkagetype_sizer = wx.BoxSizer(wx.HORIZONTAL)
        paramspanel_sizer.AddSizer(linkagetype_sizer, border=5, 
              flag=wx.GROW|wx.LEFT|wx.RIGHT)
        
        linkagetype_label = wx.StaticText(self.ParamsPanel, 
              label=_("Linkage type"))
        linkagetype_sizer.AddWindow(linkagetype_label, border=5, 
              flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL)
        
        self.LinkageType = wx.ComboBox(self.ParamsPanel, 
              style=wx.CB_READONLY)
        for symbol, linkage_type in LINKAGE_TYPES:
            self.LinkageType.Append(linkage_type)
        self.LinkageType.Bind(wx.EVT_COMBOBOX, self.OnLinkageTypeChanged, 
              self.LinkageType)
        linkagetype_sizer.AddWindow(self.LinkageType)
        
        linkageinfos_staticbox = wx.StaticBox(self.ParamsPanel,
              label=_("Linkage limits:"))
        linkageinfos_sizer = wx.StaticBoxSizer(linkageinfos_staticbox, wx.VERTICAL)
        paramspanel_sizer.AddSizer(linkageinfos_sizer, border=5, 
              flag=wx.GROW|wx.TOP|wx.LEFT|wx.RIGHT)
        
        linkagelimits_sizer = wx.BoxSizer(wx.HORIZONTAL)
        linkageinfos_sizer.AddSizer(linkagelimits_sizer, border=5,
              flag=wx.GROW|wx.LEFT|wx.RIGHT|wx.BOTTOM)
        
        for name, label, callback in [("AxisMin", _("Min:"), self.OnLinkageMinChanged), 
                                      ("AxisMax", _("Max:"), self.OnLinkageMaxChanged)]:
            st = wx.StaticText(self.ParamsPanel, label=label)
            linkagelimits_sizer.AddWindow(st, border=5,
                  flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL)
        
            tc = wx.TextCtrl(self.ParamsPanel, 
                  style=wx.TE_PROCESS_ENTER|wx.ALIGN_RIGHT)
            tc.Bind(wx.EVT_TEXT_ENTER, callback)
            tc.Bind(wx.EVT_KILL_FOCUS, callback)
            setattr(self, name, tc)
            linkagelimits_sizer.AddWindow(tc, border=5, flag=wx.RIGHT)
        
        self.ParamsPanel.SetSizer(paramspanel_sizer)
        self.ParamsPanel.Hide()
        
        linkageposition_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.AddSizer(linkageposition_sizer, 1, border=5, flag=wx.GROW|wx.ALL)
        
        linkageposition_label = wx.StaticText(parent, label=_("Position:"))
        linkageposition_sizer.AddWindow(linkageposition_label, border=5, 
              flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL)
        
        self.LinkagePosition = wx.TextCtrl(parent, 
              style=wx.TE_PROCESS_ENTER|wx.ALIGN_RIGHT)
        self.LinkagePosition.Bind(wx.EVT_TEXT_ENTER, self.OnLinkagePositionChanged)
        self.LinkagePosition.Bind(wx.EVT_KILL_FOCUS, self.OnLinkagePositionChanged)
        linkageposition_sizer.AddWindow(self.LinkagePosition, border=5, 
              flag=wx.RIGHT)
        
        self.LinkagePositionVariable = wx.TextCtrl(parent, 
              style=wx.TE_PROCESS_ENTER|wx.ALIGN_RIGHT)
        self.LinkagePositionVariable.SetDropTarget(LinkagePositionVariableDropTarget(self))    
        self.LinkagePositionVariable.Bind(wx.EVT_TEXT_ENTER, self.OnLinkagePositionVariableChanged)
        self.LinkagePositionVariable.Bind(wx.EVT_KILL_FOCUS, self.OnLinkagePositionVariableChanged)
        linkageposition_sizer.AddWindow(self.LinkagePositionVariable, 1, flag=wx.GROW)
        
        linkageslider_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.AddSizer(linkageslider_sizer, border=5, 
              flag=wx.GROW|wx.LEFT|wx.RIGHT|wx.BOTTOM)
        
        self.MinLabel = wx.StaticText(parent, label="")
        linkageslider_sizer.AddWindow(self.MinLabel, border=5, 
              flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL)
        
        self.PositionSlider = wx.Slider(parent)
        self.PositionSlider.Bind(wx.EVT_SCROLL_THUMBTRACK, 
              self.OnPositionSliderChanged, self.PositionSlider)
        linkageslider_sizer.AddWindow(self.PositionSlider, 1, border=5, 
              flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL)
        
        self.MaxLabel = wx.StaticText(parent, label="")
        linkageslider_sizer.AddWindow(self.MaxLabel, flag=wx.ALIGN_CENTER_VERTICAL)
        
        self.ParentWindow = window
        self.Expanded = False
        
        self.Num = num
        self.Values = None

    def SetValues(self, values):
        self.Values = values
        
        for param, value in values["landmark"].iteritems():
            getattr(self, param).ChangeValue(str(value))
        
        self.LinkageType.SetStringSelection(
            dict(LINKAGE_TYPES)[values["linkage"]["type"]])
        
        self.SetLimits(values["linkage"]["limits"])
        
    def GetValues(self):
        landmark = {}
        for param in LANDMARK_VALUES:
            landmark[param] = float(getattr(self, param).GetValue())
        
        linkage = {
            "type": LINKAGE_TYPES[self.LinkageType.GetSelection()][0],
            "limits": (float(self.AxisMin.GetValue()),
                       float(self.AxisMax.GetValue()))}
        return {
            "landmark": landmark,
            "linkage": linkage}

    def SetLimits(self, limits):
        for (param, label), value in zip([("AxisMin", self.MinLabel),
                                          ("AxisMax", self.MaxLabel)], limits):
            getattr(self, param).ChangeValue(str(value))
            label.SetLabel(str(value))
        self.PositionSlider.SetRange(*map(int, limits))
        
        old_position = self.ParentWindow.GetLinkagePosition(self.Num)
        position = max(limits[0], min(old_position, limits[1]))
        self.SetLinkagePosition(position)
        
        if position != old_position:
            return self.ParentWindow.SetLinkagePosition(self.Num, position, False)
    
    def GetLinkagePositionVariablePath(self):
        return self.LinkagePositionVariable.GetValue()

    def SetLinkagePositionVariablePath(self, variable_path):
        self.LinkagePositionVariable.SetValue(variable_path)
        self.SubscribeVariable()

    def SubscribeVariable(self):
        self.ParentWindow.RemoveDataConsumer(self)
        self.ParentWindow.AddDataConsumer(self.GetLinkagePositionVariablePath().upper(), self)
        
    def SetLinkagePosition(self, position):
        self.LinkagePosition.ChangeValue(str(position))
        self.PositionSlider.SetValue(int(position))
    
    def NewValue(self, tick, value, forced=False):
        """
        Function called by debug thread when a new debug value is available
        @param tick: PLC tick when value was captured
        @param value: Value captured
        @param forced: Forced flag, True if value is forced (default: False)
        """
        DebugDataConsumer.NewValue(self, tick, value, forced, raw="LREAL")
    
    def SetForced(self, forced):
        if self.Forced != forced:
            self.Forced = forced
            self.ParentWindow.HasNewData = True
    
    def SetValue(self, value):
        if self.Value != value:
            self.Value = value
            self.ParentWindow.HasNewData = True
    
    def GetValue(self):
        if self.Value is None:
            return 0.
        return self.Value
    
    def ApplyLinkagePositionFromVariable(self):
        if self.Value is not None:
            self.SetLinkagePosition(self.Value)
    
    def GetLandmarkChangedFunction(self, name, textctrl):
        def OnLandmarkChanged(event):
            try:
                value = float(textctrl.GetValue())
            except:
                value = 0.0
            if value != self.Values["landmark"][name]:
                wx.CallAfter(self.ParentWindow.SetLinkage, self.Num, self.GetValues())
            event.Skip()
        return OnLandmarkChanged

    def OnLinkageTypeChanged(self, event):
        value = LINKAGE_TYPES[self.LinkageType.GetSelection()][0]
        if self.Values["linkage"]["type"] != value:
            self.SetLimits(LINKAGE_LIMITS[value])
            wx.CallAfter(self.ParentWindow.SetLinkage, self.Num, self.GetValues())
        event.Skip()

    def OnLinkageMinChanged(self, event):
        value = float(self.AxisMin.GetValue())
        if self.Values["linkage"]["limits"][0] != value:
            self.SetLimits((value, max(value, self.Values["linkage"]["limits"][1])))
            wx.CallAfter(self.ParentWindow.SetLinkage, self.Num, self.GetValues())
        event.Skip()
    
    def OnLinkageMaxChanged(self, event):
        value = float(self.AxisMax.GetValue())
        if self.Values["linkage"]["limits"][1] != value:
            self.SetLimits((min(value, self.Values["linkage"]["limits"][0]), value))
            wx.CallAfter(self.ParentWindow.SetLinkage, self.Num, self.GetValues())
        event.Skip()
    
    def OnLinkagePositionChanged(self, event):
        value = max(self.Values["linkage"]["limits"][0],
                min(float(self.LinkagePosition.GetValue()),
                    self.Values["linkage"]["limits"][1]))
        old_value = self.ParentWindow.GetLinkagePosition(self.Num)
        if old_value != value:
            self.LinkagePosition.ChangeValue(str(value))
            self.PositionSlider.SetValue(int(value))
            wx.CallAfter(self.ParentWindow.SetLinkagePosition, self.Num, value)
        event.Skip()
    
    def OnLinkagePositionVariableChanged(self, event):
        wx.CallAfter(self.SubscribeVariable)
        event.Skip()
    
    def OnPositionSliderChanged(self, event):
        value = float(self.PositionSlider.GetValue())
        old_value = self.ParentWindow.GetLinkagePosition(self.Num)
        if old_value != value:
            self.LinkagePosition.ChangeValue(str(value))
            wx.CallAfter(self.ParentWindow.SetLinkagePosition, self.Num, value)
        event.Skip()
    
    def OnFoldButtonClick(self, event):
        self.Expanded = not self.Expanded
        self.FoldButton.SetToggle(self.Expanded)
        if self.Expanded:
            self.ParamsPanel.Show()
        else:
            self.ParamsPanel.Hide()
        self.ParentWindow.RefreshParamsPanelLayout()

LANDMARKS = [
    array([[0., 0., 1.], [1., 0., 0.], [0., -1., 0.]]),
    array([[1., 0., 0.], [0., 0., -1.], [0., -1., 0.]]),
    array([[1., 0., 0.], [math.sqrt(2.) / 4., -math.sqrt(2.) / 4., -math.sqrt(2.) / 4.], [0., -1., 0.]]),
    array([[1., 0., 0.], [0., -1., 0.], [0., 0., 1.]])]
ZOOM_VALUES = [math.sqrt(2) ** i for i in xrange(4, -9, -1)]
VOLUME_LINKAGE_POINTS_NUMBER = 10

def GetPointAbsoluteCoords(landmark_center, landmark_axis, point_coords):
    return landmark_center + array(
        landmark_axis * point_coords.reshape([3, 1])
    ).reshape([1, 3])[0]

def GetEulerAnglesMatrix(angles):
    rcos = [math.cos(angle / 180. * math.pi) for angle in angles]
    rsin = [math.sin(angle / 180. * math.pi) for angle in angles]
    return matrix(
        [[rcos[1] * rcos[2],
          rsin[0] * rsin[1] * rcos[2] - rcos[0] * rsin[2],
          rcos[0] * rsin[1] * rcos[2] + rsin[0] * rsin[2]],
         [rcos[1] * rsin[2],
          rsin[0] * rsin[1] * rsin[2] + rcos[0] * rcos[2],
          rcos[0] * rsin[1] * rsin[2] - rsin[0] * rcos[2]],
         [-rsin[1],
          rsin[0] * rcos[1],
          rcos[0] * rcos[1]]])

def UpdateLandmark(landmark_infos, landmark_center, landmark_axis):
    return (
        GetPointAbsoluteCoords(
            landmark_center, landmark_axis,
            array([landmark_infos[param] for param in LANDMARK_VALUES[:3]])),

        landmark_axis * GetEulerAnglesMatrix(
            [landmark_infos[param] for param in LANDMARK_VALUES[3:]])
    )

def GetEdges(nb_linkages, var_available=True):
    if nb_linkages == 0:
        return []
    
    if nb_linkages == 1:
        if var_available:
            return [["var"]]
        else:
            return [["min"], ["max"]]
    
    values = ["min", "max"]
    if var_available:
        values.append("var")
    edges = []
    for value in values:
        edges.extend([[value] + edge for edge in 
                      GetEdges(nb_linkages - 1,
                               var_available and value != "var")])
    return edges

SCROLLBAR_UNIT = 10

class KinematicEditor(EditorPanel, DebugViewer):
    
    def _init_Editor(self, parent):
        self.Editor = wx.SplitterWindow(parent)
        self.Editor.SetSashGravity(1.0)
        
        self.ProjectionsPanel = wx.Panel(self.Editor)
        self.Projections = []
        
        projections_sizer = wx.BoxSizer(wx.VERTICAL)
        
        if USE_MPL:
            self.Projection3DFigure = matplotlib.figure.Figure()
            self.Projection3DFigure.subplotpars.update(left=0.0, right=1.0, bottom=0.0, top=1.0)
            
            self.Projection3DCanvas = FigureCanvas(self.ProjectionsPanel, -1, self.Projection3DFigure)
            self.Projection3DCanvas.SetMinSize(wx.Size(1, 1))
            projections_sizer.AddWindow(self.Projection3DCanvas, 1, border=5, flag=wx.GROW|wx.ALL)
            
            self.LastMotionTime = gettime()
            self.Projection3DAxes = self.Projection3DFigure.gca(projection='3d')
            self.Projection3DAxes.set_color_cycle(['b'])
            setattr(self.Projection3DAxes, "_on_move", self.OnProjection3DMotion)
            
            self.Projection3DAxes.mouse_init()
            
        else:
            projections_grid = wx.GridSizer(cols=2, hgap=5, rows=2, vgap=5)
            projections_sizer.AddSizer(projections_grid, 1, border=5, 
                                       flag=wx.GROW|wx.ALL)
        
            for landmark in LANDMARKS:
                projection = KinematicProjection(self.ProjectionsPanel, 
                      landmark, self)
                self.Projections.append(projection)
                projections_grid.AddWindow(projection, flag=wx.GROW)
            
        self.ProjectionsPanel.SetSizer(projections_sizer)
        
        self.LinkagesPanel = wx.ScrolledWindow(self.Editor, 
              style=wx.VSCROLL)
        self.LinkagesPanel.SetScrollRate(0, SCROLLBAR_UNIT)
        
        self.LinkagesSizer = wx.BoxSizer(wx.VERTICAL)
        
        linkagesheader_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.LinkagesSizer.AddSizer(linkagesheader_sizer, border=5, 
              flag=wx.ALL|wx.GROW)
        
        linkages_label = wx.StaticText(self.LinkagesPanel, 
              label=_("Linkages:"))
        linkagesheader_sizer.AddWindow(linkages_label, 1,
              flag=wx.ALIGN_BOTTOM)
        
        for name, bitmap, help in [
                ("AddButton", "add_element", _("Append linkage")),
                ("DeleteButton", "remove_element", _("Remove last linkage"))]:
            button = wx.lib.buttons.GenBitmapButton(self.LinkagesPanel, 
                  bitmap=GetBitmap(bitmap), 
                  size=wx.Size(28, 28), style=wx.NO_BORDER)
            button.SetToolTipString(help)
            self.Bind(wx.EVT_BUTTON, getattr(self, "On" + name), button)
            setattr(self, name, button)
            linkagesheader_sizer.AddWindow(button, border=5, flag=wx.LEFT)
        
        self.ToolTipFoldButton = FoldPanelCaption(self.LinkagesPanel, 
              label=_("Tool Centre Point"), 
              bitmap=GetBitmap("CollapsedIconData"), 
              size=wx.Size(-1, 20), style=wx.NO_BORDER|wx.ALIGN_LEFT)
        self.ToolTipFoldButton.SetBitmapSelected(GetBitmap("ExpandedIconData"))
        self.ToolTipFoldButton.SetToggle(False)
        self.ToolTipFoldButton.Bind(wx.EVT_BUTTON, self.OnToolTipFoldButtonClick)
        
        self.LinkagesSizer.AddWindow(self.ToolTipFoldButton, flag=wx.GROW)
        
        self.ToolTipPanel = wx.Panel(self.LinkagesPanel, style=wx.TAB_TRAVERSAL)
        self.LinkagesSizer.AddWindow(self.ToolTipPanel, border=5, 
              flag=wx.GROW|wx.ALL)
        
        tooltip_staticbox = wx.StaticBox(self.ToolTipPanel, 
              label=_("Position"))
        tooltip_sizer = wx.StaticBoxSizer(tooltip_staticbox, wx.VERTICAL)
        
        tooltipcoords_sizer = wx.FlexGridSizer(cols=3, hgap=5, rows=4, vgap=5)
        for i in xrange(3):
            tooltipcoords_sizer.AddGrowableCol(i)
        tooltip_sizer.AddSizer(tooltipcoords_sizer, border=5, 
              flag=wx.GROW|wx.ALL)
        for line in [[("Tx", _("X:")), 
                      ("Ty", _("Y:")),
                      ("Tz", _("Z:"))]]:
            for name, label in line:
                st = wx.StaticText(self.ToolTipPanel, label=label)
                tooltipcoords_sizer.AddWindow(st, flag=wx.ALIGN_CENTER)
            for name, label in line:
                textctrl = wx.TextCtrl(self.ToolTipPanel, 
                      style=wx.TE_PROCESS_ENTER|wx.ALIGN_RIGHT)
                callback = self.GetToolTipChangedFunction(name, textctrl)
                textctrl.Bind(wx.EVT_TEXT_ENTER, callback)
                textctrl.Bind(wx.EVT_KILL_FOCUS, callback)
                setattr(self, name, textctrl)
                tooltipcoords_sizer.AddWindow(textctrl, flag=wx.GROW)
        
        self.ToolTipPanel.SetSizer(tooltip_sizer)
        self.ToolTipPanel.Hide()
        
        self.LinkagesPanel.SetSizer(self.LinkagesSizer)
        
        self.Editor.SplitVertically(self.ProjectionsPanel, self.LinkagesPanel, -300)
    
    def __init__(self, parent, controller, tagname, window):
        EditorPanel.__init__(self, parent, tagname, window, controller)
        DebugViewer.__init__(self, None, True)
        
        self.FilePath = tagname.split("::")[0]
        
        self.LinkageParamsPanels = []
        self.ToolTipExpanded = False
        self.CurrentZoom = ZOOM_VALUES.index(1.0)
        
        self.Load()
        
        self.HasNewData = False
        self.Changed = False
    
    def __del__(self):
        self.Controler.OnCloseEditor(self)
    
    def Load(self):
        csvfile = open(self.FilePath, "rb")
        sample = csvfile.read(1024)
        csvfile.seek(0)
        dialect = csv.Sniffer().sniff(sample)
        has_header = csv.Sniffer().has_header(sample)
        reader = csv.reader(csvfile, dialect)
        self.Linkages = []
        self.LinkagePositions = []
        self.ToolTipValues = dict([(param, 0.) for param in LANDMARK_VALUES[:3]])
        try:
            for row in reader:
                if has_header:
                    has_header = False
                else:
                    num = int(row[0])
                    if num == len(self.Linkages) + 1:
                        landmark = dict(
                            zip(LANDMARK_VALUES, map(float,row[1:7])))
                        linkage = {"type": row[7]}
                        if len(row) > 8:
                            linkage["limits"] = tuple(map(float, row[8:10]))
                        else:
                            linkage["limits"] = LINKAGE_LIMITS[linkage["type"]]
                        self.Linkages.append({"landmark": landmark,
                                              "linkage": linkage})
                        self.LinkagePositions.append(linkage["limits"][0])
                    elif num == -1:
                        self.ToolTipValues = dict(
                            zip(LANDMARK_VALUES[:3], map(float,row[1:4])))
        except:
            self.Linkages = []
            self.LinkagePositions = []
            self.ToolTipValues = dict([(param, 0.) for param in LANDMARK_VALUES[:3]])
        self.ResetToolCentrePointEnvelop()
        self.ResetScreenCenter()
        self.RefreshView()
    
    def CheckSaveBeforeClosing(self):
        if self.Changed:
            dialog = wx.MessageDialog(self, 
                _("There are changes in file %s.\nDo you want to save?") % os.path.split(self.FilePath)[1], 
                _("Close Kinematic Editor"), wx.YES_NO|wx.CANCEL|wx.ICON_QUESTION)
            answer = dialog.ShowModal()
            dialog.Destroy()
            if answer == wx.ID_YES:
                self.Save()
            elif answer == wx.ID_CANCEL:
                return False
        return True
    
    def Save(self):
        csvfile = open(self.FilePath, 'wb')
        writer = csv.writer(csvfile, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Num"] + LANDMARK_VALUES + ["Type", "Min", "Max"])
        for idx, linkage in enumerate(self.Linkages):
            writer.writerow([idx + 1] + 
                [linkage["landmark"][param] for param in LANDMARK_VALUES] +
                [linkage["linkage"][param] for param in ["type"]] +
                list(linkage["linkage"]["limits"]))
        writer.writerow([-1] + 
                [self.ToolTipValues[param] for param in LANDMARK_VALUES[:3]] + 
                [''] * (len(LANDMARK_VALUES)))
        csvfile.close()
        
        self.Changed = False
        self.ParentWindow.RefreshFileMenu()
        self.ParentWindow.RefreshPageTitles()
    
    def GetTitle(self):
        title = os.path.split(self.FilePath)[1]
        if self.Changed:
            return "~%s~" % title
        return title
        
    def GetFilePath(self):
        return self.FilePath
    
    def GetInstancePath(self):
        return self.GetFilePath()
    
    def MarkAsChanged(self):
        if not self.Changed:
            self.Changed = True
            self.ParentWindow.RefreshFileMenu()
            self.ParentWindow.RefreshPageTitles()

    def IsModified(self):
        return self.Changed

    def SetScreenCenter(self, center):
        self.ScreenCenter = center
        for projection in self.Projections:
            projection.SetScreenCenter(center)

    def GetLinkagePosition(self, num):
        return self.LinkagePositions[num - 1]
        
    def SetLinkagePosition(self, num, position, refresh=True):
        self.LinkagePositions[num - 1] = position
        if refresh:
            self.RefreshKinematicChain()
    
    def SetLinkage(self, num, values):
        self.Linkages[num - 1] = values
        self.ResetToolCentrePointEnvelop()
        self.ResetScreenCenter()
        self.RefreshView()
        self.MarkAsChanged()
    
    def ChangeZoom(self, incr):
        new_zoom = max(0, min(self.CurrentZoom - incr, len(ZOOM_VALUES) - 1))
        if new_zoom != self.CurrentZoom:
            self.CurrentZoom = new_zoom
            zoom = ZOOM_VALUES[self.CurrentZoom]
            if self.DistanceMax != 0:
                zoom /= self.DistanceMax
            for projection in self.Projections:
                projection.SetZoom(zoom)
    
    def RefreshParamsPanelLayout(self):
        self.LinkagesSizer.Layout()
        self.RefreshLinkagesPanelScrollbars()
    
    def ResetScreenCenter(self):
        landmark_matrix = matrix([[1., 0., 0.],
                                  [0., 1., 0.],
                                  [0., 0., 1.]])
        points = [array([0., 0., 0.])]
        for linkage in self.Linkages:
            landmark = linkage["landmark"]
            
            points.append(GetPointAbsoluteCoords(
                points[-1], landmark_matrix,
                array([landmark[param] for param in LANDMARK_VALUES[:3]])))
            
            landmark_matrix = landmark_matrix * GetEulerAnglesMatrix(
                [landmark[param] for param in LANDMARK_VALUES[3:]])
        
        points.append(
            GetPointAbsoluteCoords(points[-1], landmark_matrix,
                array([self.ToolTipValues[param] for param in LANDMARK_VALUES[:3]])))
        points.extend(self.ToolCentrePointEnvelop[1])
        ranges = [(min(values), max(values)) for values in zip(*points)]
        
        self.ScreenCenter = array([(v_min + v_max) / 2 for (v_min, v_max) in ranges])
        self.DistanceMax = max([norm(point - self.ScreenCenter) for point in points])
    
    def GetEdgePoints(self, edge, num=0, landmark_matrix=None, current_point=None):
        if landmark_matrix is None:
            landmark_matrix = matrix([[1., 0., 0.],
                                      [0., 1., 0.],
                                      [0., 0., 1.]])
        if current_point is None:
            current_point = array([0., 0., 0.])
        
        if len(edge) == 0:
            return [GetPointAbsoluteCoords(
                current_point, landmark_matrix,
                array([self.ToolTipValues[param] for param in LANDMARK_VALUES[:3]]))]
        
        current_point, landmark_matrix = UpdateLandmark(
            self.Linkages[num]["landmark"], current_point, landmark_matrix)
        
        linkage = self.Linkages[num]["linkage"]
        
        if edge[0] == "var":
            if linkage["type"] == "r":
                start_angle, end_angle = linkage["limits"]
                range = end_angle - start_angle
                nb_point = max(5, int(range) / 5)
                incr = range / float(nb_point)
                points = []
                for i in xrange(nb_point + 1):
                    angle = start_angle + i * incr
                    cosr = math.cos(float(angle) / 180. * math.pi)
                    sinr = math.sin(float(angle) / 180. * math.pi)
                    rotation = matrix([[cosr, -sinr, 0.],
                                       [sinr, cosr, 0.],
                                       [0., 0., 1.]])
                    points.append(
                        self.GetEdgePoints(edge[1:], num + 1, 
                            landmark_matrix * rotation, current_point))
                return points
            else:
                return [
                    self.GetEdgePoints(edge[1:], num + 1, landmark_matrix, 
                        GetPointAbsoluteCoords(current_point, landmark_matrix, 
                                               array([position, 0., 0.])))
                    for position in linkage["limits"]]
        else:
            if edge[0] == "min":
                position = linkage["limits"][0]
            else:
                position = linkage["limits"][1]
                
            if linkage["type"] == "r":
                cosr = math.cos(float(position) / 180. * math.pi)
                sinr = math.sin(float(position) / 180. * math.pi)
                landmark_matrix = landmark_matrix * matrix([[cosr, -sinr, 0.],
                                                            [sinr, cosr, 0.],
                                                            [0., 0., 1.]])
            else:
                current_point = GetPointAbsoluteCoords(
                    current_point, landmark_matrix, array([position, 0., 0.]))
            
            return self.GetEdgePoints(edge[1:], num + 1, landmark_matrix, current_point)
    
    def GetVolumePoints(self, num=0, landmark_matrix=None, current_point=None):
        if landmark_matrix is None:
            landmark_matrix = matrix([[1., 0., 0.],
                                      [0., 1., 0.],
                                      [0., 0., 1.]])
        if current_point is None:
            current_point = array([0., 0., 0.])
            
        if num == len(self.Linkages):
            return [GetPointAbsoluteCoords(
                current_point, landmark_matrix,
                array([self.ToolTipValues[param] for param in LANDMARK_VALUES[:3]]))]
    
        current_point, landmark_matrix = UpdateLandmark(
            self.Linkages[num]["landmark"], current_point, landmark_matrix)
        
        linkage = self.Linkages[num]["linkage"]
        start_position, end_position = linkage["limits"]
        incr = (end_position - start_position) / float(VOLUME_LINKAGE_POINTS_NUMBER)
        points = []
        
        for i in xrange(VOLUME_LINKAGE_POINTS_NUMBER + 1):
            position = start_position + i * incr
            
            if linkage["type"] == "r":
                cosr = math.cos(float(position) / 180. * math.pi)
                sinr = math.sin(float(position) / 180. * math.pi)
                rotation = matrix([[cosr, -sinr, 0.],
                                   [sinr, cosr, 0.],
                                   [0., 0., 1.]])
                points.extend(self.GetVolumePoints(num + 1, 
                    landmark_matrix * rotation, current_point))
    
            else:
                points.extend(self.GetVolumePoints(num + 1,
                    landmark_matrix, GetPointAbsoluteCoords(
                        current_point, landmark_matrix, array([position, 0., 0.]))))
        return points
    
    def ResetToolCentrePointEnvelop(self):
        nb_linkages = len(self.Linkages)
        if nb_linkages > 0:
            edges = GetEdges(nb_linkages)
        else:
            edges = []
        
        if len(self.Linkages) <= 3:
            self.ToolCentrePointEnvelop = (
                [self.GetEdgePoints(edge) for edge in GetEdges(len(self.Linkages))],
                self.GetVolumePoints())
        else:
            self.ToolCentrePointEnvelop = ([], [array([0., 0., 0.])])
    
    def SubscribeAllDataConsumers(self):
        DebugViewer.SubscribeAllDataConsumers(self)
        
        for idx, linkage in enumerate(self.Linkages):
            if len(self.LinkageParamsPanels) > idx:
                self.LinkageParamsPanels[idx].SubscribeVariable()
    
    def RefreshNewData(self):
        if self.HasNewData:
            self.HasNewData = False
            for idx, linkage in enumerate(self.Linkages):
                if len(self.LinkageParamsPanels) > idx:
                    self.LinkagePositions[idx] = self.LinkageParamsPanels[idx].GetValue()
                    self.LinkageParamsPanels[idx].ApplyLinkagePositionFromVariable()
            self.RefreshKinematicChain()
        DebugViewer.RefreshNewData(self)
    
    def RefreshKinematicChain(self):
        landmark_matrix = matrix([[1., 0., 0.],
                                  [0., 1., 0.],
                                  [0., 0., 1.]])
        current_point = array([0., 0., 0.])
        self.KinematicChain = [(current_point, None)]
        
        for linkage_idx, linkage in enumerate(self.Linkages):
            current_point, landmark_matrix = UpdateLandmark(
                linkage["landmark"], current_point, landmark_matrix)
            
            if linkage["linkage"]["type"] == "r":
                end_point = array([self.DistanceMax / 5., 0., 0.])
                move = []
                start_angle, end_angle = linkage["linkage"]["limits"]
                range = end_angle - start_angle
                nb_point = max(5, int(range) / 5)
                incr = range / float(nb_point)
                for i in xrange(nb_point + 1):
                    angle = start_angle + i * incr
                    cosr = math.cos(float(angle) / 180. * math.pi)
                    sinr = math.sin(float(angle) / 180. * math.pi)
                    rotation = matrix([[cosr, -sinr, 0.],
                                       [sinr, cosr, 0.],
                                       [0., 0., 1.]])
                    move.append(GetPointAbsoluteCoords(
                        current_point, landmark_matrix * rotation, end_point))
                
                decorations = []
                for angle in linkage["linkage"]["limits"]:
                    cosr = math.cos(float(angle) / 180. * math.pi)
                    sinr = math.sin(float(angle) / 180. * math.pi)
                    rotation = matrix([[cosr, -sinr, 0.],
                                       [sinr, cosr, 0.],
                                       [0., 0., 1.]])
                    decorations.append([
                        current_point, 
                        GetPointAbsoluteCoords(
                            current_point, landmark_matrix * rotation, end_point * 1.1)])
            else:
#                move = map(lambda x: GetPointAbsoluteCoords(
#                                current_point, landmark_matrix, array([x, 0, 0])),
#                           linkage["linkage"]["limits"])
#                decorations = None
                move = list(map(lambda x: GetPointAbsoluteCoords(
                                current_point, landmark_matrix, array([x, 0, 0])),
                linkage["linkage"]["limits"]))
                decorations = None

            
            self.KinematicChain.append((current_point, (linkage["linkage"]["type"], move, decorations)))
            
            position = self.LinkagePositions[linkage_idx]
            translation = None
            rotation = None
            if linkage["linkage"]["type"] == "r":
                cosr = math.cos(position / 180. * math.pi)
                sinr = math.sin(position / 180. * math.pi)
                rotation = matrix([[cosr, -sinr, 0.],
                                   [sinr, cosr, 0.],
                                   [0., 0., 1.]])
                
            elif linkage["linkage"]["type"] == "p":
                translation = array([position, 0., 0.])
                
            if translation is not None:
                current_point = GetPointAbsoluteCoords(
                    current_point, landmark_matrix, translation)
                self.KinematicChain.append((current_point, None))
            
            if rotation is not None:
                landmark_matrix = landmark_matrix * rotation
                
        self.KinematicChain.append((
            GetPointAbsoluteCoords(current_point, landmark_matrix,
                array([self.ToolTipValues[param] for param in LANDMARK_VALUES[:3]])),
            None))
        
        if USE_MPL:
            while len(self.Projection3DAxes.lines) > 0:
                self.Projection3DAxes.lines.pop()
            while len(self.Projection3DAxes.collections) > 0:
                self.Projection3DAxes.collections.pop()
            
            chain_points = array([point for point, infos in self.KinematicChain])
            self.Projection3DAxes.plot(
                chain_points[:, 0], 
                chain_points[:, 1], 
                zs=chain_points[:, 2])
            
            linkages = []
            linkage_idx = 1
            for idx, (point, infos) in enumerate(self.KinematicChain):
                if infos is not None:
                    linkages.append((linkage_idx, chain_points[idx], infos))
                    linkage_idx += 1
                elif idx == 0:
                    linkages.append((0, chain_points[idx], None))
                elif idx == len(self.KinematicChain) - 1:
                    linkages.append((-1, chain_points[idx], None))
            
            linkages_points = array([point for idx, point, infos in linkages])
            for points, color, marker in [(linkages_points[:1], 'b', 's'),
                                          (linkages_points[1:-1], 'b', 'o'),
                                          (linkages_points[-1:], 'r', 'o')]:
                self.Projection3DAxes.scatter(
                    points[:, 0], points[:, 1], zs=points[:, 2],
                    c=color, marker=marker)
            
            coords_limits = [
                (coords[argmin(coords)], coords[argmax(coords)])
                for coords in [chain_points[:, 0], 
                               chain_points[:, 1],
                               chain_points[:, 2]]]
            max_range = 0
            for coord_min, coord_max in coords_limits:
                max_range = max(max_range, coord_max - coord_min)
            
            for coord_center, func in zip(
                    self.ScreenCenter,
                    [self.Projection3DAxes.set_xlim3d,
                     self.Projection3DAxes.set_ylim3d,
                     self.Projection3DAxes.set_zlim3d]):
                func(coord_center - self.DistanceMax,
                     coord_center + self.DistanceMax)
            
            self.Projection3DCanvas.draw()
            
        else:
            zoom = ZOOM_VALUES[self.CurrentZoom]
            if self.DistanceMax != 0:
                zoom /= self.DistanceMax
            for projection in self.Projections:
                projection.SetKinematicChain(
                    self.KinematicChain,
                    self.ToolCentrePointEnvelop, 
                    self.ScreenCenter,
                    zoom)
        
    def RefreshLinkagesPanel(self):
        for idx, linkage in enumerate(self.Linkages):
            if len(self.LinkageParamsPanels) <= idx:
                panel = LinkageParamsPanel(self.LinkagesPanel, idx + 1, self)
                self.LinkagesSizer.InsertSizer(idx + 1, panel, flag=wx.GROW)
                self.LinkageParamsPanels.append(panel)
            else:
                panel = self.LinkageParamsPanels[idx]
            panel.SetValues(linkage)
    
        for idx in xrange(len(self.Linkages), len(self.LinkageParamsPanels)):
            panel = self.LinkageParamsPanels.pop(idx)
            panel.Clear(True)
            self.LinkagesSizer.Remove(panel)
        
        self.LinkagesSizer.Layout()
        self.RefreshLinkagesPanelScrollbars()
        
        self.AddButton.Enable(len(self.Linkages) < MAX_LINKAGE)
        self.DeleteButton.Enable(len(self.Linkages) > 0)
    
        for param, value in self.ToolTipValues.iteritems():
            getattr(self, param).ChangeValue(str(value)) 
    
    def RefreshView(self):
        self.RefreshLinkagesPanel()
        self.RefreshKinematicChain()
        
    def OnAddButton(self, event):
        if len(self.Linkages) < MAX_LINKAGE:
            values = {
                "landmark": dict([(param, 0.) for param in LANDMARK_VALUES]),
                "linkage": {"type": "r", "axis": "X", "limits": LINKAGE_LIMITS["r"]}}
            self.Linkages.append(values)
            self.LinkagePositions.append(values["linkage"]["limits"][0])
            self.ResetToolCentrePointEnvelop()
            self.RefreshView()
            self.MarkAsChanged()
        event.Skip()

    def OnDeleteButton(self, event):
        if len(self.Linkages) > 0:
            self.Linkages.pop(-1)
            self.LinkagePositions.pop(-1)
            self.ResetToolCentrePointEnvelop()
            self.RefreshView()
            self.MarkAsChanged()
        event.Skip()

    def GetToolTipChangedFunction(self, name, textctrl):
        def OnToolTipChanged(event):
            try:
                value = float(textctrl.GetValue())
            except:
                value = 0.0
            if value != self.ToolTipValues[name]:
                self.ToolTipValues[name] = value
                self.ResetToolCentrePointEnvelop()
                self.MarkAsChanged()
                wx.CallAfter(self.RefreshView)
            event.Skip()
        return OnToolTipChanged
    
    def OnToolTipFoldButtonClick(self, event):
        self.ToolTipExpanded = not self.ToolTipExpanded
        self.ToolTipFoldButton.SetToggle(self.ToolTipExpanded)
        if self.ToolTipExpanded:
            self.ToolTipPanel.Show()
        else:
            self.ToolTipPanel.Hide()
        self.LinkagesSizer.Layout()
        self.RefreshLinkagesPanelScrollbars()

    def OnProjection3DMotion(self, event):
        current_time = gettime()
        if current_time - self.LastMotionTime > REFRESH_PERIOD:
            self.LastMotionTime = current_time
            Axes3D._on_move(self.Projection3DAxes, event)

    def RefreshLinkagesPanelScrollbars(self):
        xstart, ystart = self.LinkagesPanel.GetViewStart()
        window_size = self.LinkagesPanel.GetClientSize()
        vwidth, vheight = self.LinkagesSizer.GetMinSize()
        posx = max(0, min(xstart, (vwidth - window_size[0]) / SCROLLBAR_UNIT))
        posy = max(0, min(ystart, (vheight - window_size[1]) / SCROLLBAR_UNIT))
        self.LinkagesPanel.Scroll(posx, posy)
        self.LinkagesPanel.SetScrollbars(SCROLLBAR_UNIT, SCROLLBAR_UNIT, 
                vwidth / SCROLLBAR_UNIT, vheight / SCROLLBAR_UNIT, posx, posy)
