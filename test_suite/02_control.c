#include "common.h"
uint32_t dispatch(uint32_t x) {
 switch(x%8) {case 0:return x+11; case 1:return x*3; case 2:return x^85;
 case 3:return x/3; case 4:return x+101; case 5:return x*x;
 case 6:return x>>1; default:return 7;}
}
uint32_t accumulate(uint32_t n) {
 uint32_t sum=0;
 for(uint32_t i=0;i<n;i++) { if(i%5==0) continue; sum+=dispatch(i); }
 return sum;
}
int main(int argc,char **argv) { int64_t n;
 if(argc!=2 || !number(argv[1],0,10000,&n)) return bad();
 printf("%" PRIu32 "\n",accumulate((uint32_t)n)); return 0;
}
