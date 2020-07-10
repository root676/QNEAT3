# -*- coding: utf-8 -*-
"""
***************************************************************************
    OdMatrixFromLayersAsLines.py
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
                       QgsFields,
                       QgsField,
                       QgsFeature,
                       QgsGeometry,
                       QgsFeatureSink,
                       QgsProcessing,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterDefinition)

from qgis.analysis import (QgsVectorLayerDirector)

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeaturesFromQgsIterable, getFieldDatatype, getListOfPoints

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class OdMatrixFromLayersAsLines(QgisAlgorithm):

    INPUT = 'INPUT'
    FROM_POINT_LAYER = 'FROM_POINT_LAYER'
    FROM_ID_FIELD = 'FROM_ID_FIELD'
    TO_POINT_LAYER = 'TO_POINT_LAYER'
    TO_ID_FIELD = 'TO_ID_FIELD'
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
        return self.tr('Distance Matrices')

    def groupId(self):
        return 'networkbaseddistancematrices'

    def name(self):
        return 'OdMatrixFromLayersAsLines'

    def displayName(self):
        return self.tr('OD Matrix from Layers as Lines (m:n)')

    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements OD Matrix analysis to return the <b>matrix of origin-destination pairs as lines yielding network based costs</b> on a given <b>network dataset between two layer of points (m:n)</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>). Distances are measured accounting for <b>ellipsoids</b>, entry-, exit-, network- and total costs are listed in the result attribute-table.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following Parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Input point layer (origin points)</li><li>Input unique ID field</li><li>Target point layer</li><li>Target unique ID field (destination points)</li><li>Path type to calculate</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction Field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed Field</li><li>Default Speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm is one layer:"\
                "<ul><li>OD Matrix as lines with network based distances as attributes</li></ul>"\
                "Shortest distance cost units are meters and Fastest time cost units are seconds."


    def print_typestring(self, var):
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

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network layer'),
                                                              [QgsProcessing.TypeVectorLine]))

        self.addParameter(QgsProcessingParameterFeatureSource(self.FROM_POINT_LAYER,
                                                              self.tr('Input point layer (origin points)'),
                                                              [QgsProcessing.TypeVectorPoint]))

        self.addParameter(QgsProcessingParameterField(self.FROM_ID_FIELD,
                                                       self.tr('Input unique ID field'),
                                                       None,
                                                       self.FROM_POINT_LAYER,
                                                       optional=False))

        self.addParameter(QgsProcessingParameterFeatureSource(self.TO_POINT_LAYER,
                                                      self.tr('Target point layer (destination points)'),
                                                      [QgsProcessing.TypeVectorPoint]))

        self.addParameter(QgsProcessingParameterField(self.TO_ID_FIELD,
                                                     self.tr('Target unique ID field'),
                                                     None,
                                                     self.TO_POINT_LAYER,
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

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output OD Matrix'), QgsProcessing.TypeVectorLine), True)

    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr("[QNEAT3Algorithm] This is a QNEAT3 Algorithm: '{}'".format(self.displayName())))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        from_points = self.parameterAsSource(parameters, self.FROM_POINT_LAYER, context) #QgsProcessingFeatureSource
        from_id_field = self.parameterAsString(parameters, self.FROM_ID_FIELD, context) #str
        to_points = self.parameterAsSource(parameters, self.TO_POINT_LAYER, context)
        to_id_field = self.parameterAsString(parameters, self.TO_ID_FIELD, context)
        strategy = self.parameterAsEnum(parameters, self.STRATEGY, context) #int

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

        if analysisCrs != from_points.sourceCrs() or from_points.sourceCrs() != to_points.sourceCrs():
            raise QgsProcessingException('QNEAT3 algorithms require that all inputs to be the same projected coordinate reference system (including project coordinate system).')

        #Points of both layers have to be merged into one layer --> then tied to the Qneat3Network
        #get point list of from layer
        from_coord_list = getListOfPoints(from_points)
        from_coord_list_length = len(from_coord_list)
        to_coord_list = getListOfPoints(to_points)

        merged_coords = from_coord_list + to_coord_list

        feedback.pushInfo("[QNEAT3Algorithm] Building Graph...")
        net = Qneat3Network(network, merged_coords, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)

        #read the merged point-list seperately for the two layers --> index at the first element of the second layer begins at len(firstLayer) and gets added the index of the current point of layer b.
        list_from_apoints = [Qneat3AnalysisPoint("from", feature, from_id_field, net, net.list_tiedPoints[i], feedback) for i, feature in enumerate(getFeaturesFromQgsIterable(from_points))]
        list_to_apoints = [Qneat3AnalysisPoint("to", feature, to_id_field, net, net.list_tiedPoints[from_coord_list_length+i], feedback) for i, feature in enumerate(getFeaturesFromQgsIterable(to_points))]

        feat = QgsFeature()
        fields = QgsFields()
        orig_id_field_data_type = getFieldDatatype(from_points, from_id_field)
        dest_id_field_data_type = getFieldDatatype(to_points, to_id_field)
        fields.append(QgsField('InputID', orig_id_field_data_type, '', 254, 0))
        fields.append(QgsField('TargetID', dest_id_field_data_type, '', 254, 0))
        fields.append(QgsField('entry_cost', QVariant.Double, '', 20,7))
        fields.append(QgsField('network_cost', QVariant.Double, '', 20, 7))
        fields.append(QgsField('exit_cost', QVariant.Double, '', 20,7))
        fields.append(QgsField('total_cost', QVariant.Double, '', 20,7))
        feat.setFields(fields)

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.LineString, network.sourceCrs())


        total_workload = float(len(from_coord_list)*len(to_coord_list))
        feedback.pushInfo("[QNEAT3Algorithm] Expecting total workload of {} iterations".format(int(total_workload)))


        current_workstep_number = 0

        for start_point in list_from_apoints:
            #optimize in case of undirected (not necessary to call calcDijkstra as it has already been calculated - can be replaced by reading from list)
            dijkstra_query = net.calcDijkstra(start_point.network_vertex_id, 0)
            for query_point in list_to_apoints:
                if (current_workstep_number%1000)==0:
                    feedback.pushInfo("[QNEAT3Algorithm] {} OD-pairs processed...".format(current_workstep_number))
                if dijkstra_query[0][query_point.network_vertex_id] == -1:
                    feat['InputID'] = start_point.point_id
                    feat['TargetID'] = query_point.point_id
                    #do not populate cost field so that it defaults to null
                    sink.addFeature(feat, QgsFeatureSink.FastInsert)
                else:
                    entry_cost = start_point.entry_cost
                    network_cost = dijkstra_query[1][query_point.network_vertex_id]
                    exit_cost = query_point.entry_cost
                    total_cost = network_cost + entry_cost + exit_cost

                    feat.setGeometry(QgsGeometry.fromPolylineXY([start_point.point_geom, query_point.point_geom]))
                    feat['InputID'] = start_point.point_id
                    feat['TargetID'] = query_point.point_id
                    feat['entry_cost'] = entry_cost
                    feat['network_cost'] = network_cost
                    feat['exit_cost'] = exit_cost
                    feat['total_cost'] = total_cost
                    sink.addFeature(feat, QgsFeatureSink.FastInsert)
                current_workstep_number=current_workstep_number+1
                feedback.setProgress((current_workstep_number/total_workload)*100)

        feedback.pushInfo("[QNEAT3Algorithm] Total number of OD-pairs processed: {}".format(current_workstep_number))

        feedback.pushInfo("[QNEAT3Algorithm] Ending Algorithm")

        results = {}
        results[self.OUTPUT] = dest_id
        return results
