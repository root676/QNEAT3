# -*- coding: utf-8 -*-
"""
***************************************************************************
    DummyAlgorithm.py
    ---------------------
    Date                 : February 2018
    Copyright            : (C) 2018 by Clemens Raffler
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

__author__ = 'Clemens Raffler'
__date__ = 'February 2018'
__copyright__ = '(C) 2018, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import  QgsProcessingParameterString
from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class DummyAlgorithm(QgisAlgorithm):

    MESSAGE = 'MESSAGE'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_polygon_missing_import.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'DummyAlgorithmIsoAreas'

    def displayName(self):
        return self.tr('[matplotlib not installed] Iso-Area as Polygon')
    
    def print_typestring(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.MESSAGE, self.tr("Help Message"), self.tr("You need to install matplotLib to enable this algorithm."), True, False),True)
    
    def processAlgorithm(self, parameters, context, feedback):
        output_message = self.parameterAsString(parameters, self.MESSAGE, context)
        feedback.pushInfo("You need to install matplotlib to enable this algorithm.")

        results = {}
        results[self.MESSAGE] = output_message
        return results

