#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz
#
# Copyright (C) 2011-2014: Laurent BESSARD, Edouard TISSERANT
#                          RTES Lab : CRKim, JBLee, youcu
#                          Higen Motor : Donggu Kang
#
# See COPYING file for copyrights details.

import os

import util.paths as paths
from util.BitmapLibrary import AddBitmapFolder

AddBitmapFolder(os.path.join(paths.AbsDir(__file__), "images"))
