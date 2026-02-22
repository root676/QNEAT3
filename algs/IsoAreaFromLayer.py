# -*- coding: utf-8 -*-
"""
***************************************************************************
    IsoAreaFromLayer.py
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

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon

from qgis.core import (Qgis,
                       QgsVectorLayer,
                       QgsFeature,
                       QgsFeatureSink,
                       QgsFields,
                       QgsField,
                       QgsProcessingAlgorithm,
                       QgsProcessingException,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterField,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterDefinition)

from qgis.analysis import QgsVectorLayerDirector

from ..QneatFramework import QneatCore, IsoAreaMethod, IsoAreaType, OptimizationStrategy,  EntryCostCalculationMethod, ProgressRange
from ..QneatUtilities import checkIfAnalysisCrsEqual, getFieldDatatype

pluginPath = os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]

from typing import (
    TYPE_CHECKING
    )  

if TYPE_CHECKING:
    from qgis.core import (
        QgsProcessingFeatureSource
        )

class IsoAreaFromLayer(QgsProcessingAlgorithm):

    GRAPH_LAYER = 'GRAPH_LAYER'
    ORIGIN_POINT_LAYER = 'ORIGIN_POINT_LAYER'
    ISO_AREA_METHOD = 'ISO_AREA_METHOD'
    ISO_AREA_TYPE = 'ISO_AREA_TYPE'
    ORIGIN_ID_FIELD = 'ORIGIN_ID_FIELD'
    MAX_COST = "MAX_COST"
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
    OUTPUT_COST_SURFACE = 'OUTPUT_COST_SURFACE'
    OUTPUT_ISO_AREAS = 'OUTPUT_ISO_AREAS'

    def __init__(self):
        super().__init__()
    
    def createInstance(self):
        return IsoAreaFromLayer()

    def tr(self, string):
        return QCoreApplication.translate('QNEAT', string)

    def icon(self):
        return QIcon(os.path.join(pluginPath, 'QNEAT3', 'icons', 'icon_servicearea_polygon_multiple.svg'))

    def group(self):
        return self.tr('Iso-Areas')

    def groupId(self):
        return 'isoareas'
    
    def name(self):
        return 'isoareafromlayer'

    def displayName(self):
        return self.tr('Iso-Area from layer')
    
    def shortHelpString(self):
        return  "<b>General:</b><br>"\
                "This algorithm implements iso-area analysis to return the <b>iso-area polygons for a maximum cost level and interval levels </b> on a given <b>network dataset for a layer of points</b>.<br>"\
                "It accounts for <b>points outside of the network</b> (eg. <i>non-network-elements</i>) and increments the iso-areas cost regarding to distance/default speed value. Distances are measured accounting for <b>ellipsoids</b>.<br>Please, <b>only use a projected coordinate system (eg. no WGS84)</b> for this kind of analysis.<br><br>"\
                "<b>Parameters (required):</b><br>"\
                "Following parameters must be set to run the algorithm:"\
                "<ul><li>Network layer</li><li>Startpoint layer</li><li>Unique point ID field (numerical)</li><li>Maximum cost level for iso-area</li><li>Cost intervals for iso-area bands</li><li>Cellsize in meters (increase default when analyzing larger networks)</li><li>Cost Strategy</li></ul><br>"\
                "<b>Parameters (optional):</b><br>"\
                "There are also a number of <i>optional parameters</i> to implement <b>direction dependent</b> shortest paths and provide information on <b>speeds</b> on the networks edges."\
                "<ul><li>Direction field</li><li>Value for forward direction</li><li>Value for backward direction</li><li>Value for both directions</li><li>Default direction</li><li>Speed field</li><li>Default speed (affects entry/exit costs)</li><li>Topology tolerance</li></ul><br>"\
                "<b>Output:</b><br>"\
                "The output of the algorithm are two layers:"\
                "<ul><li>Cost surface raster</li><li>Iso-area polygons or line contours</li></ul>"    

    def initAlgorithm(self, config=None):
        self.DIRECTIONS = OrderedDict([
            (self.tr('Forward direction'), QgsVectorLayerDirector.DirectionForward),
            (self.tr('Backward direction'), QgsVectorLayerDirector.DirectionBackward),
            (self.tr('Both directions'), QgsVectorLayerDirector.DirectionBoth)])
        
        self.ISO_AREA_METHOD_DEFINITIONS = [self.tr("Euclidean Distance Transform"),
                                            self.tr("TIN Interpolation")]

        self.ISO_AREA_TYPE_DEFINITIONS = [self.tr("Polygons"), 
                                          self.tr("Contours")]

        self.STRATEGIES = [self.tr('Shortest Path (distance optimization)'),
                           self.tr('Fastest Path (time optimization)')]

        self.addParameter(QgsProcessingParameterFeatureSource(self.GRAPH_LAYER,
                                                              self.tr('Network layer'),
                                                              [Qgis.ProcessingSourceType.VectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ORIGIN_POINT_LAYER,
                                                              self.tr('Origin point layer'),
                                                              [Qgis.ProcessingSourceType.VectorPoint]))
        self.addParameter(QgsProcessingParameterField(self.ORIGIN_ID_FIELD,
                                                       self.tr('Unique point ID field'),
                                                       None,
                                                       self.ORIGIN_POINT_LAYER,
                                                       optional=False))
        self.addParameter(QgsProcessingParameterEnum(self.ISO_AREA_METHOD,
                                                 self.tr('Iso-area type'),
                                                 self.ISO_AREA_METHOD_DEFINITIONS,
                                                 defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(self.ISO_AREA_TYPE,
                                                 self.tr('Iso-area type'),
                                                 self.ISO_AREA_TYPE_DEFINITIONS,
                                                 defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_COST,
                                                   self.tr('Size of iso-area (distance in network CRS units or time value in seconds)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   2500.0, False, 0))
        self.addParameter(QgsProcessingParameterNumber(self.INTERVAL,
                                                   self.tr('Contour interval (distance in network CRS units or time value in seconds)'),
                                                   Qgis.ProcessingNumberParameterType.Double,
                                                   500.0, False, 0))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE,
                                                    self.tr('Cellsize of interpolation raster'),
                                                    Qgis.ProcessingNumberParameterType.Double,
                                                    10, False, 0.0000001))
        self.addParameter(QgsProcessingParameterEnum(self.STRATEGY,
                                                     self.tr('Path type to calculate'),
                                                     self.STRATEGIES,
                                                     defaultValue=0))

        params = []
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
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT_COST_SURFACE, self.tr('Output cost surface')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_ISO_AREAS, self.tr('Output iso-area'), Qgis.ProcessingSourceType.VectorAnyGeometry))
        
    def processAlgorithm(self, parameters, context, feedback):
        feedback.setProgress(0)
        feedback.pushInfo(self.tr("Running '{}'".format(self.displayName())))

        network: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.GRAPH_LAYER, context) 
        origin_points: QgsProcessingFeatureSource = self.parameterAsSource(parameters, self.ORIGIN_POINT_LAYER, context) 
        origin_id_field: str = self.parameterAsString(parameters, self.ORIGIN_ID_FIELD, context) 
        iso_area_method: IsoAreaMethod = IsoAreaMethod(self.parameterAsEnum(parameters, self.ISO_AREA_METHOD, context))
        iso_area_type: IsoAreaType = IsoAreaType(self.parameterAsEnum(parameters, self.ISO_AREA_TYPE, context))
        interval: float = self.parameterAsDouble(parameters, self.INTERVAL, context)
        max_cost: float = self.parameterAsDouble(parameters, self.MAX_COST, context)
        cell_size: float = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        strategy: OptimizationStrategy = OptimizationStrategy(self.parameterAsEnum(parameters, self.STRATEGY, context)) 

        directionFieldName: str = self.parameterAsString(parameters, self.DIRECTION_FIELD, context)
        forwardValue: str = self.parameterAsString(parameters, self.VALUE_FORWARD, context) 
        backwardValue: str = self.parameterAsString(parameters, self.VALUE_BACKWARD, context)
        bothValue: str = self.parameterAsString(parameters, self.VALUE_BOTH, context) 
        defaultDirection: int = self.parameterAsEnum(parameters, self.DEFAULT_DIRECTION, context) 
        speedFieldName: str = self.parameterAsString(parameters, self.SPEED_FIELD, context) 
        defaultSpeed: float = self.parameterAsDouble(parameters, self.DEFAULT_SPEED, context) 
        tolerance: float = self.parameterAsDouble(parameters, self.TOLERANCE, context) 
        output_cost_surface: str = self.parameterAsOutputLayer(parameters, self.OUTPUT_COST_SURFACE, context) 
        output_iso_area: str = self.parameterAsOutputLayer(parameters, self.OUTPUT_ISO_AREAS, context)

        if not checkIfAnalysisCrsEqual([network.sourceCrs(), origin_points.sourceCrs()]):
            raise QgsProcessingException(f"Coordinate reference system (CRS) of graph is {network.sourceCrs().authid()} and doesn't match up with the CRS of the origin point layer ({origin_points.sourceCrs().authid()}). Reproject so that the analysis layer CRSs match up.")
        
        #unpack all points into one list
        input_point_features: list[QgsFeature] = []

        user_id_field_datatype = getFieldDatatype(origin_points, origin_id_field)

        source_point_fields = QgsFields()
        source_point_fields.append(QgsField('fid', QVariant.LongLong))
        source_point_fields.append(QgsField('user_id', user_id_field_datatype))
        source_point_fields.append(QgsField('type', QVariant.String))

        for f in origin_points.getFeatures():
            source_feat = QgsFeature(source_point_fields)
            source_feat["fid"] = f.id()
            source_feat["user_id"] = f[origin_id_field]
            source_feat.setGeometry(f.geometry())
        
            input_point_features.append(source_feat)
        
        build_progress_range = ProgressRange(feedback, 0.0, 0.25)

        core = QneatCore(network, 
                         input_point_features, 
                         strategy, 
                         speedFieldName, 
                         defaultSpeed, 
                         tolerance, 
                         EntryCostCalculationMethod.PLANAR, 
                         build_progress_range, 
                         directionFieldName, 
                         forwardValue, 
                         backwardValue, 
                         bothValue, 
                         defaultDirection)
        
        #increase max cost by 10% in order to correctly draw last distance band.
        max_cost = max_cost * 1.1
        
        iso_progress_range = ProgressRange(feedback, 0.25, 0.5)
        iso_points = core.calcIsoPoints(max_cost, iso_progress_range, cell_size * 1.5, user_id_field_datatype)

        iso_area_method_progress_range = ProgressRange(feedback, 0.5, 0.75)
        if iso_area_method == IsoAreaMethod.EUCLIDEAN_DISTANCE:
            core.calcEuclideanDistanceRaster(iso_points, cell_size, output_cost_surface, iso_area_method_progress_range ) 
        else:
            core.calcIsoTinInterpolation(iso_points, cell_size, output_cost_surface, iso_area_method_progress_range )

        iso_area_progress_range = ProgressRange(feedback, 0.75, 1)
        iso_area_layer: QgsVectorLayer = core.calcIsoAreas(output_cost_surface, max_cost, interval, iso_area_type, iso_area_progress_range)

        wkb_type: Qgis.WkbType = Qgis.WkbType.MultiPolygon if iso_area_type == IsoAreaType.POLYGONS else Qgis.WkbType.MultiLineString
    
        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT_ISO_AREAS, context, iso_area_layer.fields(), wkb_type, network.sourceCrs())   

        sink.addFeatures(iso_area_layer.getFeatures(), QgsFeatureSink.Flag.FastInsert)
        
        results = {}
        results[self.OUTPUT_COST_SURFACE] = output_cost_surface
        results[self.OUTPUT_ISO_AREAS] = dest_id
        return results


