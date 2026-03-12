#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz IDE
#
# Copyright (C) 2013: Laurent BESSARD
# Copyright (C) 2017: Andrey Skvortsov
# Copyright (C) 2025: Edouard TISSERANT
#
# See COPYING file for copyrights details.

import os
from POULibrary import POULibrary
from py_ext.PythonFileCTNMixin import PythonFileCTNMixin
import util.paths as paths


pyext_python_lib_code = open(paths.AbsNeighbourFile(__file__, "py_ext_rt.py"), "r").read()


class PythonLibrary(POULibrary):
    def GetLibraryPath(self):
        return paths.AbsNeighbourFile(__file__, "pous.xml")

    def SupportsTarget(self, target):
        return target.GetTargetName() != "Zephyr"
    
    def Generate_C(self, buildpath, pous_data, IECCFLAGS):

        plc_python_filepath = paths.AbsNeighbourFile(__file__, "plc_python.c")
        plc_python_file = open(plc_python_filepath, 'r')
        plc_python_code = plc_python_file.read()
        plc_python_file.close()

        target_fbs = {"PYTHON_EVAL", "PYTHON_POLL"}

        # Count PYTHON_EVAL/PYTHON_POLL instances, including nested ones.
        # per_type[T] = number of python-eval FBs within one instance of type T.
        per_type = {}
        def count_in_type(type_name):
            key = type_name.upper()
            if key in per_type:
                return per_type[key]
            per_type[key] = 0  # guard against recursion
            count = 0
            for name, _tc, members in pous_data.pous_list:
                if name.upper() == key:
                    for _mname, _flat, dims, base_type in members:
                        multiplicity = 1
                        for d in dims:
                            multiplicity *= d
                        if base_type.upper() in target_fbs:
                            count += multiplicity
                        else:
                            count += multiplicity * count_in_type(base_type)
                    break
            per_type[key] = count
            return count

        python_eval_fb_count = 0
        for _path, _flat_count, dims, base_type in pous_data.instances:
            multiplicity = 1
            for d in dims:
                multiplicity *= d
            if base_type.upper() in target_fbs:
                python_eval_fb_count += multiplicity
            else:
                python_eval_fb_count += multiplicity * count_in_type(base_type)
        python_eval_fb_count = max(1, python_eval_fb_count)

        # prepare python code
        plc_python_code = plc_python_code % {
            "python_eval_fb_count": python_eval_fb_count}

        Gen_Pythonfile_path = os.path.join(buildpath, "py_ext.c")
        pythonfile = open(Gen_Pythonfile_path, 'w', newline='\n')
        pythonfile.write(plc_python_code)
        pythonfile.close()

        runtimefile_path = os.path.join(buildpath, "runtime_00_pyext.py")
        runtimefile = open(runtimefile_path, 'w', newline='\n')
        runtimefile.write(pyext_python_lib_code)
        runtimefile.close()
        return ((["py_ext"], [(Gen_Pythonfile_path, IECCFLAGS)], True), "",
                ("runtime_00_pyext.py", open(runtimefile_path, "rb")))


class PythonFile(PythonFileCTNMixin):

    def GetIconName(self):
        return "Pyfile"
