# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsPointcloudFromPoint.py
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
                       QgsFeatureSink,
                       QgsFields,
                       QgsField,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterPoint,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink)

from qgis.analysis import QgsVectorLayerDirector

from ..QneatFramework import QneatCore, OptimizationStrategy, ProgressRange
from ..QneatUtilities import checkIfAnalysisCrsEqual, getFeatureFromPoint

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsFields,
        QgsPointXY,
        QgsProcessingFeatureSource
        )

class IsoAreaAsPointcloudFromPoint(QgsProcessingAlgorithm):

    GRAPH_LAYER = 'GRAPH_LAYER'
    ORIGIN_POINT = 'ORIGIN_POINT'
    MAX_COST = "MAX_COST"
    STRATEGY = 'STRATEGY'
    ENTRY_COST_CALCULATION_METHOD = 'ENTRY_COST_CALCULATION_METHOD'
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
        return IsoAreaAsPointcloudFromPoint()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_points.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaaspointcloudfrompoint'

    def displayName(self):
        return self.tr('Iso-Area as Pointcloud (from Point)')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-pointcloud analysis to return all <b>network nodes reachable within a maximum cost level as pointcloud</b> on a given <b>network dataset for a manually chosen point</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Origin Point</li><li>Unique point ID field (numerical)</li><li>Maximum cost level for Iso-Area</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one layer:"\
                "<ul><li>Point layer of reachable network nodes</li></ul><br>"\
                "You may use the output pointcloud as input for further analyses."

    def initAlgorithm(self):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest Path (distance optimization)'),
                           self.tr('Fastest Path (time optimization)')]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Planar'),
                                                self.tr('Ellipsoidal')]

        self.addParameter(QgsProcessingParameterFeatureSource(self.GRAPH_LAYER,
                                                              self.tr('Network Layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.ORIGIN_POINT,
                                                      self.tr('Origin point')))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_COST,
                                                   self.tr('Size of Iso-Area (distance in network csr units or time value in seconds)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   2500.0, False, 0))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization Criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
        params.append(QgsProcessingParameterEnum(self.ENTRY_COST_CALCULATION_METHOD,
                                                 self.tr('Entry Cost calculation method'),
                                                 self.ENTRY_COST_CALCULATION_METHODS,
                                                 defaultValue=0))
        params.append(QgsProcessingParameterField(self.DIRECTION_FIELD,
                                                  self.tr('Direction field'),
                                                  None,
                                                  self.GRAPH_LAYER,
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
                                                  self.GRAPH_LAYER,
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
        
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,
                                                            self.tr('Output Pointcloud'),
                                                            Qgis.ProcessingSourceType.VectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))

        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.GRAPH_LAYER, context) 
        origin_point: QgsPointXY = self.parameterAsPoint(parameters, self.ORIGIN_POINT, context, network.sourceCrs()) 
        max_cost: float = self.parameterAsDouble(parameters, self.MAX_COST, context)
        strategy: OptimizationStrategy = OptimizationStrategy(self.parameterAsEnum(parameters, self.STRATEGY, context))

        entry_cost_calc_method: int = self.parameterAsEnum(parameters, self.ENTRY_COST_CALCULATION_METHOD, context)
        directionFieldName: str = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) 
        forwardValue: str = self.parameterAsString(parameters, self.VALUE_FORWARD, context) 
        backwardValue: str = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) 
        bothValue: str = self.parameterAsString(parameters, self.VALUE_BOTH, context)
        defaultDirection: int = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) 
        speedFieldName: str = self.parameterAsString(parameters, self.SPEED_FIELD, context)
        defaultSpeed: float = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) 
        tolerance: float = self.parameterAsDouble(parameters, self.TOLERANCE, context) 

        if checkIfAnalysisCrsEqual(network.sourceCrs, context.project().crs()):
            analysisCrs = network.sourceCrs()
        else:
            raise QgsProcessingException(f"Coordinate reference systems of graph is {network.sourceCrs().authid()} and doesn't match up with the coordinate reference system of the project ({context.project().crs().authid()}). Reproject so that the CRSs of analysis layers match up.")
  
        input_point_features = [getFeatureFromPoint(0, origin_point)]

        build_progress_range = ProgressRange(feedback, 0.0, 0.5)

        core = QneatCore(network, 
                         input_point_features, 
                         strategy, 
                         speedFieldName, 
                         defaultSpeed, 
                         tolerance, 
                         entry_cost_calc_method, 
                         build_progress_range, 
                         directionFieldName, 
                         forwardValue, 
                         backwardValue, 
                         bothValue, 
                         defaultDirection)
        
        fields = QgsFields()
        fields.append(QgsField('vertex_id', QVariant.Int))
        fields.append(QgsField('cost', QVariant.Double))
        fields.append(QgsField('origin_point_id', QVariant.Int))
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, Qgis.WkbType.PointM, analysisCrs)

        iso_progress_range = ProgressRange(feedback, 0.5, 1.0)
        iso_points = core.calcIsoPoints('user_id', max_cost, iso_progress_range)
        
        sink.addFeatures(iso_points, QgsFeatureSink.Flag.FastInsert)
        
        results = {}
        results[self.OUTPUT] = dest_id
        return results

