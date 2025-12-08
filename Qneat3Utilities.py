# -*- coding: utf-8 -*-
"""
***************************************************************************
    Qneat3Utilities.py
    ---------------------
    
    Date                 : January 2018
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

from qgis.core import QgsWkbTypes, QgsMessageLog, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields, QgsField, QgsFeatureRequest

from qgis.PyQt.QtCore import QVariant

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.core import (
        QgsCoordinateReferenceSystem
    )

    from Qneat3Framework import(
        QneatAnalysisPoint
    )

def AssignAnalysisCrs(vlayer):
    logPanel("Setting analysis CRS")
    AnalysisCrs = vlayer.crs()
    return AnalysisCrs

def logPanel(message):
    QgsMessageLog.logMessage(message, "QNEAT3")
    
def isGeometryType(vlayer, type_obj):
    geom_type = vlayer.geometryType()
    if geom_type == type_obj:
        return True
    else:
        return False

def buildQgsVectorLayer(string_geomtype: str, string_layername: str, crs: QgsCoordinateReferenceSystem, feature_list: list[QgsFeature], list_qgsfield: list[QgsField] = None) -> QgsVectorLayer:
    
    vector_layer = QgsVectorLayer(string_geomtype, string_layername, "memory")
    
    vector_layer.setCrs(crs)
    
    provider = vector_layer.dataProvider()
    
    provider.addFeatures(feature_list)
    vector_layer.updateExtents()

    return vector_layer

def getFeatureFromPoint(point_id: int, qgs_point_xy: QgsPointXY) -> QgsFeature:     
    feature = QgsFeature()
    fields = QgsFields()
    fields.append(QgsField('point_id', QVariant.String, '', 254, 0))
    feature.setFields(fields)
    feature.setGeometry(QgsGeometry.fromPointXY(qgs_point_xy))
    feature['point_id']=point_id
    return feature

def mergeFeaturesFromQgsIterable(qgs_feature_storage_list):
    result_feature_list = []
    for qgs_feature_storage in qgs_feature_storage_list:
        fRequest = QgsFeatureRequest().setFilterFids(qgs_feature_storage.allFeatureIds())
        result_feature_list.extend(qgs_feature_storage.getFeatures(fRequest))
    return result_feature_list

        
def getFieldDatatype(qgs_feature_storage, fieldname):
    fields_list = qgs_feature_storage.fields()
    qvariant_type = fields_list.field(fieldname).type()
    return qvariant_type

def getFieldDatatypeFromPythontype(pythonvar):
    if isinstance(pythonvar, str):
        return QVariant.String
    elif isinstance(pythonvar, int):
        return QVariant.Int
    elif isinstance(pythonvar, float):
        return QVariant.Double
    else: 
        return QVariant.String

    