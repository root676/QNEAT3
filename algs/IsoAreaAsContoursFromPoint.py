# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsContourFromPoint.py
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
                       QgsVectorLayer,
                       QgsFeatureSink,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterPoint,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from QNEAT3.Qneat3Framework import Qneat3Network, Qneat3AnalysisPoint
from QNEAT3.Qneat3Utilities import getFeatureFromPointParameter

from processing.algs.qgis.QgisAlgorithm import QgisAlgorithm

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]


class IsoAreaAsContoursFromPoint(QgisAlgorithm):

    INPUT = 'INPUT'
    START_POINT = 'START_POINT'
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
    OUTPUT_CONTOURS = 'OUTPUT_CONTOURS'

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_contour.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaascontoursfrompoint'

    def displayName(self):
        return self.tr('Iso-Area as Contours (from Point)')
    
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
                                                              self.tr('Network Layer'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterPoint(self.START_POINT,
                                                      self.tr('Start point')))
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
                                                     self.tr('Optimization Criterion'),
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
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_CONTOURS, self.tr('Output Contours'), QgsProcessing.TypeVectorLine))
        
    def processAlgorithm(self, parameters, context, feedback):
        feedback.pushInfo(self.tr('This is a QNEAT Algorithm'))
        network = self.parameterAsSource(parameters, self.INPUT, context) #QgsProcessingFeatureSource
        startPoint = self.parameterAsPoint(parameters, self.START_POINT, context, network.sourceCrs()) #QgsPointXY
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
        input_coordinates = [startPoint]
        input_point = getFeatureFromPointParameter(startPoint)
        
        net = Qneat3Network(network, input_coordinates, strategy, directionFieldName, forwardValue, backwardValue, bothValue, defaultDirection, analysisCrs, speedFieldName, defaultSpeed, tolerance, feedback)

        analysis_point = Qneat3AnalysisPoint("point", input_point, "point_id", net, net.list_tiedPoints[0])
        
        feedback.pushInfo("Calculating Iso-Pointcloud...")
        
        iso_pointcloud = net.calcIsoPoints([analysis_point], max_dist+(max_dist*0.1), context)
        
        uri = "Point?crs={}&field=vertex_id:int(254)&field=cost:double(254,7)&field=origin_point_id:string(254)&index=yes".format(analysisCrs.authid())
        
        iso_pointcloud_layer = QgsVectorLayer(uri, "iso_pointcloud_layer", "memory")
        iso_pointcloud_provider = iso_pointcloud_layer.dataProvider()
        iso_pointcloud_provider.addFeatures(iso_pointcloud, QgsFeatureSink.FastInsert)
        
        feedback.pushInfo("Calculating Iso-Interpolation-Raster using QGIS TIN-Interpolator...")
        net.calcIsoInterpolation(iso_pointcloud_layer, cell_size, output_path)
            
        fields = QgsFields()
        fields.append(QgsField('id', QVariant.Int, '', 254, 0))
        fields.append(QgsField('cost_level', QVariant.Double, '', 20, 7))
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT_CONTOURS, context, fields, QgsWkbTypes.LineString, network.sourceCrs())
        
        feedback.pushInfo("Calculating Iso-Contours using numpy and matplotlib...")
        contour_featurelist = net.calcIsoContours(max_dist, interval, output_path)
        
        sink.addFeatures(contour_featurelist, QgsFeatureSink.FastInsert)
        feedback.pushInfo("Ending Algorithm")
        
        results = {}
        results[self.OUTPUT_INTERPOLATION] = output_path
        results[self.OUTPUT_CONTOURS] = dest_id
        return results

