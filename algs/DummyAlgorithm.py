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

    MESSAGE1 = 'MESSAGE1'
    MESSAGE2 = 'MESSAGE2'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_polygon_missing_import.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'DummyAlgorithmIsoAreas'

    def displayName(self):
        return self.tr('[matplotlib not installed] Iso-Area as Polygon (open for install help)')
    
    def print_typestring(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(self.MESSAGE1, self.tr("<b>[matplotlib not installed]</b><br>Some QNEAT3 isochrone area algorithms require <b>matplotlib</b> so that they can be executed properly. Depending on your operating system you may install matplotlib <b>manually</b> using the following options:<br><br> <b>Windows</b>: <ol><li>Open the <i>OSGeo4W shell</i> that has been installed alongside QGIS (click <i>Start</i> - type <i>OSGeo4W Shell</i> - hit Enter)</li><li>Copy the command displayed in the textbox below and paste it into the shell</li><li>Accept the installation by typing 'yes' when prompted</li></ol>"), self.tr('python-qgis -m pip install matplotlib'), False, False))
        self.addParameter(QgsProcessingParameterString(self.MESSAGE2, self.tr("<br><b>Linux</b><ol><li>Open a terminal</li><li>Copy the command displayed below and paste it into the terminal, then hit Enter and confirm installation with 'yes' when prompted</li></ol>"), self.tr("pip install matplotlib"),False,False))
        
    def processAlgorithm(self, parameters, context, feedback):
        output_message = self.parameterAsString(parameters, self.MESSAGE1, context)
        feedback.pushInfo("You need to install matplotlib to enable this algorithm.")

        results = {}
        results[self.MESSAGE1] = 'Refer to the help provided in the algorithm.'
        return results

