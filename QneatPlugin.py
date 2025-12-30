# -*- coding: utf-8 -*-
"""
***************************************************************************
    QneatPlugin.py
    ---------------------
    
    Date                 : December 2025
    Copyright            : (C) 2025 by Clemens Raffler
    Email                : clemens dot raffler at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


from ..QneatProvider import Qneat3Provider
from qgis.core import QgsApplication

class Qneat3Plugin:
    def __init__(self, iface):
        self.provider = None

    def initProcessing(self):
        self.provider = Qneat3Provider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)


