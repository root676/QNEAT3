# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsCostSurfaceFromPoint.py
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

__author__ = 'Clemens Raffler'
__date__ = 'December 2025'
__copyright__ = '(C) 2025, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis,
                       QgsField,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterRasterDestination)

from qgis.analysis import QgsVectorLayerDirector

from ..QneatFramework import QneatCore, EntryCostCalculationMethod, OptimizationStrategy, ProgressRange
from ..QneatUtilities import checkIfAnalysisCrsEqual, getFieldDatatype

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsFeature,
        QgsFields,
        QgsProcessingFeatureSource
        )


pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

class IsoAreaAsInterpolationFromLayer(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    ORIGIN_POINTS = 'ORIGIN_POINTS'
    ID_FIELD = 'ID_FIELD'
    MAX_COST = "MAX_COST"
    CELL_SIZE = "CELL_SIZE"
    STRATEGY = 'STRATEGY'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()
    
    def createInstance(self):
        return IsoAreaAsInterpolationFromLayer()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_interpolation_multiple.png'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaascostsurfacefromlayer'

    def displayName(self):
        return self.tr('Iso-area as cost surface (from layer)')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-area analysis to return the <b>network-distance interpolation for a maximum cost level</b> on a given <b>network dataset for a layer of points</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Startpoint layer</li><li>Unique point ID field (numerical)</li><li>Maximum cost level for iso-area</li><li>cellsize in meters (increase default when analyzing larger networks)</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is a cost surface raster"

    def initAlgorithm(self):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest Path (distance optimization)'),
                           self.tr('Fastest Path (time optimization)')]
            
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ORIGIN_POINTS,
                                                              self.tr('Start points'),
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Unique point ID field'),
                                                       None,
                                                       self.ORIGIN_POINTS,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_COST,
                                                   self.tr('Size of iso-area (distance in network csr units or time in seconds)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   2500.0, False, 0))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE,
                                                    self.tr('Cellsize of interpolation raster'),
                                                    Qgis.ProcessingNumberParameterType.Double,
                                                    10, False, 1))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
        params.append(QgsProcessingParameterField(self.DIRECTION_FIELD,
                                                  self.tr('Direction field'),
                                                  None,
                                                  self.INPUT,
                                                  optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_FORWARD,
                                                   self.tr('Value for forward direction'),
                                                   optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_BACKWARD,
                                                   self.tr('Value for backward direction'),
                                                   optional=True))
        params.append(QgsProcessingParameterString(self.VALUE_BOTH,
                                                   self.tr('Value for both directions'),
                                                   optional=True))
        params.append(QgsProcessingParameterEnum(self.DEFAULT_DIRECTION,
                                                 self.tr('Default direction'),
                                                 list(self.DIRECTIONS.keys()),
                                                 defaultValue=2))
        params.append(QgsProcessingParameterField(self.SPEED_FIELD,
                                                  self.tr('Speed field'),
                                                  None,
                                                  self.INPUT,
                                                  optional=True))
        params.append(QgsProcessingParameterNumber(self.DEFAULT_SPEED,
                                                   self.tr('Default speed (km/h)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   5.0, False, 0))
        params.append(QgsProcessingParameterNumber(self.TOLERANCE,
                                                   self.tr('Topology tolerance'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   0.0, False, 0))

        for p in params:
            p.setFlags(p.flags() | Qgis.ProcessingParameterFlag.Advanced)
            self.addParameter(p)
        
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, self.tr('Output interpolation')))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))

        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.INPUT, context) 
        origin_points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.ORIGIN_POINTS, context)
        id_field: str = self.parameterAsString(parameters, self.ID_FIELD, context) 
        max_cost: float = self.parameterAsDouble(parameters, self.MAX_COST, context)
        cell_size: float = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        strategy: OptimizationStrategy = OptimizationStrategy(self.parameterAsEnum(parameters, self.STRATEGY, context))

        directionFieldName: str = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) 
        forwardValue: str = self.parameterAsString(parameters, self.VALUE_FORWARD, context)
        backwardValue: str = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) 
        bothValue: str = self.parameterAsString(parameters, self.VALUE_BOTH, context)
        defaultDirection: int = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) 
        speedFieldName: str = self.parameterAsString(parameters, self.SPEED_FIELD, context)
        defaultSpeed: float = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) 
        tolerance: float = self.parameterAsDouble(parameters, self.TOLERANCE, context) 
        output_path: str = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if not checkIfAnalysisCrsEqual(network.sourceCrs, context.project().crs()):
            raise QgsProcessingException(f"Coordinate reference systems of graph is {network.sourceCrs().authid()} and doesn't match up with the coordinate reference system of the project ({context.project().crs().authid()}). Reproject so that the CRSs of analysis layers match up.")
        
        #unpack all points into one list
        input_point_features: list[QgsFeature] = []

        source_point_fields = QgsFields()
        source_point_fields.append(QgsField('fid', QVariant.LongLong))
        source_point_fields.append(QgsField('user_id'), getFieldDatatype(origin_points, id_field))
        source_point_fields.append(QgsField('type', QVariant.String))

        for f in origin_points.getFeatures():
            source_feat = QgsFeature(source_point_fields)
            source_feat["fid"] = f.id()
            source_feat["user_id"] = f[id_field]
            source_feat.setGeometry(f.geometry())
        
            input_point_features.append(source_feat)
        
        build_progress_range = ProgressRange(feedback, 0.0, 0.33)
        
        core = QneatCore(network, 
                         input_point_features, 
                         strategy, 
                         speedFieldName, 
                         defaultSpeed, 
                         tolerance, 
                         EntryCostCalculationMethod.PLANAR, 
                         build_progress_range, 
                         directionFieldName, 
                         forwardValue, 
                         backwardValue, 
                         bothValue, 
                         defaultDirection)
        
        iso_progress_range = ProgressRange(feedback, 0.33, 0.66)
        iso_points = core.calcIsoPoints('user_id', max_cost, iso_progress_range)

        tin_progress_range = ProgressRange(feedback, 0.66, 1.0)
        core.calcIsoTinInterpolation(iso_points, cell_size, output_path, tin_progress_range )

        results = {}
        results[self.OUTPUT] = output_path
        return results

