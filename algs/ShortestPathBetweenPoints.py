# -*- coding: utf-8 -*-
"""
***************************************************************************
    ShortestPathPointToPoint.py
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

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsGeometry,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
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
from ..QneatUtilities import getFeatureFromPoint, checkIfAnalysisCrsEqual

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsPointXY,
        QgsProcessingFeatureSource
        )

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class ShortestPathBetweenPoints(QgsProcessingAlgorithm):

    GRAPH_LAYER = 'GRAPH_LAYER'
    START_POINT = 'START_POINT'
    END_POINT = 'END_POINT'
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
        return ShortestPathBetweenPoints()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_dijkstra_onetoone.svg'))

    def group(self):
        return self.tr('Routing')

    def groupId(self):
        return 'networkanalysis'
    
    def name(self):
        return 'shortestpathpointtopoint'

    def displayName(self):
        return self.tr('Shortest path (point to point)')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements the dijkstra-search to return the <b>shortest path between two points</b> on a given <b>network dataset</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and calculates "\
                "<b>separate entry-</b> and <b>exit-costs</b>. Distances are measured accounting for <b>ellipsoids</b>.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network Layer</li><li>Startpoint coordinates</li><li>Endpoint coordinates</li><li>Cost strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the network edges."\
                "<ul><li>Direction Field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is a layer containing a <b>single linestring</b>, the attributes showcase the"\
                "<ul><li>name and coordinates of startpoint</li><li>name and coordinates of endpoint</li><li>entry-cost to enter network</li><li>exit-cost to exit network</li><li>cost of shortest path on graph</li><li>total cost as sum of all cost elements</li></ul>"

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest path (distance optimization)'),
                           self.tr('Fastest path (time optimization)')
                           ]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Planar'),
                                                self.tr('Ellipsoidal')]
            

        self.addParameter(QgsProcessingParameterFeatureSource(self.GRAPH_LAYER,
                                                              self.tr('Graph layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.START_POINT,
                                                      self.tr('Origin point')))
        self.addParameter(QgsProcessingParameterPoint(self.END_POINT,
                                                      self.tr('Destination point')))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Optimization criterion'),
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
                                                            self.tr('Shortest path layer'),
                                                            Qgis.ProcessingSourceType.VectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))
        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.GRAPH_LAYER, context)
        startPoint: QgsPointXY = self.parameterAsPoint(parameters, self.START_POINT, context, network.sourceCrs())
        endPoint: QgsPointXY = self.parameterAsPoint(parameters, self.END_POINT, context, network.sourceCrs())
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

        input_point_features = [getFeatureFromPoint(0, startPoint),getFeatureFromPoint(1, endPoint)]
        
        build_progress_range = ProgressRange(feedback, 0.0, 0.95)
        
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
        
        origin_analysis_point = core.analysis_points[0]
        destination_analysis_point = core.analysis_points[1]
        origin_vertex_id = origin_analysis_point.graph_vertex_id
        destination_vertex_id = destination_analysis_point.graph_vertex_id

        if origin_vertex_id == destination_vertex_id:
            #only output the entry geometries and costs of the two points
            route_geom: QgsGeometry = origin_analysis_point.graph_entry_geom.union(destination_analysis_point.graph_entry_geom)
            start_entry_cost: float = origin_analysis_point.graph_entry_cost
            cost_on_graph: float = 0.0
            end_exit_cost: float = destination_analysis_point.graph_entry_cost
            total_cost: float = start_entry_cost + end_exit_cost
        else:
            #do routing 
            dijkstra_query = core.calcDijkstra(origin_vertex_id)
            
            if dijkstra_query[0][destination_vertex_id] == -1:
                raise QgsProcessingException(self.tr('Could not find a path from start point to end point - Check your graph or change the input points.'))
            
            route_points: list[QgsPointXY] = list()
            route_points.append(destination_analysis_point.graph_vertex_geom)
            route_points.append(destination_analysis_point.feature.geometry().asPoint())

            current_vertex_id = destination_vertex_id
            while current_vertex_id != origin_vertex_id:
                current_vertex_id = core.qgsgraph.edge(dijkstra_query[0][current_vertex_id]).fromVertex()
                route_points.append(core.qgsgraph.vertex(current_vertex_id).point())

            route_points.append(origin_analysis_point.feature.geometry().asPoint())
            route_points.append(origin_analysis_point.graph_vertex_geom)

            route_geom: QgsGeometry = QgsGeometry().fromPolylineXY(route_points)

            start_entry_cost = origin_analysis_point.graph_entry_cost
            end_exit_cost = destination_analysis_point.graph_entry_cost
            cost_on_graph = dijkstra_query[1][destination_vertex_id]
            total_cost = start_entry_cost + cost_on_graph + end_exit_cost
            
        feat = QgsFeature()
        
        fields = QgsFields()
        fields.append(QgsField('start_id', QVariant.String))
        fields.append(QgsField('start_coordinates', QVariant.String))
        fields.append(QgsField('start_entry_cost', QVariant.Double))
        fields.append(QgsField('end_id', QVariant.String))
        fields.append(QgsField('end_coordinates', QVariant.String))
        fields.append(QgsField('end_exit_cost', QVariant.Double))
        fields.append(QgsField('cost_on_graph', QVariant.Double))
        fields.append(QgsField('total_cost', QVariant.Double))
        feat.setFields(fields)
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, Qgis.WkbType.LineString, analysisCrs)
        
        feat['start_id'] = origin_analysis_point.feature["user_id"]
        feat['start_coordinates'] = startPoint.toString()
        feat['start_entry_cost'] = start_entry_cost
        feat['end_id'] = destination_analysis_point.feature["user_id"]
        feat['end_coordinates'] = endPoint.toString()
        feat['end_exit_cost'] = end_exit_cost
        feat['cost_on_graph'] = cost_on_graph
        feat['total_cost'] = total_cost 
        feat.setGeometry(route_geom)
            
        sink.addFeature(feat, QgsFeatureSink.Flag.FastInsert)
        feedback.setProgress(100)
        results = {}
        results[self.OUTPUT] = dest_id
        return results

