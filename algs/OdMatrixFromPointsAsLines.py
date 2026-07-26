# -*- coding: utf-8 -*-
"""
***************************************************************************
    OdMatrixFromPointsAsLines.py
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
from __future__ import annotations

__author__ = 'Clemens Raffler'
__date__ = 'December 2025'
__copyright__ = '(C) 2025, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString)

from qgis.analysis import (QgsVectorLayerDirector)

from ..QneatFramework import QneatCore, OptimizationStrategy, MatrixType, ProgressRange
from ..QneatUtilities import getOdMatrixFields, checkIfAnalysisCrsEqual

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsFields,
        QgsProcessingFeatureSource
        )

class OdMatrixFromPointsAsLines(QgsProcessingAlgorithm):

    GRAPH_LAYER = 'GRAPH_LAYER'
    POINTS = 'POINTS'
    ID_FIELD = 'ID_FIELD'    
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
    MATRIX_GEOMETRY_TYPE = 'MATRIX_GEOMETRY_TYPE'

    def __init__(self):
        super().__init__()

    def createInstance(self):
        return OdMatrixFromPointsAsLines()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)
    
    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_matrix.svg'))

    def group(self):
        return self.tr('Distance Matrices')

    def groupId(self):
        return 'networkbaseddistancematrices'
    
    def name(self):
        return 'OdMatrixFromPointsAsLines'

    def displayName(self):
        return self.tr('OD matrix from points as lines (n:n)')

    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements OD-matrix analysis to return the <b>matrix of origin-destination pairs as lines yielding network based costs</b> on a given <b>network dataset between the elements of one point layer(n:n)</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>). Distances are measured accounting for <b>ellipsoids</b>, entry-, exit-, network- and total costs are listed in the result attribute-table.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Point layer</li><li>Unique point ID field (numerical)</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the network's edges."\
                "<ul><li>Matrix output type (straight line between origin and destination, or the actual routed path)</li><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one layer:"\
                "<ul><li>OD-matrix as lines (or routed paths, depending on matrix output type) with network based distances as attributes</li></ul>"

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest path (distance optimization)'),
                           self.tr('Fastest path (time optimization)')
                           ]

        self.MATRIX_GEOMETRY_TYPES = [self.tr('Line'),
                                      self.tr('Route')]

        self.addParameter(QgsProcessingParameterFeatureSource(self.GRAPH_LAYER,
                                                              self.tr('Graph layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.POINTS,
                                                              self.tr('Point layer'),
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Point ID field'),
                                                       None,
                                                       self.POINTS,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization criterion'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
        params.append(QgsProcessingParameterEnum(self.MATRIX_GEOMETRY_TYPE,
                                                 self.tr('Matrix output type'),
                                                 self.MATRIX_GEOMETRY_TYPES,
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


        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output OD matrix'), Qgis.ProcessingSourceType.VectorLine), True)

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))
        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.GRAPH_LAYER, context)
        points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.POINTS, context)
        id_field: str = self.parameterAsString(parameters, self.ID_FIELD, context)
        strategy: OptimizationStrategy = OptimizationStrategy(self.parameterAsEnum(parameters, self.STRATEGY, context))
        # MATRIX_GEOMETRY_TYPES enum only offers 'Line'/'Route' (indices 0/1), which map to
        # MatrixType.LINE/MatrixType.ROUTE (values 1/2) - MatrixType.TABLE is not selectable here.
        matrix_type: MatrixType =  MatrixType(self.parameterAsEnum(parameters, self.MATRIX_GEOMETRY_TYPE, context) + 1)


        directionFieldName: int = self.parameterAsString(parameters, self.DIRECTION_FIELD, context)
        forwardValue: str = self.parameterAsString(parameters, self.VALUE_FORWARD, context) 
        backwardValue: str = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) 
        bothValue: str = self.parameterAsString(parameters, self.VALUE_BOTH, context) 
        defaultDirection: int = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) 
        speedFieldName: str = self.parameterAsString(parameters, self.SPEED_FIELD, context) 
        defaultSpeed: float = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) 
        tolerance: float = self.parameterAsDouble(parameters, self.TOLERANCE, context) 

        #check if network and points have the same crs
        if checkIfAnalysisCrsEqual([network.sourceCrs(), points.sourceCrs()]):
            self.analysis_crs = network.sourceCrs()
        else:
            raise QgsProcessingException(f"Coordinate reference system (CRS) of graph is {network.sourceCrs().authid()} and doesn't match up with the CRS of the point layer ({points.sourceCrs().authid()}). Reproject so that the analysis layers CRSs match up.")

        input_pointlist: list[QgsFeature] = [f for f in points.getFeatures()]
        
        build_progress_range = ProgressRange(feedback, 0.0, 0.5)
        
        core = QneatCore(network, 
                         input_pointlist, 
                         strategy, 
                         speedFieldName, 
                         defaultSpeed,
                         tolerance,
                         build_progress_range,
                         directionFieldName, 
                         forwardValue, 
                         backwardValue, 
                         bothValue, 
                         defaultDirection)
        
        total_workload = float(pow(len(core.analysis_points),2))

        #create output sink
        output_fields: QgsFields = getOdMatrixFields(points, id_field, points, id_field)
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, output_fields, Qgis.WkbType.LineString, network.sourceCrs())

        feedback.pushInfo(f"{int(total_workload)} od pairs will be routed")
        od_progress_range = ProgressRange(feedback, 0.5, 1.0)

        i: int = 0
        for origin_point in core.analysis_points:
            tree, cost = core.calcDijkstra(origin_point.graph_vertex_id)
            for destination_point in core.analysis_points:
                feat = core.queryOdPair(tree, cost, origin_point, id_field, destination_point, id_field, matrix_type)
                sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)  

                i += 1
                od_progress_range.feedback().setProgress(i/total_workload)
                if od_progress_range.feedback().isCanceled():
                    raise QgsProcessingException('Calculation of OD matrix was canceled.')

        results = {}
        results[self.OUTPUT] = dest_id
        return results

