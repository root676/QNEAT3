# -*- coding: utf-8 -*-
"""
***************************************************************************
    OdMatrixFromPointsAsTable.py
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

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsWkbTypes,
                       QgsFields,
                       QgsField,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterDefinition)

from qgis.analysis import (QgsVectorLayerDirector)

from ..QneatFramework import QneatCore, OptimizationStrategy, MatrixType, ProgressRange
from ..QneatUtilities import checkIfAnalysisCrsEqual, getOdMatrixFields

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsProcessingFeatureSource
        )

class OdMatrixFromPointsAsTable(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    POINTS = 'POINTS'
    ID_FIELD = 'ID_FIELD'    
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

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_matrix.svg'))

    def group(self):
        return self.tr('Distance Matrices')

    def groupId(self):
        return 'networkbaseddistancematrices'
    
    def name(self):
        return 'OdMatrixFromPointsAsTable'

    def displayName(self):
        return self.tr('OD Matrix from Points as Table (n:n)')

    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements OD-matrix analysis to return the <b>matrix of origin-destination pairs as table yielding network based costs</b> on a given <b>network dataset between the elements of one point layer(n:n)</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>). Distances are measured accounting for <b>ellipsoids</b>, entry-, exit-, network- and total costs are listed in the result attribute-table.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Point layer</li><li>Unique point ID field (numerical)</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one table:"\
                "<ul><li>OD-matrix as table with network based distances as attributes</li></ul>"  
    
    def __init__(self):
        super().__init__()

    def initAlgorithm(self):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest path (distance optimization)'),
                           self.tr('Fastest path (time optimization)')]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Planar'),
                                                self.tr('Ellipsoidal')]


        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network layer'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.POINTS,
                                                              self.tr('Point layer'),
                                                              [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Unique point ID field'),
                                                       None,
                                                       self.POINTS,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
        params.append(QgsProcessingParameterEnum(self.ENTRY_COST_CALCULATION_METHOD,
                                         self.tr('Entry cost calculation method'),
                                         self.ENTRY_COST_CALCULATION_METHODS,
                                         defaultValue=0))
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
                                                   QgsProcessingParameterNumber.Double,
                                                   5.0, False, 0, 99999999.99))
        params.append(QgsProcessingParameterNumber(self.TOLERANCE,
                                                   self.tr('Topology tolerance'),
                                                   QgsProcessingParameterNumber.Double,
                                                   0.0, False, 0, 99999999.99))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output OD matrix'), QgsProcessing.TypeVectorLine), True)

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))
        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.INPUT, context)
        points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.POINTS, context)
        id_field: str = self.parameterAsString(parameters, self.ID_FIELD, context)
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

        #check if network and points have the same crs
        if checkIfAnalysisCrsEqual(list(network.sourceCrs(), points.sourceCrs())):
            self.analysis_crs = network.sourceCrs()
        else:
            raise QgsProcessingException(f"Coordinate reference systems of graph is {network.sourceCrs().authid()} doesn't match up with the coordinate reference system of the point layer (origin points: {points.sourceCrs().authid()}) Reproject all datasets so that their CRSs match up.")


        input_pointlist: list[QgsFeature] = [f for f in points.getFeatures()]
        
        build_progress_range = ProgressRange(feedback, 0.0, 0.5)

        core = QneatCore(network, 
                         input_pointlist, 
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
        
        total_workload = float(pow(len(core.analysis_points),2))

        #create output sink
        output_fields: QgsFields = getOdMatrixFields(points, id_field, points, id_field)
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, QgsWkbTypes.NoGeometry, network.sourceCrs())
        
        feedback.pushInfo(f"{int(total_workload)} od pairs will be routed")
        od_progress_range = ProgressRange(feedback, 0.5, 1.0)
        
        i: int = 0
        for origin_point in core.analysis_points:
            tree, cost = core.calcDijkstra(origin_point.graph_vertex_id)
            for destination_point in core.analysis_points:

                feat = core.queryOdPair(tree, cost, origin_point, id_field, destination_point, id_field, MatrixType.TABLE)                
                sink.addFeature(feat, QgsFeatureSink.FastInsert)  
                i+=i
                
                od_progress_range.feedback().setProgress(i/total_workload)

        results = {}
        results[self.OUTPUT] = dest_id
        return results

