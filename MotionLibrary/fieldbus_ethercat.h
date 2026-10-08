#ifndef FIELDBUS_ETHERCAT_H
#define FIELDBUS_ETHERCAT_H

typedef struct {
    int type;
    int slave_position;
} ethercat_axis_addr_t;

typedef struct {
    ethercat_axis_addr_t addr;
} ethercat_axis_network_u;

#define ETHERCAT_AXIS_SENTINEL 0xEC01

#endif
