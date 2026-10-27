#include "common.h"
int parse_pair(const char *s,int *left,int *right) {
 size_t n=strlen(s); if(n==0 || n>40) return 0;
 char buf[41]; memcpy(buf,s,n+1); char *colon=strchr(buf,':');
 if(!colon) return 0; *colon++=0; int64_t a,b;
 if(!number(buf,-9999,9999,&a)||!number(colon,-9999,9999,&b)) return 0;
 *left=(int)a; *right=(int)b; return 1;
}
int main(int argc,char **argv) { int a,b;
 if(argc!=2 || !parse_pair(argv[1],&a,&b)) return bad();
 printf("left=%d right=%d sum=%d\n",a,b,a+b); return 0;
}
