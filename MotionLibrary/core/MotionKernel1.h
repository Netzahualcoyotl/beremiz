// MotionKernel1.h
#ifndef MOTIONKERNEL1_H
#define MOTIONKERNEL1_H

#ifdef __cplusplus
extern "C" {
#endif

// Inicialización y limpieza del kernel de motion
int __MK_Init(void);
void __MK_Cleanup(void);

// Funciones de retrieve y publish
void __MK_Retrieve(void);
void __MK_Publish(void);

// Funciones de cómputo de ejes
int __MK_GetAxisCount(void);
void __MK_ComputeAxis(int AxisRef);

#ifdef __cplusplus
}
#endif

#endif // MOTIONKERNEL1_H

