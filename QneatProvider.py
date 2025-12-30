# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QNEAT3 - Qgis Network Analysis Toolbox 3
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
"""

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

#import all algorithms that work with basic qgis modules
from .algs import ( 
    ShortestPathBetweenPoints,
    IsoAreaAsPointcloudFromPoint,
    IsoAreaAsPointcloudFromLayer, 
    IsoAreaAsInterpolationFromPoint,
    IsoAreaAsInterpolationFromLayer,
    IsoAreaAsContoursFromPoint,
    IsoAreaAsContoursFromLayer,
    IsoAreaAsPolygonsFromPoint,
    IsoAreaAsPolygonsFromLayer,
    OdMatrixFromPointsAsLines, 
    OdMatrixFromPointsAsTable, 
    OdMatrixFromLayersAsTable, 
    OdMatrixFromLayersAsLines
    )

pluginPath = os.path.split(os.path.dirname(__file__))[0]

class Qneat3Provider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def id(self):
        return 'qneat3'

    def name(self):
        return 'QNEAT3 - Qgis Network Analysis Toolbox'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icon_qneat3.svg'))

    def svgIconPath(self):
        return os.path.join(pluginPath, 'QNEAT3', 'icon_qneat3.svg')

    def loadAlgorithms(self):
        self.addAlgorithm(ShortestPathBetweenPoints.ShortestPathBetweenPoints())
        self.addAlgorithm(IsoAreaAsPointcloudFromPoint.IsoAreaAsPointcloudFromPoint())
        self.addAlgorithm(IsoAreaAsPointcloudFromLayer.IsoAreaAsPointcloudFromLayer())
        self.addAlgorithm(IsoAreaAsInterpolationFromPoint.IsoAreaAsInterpolationFromPoint())
        self.addAlgorithm(IsoAreaAsInterpolationFromLayer.IsoAreaAsInterpolationFromLayer())
        self.addAlgorithm(IsoAreaAsContoursFromPoint.IsoAreaAsContoursFromPoint())
        self.addAlgorithm(IsoAreaAsPolygonsFromPoint.IsoAreaAsPolygonsFromPoint())
        self.addAlgorithm(IsoAreaAsPolygonsFromLayer.IsoAreaAsPolygonsFromLayer())
        self.addAlgorithm(IsoAreaAsContoursFromLayer.IsoAreaAsContoursFromLayer())
        self.addAlgorithm(OdMatrixFromPointsAsLines.OdMatrixFromPointsAsLines())
        self.addAlgorithm(OdMatrixFromPointsAsTable.OdMatrixFromPointsAsTable())
        self.addAlgorithm(OdMatrixFromLayersAsTable.OdMatrixFromLayersAsTable())
        self.addAlgorithm(OdMatrixFromLayersAsLines.OdMatrixFromLayersAsLines())