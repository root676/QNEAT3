# -*- coding: utf-8 -*-
"""
***************************************************************************
    Qneat3Exceptions.py
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

class Qneat3GeometryException(Exception):
    def __init__(self, given_geom_type, expected_geom_type):
        
        self.message = "Dataset has wrong geometry type. Got {} dataset but expected {} dataset instead. ".format( given_geom_type, expected_geom_type)

        super(Qneat3GeometryException, self).__init__(self.message)
        
class Qneat3CrsException(Exception):
    def __init__(self, *crs):
    
        self.message = "Coordinate Reference Systems don't match up: {} Reproject all datasets so that their CRSs match up.".format(list(crs))

        super(Qneat3CrsException, self).__init__(self.message)