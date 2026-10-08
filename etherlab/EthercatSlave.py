#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz
#
# Copyright (C) 2011-2014: Laurent BESSARD, Edouard TISSERANT
#                          RTES Lab : CRKim, JBLee, youcu
#                          Higen Motor : Donggu Kang
#
# See COPYING file for copyrights details.



from plcopen.types_enums import LOCATION_CONFNODE, LOCATION_VAR_INPUT, LOCATION_VAR_OUTPUT, LOCATION_VAR_MEMORY
from ConfigTreeNode import ConfigTreeNode

from etherlab.ConfigEditor import NodeEditor
import wx
# ------------------------------------------
from etherlab.CommonEtherCATFunction import _CommonSlave
# ------------------------------------------


TYPECONVERSION = {"BOOL": "X", "SINT": "B", "INT": "W", "DINT": "D", "LINT": "L",
                  "USINT": "B", "UINT": "W", "UDINT": "D", "ULINT": "L",
                  "BYTE": "B", "WORD": "W", "DWORD": "D", "LWORD": "L"}

DATATYPECONVERSION = {"BOOL": "BIT", "SINT": "S8", "INT": "S16", "DINT": "S32", "LINT": "S64",
                      "USINT": "U8", "UINT": "U16", "UDINT": "U32", "ULINT": "U64",
                      "BYTE": "U8", "WORD": "U16", "DWORD": "U32", "LWORD": "U64"}

VARCLASSCONVERSION = {"T": LOCATION_VAR_INPUT, "R": LOCATION_VAR_OUTPUT, "RT": LOCATION_VAR_MEMORY}


def ExtractHexDecValue(value):
    try:
        return int(value)
    except Exception:
        pass
    try:
        return int(value.replace("#", "0"), 16)
    except Exception:
        raise ValueError("Invalid value for HexDecValue \"%s\"" % value)


def GenerateHexDecValue(value, base=10):
    if base == 10:
        return str(value)
    elif base == 16:
        return "#x%.8x" % value
    else:
        raise ValueError("Not supported base")


def ExtractName(names, default=None):
    if len(names) == 1:
        return names[0].getcontent()
    else:
        for name in names:
            if name.getLcId() == 1033:
                return name.getcontent()
    return default

PDO ="""<xsd:attribute name="RxPDO" type="xsd:string" use="optional" default=""/>
<xsd:attribute name="TxPDO" type="xsd:string" use="optional" default=""/>
"""

# Whether the PDOs of the slave can be reassigned and remapped is normally read
# from the CoE section of its ESI file. These let the user overrule an ESI file
# that does not describe the device faithfully.
PDO_CAPABILITIES = "\n".join(["""\
<xsd:attribute name="%s" use="optional" default="Auto">
  <xsd:simpleType>
    <xsd:restriction base="xsd:string">
      <xsd:enumeration value="Auto"/>
      <xsd:enumeration value="Enabled"/>
      <xsd:enumeration value="Disabled"/>
    </xsd:restriction>
  </xsd:simpleType>
</xsd:attribute>""" % name for name in ["PdoAssign", "PdoConfig"]]) + "\n"

# --------------------------------------------------
#                    Ethercat Node
# --------------------------------------------------

class _EthercatSlaveCTN(object):
    NODE_PROFILE = None
    EditorType = NodeEditor

    XSD = """<?xml version="1.0" encoding="ISO-8859-1" ?>
    <xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">

      <xsd:element name="EthercatSlaveParams">
        <xsd:complexType>
          <xsd:sequence/>
          %s
        </xsd:complexType>
      </xsd:element>

    </xsd:schema>
    """ % (PDO + PDO_CAPABILITIES)

    def __init__(self):
        # ----------- call ethercat mng. function --------------
        self.CommonMethod = _CommonSlave(self)
        self.SelectedRxPDOIndex = []
        self.SelectedTxPDOIndex = []

    def GetSlaveParams(self):
        """
        PDO and DC parameters of this slave, whatever the XSD root element is
        called : plain slaves store them in EthercatSlaveParams, CiA402 slaves
        in CIA402SlaveParams.
        @return the confnode parameters object, None when there is none
        """
        return self.CTNParams[1] if self.CTNParams else None

    def GetIconName(self):
        return "Slave"

    def ExtractHexDecValue(self, value):
        return ExtractHexDecValue(value)

    def GetSizeOfType(self, type):
        return TYPECONVERSION.get(self.GetCTRoot().GetBaseType(type), None)

    def GetSlavePos(self):
        iec_channel = self.BaseParams.getIEC_Channel()
        slave = self.CTNParent.GetSlaveByIECChannel(iec_channel)

        if slave is not None:
            phys_addr = slave.getInfo().getPhysAddr()
            if phys_addr is not None:
                return phys_addr

        # Fallback for old configurations without IEC_Channel in
        # the EtherCAT network configuration.
        return iec_channel

    def GetParamsAttributes(self, path=None):
        if path:
            parts = path.split(".", 1)

            if self.MandatoryParams and parts[0] == self.MandatoryParams[0]:
                return self.MandatoryParams[1].getElementInfos(parts[0], parts[1])

            elif self.CTNParams and parts[0] == self.CTNParams[0]:
                return self.CTNParams[1].getElementInfos(parts[0], parts[1])

        else:
            params = []

            if self.CTNParams:
                params.append(self.CTNParams[1].getElementInfos(self.CTNParams[0]))
            else:
                params.append({
                    'use': 'required',
                    'type': 'element',
                    'name': 'SlaveParams',
                    'value': None,
                    'children': [],
                    'doc': [{"documentation": "EtherCAT slave parameters"}]
                })

            slave_type = self.CTNParent.GetSlaveType(self.GetSlavePos())

            params[0]['children'].insert(
                0,
                {
                    'use': 'optional',
                    'type': self.CTNParent.GetSlaveTypesLibrary(self.NODE_PROFILE),
                    'name': 'Type',
                    'value': (slave_type["device_type"], slave_type),
                    'doc': [{"documentation": "EtherCAT slave type"}]
                })

            # EtherCAT addressing information is stored in the
            # Master network configuration.
            slave = self.CTNParent.GetSlaveByIECChannel(
                self.BaseParams.getIEC_Channel())

            alias = 0
            address_mode = "Position"

            if slave is not None:
                slave_info = slave.getInfo()

                alias = slave_info.getAlias()
                if alias is None:
                    alias = 0

                address_mode = slave_info.getAddressMode() or "Position"

            params[0]['children'].insert(
                1,
                {
                    'use': 'optional',
                    'type': 'int',
                    'name': 'Alias',
                    'value': alias,
                    'doc': [{"documentation": "EtherCAT alias address"}]
                })

            params[0]['children'].insert(
                2,
                {
                    'use': 'optional',
                    'type': ['Position', 'Alias'],
                    'name': 'AddressMode',
                    'value': address_mode,
                    'doc': [{"documentation": "EtherCAT addressing mode: Position or Alias"}]
                })

            return params
    
    def UpdateIECChannelLocation(self, old_channel, new_channel):
        if old_channel == new_channel:
            return

        parent_location = self.CTNParent.GetCurrentLocation()

        old_leading = ".".join(
            map(str, parent_location + (old_channel,)))
        new_leading = ".".join(
            map(str, parent_location + (new_channel,)))

        self.GetCTRoot().UpdateProjectVariableLocation(
            old_leading, new_leading)


    def SetParamsAttribute(self, path, value):
            self.GetSlaveInfos()
            position = self.BaseParams.getIEC_Channel()

            # "Type" is shown among the confnode parameters but stored in the
            # master network configuration, so it is handled here rather than by
            # ConfigTreeNode. The parameters editor prefixes it with the XSD root
            # element name, the master calls it by its bare name.
            root = self.CTNParams[0] if self.CTNParams else "SlaveParams"

            if path in ("SlaveParams.AddressMode", "%s.AddressMode" % root):
                if value == "":
                    return value, True

                if value not in ("Position", "Alias"):
                    return value, True

                slave = self.CTNParent.GetSlaveByIECChannel(position)

                if slave is not None:
                    slave_info = slave.getInfo()
                    current_mode = slave_info.getAddressMode() or "Position"

                    if value == current_mode:
                        return value, True

                    if value == "Alias":
                        alias = slave_info.getAlias()

                        if alias is None:
                            alias = position

                        other_slave = self.CTNParent.GetSlaveByAlias(alias)

                        if other_slave is not None and other_slave is not slave:
                            other_info = other_slave.getInfo()
                            other_position = other_info.getPhysAddr()

                            wx.MessageBox(
                                _("Alias %s is already assigned to the slave at "
                                  "physical position %s.") % (alias, other_position),
                                _("Duplicate EtherCAT Alias"),
                                wx.OK | wx.ICON_ERROR)

                            return current_mode, True

                        logical_channel = alias

                    else:
                        logical_channel = slave_info.getPhysAddr()

                    slave_info.setAddressMode(value)
                    self.UpdateIECChannelLocation(
                        position, logical_channel)
                    slave_info.setIEC_Channel(logical_channel)
                    self.BaseParams.setIEC_Channel(logical_channel)

                    self.CTNParent.BufferModel()

                    return value, True

            if path in ("SlaveParams.Type", "%s.Type" % root):
                slave = self.CTNParent.GetSlaveByIECChannel(position)

                if slave is not None:
                    phys_addr = slave.getInfo().getPhysAddr()
                    self.CTNParent.SetSlaveType(phys_addr, value)
                    slave_type = self.CTNParent.GetSlaveType(phys_addr)
                    return slave_type["device_type"], True

            if path in ("SlaveParams.Alias", "%s.Alias" % root):
                # The text editor sends an empty string while the user is
                # replacing the current value.
                if value == "":
                    return value, True

                try:
                    alias = int(value)
                except (TypeError, ValueError):
                    return value, True

                slave = self.CTNParent.GetSlaveByIECChannel(position)

                if slave is not None:
                    slave_info = slave.getInfo()
                    current_alias = slave_info.getAlias()

                    # No change.
                    if alias == current_alias:
                        return alias, True

                    # Alias must be unique within the project configuration.
                    other_slave = self.CTNParent.GetSlaveByAlias(alias)

                    if other_slave is not None and other_slave is not slave:
                        other_info = other_slave.getInfo()
                        other_position = other_info.getPhysAddr()

                        wx.MessageBox(
                            _("Alias %s is already assigned to the slave at "
                              "physical position %s.") % (alias, other_position),
                            _("Duplicate EtherCAT Alias"),
                            wx.OK | wx.ICON_ERROR)

                        return current_alias, True

                    slave_info.setAlias(alias)

                    # In Alias mode, IEC_Channel follows the Alias.
                    if (slave_info.getAddressMode() or "Position") == "Alias":
                        self.UpdateIECChannelLocation(
                            position, alias)
                        slave_info.setIEC_Channel(alias)
                        self.BaseParams.setIEC_Channel(alias)

                    self.CTNParent.BufferModel()

                    return alias, True
            
            value, refresh = ConfigTreeNode.SetParamsAttribute(self, path, value)

            # IEC_Channel represents the configured EtherCAT address selected
            # by AddressMode.
            if path == "BaseParams.IEC_Channel" and value != position:
                slave = self.CTNParent.GetSlaveByIECChannel(position)

                if slave is not None:
                    slave_info = slave.getInfo()
                    address_mode = slave_info.getAddressMode() or "Position"

                    if address_mode == "Alias":
                        slave_info.setAlias(value)
                    else:
                        slave_info.setPhysAddr(value)

                    slave_info.setIEC_Channel(value)

                    self.CTNParent.BufferModel()
                    self.CTNRequestSave()

            return value, refresh

    def GetSlaveInfos(self):
        return self.CTNParent.GetSlaveInfos(self.GetSlavePos())

    def GetSlaveVariables(self, limits):
        return self.CTNParent.GetSlaveVariables(self.GetSlavePos(), limits)

    def GetVariableLocationTree(self):
        return {
            "name": self.BaseParams.getName(),
            "type": LOCATION_CONFNODE,
            "location": self.GetFullIEC_Channel(),
            "children": self.CTNParent.GetDeviceLocationTree(self.GetSlavePos(), self.GetCurrentLocation(), self.BaseParams.getName())
        }

    def CTNGenerate_C(self, buildpath, locations):
        return [], "", False
