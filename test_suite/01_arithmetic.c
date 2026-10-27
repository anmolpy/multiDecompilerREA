#include "common.h"
int64_t calculate(int64_t a,int64_t b) { return a*7-b*3; }
int main(int argc,char **argv) {
 int64_t a,b;
 if(argc!=3 || !number(argv[1],-1000000,1000000,&a) || !number(argv[2],-1000000,1000000,&b)) return bad();
 printf("value=%" PRId64 " quotient=%" PRId64 " remainder=%" PRId64 "\n",calculate(a,b),a/7,a%7); return 0;
}
