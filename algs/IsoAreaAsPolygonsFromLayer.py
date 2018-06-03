# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsPolygonFromLayer.py
    ---------------------
    
    Partially based on QGIS3 network analysis algorithms. 
    Copyright 2016 Alexander Bruy    
    
    Date                 : April 2018
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
__date__ = 'April 2018'
__copyright__ = '(C) 2018, Clemens Raffler'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
from collections import OrderedDict

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (QgsWkbTypes,
                       QgsVectorLayer,
                       QgsFeatureSink,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeaturesFromQgsIterable, getListOfPoints

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class IsoAreaAsPolygonsFromLayer(QgisAlgorithm):

    INPUT = 'INPUT'
    START_POINTS = 'START_POINTS'
    ID_FIELD = 'ID_FIELD'
    MAX_DIST = "MAX_DIST"
    CELL_SIZE = "CELL_SIZE"
    INTERVAL = "INTERVAL"
    STRATEGY = 'STRATEGY'
    DIRECTION_FIELD = 'DIRECTION_FIELD'
    VALUE_FORWARD = 'VALUE_FORWARD'
    VALUE_BACKWARD = 'VALUE_BACKWARD'
    VALUE_BOTH = 'VALUE_BOTH'
    DEFAULT_DIRECTION = 'DEFAULT_DIRECTION'
    SPEED_FIELD = 'SPEED_FIELD'
    DEFAULT_SPEED = 'DEFAULT_SPEED'
    TOLERANCE = 'TOLERANCE'
    OUTPUT_INTERPOLATION = 'OUTPUT_INTERPOLATION'
    OUTPUT_POLYGONS = 'OUTPUT_POLYGONS'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_polygon_multiple.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaaspolygonsfromlayer'

    def displayName(self):
        return self.tr('Iso-Area as Polygons (from Layer)')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-area analysis to return the <b>iso-area polygons for a maximum cost level and interval levels </b> on a given <b>network dataset for a layer of points</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following Parameters must be set to run the algorithm:"\
                "<ul><li>Network Layer</li><li>Startpoint Layer</li><li>Unique Point ID Field (numerical)</li><li>Maximum cost level for Iso-Area</li><li>Cost Intervals for Iso-Area Bands</li><li>Cellsize in Meters (increase default when analyzing larger networks)</li><li>Cost Strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction Field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed Field</li><li>Default Speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm are two layers:"\
                "<ul><li>TIN-Interpolation Distance Raster</li><li>Iso-Area Polygons with cost levels as attributes</li></ul>"    
    
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
        self.addParameter(QgsProcessingParameterFeatureSource(self.START_POINTS,
                                                              self.tr('Start Points'),
                                                              [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Unique Point ID Field'),
                                                       None,
                                                       self.START_POINTS,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_DIST,
                                                   self.tr('Size of Iso-Area (distance or time value)'),
                                                   QgsProcessingParameterNumber.Double,
                                                   2500.0, False, 0, 99999999.99))
        self.addParameter(QgsProcessingParameterNumber(self.INTERVAL,
                                                   self.tr('Contour Interval (distance or time value)'),
                                                   QgsProcessingParameterNumber.Double,
                                                   500.0, False, 0, 99999999.99))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE,
                                                    self.tr('Cellsize of interpolation raster'),
                                                    QgsProcessingParameterNumber.Integer,
                                                    10, False, 1, 99999999))
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

        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT_INTERPOLATION, self.tr('Output Interpolation')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_POLYGONS, self.tr('Output Polygon'), QgsProcessing.TypeVectorPolygon))
        
    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr("[QNEAT3Algorithm] This is a QNEAT3 Algorithm: '{}'".format(self.displayName())))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        startPoints = self.parameterAsSource(parameters, self.START_POINTS, context) #QgsProcessingFeatureSource
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context) #str
        interval = self.parameterAsDouble(parameters, self.INTERVAL, context)#float
        max_dist = self.parameterAsDouble(parameters, self.MAX_DIST, context)#float
        cell_size = self.parameterAsInt(parameters, self.CELL_SIZE, context)#int
        strategy = self.parameterAsEnum(parameters, self.STRATEGY, context) #int

        directionFieldName = self.parameterAsString(parameters, self.DIRECTION_FIELD, context) #str (empty if no field given)
        forwardValue = self.parameterAsString(parameters, self.VALUE_FORWARD, context) #str
        backwardValue = self.parameterAsString(parameters, self.VALUE_BACKWARD, context) #str
        bothValue = self.parameterAsString(parameters, self.VALUE_BOTH, context) #str
        defaultDirection = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) #int
        speedFieldName = self.parameterAsString(parameters, self.SPEED_FIELD, context) #str
        defaultSpeed = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) #float
        tolerance = self.parameterAsDouble(parameters, self.TOLERANCE, context) #float
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_INTERPOLATION, context) #string

        analysisCrs = network.sourceCrs()
        input_coordinates = getListOfPoints(startPoints)
        
        feedback.pushInfo("[QNEAT3Algorithm] Building Graph...")
        feedback.setProgress(10)
        net = Qneat3Network(network, input_coordinates, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)
        feedback.setProgress(40)
        
        list_apoints = [Qneat3AnalysisPoint("from", feature, id_field, net, net.list_tiedPoints[i], feedback) for i, feature in enumerate(getFeaturesFromQgsIterable(startPoints))]
        
        feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Pointcloud...")
        iso_pointcloud = net.calcIsoPoints(list_apoints, max_dist+(max_dist*0.1))
        feedback.setProgress(50)
        
        uri = "Point?crs={}&field=vertex_id:int(254)&field=cost:double(254,7)&field=origin_point_id:string(254)&index=yes".format(analysisCrs.authid())
        
        iso_pointcloud_layer = QgsVectorLayer(uri, "iso_pointcloud_layer", "memory")
        iso_pointcloud_provider = iso_pointcloud_layer.dataProvider()
        iso_pointcloud_provider.addFeatures(iso_pointcloud, QgsFeatureSink.FastInsert)
        
        feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Interpolation-Raster using QGIS TIN-Interpolator...")
        net.calcIsoInterpolation(iso_pointcloud_layer, cell_size, output_path)
        feedback.setProgress(70)
            
        fields = QgsFields()
        fields.append(QgsField('id', QVariant.Int, '', 254, 0))
        fields.append(QgsField('cost_level', QVariant.Double, '', 20, 7))
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT_POLYGONS, context, fields, QgsWkbTypes.Polygon, network.sourceCrs())   
        
        feedback.pushInfo("[QNEAT3Algorithm] Calculating Iso-Polygons using numpy and matplotlib...")
        polygon_featurelist = net.calcIsoPolygons(max_dist, interval, output_path)
        feedback.setProgress(90)
        
        sink.addFeatures(polygon_featurelist, QgsFeatureSink.FastInsert)
        feedback.pushInfo("[QNEAT3Algorithm] Ending Algorithm")
        feedback.setProgress(100)
        
        results = {}
        results[self.OUTPUT_INTERPOLATION] = output_path
        results[self.OUTPUT_POLYGONS] = dest_id
        return results


