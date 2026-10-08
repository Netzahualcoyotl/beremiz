#include "MotionKernel1.c"  // Contiene _MC_OUTPUT_REF_s
#include "iec_std_types.h"   // Para DWORD

#include <stdint.h>

DWORD MC_OUTPUT_REF_To_DWORD(MC_OUTPUT_REF* output) {
    return *((DWORD*)output);  // convierte MC_OUTPUT_REF a DWORD
}


