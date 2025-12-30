# -*- coding: utf-8 -*-
"""
***************************************************************************
    QneatProvider.py
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

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

#import all algorithms that work with basic qgis modules
from .algs import ( 
    IsoAreaAsCostSurfaceFromPoint,
    ShortestPathBetweenPoints,
    IsoAreaAsPointcloudFromPoint,
    IsoAreaAsPointcloudFromLayer, 
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

class QneatProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()

    def id(self):
        return 'qneat'

    def name(self):
        return 'QNEAT - Qgis Network Analysis Toolbox'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT', 'icon_qneat.svg'))

    def svgIconPath(self):
        return os.path.join(pluginPath, 'QNEAT', 'icon_qneat.svg')

    def loadAlgorithms(self):
        self.addAlgorithm(ShortestPathBetweenPoints.ShortestPathBetweenPoints())
        self.addAlgorithm(IsoAreaAsPointcloudFromPoint.IsoAreaAsPointcloudFromPoint())
        self.addAlgorithm(IsoAreaAsPointcloudFromLayer.IsoAreaAsPointcloudFromLayer())
        self.addAlgorithm(IsoAreaAsCostSurfaceFromPoint.IsoAreaAsInterpolationFromPoint())
        self.addAlgorithm(IsoAreaAsInterpolationFromLayer.IsoAreaAsInterpolationFromLayer())
        self.addAlgorithm(IsoAreaAsContoursFromPoint.IsoAreaAsContoursFromPoint())
        self.addAlgorithm(IsoAreaAsPolygonsFromPoint.IsoAreaAsPolygonsFromPoint())
        self.addAlgorithm(IsoAreaAsPolygonsFromLayer.IsoAreaAsPolygonsFromLayer())
        self.addAlgorithm(IsoAreaAsContoursFromLayer.IsoAreaAsContoursFromLayer())
        self.addAlgorithm(OdMatrixFromPointsAsLines.OdMatrixFromPointsAsLines())
        self.addAlgorithm(OdMatrixFromPointsAsTable.OdMatrixFromPointsAsTable())
        self.addAlgorithm(OdMatrixFromLayersAsTable.OdMatrixFromLayersAsTable())
        self.addAlgorithm(OdMatrixFromLayersAsLines.OdMatrixFromLayersAsLines())