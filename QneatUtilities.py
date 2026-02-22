# -*- coding: utf-8 -*-
"""
***************************************************************************
    QneatUtilities.py
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

import math
from qgis.PyQt.QtCore import QVariant

from qgis.core import (QgsMessageLog, 
                       QgsVectorLayer, 
                       QgsFeature, 
                       QgsGeometry, 
                       QgsFields, 
                       QgsField)

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsFeatureSource,
        QgsPointXY,
        QgsRectangle
    )


def logPanel(message):
    QgsMessageLog.logMessage(message, "QNEAT")

def checkIfAnalysisCrsEqual(sourceCrss : list[QgsCoordinateReferenceSystem]) -> bool:
    first_crs = sourceCrss[0]

    return all(
        crs.toWkt() == first_crs.toWkt()
        for crs in sourceCrss
        )


def buildQgsVectorLayer(string_geomtype: str, string_layername: str, crs: QgsCoordinateReferenceSystem, feature_list: list[QgsFeature]) -> QgsVectorLayer:
    vector_layer = QgsVectorLayer(string_geomtype, string_layername, "memory")
    vector_layer.setCrs(crs)
    provider = vector_layer.dataProvider()
    provider.addFeatures(feature_list)
    vector_layer.updateExtents()
    return vector_layer

def getFeatureFromPoint(user_id: int, qgs_point_xy: QgsPointXY) -> QgsFeature:     
    feature = QgsFeature()
    fields = QgsFields()
    fields.append(QgsField('user_id', QVariant.LongLong))
    feature.setFields(fields)
    feature.setGeometry(QgsGeometry.fromPointXY(qgs_point_xy))
    feature['user_id']=user_id
    return feature
        
def getFieldDatatype(qgs_feature_storage: Union[QgsFeatureSource, QgsFeature], fieldname) -> QVariant.Type:
    fields_list: QgsFields = qgs_feature_storage.fields()
    type: QVariant.Type = fields_list.field(fieldname).type()
    return type

def getFieldDatatypeFromPythontype(pythonvar):
    if isinstance(pythonvar, str):
        return QVariant.String
    elif isinstance(pythonvar, int):
        return QVariant.Int
    elif isinstance(pythonvar, float):
        return QVariant.Double
    else: 
        return QVariant.String
    
def getOdMatrixFields(origin_points: QgsFeatureSource, origin_id_field: str, destination_points: QgsFeatureSource, destination_id_field: str) -> QgsFields:
    output_fields = QgsFields()
    output_fields.append(QgsField('origin_id', getFieldDatatype(origin_points, origin_id_field)))
    output_fields.append(QgsField('destination_id', getFieldDatatype(destination_points, destination_id_field)))
    output_fields.append(QgsField('entry_cost', QVariant.Double))
    output_fields.append(QgsField('network_cost', QVariant.Double))
    output_fields.append(QgsField('exit_cost', QVariant.Double))
    output_fields.append(QgsField('total_cost', QVariant.Double))
    return output_fields

def getCellIndexFromPoint(x: float, y:float, rasterExtent:QgsRectangle, cellsize: float, rows: int, cols: int):

    col = int((x - rasterExtent.xMinimum()) / cellsize)
    row = int((rasterExtent.yMaximum() - y) / cellsize)

    # clamp to valid range
    if col < 0 or col >= cols or row < 0 or row >= rows:
        return None

    return row, col


    