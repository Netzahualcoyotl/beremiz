from ctypes import *
import csv

def MK_LoadCSV(location, translation):
    csvfile = open(location,"rb")
    sample = csvfile.read(1024)
    dialect = csv.Sniffer().sniff(sample)
    csvfile.seek(0)
    has_header = csv.Sniffer().has_header(sample)
    reader = csv.reader(csvfile, dialect)
    if has_header:
        reader.next()
    return tuple([tuple(translation(row)) for row in reader])

class Point2D(Structure):
    _fields_ = [("x", c_double),
                ("y", c_double)]

class Array2D(Structure):
    _fields_ = [("count", c_int),
                ("points", POINTER(Point2D))]

def Array2DTranslate(row):
    return map(float,row)

def MK_MakeArray2D(table, data):
    oldx = None
    if len(data)>0 and len(data[0])==2:
        for x,y in data:
            if oldx is not None and oldx >= x :
                table[0].count = 0
                raise Exception("1st column not strictly increasing")
            oldx=x
        table[0].count = len(data) 
        obj = (Point2D*len(data))(*data)
        table[0].points = obj
        return obj
    else:
        raise Exception("Empty or wrong CSV")
    
MC_TP_REF_CSVs = {} 
MK_GetPublic_MC_TP_REF = PLCIOsBinary.__MK_GetPublic_MC_TP_REF
MK_GetPublic_MC_TP_REF.restype = POINTER(Array2D)
def MK_Load_MC_TP_REF_CSV(index, location):
    data = MK_LoadCSV(location, Array2DTranslate)
    c_data = MK_MakeArray2D(MK_GetPublic_MC_TP_REF(index), data)
    MC_TP_REF_CSVs[(index,location)] = c_data
    return True

MC_TV_REF_CSVs = {} 
MK_GetPublic_MC_TV_REF = PLCIOsBinary.__MK_GetPublic_MC_TV_REF
MK_GetPublic_MC_TV_REF.restype = POINTER(Array2D)
def MK_Load_MC_TV_REF_CSV(index, location):
    data = MK_LoadCSV(location, Array2DTranslate)
    c_data = MK_MakeArray2D(MK_GetPublic_MC_TV_REF(index), data)
    MC_TV_REF_CSVs[(index,location)] = c_data
    return True

MC_TA_REF_CSVs = {} 
MK_GetPublic_MC_TA_REF = PLCIOsBinary.__MK_GetPublic_MC_TA_REF
MK_GetPublic_MC_TA_REF.restype = POINTER(Array2D)
def MK_Load_MC_TA_REF_CSV(index, location):
    data = MK_LoadCSV(location, Array2DTranslate)
    c_data = MK_MakeArray2D(MK_GetPublic_MC_TA_REF(index), data)
    MC_TA_REF_CSVs[(index,location)] = c_data
    return True

MC_CAM_REF_CSVs = {} 
MK_GetPublic_MC_CAM_REF = PLCIOsBinary.__MK_GetPublic_MC_CAM_REF
MK_GetPublic_MC_CAM_REF.restype = POINTER(Array2D)
def MK_Load_MC_CAM_REF_CSV(index, location):
    data = MK_LoadCSV(location, Array2DTranslate)
    c_data = MK_MakeArray2D(MK_GetPublic_MC_CAM_REF(index), data)
    MC_CAM_REF_CSVs[(index,location)] = c_data
    return True


class Linkage(Structure):
    _fields_ = [("Tx", c_double),
                ("Ty", c_double),
                ("Tz", c_double),
                ("Rx", c_double),
                ("Ry", c_double),
                ("Rz", c_double),
                ("type", c_int)]

class KinChain(Structure):
    _fields_ = [("count", c_int),
                ("linkages", POINTER(Linkage))]

#def KinChainTranslate(row):
#    return map(
#        lambda (trslt, dflt, val) : trslt(val) if val != '' else dflt,
#        zip([float]*6 + [lambda x: {"r":1, "p":2}.get(x, 0)],
#            [0.]*6 + [0],
#            row[1:]))
def KinChainTranslate(row):
    return list(map(
        lambda t: t[0](t[2]) if t[2] != '' else t[1],
        zip(
            [float]*6 + [lambda x: {"r":1, "p":2}.get(x, 0)],
            [0.]*6 + [0],
            row[1:]
        )
    ))


def MK_MakeKinChain(chain, data):
    if len(data)>0 and len(data[0])==7:
        chain[0].count = len(data)
        obj = (Linkage*len(data))(*data)
        chain[0].linkages = obj
        return obj
    else:
        raise Exception("Empty or wrong CSV")

MC_KIN_REF_CSVs = {} 
