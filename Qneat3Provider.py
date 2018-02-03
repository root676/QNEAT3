# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QNEAT3 - Qgis Network Analysis Toolbox
 A QGIS processing provider for network analysis
 
 Qneat3Provider.py
 
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
 Processing Provider Class
"""

import os

from qgis.core import QgsProcessingProvider
from PyQt5.QtGui import QIcon

from .algs import (
    ShortestPathBetweenPoints,
    OdMatrix 
    )

pluginPath = os.path.split(os.path.dirname(__file__))[0]

class Qneat3Provider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()
        self.alglist = [
            ShortestPathBetweenPoints.ShortestPathBetweenPoints(),
            OdMatrix.OdMatrix()
        ]

    def getAlgs(self):
        return self.alglist

    def id(self, *args, **kwargs):
        return 'qneat3'

    def name(self, *args, **kwargs):
        return 'QNEAT3'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icon.svg'))

    def svgIconPath(self):
        return os.path.join(pluginPath, 'QNEAT3', 'icon.svg')

    def loadAlgorithms(self, *args, **kwargs):
        for alg in self.alglist:
            self.addAlgorithm(alg)