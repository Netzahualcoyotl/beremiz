#include "beremiz.h"
#include "iec_types_all.h"
#include "accessor.h"
#include "POUS.h"
/*#include "MotionKernel1.h"*/
%(headers)s

int __init_motion()
{
    return __MK_Init();
}

void __cleanup_motion()
{
    __MK_Cleanup();
}

void __retrieve_motion()
{
    __MK_Retrieve();
}

void __compute_motion()
{
    int i;
    int axis_count = __MK_GetAxisCount();
    for(i = 0; i < axis_count; i++)
    {
        __MK_ComputeAxis(i);
    }
}

void __publish_motion()
{
    __MK_Publish();
}
