#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz
#
# Copyright (C) 2011-2014: Laurent BESSARD
#                          RTES Lab : CRKim, JBLee, youcu
#                          Higen Motor : Donggu Kang
# Copyright (C) 2011-2026: Edouard TISSERANT
#
# See COPYING file for copyrights details.


from plcopen.types_enums import LOCATION_CONFNODE

from cia402.cia402 import \
    CIA402NodeCTNMixin, \
    GetCIA402XSD, \
    ADD_NODE_VARIABLES, \
    ADD_NODE_PUBLISH_TEMPLATE, \
    ADD_NODE_RETRIEVE_TEMPLATE, \
    MODE_OF_OPERATION_INDEXES, \
    NODE_VARIABLES
from etherlab.EthercatSlave import _EthercatSlaveCTN, _CommonSlave, PDO, PDO_CAPABILITIES
from etherlab.ConfigEditor import CIA402NodeEditor

DC ="""<xsd:attribute name="DC_Enable" type="xsd:boolean" use="optional" default="false"/>
<xsd:attribute name="DC_Desc" type="xsd:string" use="optional" default="None"/>
<xsd:attribute name="DC_Assign_Activate" type="xsd:string" use="optional" default="None"/>
<xsd:attribute name="DC_Sync0_Cycle_Time" type="xsd:string" use="optional" default="None"/>
<xsd:attribute name="DC_Sync0_Shift_Time" type="xsd:string" use="optional" default="None"/>
<xsd:attribute name="DC_Sync1_Cycle_Time" type="xsd:string" use="optional" default="None"/>
<xsd:attribute name="DC_Sync1_Shift_Time" type="xsd:string" use="optional" default="None"/>
"""

# Confnode parameters of an EtherCAT CiA402 slave that describe the bus rather
# than the axis, and so must not end up as axis_s assignments
ETHERCAT_PARAMS_NO_C = frozenset({
    "RxPDO",
    "TxPDO",
    "PdoAssign",
    "PdoConfig",
    "DC_Enabled",
    "DC_Desc",
    "DC_Assign_Activate",
    "DC_Sync0_Cycle_Time",
    "DC_Sync0_Shift_Time",
    "DC_Sync1_Cycle_Time",
    "DC_Sync1_Shift_Time",
})


# --------------------------------------------------
#                 Ethercat CIA402 Node
# --------------------------------------------------


class _EthercatCIA402SlaveCTN(CIA402NodeCTNMixin, _EthercatSlaveCTN):
    XSD = GetCIA402XSD("CIA402SlaveParams", PDO + PDO_CAPABILITIES + DC)

    EditorType = CIA402NodeEditor

    CIA402_FIELDBUS_INCLUDES = '#include "ecrt.h"\n#include "fieldbus_ethercat.h"'
    CIA402_EXTRA_PARAMS_NO_C = ETHERCAT_PARAMS_NO_C

# --------------------------------------------------
#    class code
# --------------------------------------------------

    def __init__(self):
        _EthercatSlaveCTN.__init__(self)

        # ----------- call ethercat mng. function --------------
        self.CommonMethod = _CommonSlave(self)

    def FilterNodeVariablesFromESI(self, device_entries):
        """
        Split ADD_NODE_VARIABLES between the variables the ESI file of the
        device does declare, and the ones it does not.
        @param device_entries : entries declared by the ESI file
        @return (kept, removed) : two lists of node variable descriptions
        """
        valid_indices = set(idx for (idx, _subidx) in device_entries.keys())

        kept = []
        removed = []
        for var in ADD_NODE_VARIABLES:
            if var['index'] in valid_indices:
                kept.append(var)
            else:
                removed.append(var)

        return kept, removed

    def GetVariableLocationTree(self):
        axis_name = self.CTNName()
        current_location = self.GetCurrentLocation()
        children = self.CIA402LocationTreeChildren(axis_name)
        children.extend(self.CTNParent.GetDeviceLocationTree(self.GetSlavePos(),
                                                             current_location,
                                                             axis_name))
        return {
            "name": axis_name,
            "type": LOCATION_CONFNODE,
            "location": self.GetFullIEC_Channel(),
            "children": children,
        }

    def LoadPDOSelectData(self):
        try:
            # always start from empty selections
            self.SelectedRxPDOIndex = []
            self.SelectedTxPDOIndex = []

            params = self.GetSlaveParams()

            # -------- Rx --------
            RxPDOData = params.getRxPDO()

            if RxPDOData and RxPDOData != "None":
                RxPDOs = RxPDOData.replace(",", " ").split()

                self.SelectedRxPDOIndex = list({
                    int(RxPDO, 0) for RxPDO in RxPDOs if RxPDO
                })

            # -------- Tx --------
            TxPDOData = params.getTxPDO()

            if TxPDOData and TxPDOData != "None":
                TxPDOs = TxPDOData.replace(",", " ").split()

                self.SelectedTxPDOIndex = list({
                    int(TxPDO, 0) for TxPDO in TxPDOs if TxPDO
                })

        except Exception as e:
            self.GetCTRoot().logger.write_warning(
                _("Warning: could not load PDO selection: %s\n") % str(e))

    def LoadDefaultPDOSet(self):
        ReturnData = []
        rx_pdo_entries = self.CommonMethod.GetRxPDOCategory()
        if len(rx_pdo_entries):
            for i in range(len(rx_pdo_entries)):
                if rx_pdo_entries[i]['sm'] is not None:
                    ReturnData.append(rx_pdo_entries[i]['pdo_index'])

        tx_pdo_entries = self.CommonMethod.GetTxPDOCategory()
        if len(tx_pdo_entries):
            for i in range(len(tx_pdo_entries)):
                if tx_pdo_entries[i]['sm'] is not None:
                    ReturnData.append(tx_pdo_entries[i]['pdo_index'])

        if ReturnData :
            return ReturnData
        else :
            return [5632, 6656]

# --------------------------------------------------
#    CiA402 field bus hooks
# --------------------------------------------------

    def CIA402AxisRefSuffix(self):
        return ".402"
    
    def CIA402FieldbusLocation(self):
        return self.GetCurrentLocation()

    def CIA402AxisNetwork(self):
        location = "_".join(map(str, self.GetCurrentLocation()))
        return ("static ethercat_axis_network_u __axis_network_%s =\n"
                "    { .addr = { ETHERCAT_AXIS_SENTINEL, %d } };" % (
                    location, self.GetSlavePos()),
                "        AxsPub.axis->Network = &__axis_network_%s;" % location)

    def CIA402ResolveEntry(self, index, subindex, var_type, direction):
        self.LoadPDOSelectData()

        if not self.SelectedRxPDOIndex and not self.SelectedTxPDOIndex:
            selected_rx = self.LoadDefaultPDOSet()
            selected_tx = []
        else:
            selected_rx = self.SelectedRxPDOIndex
            selected_tx = self.SelectedTxPDOIndex

        self.CommonMethod.RequestPDOInfo()

        if direction == "Q":
            pdo_categories = self.CommonMethod.GetRxPDOCategory()
            pdo_entries = self.CommonMethod.GetRxPDOInfo()
            selected_pdos = selected_rx
        else:
            pdo_categories = self.CommonMethod.GetTxPDOCategory()
            pdo_entries = self.CommonMethod.GetTxPDOInfo()
            selected_pdos = selected_tx

        list_index = 0
        for pdo in pdo_categories:
            count = pdo["number_of_entry"]

            if pdo["pdo_index"] in selected_pdos:
                used = pdo_entries[list_index:list_index + count]

                for entry in used:
                    if (entry["entry_index"] == index and
                            entry["subindex"] == subindex):
                        return (index, subindex)

            list_index += count

        return None

    def CIA402DeclareEntryPointer(self, var_infos):
        self.CTNParent.FileGenerator.DeclareVariable(
                self.GetSlavePos(), var_infos["index"], var_infos["subindex"],
                var_infos["var_type"], var_infos["dir"], var_infos["var_name"])

    def CIA402SelectVariables(self):
        """
        Only the objects carried by the PDOs selected for this slave are
        exchanged. What the ESI file does not declare at all is dropped first.
        """
#HSAHN
#2015. 7. 24 PDO Variable
        #if PDO is not selected, use 1st PDO set
        self.LoadPDOSelectData()

        if not self.SelectedRxPDOIndex and not self.SelectedTxPDOIndex :
            self.SelectedPDOIndex = self.LoadDefaultPDOSet()
        else :
            self.SelectedPDOIndex = self.SelectedRxPDOIndex + self.SelectedTxPDOIndex
        add_idx = []
        # only keep the variables the ESI file of the device knows about
        device_entries = self.CommonMethod.GetAllEntriesList()
        add_node_variables, removed = self.FilterNodeVariablesFromESI(device_entries)
        removed_indices = {v["index"] for v in removed}

        variables = [
            v for v in NODE_VARIABLES
            if v[1] not in removed_indices
        ]

        default_variables_retrieve = []
        default_variables_publish = []

        for i in range(len(add_node_variables)):
            add_idx.append(add_node_variables[i]['index'])

        self.CommonMethod.RequestPDOInfo()
        pdo_info = self.CommonMethod.GetRxPDOCategory() + self.CommonMethod.GetTxPDOCategory()
        pdo_entry = self.CommonMethod.GetRxPDOInfo() + self.CommonMethod.GetTxPDOInfo()
        list_index = 0
        ModeOfOpFlag = False
        ModeOfOpDisplayFlag = False
        for i in range(len(pdo_info)):
            #if pdo_index is in the SelectedPDOIndex: put the PDO mapping information intto the "used" object
            if pdo_info[i]['pdo_index'] in self.SelectedPDOIndex:
                used = pdo_entry[list_index:list_index + pdo_info[i]['number_of_entry']]

                for used_data in used:
                    # 24672 -> 0x6060, Mode of Operation
                    if used_data['entry_index'] == MODE_OF_OPERATION_INDEXES[0]:
                        ModeOfOpFlag = True
                    # 24673 -> 0x6061, Mode of Operation Display
                    elif used_data["entry_index"] == MODE_OF_OPERATION_INDEXES[1]:
                        ModeOfOpDisplayFlag = True

                    if used_data['entry_index'] in add_idx:
                        idx = add_idx.index(used_data['entry_index'])
                        adder = list([add_node_variables[idx]['name'], add_node_variables[idx]['index'], \
                                     add_node_variables[idx]['sub-index'], add_node_variables[idx]['type'], \
                                     add_node_variables[idx]['direction']])
                        variables.append(adder)
                        if add_node_variables[idx]['direction'] == "Q":
                            parsed_string = add_node_variables[idx]['name'].replace("Target", "")
                            # add jblee
                            check_q_data = ADD_NODE_PUBLISH_TEMPLATE % {"base": parsed_string}
                            if check_q_data not in default_variables_publish:
                                default_variables_publish.append(check_q_data)
                        elif add_node_variables[idx]['direction'] == "I":
                            parsed_string = add_node_variables[idx]['name'].replace("Actual", "")
                            # add jblee
                            check_i_data = ADD_NODE_RETRIEVE_TEMPLATE % {"base": parsed_string}
                            if check_i_data not in default_variables_retrieve:
                                default_variables_retrieve.append(check_i_data)
            list_index += pdo_info[i]['number_of_entry']
#HSAHN END

        return (variables,
                default_variables_retrieve,
                default_variables_publish,
                ModeOfOpFlag and ModeOfOpDisplayFlag)

    def CTNGenerate_C(self, buildpath, locations):
        Gen_CIA402Nodefile_path = self.CIA402Generate_C(
            buildpath, self.CIA402CollectVariables())

        return [(Gen_CIA402Nodefile_path, self.CIA402CFlags())], "", True
