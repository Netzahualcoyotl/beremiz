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

"""
Field bus independent part of the CiA402 drive profile support.

CiA402 is the drive profile of the CANopen application layer. EtherCAT reuses
that same application layer (CoE), so the object dictionary entries, the PDS
state machine and the way an axis is handed over to the Motion Control Library
are identical on both. Only the plumbing that makes an object dictionary entry
reachable from C differs, and that is left to the field bus through a handful
of hooks.
"""

import os

import wx

from plcopen.types_enums import LOCATION_VAR_INPUT

from MotionLibrary import Headers, AxisXSD


CIA402_NODE_PROFILE = 402

# Modes of operation and its display. Both have to be mapped, or none.
MODE_OF_OPERATION_INDEXES = (0x6060, 0x6061)

# IEC type -> located variable size letter
TYPECONVERSION = {"BOOL": "X", "SINT": "B", "INT": "W", "DINT": "D", "LINT": "L",
                  "USINT": "B", "UINT": "W", "UDINT": "D", "ULINT": "L",
                  "BYTE": "B", "WORD": "W", "DWORD": "D", "LWORD": "L"}

# Definition of node variables that have to be mapped in PDO
# [(name, index, subindex, type,
#   direction for master ('I': input, 'Q': output)),...]
NODE_VARIABLES = [
    ("ControlWord",             0x6040, 0x00, "UINT", "Q"),
    ("TargetPosition",          0x607a, 0x00, "DINT", "Q"),
    ("TargetVelocity",          0x60ff, 0x00, "DINT", "Q"),
    ("TargetTorque",            0x6071, 0x00, "INT",  "Q"),
    ("ModesOfOperation",        0x6060, 0x00, "SINT", "Q"),
    ("StatusWord",              0x6041, 0x00, "UINT", "I"),
    ("ModesOfOperationDisplay", 0x6061, 0x00, "SINT", "I"),
    ("ActualPosition",          0x6064, 0x00, "DINT", "I"),
    ("ActualVelocity",          0x606c, 0x00, "DINT", "I"),
    ("ActualTorque",            0x6077, 0x00, "INT",  "I")
]

# ------------------- restored from the previous version ----------------
#HSAHN 2015.07.26
#reference variable
ADD_NODE_VARIABLES = ({'name':"TargetPosition"   , 'index':0x607a, 'sub-index':0x00, 'type':"DINT", 'direction':"Q"},
                      {'name':"TargetVelocity"   , 'index':0x60ff, 'sub-index':0x00, 'type':"DINT", 'direction':"Q"},
                      {'name':"TargetTorque"     , 'index':0x6071, 'sub-index':0x00, 'type':"INT",  'direction':"Q"},
                      {'name':"ActualPosition"   , 'index':0x6064, 'sub-index':0x00, 'type':"DINT", 'direction':"I"},
                      {'name':"ActualVelocity"   , 'index':0x606c, 'sub-index':0x00, 'type':"DINT", 'direction':"I"},
                      {'name':"ActualTorque"     , 'index':0x6077, 'sub-index':0x00, 'type':"INT",  'direction':"I"}
                     )

DEFAULT_RETRIEVE = "    __CIA402Node_%(location)s.axis->%(name)s = *(__CIA402Node_%(location)s.%(name)s);"
DEFAULT_PUBLISH = "    *(__CIA402Node_%(location)s.%(name)s) = __CIA402Node_%(location)s.axis->%(name)s;"

# Raw setpoint / actual value exchange generated for the ADD_NODE_VARIABLES
# that the device really carries in its process data
ADD_NODE_RETRIEVE_TEMPLATE = "    AxsPub.axis->ActualRaw%(base)s = *(AxsPub.Actual%(base)s);"
ADD_NODE_PUBLISH_TEMPLATE = "    *(AxsPub.Target%(base)s) = AxsPub.axis->Raw%(base)sSetPoint;"

# -----------------------------------------------------------------------
# Definition of optional node variables that can be added to PDO mapping.
# A checkbox will be displayed for each section in node configuration panel to
# enable them
# [(section_name,
#   [{'description', (name, index, subindex, type,
#                     direction for master ('I': input, 'Q': output)),
#     'retrieve', string_template_for_retrieve_variable (None: not retrieved,
#                                 default string template if not defined),
#     'publish', string_template_for_publish_variable (None: not published,
#                                 default string template if not defined),
#    },...]
EXTRA_NODE_VARIABLES = [
    ("ErrorCode", [
        {"description": ("ErrorCode", 0x603F, 0x00, "UINT", "I"),
         "publish": None}
        ]),
    ("DigitalInputs", [
        {"description": ("DigitalInputs", 0x60FD, 0x00, "UDINT", "I"),
         "publish": None}
        ]),
    ("DigitalOutputs", [
        {"description": ("DigitalOutputs", 0x60FE, 0x00, "UDINT", "Q"),
         "retrieve": None}
        ]),
    ("TouchProbe", [
        {"description": ("TouchProbeFunction", 0x60B8, 0x00, "UINT", "Q"),
         "retrieve": None},
        {"description": ("TouchProbeStatus", 0x60B9, 0x00, "UINT", "I"),
         "publish": None},
        {"description": ("TouchProbePos1PosValue", 0x60BA, 0x00, "DINT", "I"),
         "publish": None},
        {"description": ("TouchProbePos1NegValue", 0x60BB, 0x00, "DINT", "I"),
         "publish": None},
        ]),
]

# List of parameters name in no configuration panel for optional variable
# sections
EXTRA_NODE_VARIABLES_DICT = {
    "Enable" + name: params
    for name, params in EXTRA_NODE_VARIABLES}

# Confnode parameters that must not be pushed into axis_s : either they are not
# axis parameters at all, or the axis structure spells them differently. Field
# buses add their own through CIA402_EXTRA_PARAMS_NO_C.
PARAMS_NO_C = {
    "LimitPosEnabled",
    "LimitNegEnabled",
    "PosLagMonitoringEnabled",
    "SimulationEnabled",
    "LimitSwitchNCEnabled",
    "ActualVelocity",
    "EnableDigitalOutputs",
    "EnableTouchProbe",
    "TouchProbePos1NegValue",
    "DigitalOutputs",
    "DigitalOutputsEnable"
}

# XSD fragment shared by every CiA402 node : one checkbox per optional variable
# section, followed by the PLCopen axis parameters MCL exposes.
EXTRA_SECTIONS_XSD = "\n".join(["""\
          <xsd:attribute name="Enable%s" type="xsd:boolean"
                         use="optional" default="false"/>""" % category
                                for category, variables in EXTRA_NODE_VARIABLES])

CIA402_XSD_FRAGMENT = EXTRA_SECTIONS_XSD + AxisXSD

# ------------------- restored from the previous version ------------------
BLOCK_INPUT_TEMPLATE = "    __SET_VAR(%(blockname)s->,%(input_name)s,, %(input_value)s);"
BLOCK_OUTPUT_TEMPLATE = "    __SET_VAR(data__->,%(output_name)s,, __GET_VAR(%(blockname)s->%(output_name)s));"

BLOCK_FUNCTION_TEMPLATE = """
extern void %(fb_prefix)s%(ucase_blocktype)s_body__(%(fb_prefix)s%(ucase_blocktype)s_data__* data__);
void __%(blocktype)s_%(location)s(MC_%(ucase_blocktype)s_data__ *data__) {
__DECLARE_GLOBAL_PROTOTYPE(%(fb_prefix)s%(ucase_blocktype)s_data__, %(blockname)s);
%(fb_prefix)s%(ucase_blocktype)s_data__* %(blockname)s = __GET_GLOBAL_%(blockname)s();
__SET_VAR(%(blockname)s->, POS,, AxsPub.axis->NetworkPosition);
%(extract_inputs)s
%(fb_prefix)s%(ucase_blocktype)s_body__(%(blockname)s);
%(return_outputs)s
}
"""

BLOCK_FUNTION_DEFINITION_TEMPLATE = "        __CIA402Node_%(location)s.axis->__mcl_func_MC_%(blocktype)s = __%(blocktype)s_%(location)s;"
# -------------------------------------------------------------------------

# List of block to define to interface MCL to fieldbus for specific functions
FIELDBUS_INTERFACE_GLOBAL_INSTANCES = [
    {"blocktype": "GetTorqueLimit",
     "inputs": [],
     "outputs": [{"name": "TorqueLimitPos", "type": "UINT"},
                 {"name": "TorqueLimitNeg", "type": "UINT"}]},
    {"blocktype": "SetTorqueLimit",
     "inputs": [{"name": "TorqueLimitPos", "type": "UINT"},
                {"name": "TorqueLimitNeg", "type": "UINT"}],
     "outputs": []},
]

# ------------------- restored from the previous version ------------------
# add jblee
MODEOFOP_HOMING_METHOD_TEMPLATE = """
	if(*(AxsPub.ModesOfOperation) == 0x06){
		IEC_BOOL homing = AxsPub.axis->HomingOperationStart;
		if(power){
			if (homing)
				CW |= Homing_OperationStart_Origin;
			else
				CW &= ~(Homing_OperationStart_Origin);
		}
		else{
			if (homing)
				CW |= Homing_OperationStart_Edit;
			else
				CW &= ~(EnableOperation);
		}

	}
"""

MODEOFOP_COMPUTATION_MODE_TEMPLATE = """
	switch (AxsPub.axis->AxisMotionMode) {

		case mc_mode_hm:
			*(AxsPub.ModesOfOperation) = 0x06;
			break;
		case mc_mode_cst:
			*(AxsPub.ModesOfOperation) = 0x0a;
			break;
		case mc_mode_csv:
			*(AxsPub.ModesOfOperation) = 0x09;
			break;
		default:
			*(AxsPub.ModesOfOperation) = 0x08;
			break;
	}
"""


def GetCIA402XSD(root_element, extra_attributes=""):
    """
    Build the confnode schema of a CiA402 node.
    @param root_element: name of the XSD root element
    @param extra_attributes: field bus specific attributes to append
    """
    return """<?xml version="1.0" encoding="ISO-8859-1" ?>
    <xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">
      <xsd:element name="%s">
        <xsd:complexType>
          %s
        </xsd:complexType>
      </xsd:element>
    </xsd:schema>
    """ % (root_element, CIA402_XSD_FRAGMENT + extra_attributes)


# --------------------------------------------------
#                 CiA402 Node
# --------------------------------------------------


class CIA402NodeCTNMixin(object):
    """
    Field bus independent behaviour of a CiA402 node confnode.

    Mixed in *before* the field bus specific base class, so that the field bus
    keeps the last word on everything this mixin does not define.
    """

    NODE_PROFILE = CIA402_NODE_PROFILE

    # C symbol prefix of the field bus interface function blocks
    # ("ETHERLAB" -> ETHERLABGETTORQUELIMIT_body__)
    CIA402_FB_PREFIX = None
    # POU type name prefix of the same blocks ("EtherLab" -> EtherLabGetTorqueLimit)
    CIA402_FB_POU_PREFIX = None
    # verbatim #include lines the field bus needs in the generated node
    CIA402_FIELDBUS_INCLUDES = ""
    # confnode parameters that are not axis_s members on this field bus
    CIA402_EXTRA_PARAMS_NO_C = frozenset()

    ConfNodeMethods = [
        {
            "bitmap": "CIA402AxisRef",
            "name": _("Axis Ref"),
            "tooltip": _("Initiate Drag'n drop of Axis ref located variable"),
            "method": "_getCIA402AxisRef",
            "push": True,
        },
        {
            "bitmap": "CIA402NetPos",
            "name": _("Axis Pos"),
            "tooltip": _("Initiate Drag'n drop of Network position located variable"),
            "method": "_getCIA402NetworkPosition",
            "push": True,
        },
    ]

    def GetIconName(self):
        return "CIA402Slave"

# --------------------------------------------------
#    field bus hooks
# --------------------------------------------------

    def CIA402LocationSuffixes(self):
        """
        Where this node's own located variables sit, relative to its confnode
        location.
        @return (network position suffix, axis ref suffix)
        """
        raise NotImplementedError

    def CIA402NetworkPosition(self):
        """
        @return the field bus address of the drive, as an integer
        """
        raise NotImplementedError

    def CIA402ResolveEntry(self, index, subindex, var_type, direction):
        """
        Check an object against the device description of the drive.
        @return the (index, subindex) to use, None when the drive does not
        carry that object as process data
        """
        raise NotImplementedError

    def CIA402SelectVariables(self):
        """
        Decide which of the CiA402 objects this drive really exchanges.
        @return (variables, default_retrieve, default_publish, modeofop_ok)
        variables being a list of (name, index, subindex, type, dir) tuples
        """
        raise NotImplementedError

    def CIA402DeclareEntryPointer(self, var_infos):
        """
        Arrange for var_infos["var_name"] to exist at link time. The generated
        node only refers to it.
        """
        raise NotImplementedError

    def CIA402FieldbusBlockExtraInputs(self):
        """
        @return extra constant inputs the MC_* -> field bus block wrappers must
        set, as BLOCK_INPUT_TEMPLATE dictionaries
        """
        return []

# --------------------------------------------------
#    located variables
# --------------------------------------------------

    def CIA402Locations(self):
        """
        Locations and C symbols of the two located variables every CiA402 node
        publishes : its network position, and the MCL axis reference.
        """
        netpos_suffix, axisref_suffix = self.CIA402LocationSuffixes()
        location = self.GetCurrentLocation()
        dotted = ".".join(map(str, location))
        under = "_".join(map(str, location))
        return {
            "location": under,
            "netpos_location": "%%IW%s%s" % (dotted, netpos_suffix),
            "netpos_symbol": "__IW%s%s" % (under, netpos_suffix.replace(".", "_")),
            "axisref_location": "%%IW%s%s" % (dotted, axisref_suffix),
            "axisref_symbol": "__IW%s%s" % (under, axisref_suffix.replace(".", "_")),
        }

    def CIA402LocationTreeChildren(self, axis_name):
        locations = self.CIA402Locations()
        return [
            {
                "name": name_frmt % (axis_name),
                "type": LOCATION_VAR_INPUT,
                "size": "W",
                "IEC_type": iec_type,
                "var_name": var_name_frmt % axis_name,
                "location": locations[location_key],
                "description": "",
                "children": []
            }
            for name_frmt, iec_type, var_name_frmt, location_key in [
                ("%s Network Position", "UINT", "%s_pos", "netpos_location"),
                ("%s Axis Ref", "AXIS_REF", "%s", "axisref_location")
            ]
        ]

    def StartDragNDrop(self, data):
        data_obj = wx.TextDataObject(str(data))
        dragSource = wx.DropSource(self.GetCTRoot().AppFrame)
        dragSource.SetData(data_obj)
        dragSource.DoDragDrop()

    def _getCIA402NetworkPosition(self):
        self.StartDragNDrop(
            (self.CIA402Locations()["netpos_location"],
             "location", "UINT", self.CTNName() + "_Pos", ""))

    def _getCIA402AxisRef(self):
        self.StartDragNDrop(
            (self.CIA402Locations()["axisref_location"],
             "location", "AXIS_REF", self.CTNName(), ""))

    def CTNGlobalInstances(self):
        current_location = self.GetCurrentLocation()
        return [("%s_%s" % (block_infos["blocktype"],
                            "_".join(map(str, current_location))),
                 "%s%s" % (self.CIA402_FB_POU_PREFIX, block_infos["blocktype"]), "")
                for block_infos in FIELDBUS_INTERFACE_GLOBAL_INSTANCES]

    def CIA402SizeOfType(self, var_type):
        return TYPECONVERSION.get(self.GetCTRoot().GetBaseType(var_type), None)

# --------------------------------------------------
#    C code generation
# --------------------------------------------------

    def CIA402CollectVariables(self):
        """
        Work out everything the generated node depends on : which object
        dictionary entries it exchanges, and the C fragments derived from the
        confnode parameters.

        Kept free of side effects, so that a field bus master needing the same
        list before the node itself is generated can simply ask again.

        @return (variables, completion) where variables is the list of
        var_infos dictionaries, and completion holds the C fragment lists
        """
        location_str = "_".join(map(str, self.GetCurrentLocation()))

        (variables,
         default_variables_retrieve,
         default_variables_publish,
         modeofop_ok) = self.CIA402SelectVariables()

        # the lists are copied, CIA402SelectVariables may well return module
        # level constants
        variables = list(variables)

        completion = {
            "extern_located_variables_declaration": [],
            "entry_variables": [],
            "init_axis_params": [],
            "init_entry_variables": [],
            "default_variables_retrieve": list(default_variables_retrieve),
            "default_variables_publish": list(default_variables_publish),
            "extra_variables_retrieve": [],
            "extra_variables_publish": [],
            "modeofop_homing_method": [],
            "modeofop_computation_mode": [],
        }

        params_no_c = PARAMS_NO_C | set(self.CIA402_EXTRA_PARAMS_NO_C)

        params = self.CTNParams[1].getElementInfos(self.CTNParams[0])
        for param in params["children"]:

            if param["type"] == "boolean":
                cname = param["name"].replace("Enable", "") + "Enabled"
            else:
                cname = param["name"]

            if cname in params_no_c:
                continue
            if param["name"] in EXTRA_NODE_VARIABLES_DICT:
                if param["value"]:
                    extra_variables = EXTRA_NODE_VARIABLES_DICT.get(param["name"])
                    # skip the extra variables the drive does not declare
                    for variable_infos in extra_variables:
                        name, index, subindex, var_type, dir = \
                            variable_infos["description"]
                        entry = self.CIA402ResolveEntry(index, subindex,
                                                        var_type, dir)
                        if entry is None:
                            continue

                        var_infos = {
                            "location": location_str,
                            "name": name
                        }
                        variables.append((name, entry[0], entry[1], var_type, dir))
                        retrieve_template = variable_infos.get("retrieve", DEFAULT_RETRIEVE)
                        publish_template = variable_infos.get("publish", DEFAULT_PUBLISH)

                        if retrieve_template is not None:
                            completion["extra_variables_retrieve"].append(
                                retrieve_template % var_infos)
                        if publish_template is not None:
                            completion["extra_variables_publish"].append(
                                publish_template % var_infos)

            #elif param["value"] is not None:
            if param["value"] is not None:
                param_infos = {
                    "location": location_str,
                    "param_name": param["name"],
                }
                if param["type"] == "boolean":
                    param_infos["param_value"] = {True: "1", False: "0"}[param["value"]]
                    param_infos["param_name"] = param["name"].replace("Enable", "") + "Enabled"
                    if param["value"] == False:
                        continue
                else:
                    param_infos["param_value"] = str(param["value"])
                # param_name = param_name.replace("Enable", "") + "Enabled"
                completion["init_axis_params"].append(
                    "        __CIA402Node_%(location)s.axis->%(param_name)s = %(param_value)s;" % param_infos)

        seen_indexes = set()
        collected = []

        for variable in variables:
            var_infos = dict(list(zip(["name", "index", "subindex", "var_type", "dir"], variable)))

            # add jblee
            if var_infos["index"] in MODE_OF_OPERATION_INDEXES and not modeofop_ok:
                continue

            # a same entry may be described both in NODE_VARIABLES and in the
            # PDO mapping, declare it only once
            key = (var_infos["index"], var_infos["subindex"])
            if key in seen_indexes:
                continue
            seen_indexes.add(key)

            var_infos["location"] = location_str
            var_infos["var_size"] = self.CIA402SizeOfType(var_infos["var_type"])
            var_infos["var_name"] = "__%(dir)s%(var_size)s%(location)s_%(index)d_%(subindex)d" % var_infos

            # add jblee
            if var_infos["index"] == MODE_OF_OPERATION_INDEXES[0]:
                completion["modeofop_homing_method"].append(MODEOFOP_HOMING_METHOD_TEMPLATE)
                completion["modeofop_computation_mode"].append(MODEOFOP_COMPUTATION_MODE_TEMPLATE)

            # the field bus generated file holds the definition, this one only
            # refers to it, so that the symbol is defined exactly once
            completion["extern_located_variables_declaration"].append(
                    "extern IEC_%(var_type)s *%(var_name)s;" % var_infos)
            completion["entry_variables"].append(
                    "    IEC_%(var_type)s *%(name)s;" % var_infos)
            completion["init_entry_variables"].append(
                    "    __CIA402Node_%(location)s.%(name)s = %(var_name)s;" % var_infos)

            collected.append(var_infos)

        return collected, completion

    def CIA402Generate_C(self, buildpath, collected):
        """
        Write the C code of this axis.
        @param collected: what CIA402CollectVariables returned
        @return path of the generated file
        """
        variables, str_completion = collected

        current_location = self.GetCurrentLocation()
        location_str = "_".join(map(str, current_location))
        locations = self.CIA402Locations()

        # Open CIA402 node code template file
        plc_cia402node_filepath = os.path.join(os.path.split(__file__)[0],
                                               "plc_cia402node.c")
        plc_cia402node_file = open(plc_cia402node_filepath, 'r')
        plc_cia402node_code = plc_cia402node_file.read()
        plc_cia402node_file.close()

        str_completion.update({
            "network_position": self.CIA402NetworkPosition(),
            "location": location_str,
            "netpos_symbol": locations["netpos_symbol"],
            "axisref_symbol": locations["axisref_symbol"],
            "fieldbus_includes": self.CIA402_FIELDBUS_INCLUDES,
            "MCL_headers": Headers,
            "fieldbus_interface_declaration": [],
            "fieldbus_interface_definition": [],
        })

        for blocktype_infos in FIELDBUS_INTERFACE_GLOBAL_INSTANCES:
            texts = {
                "blocktype": blocktype_infos["blocktype"],
                "ucase_blocktype": blocktype_infos["blocktype"].upper(),
                "fb_prefix": self.CIA402_FB_PREFIX,
                "location": location_str
            }
            texts["blockname"] = "%(ucase_blocktype)s_%(location)s" % texts

            inputs = [{"input_name": "POS", "input_value": str(self.CIA402NetworkPosition())},
                      {"input_name": "EXECUTE", "input_value": "__GET_VAR(data__->EXECUTE)"}] +\
                     self.CIA402FieldbusBlockExtraInputs() +\
                     [{"input_name": input["name"].upper(),
                       "input_value": "__GET_VAR(data__->%s)" % input["name"].upper()}
                      for input in blocktype_infos["inputs"]]
            input_texts = []
            for input_infos in inputs:
                input_infos.update(texts)
                input_texts.append(BLOCK_INPUT_TEMPLATE % input_infos)
            texts["extract_inputs"] = "\n".join(input_texts)

            outputs = [{"output_name": output} for output in ["DONE", "BUSY", "ERROR"]] + \
                      [{"output_name": output["name"].upper()} for output in blocktype_infos["outputs"]]
            output_texts = []
            for output_infos in outputs:
                output_infos.update(texts)
                output_texts.append(BLOCK_OUTPUT_TEMPLATE % output_infos)
            texts["return_outputs"] = "\n".join(output_texts)

            str_completion["fieldbus_interface_declaration"].append(
                    BLOCK_FUNCTION_TEMPLATE % texts)

            str_completion["fieldbus_interface_definition"].append(
                    BLOCK_FUNTION_DEFINITION_TEMPLATE % texts)

        for var_infos in variables:
            self.CIA402DeclareEntryPointer(var_infos)

        for element in ["extern_located_variables_declaration",
                        "fieldbus_interface_declaration",
                        "fieldbus_interface_definition",
                        "entry_variables",
                        "init_axis_params",
                        "init_entry_variables",
                        "default_variables_retrieve",
                        "default_variables_publish",
                        "extra_variables_retrieve",
                        "extra_variables_publish",
                        "modeofop_homing_method",
                        "modeofop_computation_mode"]:
            str_completion[element] = "\n".join(str_completion[element])

        Gen_CIA402Nodefile_path = os.path.join(buildpath, "cia402node_%s.c" % location_str)
        cia402nodefile = open(Gen_CIA402Nodefile_path, 'w')
        cia402nodefile.write(plc_cia402node_code % str_completion)
        cia402nodefile.close()

        return Gen_CIA402Nodefile_path
