
import os
import numpy
import math
import csv

import wx
import wx.lib.plot as plot

from editors.EditorPanel import EditorPanel

ZOOM_VALUES = [math.sqrt(2) ** i for i in xrange(4, -9, -1)]

class CamEditor(EditorPanel):
    
    def _init_Editor(self, parent):
        self.Editor = wx.Panel(parent)
        
        self.KeyReceiver = wx.TextCtrl(self.Editor)
        self.KeyReceiver.Hide()
        self.KeyReceiver.Bind(wx.EVT_CHAR, self.OnChar)
        
        self.MainSizer = wx.BoxSizer(wx.VERTICAL)
        
        self.Canvas = plot.PlotCanvas(self.Editor, name='Canvas')
        self.Canvas.canvas.Bind(wx.EVT_LEFT_DOWN, self.OnCanvasLeftDown)
        self.Canvas.canvas.Bind(wx.EVT_LEFT_UP, self.OnCanvasLeftUp)
        self.Canvas.canvas.Bind(wx.EVT_MIDDLE_DOWN, self.OnCanvasMiddleDown)
        self.Canvas.canvas.Bind(wx.EVT_MIDDLE_UP, self.OnCanvasMiddleUp)
        self.Canvas.canvas.Bind(wx.EVT_MOTION, self.OnCanvasMotion)
        self.Canvas.canvas.Bind(wx.EVT_LEFT_DCLICK, self.OnCanvasLeftDClick)
        
        self.MainSizer.AddWindow(self.Canvas, 1, flag=wx.GROW)
        
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.MainSizer.AddSizer(controls_sizer, border=5, flag=wx.ALIGN_CENTER|wx.ALL)
        
        self.XAxisLabel = wx.StaticText(self.Editor, label="X axis:")
        controls_sizer.AddWindow(self.XAxisLabel, border=5, 
              flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT)
        
        self.XAxisValue = wx.TextCtrl(self.Editor, 
              size=wx.Size(150, -1), style=wx.TE_PROCESS_ENTER)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnXAxisValueChanged, 
              self.XAxisValue)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnXAxisValueChanged, 
              self.XAxisValue)
        controls_sizer.AddWindow(self.XAxisValue, border=5, flag=wx.RIGHT)

        self.YAxisLabel = wx.StaticText(self.Editor, label="Y axis:")
        controls_sizer.AddWindow(self.YAxisLabel, border=5, 
              flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT)
        
        self.YAxisValue = wx.TextCtrl(self.Editor, 
              size=wx.Size(150, -1), style=wx.TE_PROCESS_ENTER)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnYAxisValueChanged, 
              self.YAxisValue)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnYAxisValueChanged, 
              self.YAxisValue)
        controls_sizer.AddWindow(self.YAxisValue, border=5, flag=wx.RIGHT)
        
        self.Editor.SetSizer(self.MainSizer)
        
        self.Editor.Bind(wx.EVT_MOUSEWHEEL, self.OnCanvasMouseWheel)
        
    def __init__(self, parent, controller, tagname, window):
        EditorPanel.__init__(self, parent, tagname, window, controller)
        
        self.FilePath = tagname.split("::")[0]
        self.Headers = ("Master", "Slave")
        self.SelectedPoint = None    
        self.Changed = False
        
        self.CurrentZoom = ZOOM_VALUES.index(1.0)
        self.StartPos = None
        self.MouseOldPos = None
        
        self.Load()
        
        self.CurrentCursor = wx.StockCursor(wx.CURSOR_CROSS)
        self.KeyReceiver.SetFocus()
    
    def __del__(self):
        self.Controler.OnCloseEditor(self)
    
    def GetTitle(self):
        title = os.path.split(self.FilePath)[1]
        if self.Changed:
            return "~%s~" % title
        return title
    
    def GetFilePath(self):
        return self.FilePath
    
    def MarkAsChanged(self):
        if not self.Changed:
            self.Changed = True
            self.ParentWindow.RefreshFileMenu()
            self.ParentWindow.RefreshPageTitles()
    
    def IsModified(self):
        return self.Changed
    
    def Load(self):
        csvfile = open(self.FilePath, "rb")
        sample = csvfile.read(1024)
        csvfile.seek(0)
        dialect = csv.Sniffer().sniff(sample)
        has_header = csv.Sniffer().has_header(sample)
        reader = csv.reader(csvfile, dialect)
        self.Points = []
        limits = None
        try:
            for row in reader:
                if has_header:
                    has_header = False
                    self.Headers = row
                    if len(self.Headers) != 2:
                        break
                else:
                    point = tuple(map(float,row))
                    if limits is None:
                        limits = (
                            (point[0], point[0]),
                            (point[1], point[1]))
                    else:
                        limits = (
                            (min(point[0], limits[0][0]),
                             max(point[0], limits[0][1])),
                            (min(point[1], limits[1][0]),
                             max(point[1], limits[1][1])))
                    self.Points.append(point)
            if len(self.Points) == 0 or len(self.Points[0]) != 2:
                self.Points = []
                limits = None
        except:
            self.Points = []
            limits = None
        if limits is not None:
            self.PointsRange = (
                limits[0][1] - limits[0][0],
                limits[1][1] - limits[1][0])
            self.ScreenMiddle = (
                (limits[0][0] + limits[0][1]) / 2,
                (limits[1][0] + limits[1][1]) / 2)
        else:
            self.PointsRange = None
            self.ScreenMiddle = None
        for st, label in zip([self.XAxisLabel, self.YAxisLabel],
                             self.Headers):
            st.SetLabel("%s:" % label)
        self.RefreshGraph()
    
    def CheckSaveBeforeClosing(self):
        if self.Changed:
            dialog = wx.MessageDialog(self, 
                _("There are changes in file %s.\nDo you want to save?") % os.path.split(self.FilePath)[1], 
                _("Close Cam Editor"), wx.YES_NO|wx.CANCEL|wx.ICON_QUESTION)
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
        writer.writerow(["Master", "Slave"])
        for point in self.Points:
            writer.writerow(point)
        csvfile.close()
        
        self.Changed = False
        self.ParentWindow.RefreshFileMenu()
        self.ParentWindow.RefreshPageTitles()
    
    def SaveAs(self):
        self.Save()
    
    def GetPoint(self, event):
        if self.PointsGraph is not None:
            mouse = event.GetPosition()
            result = self.PointsGraph.getClosestPoint(self.Canvas._getXY(event), False)
            point = self.Canvas.PositionUserToScreen(result[1])
            if abs(point[0] - mouse[0]) < 5 and abs(point[1] - mouse[1]) < 5:
                return result[0]
        return None
    
    def RefreshGraph(self):
        if len(self.Points) > 0:
            graph = numpy.array(self.Points)
            polyline = plot.PolyLine(graph, legend='Test', colour='blue')
            self.PointsGraph = plot.PolyMarker(
                graph, colour='blue', marker='square', fillstyle=wx.TRANSPARENT)
            
            graphs = [polyline, self.PointsGraph]
            if self.SelectedPoint is not None:
                graphs.append(
                    plot.PolyMarker(
                        numpy.array(self.Points[self.SelectedPoint:self.SelectedPoint+1]), 
                        colour='red', marker='square', fillstyle=wx.TRANSPARENT))
            self.Graphics = plot.PlotGraphics(
                graphs, os.path.split(self.FilePath)[1], *self.Headers)
            self.RefreshDraw()
        else:
            self.PointsGraph = None
            self.Graphics = None
        self.RefreshControlsValue()
    
    def RefreshDraw(self):
        if self.Graphics is not None:
            x_range = self.PointsRange[0] * ZOOM_VALUES[self.CurrentZoom] * 1.1
            y_range = self.PointsRange[1] * ZOOM_VALUES[self.CurrentZoom] * 1.1
            self.Canvas.Draw(self.Graphics,
                xAxis=(self.ScreenMiddle[0] - x_range / 2, self.ScreenMiddle[0] + x_range / 2),    
                yAxis=(self.ScreenMiddle[1] - y_range / 2, self.ScreenMiddle[1] + y_range / 2))
    
    def RefreshControlsValue(self):
        if self.SelectedPoint is not None:
            x, y = map(str, self.Points[self.SelectedPoint])
        else:
            x = y = ""
        self.XAxisValue.ChangeValue(x)
        self.YAxisValue.ChangeValue(y)
        self.XAxisValue.Enable(self.SelectedPoint is not None)
        self.YAxisValue.Enable(self.SelectedPoint is not None)
        
    def OnCanvasLeftDown(self, event):
        self.SelectedPoint = self.GetPoint(event)
        if self.SelectedPoint is not None:
            self.StartPos = self.Canvas.PositionUserToScreen(
                self.Points[self.SelectedPoint])
            self.RefreshGraph()
        self.KeyReceiver.SetFocus()
        event.Skip()
        
    def OnCanvasLeftUp(self, event):
        self.StartPos = None
        event.Skip()
    
    def OnCanvasMiddleDown(self, event):
        self.MouseOldPos = event.GetPosition()
        self.KeyReceiver.SetFocus()
        event.Skip()
    
    def OnCanvasMiddleUp(self, event):
        self.MouseOldPos = None
        event.Skip()
    
    def OnCanvasMotion(self, event):
        if self.SelectedPoint is not None and event.LeftIsDown():
            pos = event.GetPosition()
            if event.ControlDown():
                if abs(self.StartPos[0] - pos[0]) > abs(self.StartPos[1] - pos[1]):
                    pos = (pos[0], self.StartPos[1])
                else:
                    pos = (self.StartPos[0], pos[1])
            point = self.Canvas.PositionScreenToUser(pos)
            self.Points[self.SelectedPoint] = point
            self.Points.sort()
            self.SelectedPoint = self.Points.index(point)
            self.MarkAsChanged()
            self.RefreshGraph()
        elif self.MouseOldPos is not None and event.MiddleIsDown():
            old_pos = self.Canvas.PositionScreenToUser(self.MouseOldPos)
            new_pos = self.Canvas.PositionScreenToUser(event.GetPosition())
            self.ScreenMiddle = (
                self.ScreenMiddle[0] + old_pos[0] - new_pos[0],
                self.ScreenMiddle[1] + old_pos[1] - new_pos[1])
            self.MouseOldPos = event.GetPosition()
            self.RefreshDraw()
        else:
            if self.GetPoint(event) is not None:
                cursor = wx.StockCursor(wx.CURSOR_HAND)
            else:
                cursor = wx.StockCursor(wx.CURSOR_CROSS)
            if cursor != self.CurrentCursor:
                self.Canvas.SetCursor(cursor)
                self.CurrentCursor = cursor
        event.Skip()
    
    def OnCanvasLeftDClick(self, event):
        point = self.Canvas.PositionScreenToUser(event.GetPosition())
        self.Points.append(point)
        self.Points.sort()
        self.SelectedPoint = self.Points.index(point)
        self.MarkAsChanged()
        self.RefreshGraph()
        event.Skip()
    
    def ChangeZoom(self, incr, mouse_pos=None):
        new_zoom = max(0, min(self.CurrentZoom + incr, len(ZOOM_VALUES) - 1))
        if new_zoom != self.CurrentZoom:
            if mouse_pos is not None:
                user_mouse_pos = self.Canvas.PositionScreenToUser(mouse_pos)
                x_range = self.PointsRange[0] * ZOOM_VALUES[self.CurrentZoom] * 1.1
                y_range = self.PointsRange[1] * ZOOM_VALUES[self.CurrentZoom] * 1.1
                xp_range = self.PointsRange[0] * ZOOM_VALUES[new_zoom] * 1.1
                yp_range = self.PointsRange[1] * ZOOM_VALUES[new_zoom] * 1.1
                ratio = (
                    (user_mouse_pos[0] - self.ScreenMiddle[0] + x_range / 2) / x_range,
                    (user_mouse_pos[1] - self.ScreenMiddle[1] + y_range / 2) / y_range
                )
                self.ScreenMiddle = (
                    user_mouse_pos[0] + xp_range / 2 - ratio[0] * xp_range,
                    user_mouse_pos[1] + yp_range / 2 - ratio[1] * yp_range)
            self.CurrentZoom = new_zoom
            self.RefreshDraw()
    
    def OnCanvasMouseWheel(self, event):
        if self.StartPos is None and self.MouseOldPos is None:
            rotation = event.GetWheelRotation() / event.GetWheelDelta()
            self.ChangeZoom(rotation, event.GetPosition())
        event.Skip()
    
    def SetSelectedPointValue(self, x=None, y=None):
        if self.SelectedPoint is not None:
            point = self.Points[self.SelectedPoint]
            if x is not None:
                point = (x, point[1])
            if y is not None:
                point = (point[0], y)
            self.Points[self.SelectedPoint] = point
            self.Points.sort()
            self.SelectedPoint = self.Points.index(point)
            self.MarkAsChanged()
            self.RefreshGraph()
    
    def OnXAxisValueChanged(self, event):
        try:
            self.SetSelectedPointValue(
                x = float(self.XAxisValue.GetValue()))
        except ValueError, e:
            self.RefreshControlsValue()
        event.Skip()
    
    def OnYAxisValueChanged(self, event):
        try:
            self.SetSelectedPointValue(
                y = float(self.YAxisValue.GetValue()))
        except ValueError, e:
            self.RefreshControlsValue()
        event.Skip()
    
    ARROW_KEY_MOVE = {
        wx.WXK_LEFT: (-1, 0),
        wx.WXK_RIGHT: (1, 0),
        wx.WXK_UP: (0, -1),
        wx.WXK_DOWN: (0, 1),
    }
    
    def OnChar(self, event):
        keycode = event.GetKeyCode()
        if self.SelectedPoint is not None:
            if keycode == wx.WXK_DELETE:
                self.Points.pop(self.SelectedPoint)
                self.SelectedPoint = None
                self.Changed = True
                self.RefreshGraph()
            elif keycode == ord("+"):
                self.ChangeZoom(1)
            elif keycode == ord("-"):
                self.ChangeZoom(-1)
            elif self.ARROW_KEY_MOVE.has_key(keycode):
                move = self.ARROW_KEY_MOVE[keycode]
                scaling = (8, 8)
                if not event.AltDown() or event.ShiftDown():
                    move = (move[0] * scaling[0], move[1] * scaling[1])
                    if event.ShiftDown() and not event.AltDown():
                        move = (move[0] * 10, move[1] * 10)
                point = self.Canvas.PositionUserToScreen(self.Points[self.SelectedPoint])
                point = self.Canvas.PositionScreenToUser(
                            (point[0] + move[0], point[1] + move[1]))
                self.Points[self.SelectedPoint] = point
                self.Points.sort()
                self.SelectedPoint = self.Points.index(point)
                self.MarkAsChanged()
                self.RefreshGraph()
        event.Skip()
