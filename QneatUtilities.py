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

from itertools import groupby

from qgis.core import QgsWkbTypes, QgsMessageLog, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields, QgsField, QgsFeatureRequest

from qgis.PyQt.QtCore import QVariant, QMetaType

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsFeatureSource,
        QgsPointXY
    )

    from QneatFramework import(
        QneatAnalysisPoint
    )


def logPanel(message):
    QgsMessageLog.logMessage(message, "QNEAT3")

def checkAnalysisCrsEquality(sources : list[QgsFeatureSource]) -> bool:
    
    first_crs = sources[0].sourceCrs()

    return all(
        src.sourceCrs() == first_crs 
        for src in sources
        )




def buildQgsVectorLayer(string_geomtype: str, string_layername: str, crs: QgsCoordinateReferenceSystem, feature_list: list[QgsFeature]) -> QgsVectorLayer:
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
        
def getFieldDatatype(qgs_feature_storage: QgsFeatureSource, fieldname) -> QMetaType.Type:
    fields_list: QgsFields = qgs_feature_storage.fields()
    type: QMetaType.Type = fields_list.field(fieldname).type()
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
    