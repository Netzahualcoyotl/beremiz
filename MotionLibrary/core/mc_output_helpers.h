#ifndef MC_OUTPUT_HELPERS_H
#define MC_OUTPUT_HELPERS_H

#include "MotionKernel1.c"  // o el .h que contenga la definición de _MC_OUTPUT_REF_s
#include "iec_std_types.h"   // para DWORD

// Función para convertir MC_OUTPUT_REF a DWORD
DWORD MC_OUTPUT_REF_To_DWORD(MC_OUTPUT_REF_data__* output);

#endif


