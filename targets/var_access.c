
#define __Unpack_case_t(TYPENAME)                                           \
        case TYPENAME##_ENUM :                                              \
            if(flags) *flags = ((__IEC_##TYPENAME##_t *)varp)->flags;       \
            if(value_p) *value_p = &((__IEC_##TYPENAME##_t *)varp)->value;  \
		    if(size) *size = sizeof(TYPENAME);                              \
            break;

#define __Unpack_case_p(TYPENAME)                                           \
        case TYPENAME##_O_ENUM :                                            \
        case TYPENAME##_P_ENUM :                                            \
            if(flags) *flags = ((__IEC_##TYPENAME##_p *)varp)->flags;       \
            if(value_p) *value_p = ((__IEC_##TYPENAME##_p *)varp)->value;   \
		    if(size) *size = sizeof(TYPENAME);                              \
            break;

/* SFC types (STEP, TRANSITION, ACTION) are always passed as __IEC_BOOL_t*:
 *   STEP_ENUM       -> &step_list[i].X         (__IEC_BOOL_t)
 *   TRANSITION_ENUM -> &debug_transition_list[i] (__IEC_BOOL_t)
 *   ACTION_ENUM     -> &action_list[i].state   (__IEC_BOOL_t)
 */
#define __Unpack_case_sfc(TYPENAME)                                         \
        case TYPENAME##_ENUM :                                              \
            if(flags) *flags = ((__IEC_BOOL_t *)varp)->flags;              \
            if(value_p) *value_p = &((__IEC_BOOL_t *)varp)->value;        \
            if(size) *size = sizeof(BOOL);                                  \
            break;

#define __Is_a_string(dsc) (dsc->type == STRING_ENUM)   ||\
                           (dsc->type == STRING_P_ENUM) ||\
                           (dsc->type == STRING_O_ENUM)

static int UnpackVar(__Unpack_desc_type *dsc, void **value_p, char *flags, size_t *size)
{
    void *varp = dsc->ptr;
    /* find data to copy*/
    switch(dsc->type){
        __ANY(__Unpack_case_t)
        __ANY(__Unpack_case_p)
        __ANY_SFC(__Unpack_case_sfc)
    default:
        return 0; /* should never happen */
    }
    return 1;
}

