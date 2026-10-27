#include "common.h"
typedef uint32_t (*Operation)(uint32_t,uint32_t);
uint32_t add(uint32_t a,uint32_t b){return a+b;}
uint32_t multiply(uint32_t a,uint32_t b){return a*b;}
uint32_t exclusive(uint32_t a,uint32_t b){return a^b;}
uint32_t apply(Operation op,uint32_t a,uint32_t b){return op(a,b);}
int main(int argc,char **argv) {
 int64_t m,a,b; Operation table[]={add,multiply,exclusive};
 if(argc!=4 || !number(argv[1],0,2,&m)||!number(argv[2],0,4294967295LL,&a)||!number(argv[3],0,4294967295LL,&b)) return bad();
 printf("%" PRIu32 "\n",apply(table[m],(uint32_t)a,(uint32_t)b)); return 0;
}
