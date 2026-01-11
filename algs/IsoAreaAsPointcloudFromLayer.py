# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaAsPointcloudFromLayer.py
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

from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis, 
                       QgsWkbTypes,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsFields,
                       QgsField,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from ..QneatFramework import QneatCore, OptimizationStrategy, ProgressRange
from ..QneatUtilities import getFieldDatatype, checkIfAnalysisCrsEqual

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsFields,
        QgsProcessingFeatureSource
        )

class IsoAreaAsPointcloudFromLayer(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    ORIGIN_POINTS = 'ORIGIN_POINTS'
    ID_FIELD = 'ID_FIELD'
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

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_points_multiple.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareaaspointcloudfromlayer'

    def displayName(self):
        return self.tr('Iso-Area as Pointcloud (from Layer)')

    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-pointcloud analysis to return all <b>network nodes reachable within a maximum cost level as pointcloud</b> on a given <b>network dataset for a layer of points</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Origin-point layer</li><li>Unique point ID field (numerical)</li><li>Maximum cost level for iso-area</li><li>Cost strategy</li></ul><br>"\
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
    
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT,
                                                              self.tr('Network Layer'),
                                                              [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ORIGIN_POINTS,
                                                              self.tr('Origin point Layer'),
                                                              [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ID_FIELD,
                                                       self.tr('Unique Point ID Field'),
                                                       None,
                                                       self.ORIGIN_POINTS,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_DIST,
                                                   self.tr('Size of Iso-Area (distance in network csr units or time value in seconds)'),
                                                   QgsProcessingParameterNumber.Double,
                                                   2500.0, False, 0, 99999999.99))
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
            p.setFlags(p.flags() | Qgis.ProcessingParameterFlag.Advanced)
            self.addParameter(p)
        
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,
                                                            self.tr('Output Pointcloud'),
                                                            QgsProcessing.TypeVectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))

        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.INPUT, context)
        origin_points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.ORIGIN_POINTS, context) 
        id_field: str = self.parameterAsString(parameters, self.ID_FIELD, context) 
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
        
        #unpack all points into one list
        input_point_features: list[QgsFeature] = []

        source_point_fields = QgsFields()
        source_point_fields.append(QgsField('fid', QMetaType.Type.LongLong))
        source_point_fields.append(QgsField('user_id'), getFieldDatatype(origin_points, id_field))
        source_point_fields.append(QgsField('type', QMetaType.Type.QString))

        for f in origin_points.getFeatures():
            source_feat = QgsFeature(source_point_fields)
            source_feat["fid"] = f.id()
            source_feat["user_id"] = f[id_field]
            source_feat.setGeometry(f.geometry())
        
            input_point_features.append(source_feat)
        
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
        fields.append(QgsField('vertex_id', QMetaType.Type.Int))
        fields.append(QgsField('cost', QMetaType.Type.Double))
        fields.append(QgsField('origin_point_id', getFieldDatatype(origin_points, id_field)))
        
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.Point, analysisCrs)
        
        iso_progress_range = ProgressRange(feedback, 0.5, 1.0)
        iso_points = core.calcIsoPoints('user_id', max_cost, iso_progress_range)
        
        sink.addFeatures(iso_points, QgsFeatureSink.FastInsert)  
        
        results = {}
        results[self.OUTPUT] = dest_id
        return results

