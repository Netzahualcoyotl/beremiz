import wx


class EtherCATConflictDialog(wx.Dialog):

    def __init__(self, parent, conflict_position,
                 configured_slave, found_slave):
        wx.Dialog.__init__(
            self,
            parent,
            title=_("EtherCAT physical position conflict"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.configured_slave = configured_slave
        self.found_slave = found_slave
        self.conflict_position = conflict_position

        configured_info = configured_slave.getInfo()
        found_info = found_slave.getInfo()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(
            self,
            label=_(
                "Physical position %s contains a different EtherCAT "
                "device than the one configured there.") %
            conflict_position)

        main_sizer.Add(
            title,
            0,
            wx.ALL | wx.EXPAND,
            10)

        conflict_text = wx.StaticText(
            self,
            label=_(
                "physical position %s\n"
                "configured for: IEC%d / %s\n"
                "found there: IEC%d / %s") % (
                    conflict_position,
                    configured_info.getIEC_Channel(),
                    configured_info.getName(),
                    found_info.getIEC_Channel(),
                    found_info.getName()))

        main_sizer.Add(
            conflict_text,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            10)

        # ------------------------------------------------------------
        # Configured slave
        # ------------------------------------------------------------

        configured_box = wx.StaticBox(
            self,
            label=_("Configured slave"))

        configured_sizer = wx.StaticBoxSizer(
            configured_box,
            wx.VERTICAL)

        configured_grid = wx.FlexGridSizer(
            rows=4,
            cols=2,
            hgap=10,
            vgap=8)

        configured_grid.AddGrowableCol(1, 1)

        configured_grid.Add(
            wx.StaticText(self, label=_("IEC_Channel")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        configured_iec = wx.TextCtrl(
            self,
            value=str(configured_info.getIEC_Channel()),
            style=wx.TE_READONLY)

        configured_grid.Add(configured_iec, 1, wx.EXPAND)

        configured_grid.Add(
            wx.StaticText(self, label=_("AddressMode")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        configured_mode = wx.TextCtrl(
            self,
            value=str(configured_info.getAddressMode() or "Position"),
            style=wx.TE_READONLY)

        configured_grid.Add(configured_mode, 1, wx.EXPAND)

        configured_grid.Add(
            wx.StaticText(self, label=_("PhysAddr")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        self.configured_phys = wx.SpinCtrl(
            self,
            min=-2147483648,
            max=2147483647,
            initial=int(configured_info.getPhysAddr()))

        configured_grid.Add(self.configured_phys, 1, wx.EXPAND)

        configured_grid.Add(
            wx.StaticText(self, label=_("Alias")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        self.configured_alias = wx.SpinCtrl(
            self,
            min=-2147483648,
            max=2147483647,
            initial=int(configured_info.getAlias()))

        configured_grid.Add(self.configured_alias, 1, wx.EXPAND)

        configured_sizer.Add(
            configured_grid,
            1,
            wx.ALL | wx.EXPAND,
            8)

        main_sizer.Add(
            configured_sizer,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            10)

        # ------------------------------------------------------------
        # Found slave configuration
        # ------------------------------------------------------------

        found_box = wx.StaticBox(
            self,
            label=_("Found slave configuration"))

        found_sizer = wx.StaticBoxSizer(
            found_box,
            wx.VERTICAL)

        found_grid = wx.FlexGridSizer(
            rows=4,
            cols=2,
            hgap=10,
            vgap=8)

        found_grid.AddGrowableCol(1, 1)

        found_grid.Add(
            wx.StaticText(self, label=_("IEC_Channel")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        found_iec = wx.TextCtrl(
            self,
            value=str(found_info.getIEC_Channel()),
            style=wx.TE_READONLY)

        found_grid.Add(found_iec, 1, wx.EXPAND)

        found_grid.Add(
            wx.StaticText(self, label=_("AddressMode")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        found_mode = wx.TextCtrl(
            self,
            value=str(found_info.getAddressMode() or "Position"),
            style=wx.TE_READONLY)

        found_grid.Add(found_mode, 1, wx.EXPAND)

        found_grid.Add(
            wx.StaticText(self, label=_("PhysAddr")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        self.found_phys = wx.SpinCtrl(
            self,
            min=-2147483648,
            max=2147483647,
            initial=int(found_info.getPhysAddr()))

        found_grid.Add(self.found_phys, 1, wx.EXPAND)

        found_grid.Add(
            wx.StaticText(self, label=_("Alias")),
            0,
            wx.ALIGN_CENTER_VERTICAL)

        self.found_alias = wx.SpinCtrl(
            self,
            min=-2147483648,
            max=2147483647,
            initial=int(found_info.getAlias()))

        found_grid.Add(self.found_alias, 1, wx.EXPAND)

        found_sizer.Add(
            found_grid,
            1,
            wx.ALL | wx.EXPAND,
            8)

        main_sizer.Add(
            found_sizer,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            10)

        # ------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------

        button_sizer = self.CreateButtonSizer(
            wx.OK | wx.CANCEL)

        main_sizer.Add(
            button_sizer,
            0,
            wx.ALL | wx.ALIGN_RIGHT,
            10)

        self.SetSizerAndFit(main_sizer)

        self.CentreOnParent()
