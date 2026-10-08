import features

def GetMotionLibClass():
    from MotionLibrary import MotionLibrary
    return MotionLibrary

features.libraries.append(
    ('Motion', GetMotionLibClass))

def GetCamEditorClass():
    from CamEditor import CamEditor
    return CamEditor

def GetKinematicEditorClass():
    from KinematicEditor import KinematicEditor
    return KinematicEditor

features.file_editors.extend(
    [('.csv', 'Cam Editor', GetCamEditorClass),
     ('.hki', 'Kinematic Editor', GetKinematicEditorClass)])
