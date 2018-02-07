# -*- coding: utf-8 -*-
"""
***************************************************************************
    OdMatrixFromPointsAsLines.py
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
                       QgsFields,
                       QgsField,
                       QgsGeometry,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsProcessing,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterDefinition)

from qgis.analysis import (QgsVectorLayerDirector)

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeaturesFromQgsIterable, getFieldDatatype

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class OdMatrixFromPointsAsLines(QgisAlgorithm):

    INPUT = 'INPUT'
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

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_matrix.svg'))

    def group(self):
        return self.tr('Distance Matrices (Network based)')

    def groupId(self):
        return 'networkbaseddistancematrices'
    
    def name(self):
        return 'OdMatrixFromPointsAsLines'

    def displayName(self):
        return self.tr('OD-Matrix from Points as Lines (n:n)')
    
    def print_typestring(self, var):
        return "Type:"+str(type(var))+" repr: "+var.__str__()


    def __init__(self):
        super().__init__()

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])

        self.STRATEGIES = [self.tr('Shortest'),
                           self.tr('Fastest')]

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Vector layer representing network'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.POINTS,
                                                              self.tr('Point Layer'),
                                                              [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Unique Point ID Field'),
                                                       None,
                                                       self.POINTS,
                                                       optional=False))
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


        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output OD Matrix'), QgsProcessing.TypeVectorLine), True)

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr('This is a QNEAT Algorithm'))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        points = self.parameterAsSource(parameters, self.POINTS, context) #QgsProcessingFeatureSource
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context) #str
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
        
        net = Qneat3Network(network, points, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
        
        list_analysis_points = [Qneat3AnalysisPoint("point", feature, id_field, net.network, net.list_tiedPoints[i]) for i, feature in enumerate(getFeaturesFromQgsIterable(net.input_points))]
        
        feat = QgsFeature()
        fields = QgsFields()
        output_id_field_data_type = getFieldDatatype(points, id_field)
        fields.append(QgsField('origin_id', output_id_field_data_type, '', 254, 0))
        fields.append(QgsField('destination_id', output_id_field_data_type, '', 254, 0))
        fields.append(QgsField('network_cost', QVariant.Double, '', 20, 7))
        feat.setFields(fields)
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields, QgsWkbTypes.LineString, network.sourceCrs())

        
        total_workload = float(pow(len(list_analysis_points),2))
        feedback.pushInfo("Expecting total workload of {} iterations".format(int(total_workload)))
        
        
        current_workstep_number = 0
        
        for start_point in list_analysis_points:
            #optimize in case of undirected (not necessary to call calcDijkstra as it has already been calculated - can be replaced by reading from list)
            dijkstra_query = net.calcDijkstra(start_point.network_vertex_id, 0)
            for query_point in list_analysis_points:
                if (current_workstep_number%1000)==0:
                    feedback.pushInfo("{} OD-pairs processed...".format(current_workstep_number))
                if query_point.point_id == start_point.point_id:
                    feat['origin_id'] = start_point.point_id
                    feat['destination_id'] = query_point.point_id
                    feat['network_cost'] = 0.0
                    sink.addFeature(feat, QgsFeatureSink.FastInsert)
                elif dijkstra_query[0][query_point.network_vertex_id] == -1:
                    feat['origin_id'] = start_point.point_id
                    feat['destination_id'] = query_point.point_id
                    #do not populate cost field so that it defaults to null
                    sink.addFeature(feat, QgsFeatureSink.FastInsert)
                else:
                    entry_cost = start_point.calcEntryCost(strategy)+query_point.calcEntryCost(strategy)
                    total_cost = dijkstra_query[1][query_point.network_vertex_id]+entry_cost
                    feat.setGeometry(QgsGeometry.fromPolylineXY([start_point.point_geom, query_point.point_geom]))
                    feat['origin_id'] = start_point.point_id
                    feat['destination_id'] = query_point.point_id
                    feat['network_cost'] = total_cost
                    sink.addFeature(feat, QgsFeatureSink.FastInsert)  
                current_workstep_number=current_workstep_number+1
                feedback.setProgress(current_workstep_number/total_workload)
                    
        feedback.pushInfo("Total number of OD-pairs processed: {}".format(current_workstep_number))
    
        feedback.pushInfo("Initialization Done")
        feedback.pushInfo("Ending Algorithm")

        results = {}
        results[self.OUTPUT] = dest_id
        return results

