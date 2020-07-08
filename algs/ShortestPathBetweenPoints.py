# -*- coding: utf-8 -*-
"""
***************************************************************************
    ShortestPathPointToPoint.py
    ---------------------

    Partially based on QGIS3 network analysis algorithms.
    Copyright 2016 Alexander Bruy

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
from collections import OrderedDict

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsWkbTypes,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsGeometry,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterPoint,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeatureFromPointParameter

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class ShortestPathBetweenPoints(QgisAlgorithm):

    INPUT = 'INPUT'
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
                "This algorithm implements the Dijkstra-Search to return the <b>shortest path between two points</b> on a given <b>network dataset</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and calculates "\
                "<b>separate entry-</b> and <b>exit-costs</b>. Distances are measured accounting for <b>ellipsoids</b>.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following Parameters must be set to run the algorithm:"\
                "<ul><li>Network Layer</li><li>Startpoint Coordinates</li><li>Endpoint Coordinates</li><li>Path type to calculate</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction Field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed Field</li><li>Default Speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is a Layer containing a <b>single linestring</b>, the attributes showcase the"\
                "<ul><li>Name and coordinates of startpoint</li><li>Name and coordinates of endpoint</li><li>Entry-cost to enter network</li><li>Exit-cost to exit network</li><li>Cost of shortest path on graph</li><li>Total cost as sum of all cost elements</li></ul>"\
                "Shortest distance cost units are meters and Fastest time cost units are seconds."

    def msg(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest distance'),
                           self.tr('Fastest time')
                           ]

        self.ENTRY_COST_CALCULATION_METHODS = [self.tr('Ellipsoidal'),
                                       self.tr('Planar (only use with projected CRS)')]


        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network Layer'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.START_POINT,
                                                      self.tr('Start point')))
        self.addParameter(QgsProcessingParameterPoint(self.END_POINT,
                                                      self.tr('End point')))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Path type to calculate'),
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
                                                  self.tr('Speed field (km/h)'),
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
                                                   0.00001, False, 0, 99999999.99))

        for p in params:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,
                                                            self.tr('Shortest Path Layer'),
                                                            QgsProcessing.TypeVectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr("[QNEAT3Algorithm] This is a QNEAT3 Algorithm: '{}'".format(self.displayName())))
        feedback.pushInfo(self.tr('[QNEAT3Algorithm] Initializing Variables'))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        startPoint = self.parameterAsPoint(parameters, self.START_POINT, context, network.sourceCrs()) #QgsPointXY
        endPoint = self.parameterAsPoint(parameters, self.END_POINT, context, network.sourceCrs()) #QgsPointXY
        strategy = self.parameterAsEnum(parameters, self.STRATEGY, context) #int

        entry_cost_calc_method = self.parameterAsEnum(parameters, self.ENTRY_COST_CALCULATION_METHOD, context) #int
        directionFieldName = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) #str (empty if no field given)
        forwardValue = self.parameterAsString(parameters, self.VALUE_FORWARD, context) #str
        backwardValue = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) #str
        bothValue = self.parameterAsString(parameters, self.VALUE_BOTH, context) #str
        defaultDirection = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) #int
        speedFieldName = self.parameterAsString(parameters, self.SPEED_FIELD, context) #str
        defaultSpeed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) #float
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context) #float

        analysisCrs = network.sourceCrs()

        if analysisCrs.isGeographic():
            raise QgsProcessingException('QNEAT3 algorithms are designed to work with projected coordinate systems. Please use a projected coordinate system (eg. UTM zones) instead of geographic coordinate systems (eg. WGS84)!')

        if analysisCrs != startPoint.sourceCrs() | startPoint.sourceCrs() != endPoint.sourceCrs():
            raise QgsProcessingException('QNEAT3 algorithms require that all inputs to be the same projected coordinate reference system.')

        input_qgspointxy_list = [startPoint,endPoint]
        input_points = [getFeatureFromPointParameter(startPoint),getFeatureFromPointParameter(endPoint)]

        feedback.pushInfo(self.tr('[QNEAT3Algorithm] Building Graph'))
        feedback.setProgress(10)
        net = Qneat3Network(network, input_qgspointxy_list, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
        feedback.setProgress(40)

        list_analysis_points = [Qneat3AnalysisPoint("point", feature, "point_id", net, net.list_tiedPoints[i], entry_cost_calc_method, feedback) for i, feature in enumerate(input_points)]

        start_vertex_idx = list_analysis_points[0].network_vertex_id
        end_vertex_idx = list_analysis_points[1].network_vertex_id

        feedback.pushInfo("[QNEAT3Algorithm] Calculating shortest path...")
        feedback.setProgress(50)

        dijkstra_query = net.calcDijkstra(start_vertex_idx,0)

        if dijkstra_query[0][end_vertex_idx] == -1:
            raise QgsProcessingException(self.tr('Could not find a path from start point to end point - Check your graph or alter the input points.'))

        path_elements = [list_analysis_points[1].point_geom] #start route with the endpoint outside the network
        path_elements.append(net.network.vertex(end_vertex_idx).point()) #then append the corresponding vertex of the graph

        count = 1
        current_vertex_idx = end_vertex_idx
        while current_vertex_idx != start_vertex_idx:
            current_vertex_idx = net.network.edge(dijkstra_query[0][current_vertex_idx]).fromVertex()
            path_elements.append(net.network.vertex(current_vertex_idx).point())


            count = count + 1
            if count%10 == 0:
                feedback.pushInfo("[QNEAT3Algorithm] Taversed {} Nodes...".format(count))

        path_elements.append(list_analysis_points[0].point_geom) #end path with startpoint outside the network
        feedback.pushInfo("[QNEAT3Algorithm] Total number of Nodes traversed: {}".format(count+1))
        path_elements.reverse() #reverse path elements because it was built from end to start

        start_entry_cost = list_analysis_points[0].entry_cost
        end_exit_cost = list_analysis_points[1].entry_cost
        cost_on_graph = dijkstra_query[1][end_vertex_idx]
        total_cost = start_entry_cost + cost_on_graph + end_exit_cost

        feedback.pushInfo("[QNEAT3Algorithm] Writing path-feature...")
        feedback.setProgress(80)
        feat = QgsFeature()

        fields = QgsFields()
        fields.append(QgsField('start', QVariant.String, '', 254, 0))
        fields.append(QgsField('start_entry_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('end', QVariant.String, '', 254, 0))
        fields.append(QgsField('end_exit_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('cost_on_graph', QVariant.Double, '', 20, 7))
        fields.append(QgsField('total_cost', QVariant.Double, '', 20, 7))
        feat.setFields(fields)

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.LineString, network.sourceCrs())

        feat['start'] = startPoint.toString()
        feat['start_entry_cost'] = start_entry_cost
        feat['end'] = endPoint.toString()
        feat['end_exit_cost'] = end_exit_cost
        feat['cost_on_graph'] = cost_on_graph
        feat['total_cost'] = total_cost
        geom = QgsGeometry.fromPolylineXY(path_elements)
        feat.setGeometry(geom)

        sink.addFeature(feat, QgsFeatureSink.FastInsert)
        feedback.pushInfo("[QNEAT3Algorithm] Ending Algorithm")
        feedback.setProgress(100)
        results = {}
        results[self.OUTPUT] = dest_id
        return results
