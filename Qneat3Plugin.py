# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QNEAT3 - Qgis Network Analysis Toolbox
 A QGIS processing provider for network analysis
 
 Qneat3Plugin.py
 
-------------------
        begin                : 2018-01-15
        copyright            : (C) 2018 by Clemens Raffler
        email                : clemens.raffler@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 QNEAT3 Plugin Class
"""


from QNEAT3.Qneat3Provider import Qneat3Provider
from qgis.core import QgsApplication

class Qneat3Plugin:
    def __init__(self, iface):
        self.provider = Qneat3Provider()

    def initGui(self):
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)


