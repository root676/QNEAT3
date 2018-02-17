# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsContour.py
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
from email.policy import default
from plotly.api.v2.users import current

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
                       QgsUnitTypes,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsGeometry,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
                       QgsProcessingException,
                       QgsProcessingOutputNumber,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterPoint,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import (QgsVectorLayerDirector,
                           QgsNetworkDistanceStrategy,
                           QgsNetworkSpeedStrategy,
                           QgsGraphBuilder,
                           QgsGraphAnalyzer
                           )

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeaturesFromQgsIterable, getFeatureFromPointParameter

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class IsoAreaAsContour(QgisAlgorithm):

    INPUT = 'INPUT'
    START_POINT = 'START_POINT'
    END_POINT = 'END_POINT'
    STRATEGY = 'STRATEGY'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    TRAVEL_COST = 'TRAVEL_COST'
    OUTPUT = 'OUTPUT'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_contour.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaascontour'

    def displayName(self):
        return self.tr('Iso-Area as Contour')
    
    def msg(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()

    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest'),
                           self.tr('Fastest')
                           ]

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Vector layer representing network'),
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

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,
                                                            self.tr('Shortest path'),
                                                            QgsProcessing.TypeVectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr('This is a QNEAT Algorithm'))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        startPoint = self.parameterAsPoint(parameters, self.START_POINT, context, network.sourceCrs()) #QgsPointXY
        endPoint = self.parameterAsPoint(parameters, self.END_POINT, context, network.sourceCrs()) #QgsPointXY
        strategy = self.parameterAsEnum(parameters, self.STRATEGY, context) #int

        directionFieldName = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) #str (empty if no field given)
        forwardValue = self.parameterAsString(parameters, self.VALUE_FORWARD, context) #str
        backwardValue = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) #str
        bothValue = self.parameterAsString(parameters, self.VALUE_BOTH, context) #str
        defaultDirection = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) #int
        speedFieldName = self.parameterAsString(parameters, self.SPEED_FIELD, context) #str
        defaultSpeed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) #float
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context) #float

        analysisCrs = context.project().crs()
        input_coordinates = [startPoint,endPoint]
        input_points = [getFeatureFromPointParameter(startPoint),getFeatureFromPointParameter(endPoint)]
        
        net = Qneat3Network(network, input_coordinates, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
        
        list_analysis_points = [Qneat3AnalysisPoint("point", feature, "point_id", net.network, net.list_tiedPoints[i]) for i, feature in enumerate(input_points)]
        
        start_vertex_idx = list_analysis_points[0].network_vertex_id
        end_vertex_idx = list_analysis_points[1].network_vertex_id
        
        feedback.pushInfo("Calculating shortest path...")
        dijkstra_query = net.calcDijkstra(start_vertex_idx, 0)
        
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
                feedback.pushInfo("Taversed {} Nodes...".format(count))
        
        path_elements.append(list_analysis_points[0].point_geom) #end path with startpoint outside the network   
        feedback.pushInfo("Total number of Nodes traversed: {}".format(count+1))
        path_elements.reverse() #reverse path elements because it was built from end to start
        
        start_entry_cost = list_analysis_points[0].calcEntryCost(strategy)
        end_exit_cost = list_analysis_points[1].calcEntryCost(strategy)
        cost_on_graph = dijkstra_query[1][end_vertex_idx]
        total_cost = start_entry_cost + cost_on_graph + end_exit_cost
    
        feedback.pushInfo("Writing path-feature...")
        feat = QgsFeature()
        
        fields = QgsFields()
        fields.append(QgsField('start_id', QVariant.String, '', 254, 0))
        fields.append(QgsField('start_coordinates', QVariant.String, '', 254, 0))
        fields.append(QgsField('start_entry_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('end_id', QVariant.String, '', 254, 0))
        fields.append(QgsField('end_coordinates', QVariant.String, '', 254, 0))
        fields.append(QgsField('end_exit_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('cost_on_graph', QVariant.Double, '', 20, 7))
        fields.append(QgsField('total_cost', QVariant.Double, '', 20, 7))
        feat.setFields(fields)
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.LineString, network.sourceCrs())
        
        feat['start_id'] = "A"
        feat['start_coordinates'] = startPoint.toString()
        feat['start_entry_cost'] = start_entry_cost
        feat['end_id'] = "B"
        feat['end_coordinates'] = endPoint.toString()
        feat['end_exit_cost'] = end_exit_cost
        feat['cost_on_graph'] = cost_on_graph
        feat['total_cost'] = total_cost 
        geom = QgsGeometry.fromPolylineXY(path_elements)
        feat.setGeometry(geom)
        
        sink.addFeature(feat, QgsFeatureSink.FastInsert)
        feedback.pushInfo("Ending Algorithm")        
        
        results = {}
        results[self.OUTPUT] = dest_id
        return results

