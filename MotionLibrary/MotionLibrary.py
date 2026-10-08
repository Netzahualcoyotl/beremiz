import os
import shutil
from POULibrary import POULibrary

def GetLocalPath(filename):
    return os.path.join(os.path.split(__file__)[0], filename) 

Headers="""
typedef struct {
    MC_REAL_ARRAY CenterPoint;
    MC_REAL_ARRAY CosRay;
    MC_REAL_ARRAY SinRay;
    MC_REAL_ARRAY CosAxis;
    MC_REAL_ARRAY SinAxis;
    double Radius;
    double Angle;
    double DistanceCurv;
    MC_REAL_ARRAY Pf;
    MC_REAL_ARRAY Vf;
} CircleData;
    int __MK_Init();
    void __MK_Cleanup();
    void __MK_Retrieve();
    void __MK_Publish();
    void __MK_ComputeAxis(int);
    
    typedef enum {
        mc_mode_none, // No motion mode
        mc_mode_csp,  // Continuous Synchronous Positionning mode
        mc_mode_csv,  // Continuous Synchronous Velocity mode
        mc_mode_cst,  // Continuous Synchronous Torque mode
        mc_mode_hm, // Homing mode
    } mc_axismotionmode_enum;
    
    typedef struct {
       IEC_BOOL Power;
       IEC_BOOL CommunicationReady;
       IEC_UINT NetworkPosition;
       void *Network;
       IEC_BOOL ReadyForPowerOn;
       IEC_BOOL PowerFeedback;
       IEC_BOOL HomingOperationStart;
       IEC_BOOL HomingCompleted;
       IEC_BOOL ErrorCodeEnabled;
       IEC_UINT ErrorCode;
       IEC_BOOL DriveFault;
       IEC_BOOL DriveFaultReset;
       IEC_BOOL DigitalInputsEnabled;
       IEC_DWORD DigitalInputs;
       IEC_BOOL DigitalOutputsEnabled;
       IEC_DWORD DigitalOutputs;
       IEC_BOOL TouchProbeEnabled;
       IEC_WORD TouchProbeFunction;
       IEC_WORD TouchProbeStatus;
       IEC_DINT TouchProbePos1PosValue;
       IEC_DINT TouchProbePos1NegValue;
       IEC_BOOL TouchProbeRisingTrigger;
       IEC_BOOL TouchProbeSignalFound;
       IEC_BOOL HomingSignalFound;
       IEC_BOOL HomingCtrlByPwr;
       IEC_LREAL Axis_Zpulse;
       IEC_DINT ActualRawPosition;
       IEC_DINT ActualRawVelocity;
       IEC_DINT ActualRawTorque;
       IEC_DINT RawPositionSetPoint;
       IEC_DINT RawVelocitySetPoint;
       IEC_DINT RawTorqueSetPoint;
       mc_axismotionmode_enum AxisMotionMode;
       /*PLCopen TC2 parameters (MC_{Read,Write}{,Bool}Parameter)*/
       IEC_LREAL CommandedPosition; /*Commanded position (#1,R)*/
       IEC_LREAL SWLimitPos; /*Positive Software limit switch position (#2,R/W)*/
       IEC_LREAL SWLimitNeg; /*Negative Software limit switch position (#3,R/W)*/
       IEC_BOOL EnableLimitPos; /*Enable positive software limit switch (#4,R/W)*/
       IEC_BOOL EnableLimitNeg; /*Enable negative software limit switch (#5,R/W)*/
       IEC_BOOL EnablePosLagMonitoring; /*Enable monitoring of position lag (#6,R/W)*/
       IEC_LREAL MaxPositionLag; /*Maximal position lag (#7,R/W)*/
       IEC_LREAL MaxVelocitySystem; /*Maximal allowed velocity of the axis in the motion system (#8,R)*/
       IEC_LREAL MaxVelocityAppl; /*Maximal allowed velocity of the axis in the application (#9,R/W)*/
       IEC_LREAL ActualVelocity; /*Actual velocity (#10,R)*/
       IEC_LREAL CommandedVelocity; /*Commanded velocity (#11,R)*/
       IEC_LREAL MaxAccelerationSystem; /*Maximal allowed acceleration of the axis in themotion system (#12,R)*/
       IEC_LREAL MaxAccelerationAppl; /*Maximal allowed acceleration of the axis in theapplication (#13,R/W)*/
       IEC_LREAL MaxDecelerationSystem; /*Maximal allowed deceleration of the axis in themotion system (#14,R)*/
       IEC_LREAL MaxDecelerationAppl; /*Maximal allowed deceleration of the axis in theapplication (#15,R/W)*/
       IEC_LREAL MaxJerkSystem; /*Maximum allowed jerk of the axis in the motionsystem (#16,R)*/
       IEC_LREAL MaxJerkAppl; /*Maximum allowed jerk of the axis in the application (#17,R/W)*/
       IEC_BOOL Simulation; /*Simulation Mode (#1000,R/W)*/
       IEC_LREAL PositionSetPoint; /*Position SetPoint (#1001,R)*/
       IEC_LREAL VelocitySetPoint; /*Velocity SetPoint (#1002,R)*/
       IEC_LREAL RatioNumerator; /*Drive_Unit = PLCopen_Unit * RatioNumerator / RatioDenominator (#1003,R/W)*/
       IEC_LREAL RatioDenominator; /*Drive_Unit = PLCopen_Unit * RatioNumerator / RatioDenominator (#1004,R/W)*/
       IEC_LREAL PositionOffset; /*SentPosition = (PositionSepoint + PosotionOffset) * RatioNumerator / RatioDenominator (#1005,R/W)*/
       IEC_BOOL LimitSwitchNC; /*Set if limit switches are normaly closed (#1006,R/W)*/
       IEC_LREAL JerkSetPoint; /*Jerk setpoint (#1007,R/W)*/
       IEC_LREAL ActualPosition; /*Position from drive, scaled but without offset. (#1008,R)*/
       IEC_LREAL HomingLimitWindow; /*Distance at which soft limit is alredy valid during homing (#1009,R/W)*/
       IEC_LREAL HomingVelocity; /*Velocity applied on drive while homing (#1010,R/W)*/
       IEC_LREAL HomingVelocitySearchIndexPulse; /*Velocity applied on drive while Search Index Pulse (#1018,R/W)*/
       IEC_LREAL TorqueSetPoint; /*Torque SetPoint (#1011,R)*/
       IEC_LREAL ActualTorque; /*Torque from drive scaled (#1012,R)*/
       IEC_LREAL TorqueRatioNumerator; /*Drive_Unit = PLCopen_Unit * TorqueRatioNumerator / TorqueRatioDenominator (#1013,R/W)*/
       IEC_LREAL TorqueRatioDenominator; /*Drive_Unit = PLCopen_Unit * TorqueRatioNumerator / TorqueRatioDenominator (#1014,R/W)*/
       IEC_LREAL AccelerationSetPoint; /*AccelerationSetPoint (#1015,R)*/
       IEC_LREAL ModuloAxisRange; /*Range of valid positions in modulo axis (#1016     ,R/W)*/
       IEC_LREAL ActualAcceleration; /*Acceleration calculated from velocity variation (#1017,R)*/
           /* Punteros a funciones con nombres correctos (_data__) */
        void (*__mcl_func_MC_GetTorqueLimit)(MC_GETTORQUELIMIT_data__ *data__);
        void (*__mcl_func_MC_SetTorqueLimit)(MC_SETTORQUELIMIT_data__ *data__);
        void (*__mcl_func_MC_Power)(MC_POWER_data__ *data__);
        void (*__mcl_func_MC_Home)(MC_HOME_data__ *data__);
    } axis_s;
    
    typedef struct {
      double x;
      double y;
    } point2d_s;
    
    typedef struct {
      int count;
      point2d_s *points;
    } array2d_s;
    
    typedef struct {
      int64_t OnCompensation;
      int64_t OffCompensation;
      double Hysteresis;
    } track_s;
    
    typedef struct {
      int count;
      track_s *tracks;
    } tracklist_s;
    
    #define AD_BOTH     0
    #define AD_POSITIVE 1
    #define AD_NEGATIVE 2
    
    #define CSM_POSITION 0
    #define CSM_TIME     1
    
    typedef struct {
      int TrackNumber;
      double FirstOnPosition;
      double LastOnPosition;
      int AxisDirection;
      int CamSwitchMode;
      uint64_t Duration;
    } camswitch_s;
    
    typedef struct {
      int count;
      camswitch_s *camswitches;
    } camswitchlist_s;
    
    typedef struct {
       double _[9];
    } mc_matrix;
    
    typedef struct {
       double dist_curv;
       CircleData segment_profile;
       double Vmvt;
       double Vf;
       double Acc;
       double Dec;
    } path_data_segment_s;
    
    typedef struct {
      int count;
      path_data_segment_s *segments;
    } path_data_s;
    
    int __MK_Alloc_AXIS_REF();
    axis_s* __MK_GetPublic_AXIS_REF(int index);
    int __MK_CheckPublicValid_AXIS_REF(int index);
    void __MK_Set_AXIS_REF_Pos(int index, int pos);
    int __MK_Get_AXIS_REF_Pos(int index);
    int __MK_Alloc_MC_TP_REF();
    array2d_s* __MK_GetPublic_MC_TP_REF(int index);
    int __MK_CheckPublicValid_MC_TP_REF(int index);
    int __MK_Alloc_MC_TV_REF();
    array2d_s* __MK_GetPublic_MC_TV_REF(int index);
    int __MK_CheckPublicValid_MC_TV_REF(int index);
    int __MK_Alloc_MC_TA_REF();
    array2d_s* __MK_GetPublic_MC_TA_REF(int index);
    int __MK_CheckPublicValid_MC_TA_REF(int index);
    int __MK_Alloc_MC_CAMSWITCH_REF();
    camswitchlist_s* __MK_GetPublic_MC_CAMSWITCH_REF(int index);
    int __MK_CheckPublicValid_MC_CAMSWITCH_REF(int index);
    int __MK_Alloc_MC_OUTPUT_REF();
    uint32_t* __MK_GetPublic_MC_OUTPUT_REF(int index);
    int __MK_CheckPublicValid_MC_OUTPUT_REF(int index);
    int __MK_Alloc_MC_TRACK_REF();
    tracklist_s* __MK_GetPublic_MC_TRACK_REF(int index);
    int __MK_CheckPublicValid_MC_TRACK_REF(int index);
    int __MK_Alloc_MC_TRIGGER_REF();
    uint8_t* __MK_GetPublic_MC_TRIGGER_REF(int index);
    int __MK_CheckPublicValid_MC_TRIGGER_REF(int index);
    int __MK_Alloc_MC_CAM_REF();
    array2d_s* __MK_GetPublic_MC_CAM_REF(int index);
    int __MK_CheckPublicValid_MC_CAM_REF(int index);
    int __MK_Alloc_MC_CAM_ID();
"""

AxisXSD="""
 <!-- Positive Software limit switch position (#2,R/W) -->
 <xsd:attribute name="SWLimitPos" type="xsd:float" use="optional" >
    <xsd:annotation>
     <xsd:documentation>Positive Software limit switch position</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Negative Software limit switch position (#3,R/W) -->
 <xsd:attribute name="SWLimitNeg" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Negative Software limit switch position</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Enable positive software limit switch (#4,R/W) -->
 <xsd:attribute name="EnableLimitPos" type="xsd:boolean" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Enable positive software limit witch (#4,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Enable negative software limit switch (#5,R/W) -->
 <xsd:attribute name="EnableLimitNeg" type="xsd:boolean" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Enable negative software limit switch (#5,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Enable monitoring of position lag (#6,R/W) -->
 <xsd:attribute name="EnablePosLagMonitoring" type="xsd:boolean" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Enable monitoring of position lag (#6,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Maximal position lag (#7,R/W) -->
 <xsd:attribute name="MaxPositionLag" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Maximal position lag (#7,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Maximal allowed velocity of the axis in the application (#9,R/W) -->
 <xsd:attribute name="MaxVelocityAppl" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Maximal allowed velocity of the axis in the application (#9,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Maximal allowed acceleration of the axis in theapplication (#13,R/W) -->
 <xsd:attribute name="MaxAccelerationAppl" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Maximal allowed acceleration of the axis in the application (#13,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Maximal allowed deceleration of the axis in theapplication (#15,R/W) -->
 <xsd:attribute name="MaxDecelerationAppl" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Maximal allowed deceleration of the axis in the application (#15,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Maximum allowed jerk of the axis in the application (#17,R/W) -->
 <xsd:attribute name="MaxJerkAppl" type="xsd:float" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Maximum allowed jerk of the axis in the application (#17,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Simulation Mode (#1000,R/W) -->
 <xsd:attribute name="Simulation" type="xsd:boolean" use="optional" >
   <xsd:annotation>
     <xsd:documentation>Simulation Mode (#1000,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Drive_Unit = PLCopen_Unit * RatioNumerator / RatioDenominator (#1003,R/W) -->
 <xsd:attribute name="RatioNumerator" type="xsd:float" use="optional" default="65536.0">
   <xsd:annotation>
     <xsd:documentation>Drive_Unit = PLCopen_Unit * RatioNumerator / RatioDenominator (#1003,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Drive_Unit = PLCopen_Unit * RatioNumerator / RatioDenominator (#1004,R/W) -->
 <xsd:attribute name="RatioDenominator" type="xsd:float" use="optional" default="360.0">
   <xsd:annotation>
     <xsd:documentation>Drive Unit = PLCopen_Unit * RatioNumerator / RationDenominator (#1004,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- SentPosition = (PositionSepoint + PosotionOffset) * RatioNumerator / RatioDenominator (#1005,R/W) -->
 <xsd:attribute name="PositionOffset" type="xsd:float" use="optional" default="0.0">
   <xsd:annotation>
     <xsd:documentation>SentPosition = (PositionSetpoint + PositionOffset) * RatioNumerator / RatioDenominator (#1005,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Set if limit switches are normaly closed (#1006,R/W) -->
 <xsd:attribute name="LimitSwitchNC" type="xsd:boolean" use="optional" default="0">
   <xsd:annotation>
     <xsd:documentation>Set if limit switches are normaly closed (#1006,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Jerk setpoint (#1007,R/W) -->
 <xsd:attribute name="JerkSetPoint" type="xsd:float" use="optional" default="0.0">
   <xsd:annotation>
     <xsd:documentation>Jerk setpoint (#1007,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Distance at which soft limit is alredy valid during homing (#1009,R/W) -->
 <xsd:attribute name="HomingLimitWindow" type="xsd:float" use="optional" default="10.0">
   <xsd:annotation>
     <xsd:documentation>Distance at which soft limit is alredy valid during homing (#1009,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Velocity applied on drive while homing (#1010,R/W) -->
 <xsd:attribute name="HomingVelocity" type="xsd:float" use="optional" default="360.0">
   <xsd:annotation>
     <xsd:documentation>Velocity applied on drive while homing (#1010,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Velocity applied on drive while Search Index Pulse (#1018,R/W) -->
 <xsd:attribute name="HomingVelocitySearchIndexPulse" type="xsd:float" use="optional" default="0.0">
   <xsd:annotation>
     <xsd:documentation>Velocity applied on drive while Search Index Pulse (#1018,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Drive_Unit = PLCopen_Unit * TorqueRatioNumerator / TorqueRatioDenominator (#1013,R/W) -->
 <xsd:attribute name="TorqueRatioNumerator" type="xsd:float" use="optional" default="10.0">
   <xsd:annotation>
     <xsd:documentation>Drive_Unit = PLCopen_Unit * TorqueRatioNumerator / TorqueRatioDenominator (#1013,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Drive_Unit = PLCopen_Unit * TorqueRatioNumerator / TorqueRatioDenominator (#1014,R/W) -->
 <xsd:attribute name="TorqueRatioDenominator" type="xsd:float" use="optional" default="1.0">
   <xsd:annotation>
     <xsd:documentation>Drive_Unit = PLCoopen_Unit * TroqueRatioNumerator / TorqueRatioDenominator (#1014,R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
 <!-- Range of valid positions in modulo axis (#1016     ,R/W) -->
 <xsd:attribute name="ModuloAxisRange" type="xsd:float" use="optional" default="0.0">
   <xsd:annotation>
     <xsd:documentation>Range of valid positions in modulo axis (#1016, R/W)</xsd:documentation>
   </xsd:annotation>
 </xsd:attribute>
"""

class MotionLibrary(POULibrary):

    def GetLibraryPath(self):
        return GetLocalPath("plcopen/poustesteds.xml")

    def Generate_C(self, buildpath, varlist, IECCFLAGS):
        
        IECCFLAGS = IECCFLAGS + " -I" + buildpath

        # Copiar motion.c al buildpath
        src_motion = GetLocalPath("motion.c")
        dst_motion = os.path.join(buildpath, "motion.c")

        with open(src_motion, "r") as f:
            c_code = f.read()

        c_code = c_code % {"headers": Headers}

        with open(dst_motion, "w") as f:
            f.write(c_code)

        # Rutas de los C files
        kernel_path = GetLocalPath("core/MotionKernel1.c")

        return (
            (["motion"],  # nombre módulo
             [(dst_motion, IECCFLAGS),
              (kernel_path, IECCFLAGS)],
             True),      # NO separate build
            "-lm",
            ("runtime_motion.py",
             open(GetLocalPath("MotionHelpers.py"), "rb"))
        )

