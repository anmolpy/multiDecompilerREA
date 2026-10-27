#ifndef COMMON_H
#define COMMON_H
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <errno.h>
#include <string.h>
static int number(const char *s, int64_t low, int64_t high, int64_t *out) {
    char *end; errno=0;
    long long v=strtoll(s,&end,10);
    if (!*s || *end || errno || v<low || v>high) return 0;
    *out=(int64_t)v; return 1;
}
static int bad(void) { fputs("invalid input\n",stderr); return 2; }
#endif
